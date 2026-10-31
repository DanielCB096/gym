# ADR-076 · Programador de avisos diferidos

- **Fecha:** 2026-10-31
- **Estado:** propuesta inicial
- **Cierra el pendiente «un programador que emita los avisos diferidos sin depender de abrir la bandeja»** del módulo de notificaciones y revisa el límite de ADR-016, ADR-028, ADR-035, ADR-039 y ADR-045.

## Contexto

Los recordatorios del socio —membresía por vencer, clase próxima y cita de fisioterapia— y dos avisos del personal —la solicitud de asistencia vencida y el token del kiosco por caducar— no nacen de un evento: se vuelven ciertos con el paso del tiempo. Sin un proceso de fondo, el proyecto los materializa en las rutas de lectura (ADR-016, ADR-028, ADR-035, ADR-039 y ADR-045): abrir la bandeja o su contador escribe el aviso que ya tocaba.

Ese patrón cubre al socio que entra a la app, pero deja dos huecos. Un socio que no la abre no recibe el recordatorio, y ni siquiera el push lo salva porque los recordatorios se escriben con `push=False` (ADR-052). Y el personal solo se entera de una solicitud vencida o de un token por caducar cuando alguien abre el panel; si el club pasa el fin de semana sin abrirlo, el aviso llega tarde.

Desde ADR-063 el club ya tiene un bloque de cron idempotente que instala las tareas de operación (`ops_cron.py`), y ADR-071 y ADR-073 agregaron entradas nuevas con el mismo patrón. Faltaba la tarea que materializa estos avisos sin un lector.

## Decisión

- **Un punto de entrada público, `materialise_deferred_notices(session, now)`**, que devuelve `DeferredNoticesResult`: socios revisados, avisos del socio escritos, escalamientos de asistencia y avisos del token del kiosco. La suma de los dos últimos es la propiedad `staff_notices_written`. Los productores son los mismos que usan las rutas de lectura; no hay una segunda copia de la lógica.
- **Solo se revisan los socios con una fuente en ventana.** Tres consultas de candidatos se unen por `member_id`: membresías `active` que terminan dentro de siete días, reservas `reserved` de clases `scheduled` que empiezan dentro de 24 horas y citas `scheduled` que empiezan dentro de 24 horas. La corrida no recorre la plantilla entera de socios ni escribe avisos de fuentes fuera de ventana.
- **Cada productor devuelve cuántas filas escribió, no cuántas intentó.** `_ensure_membership_expiring`, `_ensure_class_reminders`, `_ensure_physio_reminders` y `_ensure_attendance_request_escalations` comprueban la clave de deduplicación antes de crear y solo cuentan la fila nueva. `warn_expiring_kiosk_tokens` hace lo mismo: antes incrementaba el contador también cuando la clave ya existía, lo que hacía que una segunda pasada pareciera haber escrito avisos.
- **Las ventanas de la membresía se ordenan de la más estrecha a la más ancha** (`1, 3, 7` días). Con el orden anterior (`7, 3, 1`) cualquier membresía dentro de siete días caía en la ventana de siete y nunca avanzaba a la de tres ni a la de uno; el aviso se repetía como máximo una vez, pero el `dedupe_key` no reflejaba el umbral real. El orden ascendente elige el umbral más ajustado, igual que las ventanas de clase.
- **Un script propio, `backend/emit_deferred_notices.py`**, con `--preview` y `--database-url`. Escribe con `materialise_deferred_notices` y resume en consola los socios revisados y los avisos escritos por bandeja. Sin URL sale con código 2 y una base inalcanzable con código 1; `--preview` crea el esquema en `gym_preview.db` y deja todo en la máquina.
- **Octava entrada del bloque de cron.** `ops_cron.py` programa la pasada cada 60 minutos por defecto (`0 * * * *`, ajustable con `--notices-every` de 5 a 59 minutos o 60), escribe `deferred-notices.log` y `--install` exige también `emit_deferred_notices.py`. Las horas siguen siendo las del host (ADR-063).
- **Las rutas de lectura se conservan.** La bandeja y el contador de no leídos siguen materializando los recordatorios, así que el panel y la vista previa funcionan también sin cron instalado. El cron y la lectura comparten las claves de deduplicación: la primera ruta que llega escribe el aviso y la otra no lo repite.
- **No hay migración.** Los índices existentes de membresías, reservas, citas y avisos ya cubren las consultas de candidatos.

## Consecuencias y límites

- **La puntualidad es de una hora.** Un recordatorio puede escribirse hasta una hora después de entrar en su ventana. En la membresía no importa —la ventana se mide en días—, y en la clase de dos horas el socio todavía lo recibe con margen; el aviso de 24 horas puede aparecer con 23. Una corrida perdida se recupera sola en la siguiente porque las ventanas son amplias y el dedupe evita repetir.
- **Sigue sin haber push para los recordatorios.** La tarea escribe la fila en la bandeja, no contacta a Expo; el socio sin push ve el aviso la próxima vez que abre la app, pero ya no depende de que la abra para que el aviso exista. El correo y el push de los recordatorios quedan como evolución aparte.
- **El correo del personal que nace en el cron espera a una petición.** Los dos avisos del personal encolan su entrega de correo al escribirse (ADR-048), pero el script no drena la cola: la pasada de correo cuelga de la respuesta de las rutas del panel, así que una solicitud vencida o un token por caducar avisados por el cron envían su correo en la primera consulta del panel, no a la hora del cron. La bandeja ya tiene el aviso; solo el correo espera.
- **Depende del cron del host.** Sin `ops_cron.py --install` la capacidad existe en el script pero no ocurre sola; `deferred-notices.log` es la única señal de fallo. Es el mismo límite de ADR-063, ADR-071 y ADR-073.
- **El costo crece con los eventos próximos, no con la plantilla.** Por cada socio candidato se ejecutan tres consultas acotadas por esa persona. Es suficiente para la escala del club; muchas sedes o miles de citas simultáneas pedirían una pasada por lotes o una clave de deduplicación indexada por ventana.
- **La audiencia de los avisos del personal no cambia.** El escalamiento sigue yendo a las cuentas con rol `owner` —nunca a quien pidió— y el token del kiosco a quienes pueden rotarlo (`settings.manage`). La tarea no amplía ni reduce esas audiencias.
- **La retención de ADR-075 sigue mandando.** Los avisos emitidos son avisos normales: se podan cuando el socio los lee o el personal los cierra. La advertencia del token del kiosco se conserva porque se regeneraría.

## Referencias

- ADR-016 (notificaciones del socio), ADR-028 (token del kiosco), ADR-035 (recordatorios de clase), ADR-039 (fisioterapia), ADR-045 (plazo de solicitudes), ADR-052 (push del socio), ADR-063 (cron de operación), ADR-071 (cola del push del personal), ADR-073 (cierre de fisioterapia), ADR-075 (retención de la bandeja).
- Implementación: `app/modules/notifications/service.py`, `app/modules/access/kiosk.py`, `backend/emit_deferred_notices.py`, `backend/ops_cron.py`.
- Pruebas: `backend/tests/test_deferred_notices_scheduler.py` (7 casos) y `backend/tests/test_ops_cron.py` (35).
