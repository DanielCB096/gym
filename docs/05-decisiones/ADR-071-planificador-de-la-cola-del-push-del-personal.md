# ADR-071: Planificador de la cola del push web del personal

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Cierra el límite (6) de ADR-070 («sin planificador»)

## Contexto

ADR-070 dejó el push web del personal viajando con la respuesta que crea el aviso: `AttendanceEmailFlush` lanza la pasada en segundo plano y, si el proceso muere entre el commit del aviso y esa pasada —un reinicio del servicio, un despliegue, un worker que no llega a ejecutar la tarea—, las entregas quedan `pending` para siempre. El panel puede drenarlas con «Enviar pendientes» (`POST /admin/staff/push/deliveries/send`), pero eso exige que alguien entre a Equipo y lo pulse; un cuadro de recepción que nunca lo hace pierde los avisos sin darse cuenta.

La cola del socio ya tiene su planificador (ADR-062) y el instalador de cron (ADR-063) genera un bloque idempotente con las tareas de operación. El push del personal era la única cola que dependía por completo de una petición.

## Decisión

- **Un script propio, no un planificador interno.** `backend/flush_staff_push.py` llama a `send_pending_staff_push_deliveries_from_engine` —la misma pasada del gancho— y no agrega estado, tabla ni migración. Toma hasta 20 filas `pending` por corrida (`--limit`, de 1 a 100), las reclama con el compare-and-set de `attempts` y las envía cifradas con VAPID.
- **Solo `pending`; las `failed` siguen esperando a una persona.** El script no reintenta ni reprograma: un canal roto que se reintenta solo alertaría a las mismas cuentas que operan el panel (ADR-070). Para reintentar una `failed` sigue estando el botón «Reintentar» del panel.
- **Vista previa que no sale de la máquina.** `--preview` apunta a `gym_preview.db`, crea las tablas si faltan y marca las entregas como `simulated`; no contacta al servicio de push. `--database-url` apunta a otra base y exige `DATABASE_URL` del entorno si no se pasa ninguna. Una configuración inválida —`--preview` con `--database-url`, `--limit` fuera de rango, sin URL— sale con código 2; una base inalcanzable, con código 1 y el motivo en la bitácora.
- **Cuarta entrada del bloque de cron.** `ops_cron.py` agrega `flush_staff_push.py` con `--staff-push-every` (5 a 59 minutos, o 60; 15 por defecto), la bitácora `logs/staff-push.log` y el mismo delimitador `# BEGIN gimnasio-ops` / `# END gimnasio-ops`. Instalar de nuevo reemplaza el bloque completo, así que el crontab nunca queda con dos copias; sin el comando `crontab` la instalación explica qué falta y no declara éxito, y `--print` sigue siendo la opción por defecto.
- **La cola se drena sin tocar el panel.** Un aviso que quedó `pending` se envía en la siguiente corrida aunque nadie abra el panel; el operador conserva «Enviar pendientes» para forzar el drenaje en el momento y «Reintentar» para las fallidas.

## Consecuencias y límites

- **El cron no garantiza el instante.** Corre en la hora local del servidor y cada 15 minutos por defecto: un aviso atorado espera hasta la siguiente corrida, y una corrida que falla no se repite hasta la próxima. No hay alerta si el cron está detenido; la cola del panel sigue mostrando los `pending`.
- **El script no sustituye a la pasada por respuesta.** La pasada del gancho sigue siendo el camino normal (latencia de segundos); el cron solo recoge lo que quedó atrás.
- **Sigue sin haber acuse de visualización.** `sent` significa que el servicio de push aceptó el mensaje (ADR-070); el planificador no cambia eso.
- **Cada corrida envía como máximo 20 entregas.** Si la cola crece por un apagón largo, se drena en varias corridas o se lanza el script a mano con `--limit` mayor.
- **Requiere la configuración VAPID del backend.** Sin `VAPID_PRIVATE_KEY` el script falla cada entrega y las deja `failed`, igual que el gancho; el motivo queda en el detalle de cada fila.

## Referencias

- `backend/flush_staff_push.py`
- `backend/ops_cron.py` (`staff_push_schedule`, `--staff-push-every`, `flush_staff_push.py` en `_SCRIPTS`)
- `backend/src/app/modules/notifications/webpush.py` (`send_pending_staff_push_deliveries_from_engine`)
- `backend/tests/test_staff_push_flush.py`, `backend/tests/test_ops_cron.py`
- `docs/06-operacion/despliegue.md`
- `docs/05-decisiones/ADR-063-programacion-de-las-tareas-de-operacion.md`, `ADR-070-push-web-para-el-personal.md`
