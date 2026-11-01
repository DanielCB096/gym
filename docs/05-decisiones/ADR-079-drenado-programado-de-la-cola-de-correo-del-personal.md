# ADR-079: Drenado programado de la cola de correo del personal

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Cierra el límite de ADR-049 («la pasada viaja con la respuesta»)

## Contexto

`create_staff_notification` escribe una entrega `pending` por destinatario en la misma transacción del aviso, y la pasada de envío sale **después** de la respuesta de la petición que lo creó (ADR-048, ADR-049). Ese diseño mantiene el correo fuera de la transacción del dominio, pero deja un hueco: si el proceso muere entre el commit del aviso y la pasada —un reinicio, un despliegue, una respuesta que nunca llega a pintarse— las filas quedan `pending` en la base y nadie las envía. El panel puede drenarlas con «Enviar pendientes» en la tarjeta «Correos del personal» (ADR-050), pero eso exige que alguien entre a Equipo y lo pulse; un club que nunca abre esa tarjeta pierde los avisos sin darse cuenta, y el lote de 20 filas por pasada solo avanza con una pulsación.

La cola de push del personal ya resolvió este problema con un script propio y su entrada de cron (ADR-071), y la de avisos diferidos hizo lo mismo con el push del socio (ADR-078). La cola de correo era la única que todavía dependía por completo de una petición.

## Decisión

- **Un script propio, no un planificador interno.** `backend/flush_staff_email.py` llama a `send_pending_staff_notification_emails_from_engine` —la misma pasada del gancho y del botón— y no agrega estado, tabla ni migración. Toma hasta 20 filas `pending` por corrida (`--limit`, de 1 a 100), las reclama con el compare-and-set de `attempts` y las envía por SMTP.
- **Solo `pending`; las `failed` siguen esperando a una persona.** El script no reintenta ni reprograma: un canal roto que se reintenta solo alertaría a las mismas cuentas que operan el panel. Para reintentar una `failed` sigue estando el botón «Reintentar» de la tarjeta.
- **El interruptor del club se respeta al drenar.** Si la política tiene el correo del personal apagado, la pasada no envía nada, imprime `El correo del personal está apagado en la política del club; las entregas siguen pendientes.` y deja las filas como estaban; al reactivar el interruptor la siguiente corrida las recoge.
- **Vista previa que no sale de la máquina.** `--preview` apunta a `gym_preview.db`, crea las tablas si faltan y marca las entregas como `simulated`; no contacta al servidor de correo. `--database-url` apunta a otra base y exige `DATABASE_URL` del entorno si no se pasa ninguna. Una configuración inválida —`--preview` con `--database-url`, `--limit` fuera de rango, sin URL— sale con código 2; una base inalcanzable, con código 1 y el motivo en la salida de error.
- **Novena entrada del bloque de cron.** `ops_cron.py` agrega `flush_staff_email.py` con `--staff-email-every` (5 a 59 minutos, o 60; 15 por defecto), la bitácora `logs/staff-email.log` y el mismo delimitador `# BEGIN gimnasio-ops` / `# END gimnasio-ops`. Instalar de nuevo reemplaza el bloque completo, así que el crontab nunca queda con dos copias; sin el comando `crontab` la instalación explica qué falta y no declara éxito, y `--print` sigue siendo la opción por defecto.
- **La cola se drena sin tocar el panel.** Un aviso que quedó `pending` se envía en la siguiente corrida aunque nadie abra el panel; el operador conserva «Enviar pendientes» para forzar el drenaje en el momento y «Reintentar» para las fallidas.

## Consecuencias y límites

- **El cron no garantiza el instante.** Corre en la hora local del servidor y cada 15 minutos por defecto: un aviso atorado espera hasta la siguiente corrida, y una corrida que falla no se repite hasta la próxima. No hay alerta si el cron está detenido; la tarjeta «Correos del personal» sigue mostrando los `pending`.
- **El script no sustituye a la pasada por respuesta.** La pasada del gancho sigue siendo el camino normal (latencia de segundos); el cron solo recoge lo que quedó atrás.
- **Mismo lote de 20 filas por corrida** que el botón del panel, porque reutiliza la misma pasada. Si la cola crece por un apagón largo, se drena en varias corridas o se lanza el script a mano con `--limit` mayor.
- **Sin SMTP configurado las filas quedan `failed`, no `pending`.** Igual que el gancho: el motivo queda en el detalle de cada fila y el operador decide cuándo reintentar.
- **Sin cambios de contrato ni de pantalla.** No hay endpoint nuevo, ni campo nuevo en la tarjeta, ni migración: el script escribe con el mismo código de la pasada existente.

## Referencias

- `backend/flush_staff_email.py`
- `backend/ops_cron.py` (`staff_email_schedule`, `--staff-email-every`, `flush_staff_email.py` en `_SCRIPTS`)
- `backend/src/app/modules/notifications/delivery.py` (`send_pending_staff_notification_emails_from_engine`)
- `backend/tests/test_staff_email_flush.py`, `backend/tests/test_ops_cron.py`
- `docs/06-operacion/despliegue.md`
- `docs/05-decisiones/ADR-049-envio-y-reintento-de-la-cola-de-correos-de-asistencia.md`, `ADR-050-correo-de-todos-los-avisos-del-personal.md`, `ADR-063-programacion-de-las-tareas-de-operacion.md`, `ADR-071-planificador-de-la-cola-del-push-del-personal.md`
