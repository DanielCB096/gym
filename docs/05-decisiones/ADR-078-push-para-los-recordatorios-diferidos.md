# ADR-078 · Push para los recordatorios diferidos

- **Fecha:** 2026-10-31
- **Estado:** propuesta inicial
- **Cierra el límite «sigue sin haber push para los recordatorios» de ADR-076** y revisa ADR-016, ADR-035, ADR-039, ADR-052, ADR-059, ADR-061, ADR-063 y ADR-065.

## Contexto

ADR-076 dejó de esperar a que alguien abriera la bandeja: `materialise_deferred_notices` escribe por cron el recordatorio de membresía por vencer, el de la clase próxima y el de la cita de fisioterapia. Pero esos avisos se escriben con `push=False`, porque nacieron como materialización de lectura y la lectura no debe sonar el teléfono de quien ya tiene la bandeja abierta. El resultado es una mejora a medias: el aviso existe aunque el socio no abra la app, pero el socio sin costumbre de abrirla tampoco se entera; el recordatorio espera en la bandeja hasta la próxima visita.

El push del socio ya resuelve todo lo demás. `create_notification(..., push=True)` encola una entrega por token activo en la misma transacción, respeta la preferencia por categoría (ADR-059), y la pasada `send_pending_member_push_deliveries` aplica la ventana de silencio del club (ADR-061), la del propio socio (ADR-065), el reintento con espera (ADR-054) y el aviso al personal cuando se agota (ADR-055). Faltaba decidir quién y cuándo enciende ese `push` para los recordatorios.

La diferencia con la lectura es quién mira: quien abre la bandeja ya está viendo el aviso, así que hacer sonar el teléfono sería anunciar lo que tiene en pantalla. La corrida del cron, en cambio, no tiene lector: es el momento correcto para encolar y enviar.

## Decisión

- **Un parámetro `push` en la materialización diferida, apagado por defecto.** `_materialise_deferred` y los tres productores —`_ensure_membership_expiring`, `_ensure_class_reminders` y `_ensure_physio_reminders`— aceptan `push: bool = False` como argumento de solo palabra y lo pasan a `create_notification`. Las rutas de lectura de la bandeja y del contador no cambian: siguen materializando en silencio.
- **El programador enciende el push.** `materialise_deferred_notices` llama a `_materialise_deferred(..., push=True)` porque su premisa es que nadie está mirando la bandeja. El aviso y sus entregas se escriben juntos; no hay una segunda pasada que recorra los avisos para decidir a quién avisar.
- **Las reglas de entrega no se duplican.** La preferencia por categoría, la ausencia de token activo, la ventana del club y la del socio, el reintento y el aviso al personal se aplican donde ya estaban: al encolar y al enviar. Este incremento no reimplementa ninguna de esas comprobaciones.
- **La misma corrida drena la cola.** `backend/emit_deferred_notices.py` llama a `send_pending_member_push_deliveries_from_engine(engine, limit=...)` después de materializar. Así el push sale a la hora del cron y no espera a que el socio abra la app ni a una petición posterior del panel. El resumen en consola suma una línea con intentos, enviados, simulados, fallidos, dispositivos retirados y entregas pendientes, y otra cuando la ventana del club retuvo la pasada.
- **Un tope por corrida, configurable.** El script estrena `--push-limit` (1 a `MAX_SEND_BATCH_LIMIT`, 100; por defecto `DEFAULT_SEND_BATCH_LIMIT`, 20). Lo que no entra en el lote queda `pending` y sale en la siguiente pasada, que con el cron por defecto llega una hora después.
- **La vista previa simula.** `--preview` activa `PREVIEW_MODE`, la pasada no contacta a Expo y las entregas quedan `simulated`, igual que el resto de los envíos de vista previa. El script nunca toca el teléfono de nadie al ejecutarse sobre `gym_preview.db`.
- **El correo del personal que nace en la corrida también sale.** El drenaje por motor es el mismo gancho de ADR-055: tras la pasada de push vacía la cola de correo del personal. Si un push se agota y escribe el aviso `member_push_receipt_failed` o cualquier aviso de personal del cron, su correo ya no espera a la primera consulta del panel. Esto reduce, para la corrida del cron, el límite que ADR-076 dejó abierto.
- **Sin migración.** Las tablas de entregas y preferencias ya existen (ADR-052, ADR-059, ADR-065); el cambio es de flujo y de argumentos.

## Consecuencias y límites

- **La puntualidad sigue siendo la del cron.** El push de un recordatorio sale en la primera pasada posterior a que el aviso entre en su ventana: hasta una hora con los valores por defecto. La clase de dos horas conserva margen; el aviso de 24 horas puede llegar con 23. Una corrida perdida se recupera sola en la siguiente porque el aviso ya quedó escrito y las entregas pendientes esperan.
- **El tope reparte una audiencia grande en varias pasadas.** Con 20 envíos por corrida y una hora entre corridas, cien recordatorios nuevos tardarían cinco horas en salir. Es aceptable para el tamaño del club y se ajusta con `--push-limit`; una campaña masiva pediría otro diseño.
- **Los silencios retienen, no pierden.** Dentro de la ventana del club la pasada no envía y lo dice en el resumen; la primera pasada tras la ventana los manda. La ventana propia descarta solo las filas de ese socio, que siguen esperando. En ambos casos el aviso ya está en la bandeja y cuenta como no leído.
- **Un socio con la categoría apagada recibe la fila, no el push.** La preferencia (ADR-059) actúa al encolar, así que el recordatorio queda en la bandeja y el teléfono calla. Apagar la categoría con entregas pendientes las cancela, también las de un recordatorio recién encolado.
- **Un fallo de Expo no se pierde.** La entrega sigue el reintento con espera de ADR-054 y, agotado, el aviso al personal de ADR-055 con su correo, que esta corrida ya drena. Un `DeviceNotRegistered` retira el token y no reintenta.
- **El push de los avisos del personal no cambia.** El escalamiento de asistencia vencida y la advertencia del token del kiosco siguen siendo avisos de bandeja y correo; no se convierten en push del socio porque no tienen destinatario socio.
- **Sigue dependiendo del cron del host.** Sin el bloque de `ops_cron.py --install`, el aviso se escribe al abrir la bandeja pero el push no sale. `deferred-notices.log` es la única señal de fallo; es el mismo límite de ADR-063, ADR-071 y ADR-073.
- **La lectura nunca enciende el push.** Abrir la bandeja antes que el cron deja el aviso escrito en silencio y el cron ya no lo reescribe (la clave de deduplicación es la misma), así que ese recordatorio no sonará. Es el precio de no molestar a quien ya está leyendo; el aviso no se pierde.

## Referencias

- ADR-016 (notificaciones del socio), ADR-035 (recordatorios de clase), ADR-039 (fisioterapia), ADR-052 (push del socio), ADR-054 (reintento con espera), ADR-055 (aviso al personal cuando el push se agota), ADR-059 (preferencias por categoría), ADR-061 (silencio del club), ADR-063 (cron de operación), ADR-065 (silencio del socio), ADR-076 (programador de avisos diferidos).
- Implementación: `app/modules/notifications/service.py`, `app/modules/notifications/push.py`, `backend/emit_deferred_notices.py`, `backend/ops_cron.py`.
- Pruebas: `backend/tests/test_deferred_notices_scheduler.py` (12 casos, cinco nuevos) y `backend/tests/test_ops_cron.py` (35). Suite completa: **575 pruebas, 567 aprobadas y 8 omitidas** sin `TEST_POSTGRES_URL`.
