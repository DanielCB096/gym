# Despliegue

## Objetivo

Definir la ruta inicial para desplegar la aplicación con infraestructura simple, manejable y segura.

## Recomendación de despliegue inicial

- Backend: contenedor Docker + servicio en VPS o Azure App Service
- Base de datos: PostgreSQL administrado
- Redis: servicio administrado
- Web: Vercel o Netlify para panel web
- Mobile: Expo EAS
- Kiosco: Electron o aplicación web táctil con despliegue en tablet

## Pipeline sugerido

1. commit en rama de tarea
2. validación en GitHub Actions
3. revisión manual de cambios de negocio
4. despliegue controlado a entorno de prueba
5. despliegue a producción con aprobaciones

La validación del paso 2 incluye el job `migrations`: aplica la cadena Alembic completa sobre PostgreSQL 16 y revierte/reaplica la revisión más reciente, así que una migración que no funciona en el motor de producción rompe el push en lugar del despliegue. **Aplicar las migraciones al desplegar sigue siendo un paso manual** (`alembic upgrade head` con respaldo previo): el CI demuestra que la cadena es correcta, no la ejecuta contra la base real.

## Mantenimiento programado

La purga de los datos operativos, la consulta de acuses, la cola del push web del personal, la cola de correo del personal, la retención de la bandeja, los avisos diferidos y el cierre del día de fisioterapia **no corren solas**: no hay programador dentro de la aplicación y dependen del cron del servidor. El bloque de las nueve tareas se genera desde el repositorio con `backend/ops_cron.py` (ADR-063); no se copia a mano.

Primero se revisa lo que se va a escribir y después se instala, con el usuario de la aplicación y después del respaldo:

```bash
cd /srv/gimnasio/backend
DATABASE_URL="postgresql+psycopg://gym:...@db:5432/gym" .venv/bin/python ops_cron.py --print
DATABASE_URL="postgresql+psycopg://gym:...@db:5432/gym" .venv/bin/python ops_cron.py --install
```

- `--print` es el valor por defecto y no toca nada: imprime el bloque delimitado por `# BEGIN gimnasio-ops` / `# END gimnasio-ops`. **No pegues esa salida con una URL real en un ticket ni en un chat**: la URL de la base queda escrita en el crontab del usuario, que el propio cron protege con modo `600`.
- `--install` crea la carpeta de bitácoras (`<backend>/logs` por defecto), comprueba que los nueve scripts existan y **reemplaza** el bloque marcado en el crontab del usuario actual; las demás entradas se conservan. Volver a instalarlo con los mismos valores deja el crontab igual, así que cambiar la contraseña de la base o mover la carpeta se resuelve reinstalando, no editando a mano.
- `--uninstall` retira solo el bloque marcado y deja el resto del crontab intacto.
- Sin el comando `crontab` (Windows, un contenedor mínimo) la instalación no inventa un programador: explica que hay que instalar cron o usar `--print` y sale con código 1.
- Las horas son **locales del servidor**: el cron no interpreta `APP_TIMEZONE`. Fija la zona del host o ajusta `--daily-at` al desplegar.

Valores por defecto y banderas:

| Tarea | Cuándo | Script | Bitácora |
| --- | --- | --- | --- |
| Cierre del día de fisioterapia | diaria a las `00:30` | `close_physio_day.py` | `logs/physio-close.log` |
| Purga de accesos | diaria a las `03:15` | `purge_access_data.py` | `logs/purge-access.log` |
| Purga de acuses del correo | diaria a las `03:45` | `purge_email_receipts.py` | `logs/purge-email.log` |
| Purga de acuses y entregas del push | diaria a las `04:15` | `purge_push_data.py` | `logs/purge-push.log` |
| Purga de la bandeja y entregas del personal | diaria a las `04:45` | `purge_inbox_data.py` | `logs/purge-inbox.log` |
| Acuses del push | cada 30 minutos (`*/30`) | `sync_push_receipts.py --limit 200` | `logs/push-receipts.log` |
| Push web del personal | cada 15 minutos (`*/15`) | `flush_staff_push.py` | `logs/staff-push.log` |
| Correo del personal | cada 15 minutos (`*/15`) | `flush_staff_email.py` | `logs/staff-email.log` |
| Avisos diferidos y su push | cada 60 minutos (`0 * * * *`) | `emit_deferred_notices.py` | `logs/deferred-notices.log` |

- `--daily-at HH:MM` mueve la primera purga; la de acuses del correo queda 30 minutos después, la del push 60 y la de la bandeja 90, para no solaparse.
- `--physio-close-at HH:MM` mueve el cierre del día de fisioterapia (`00:30` por defecto); el día que se cierra se calcula en `APP_TIMEZONE`, pero la hora de la corrida es la del servidor.
- `--receipts-every` acepta de 5 a 59 minutos (`*/N`) o 60 (`0 * * * *`): un acuse de Expo vence a las 24 horas, así que no se programa a diario.
- `--staff-push-every` acepta de 5 a 59 minutos (`*/N`) o 60 (`0 * * * *`): una entrega pendiente del push web del personal se drena en la siguiente corrida; 15 minutos por defecto.
- `--staff-email-every` acepta de 5 a 59 minutos (`*/N`) o 60 (`0 * * * *`): un correo del personal atorado en `pending` se drena en la siguiente corrida; 15 minutos por defecto.
- `--notices-every` acepta de 5 a 59 minutos (`*/N`) o 60 (`0 * * * *`): una pasada al día no basta para los recordatorios de clase de 24 y 2 horas; 60 minutos por defecto.
- `--limit` va de 1 a 1000 tickets por corrida (el tope de Expo); 200 por defecto.
- `--app-dir`, `--python`, `--log-dir` y `--database-url` ajustan la ruta del backend, el intérprete, la carpeta de bitácoras y la URL sin depender del entorno.

Qué hace cada tarea:

- `purge_access_data.py` borra los códigos rotativos cuyo `expires_at` quedó antes del corte —vencidos o consumidos hace días, nunca uno vigente— y los intentos del kiosco anteriores al corte. **No toca `access_events`**: la bitácora es registro de negocio y su retención debe acordarse con el club. La retención del kiosco se ajusta con `KIOSK_CODE_RETENTION_DAYS` (7 días por defecto) y `KIOSK_ATTEMPT_RETENTION_DAYS` (30), enteros entre 1 y 3650; `--codes-days` y `--attempts-days` permiten una corrida puntual sin cambiar el entorno.
- `purge_email_receipts.py` borra de `staff_notification_delivery_receipts` los acuses con `received_at` anterior al corte. **No toca las entregas ni la bandeja**: solo los reportes del proveedor de correo. La retención es `STAFF_RECEIPT_RETENTION_DAYS` (90 días por defecto) o `--days`, entre 7 —la ventana del webhook, para que un acuse purgado no vuelva por un reintento tardío— y 3650.
- `purge_push_data.py` poda el push del socio (ADR-074): borra de `member_push_delivery_receipts` los acuses con `received_at` anterior al corte y de `member_push_deliveries` las entregas en estado terminal (`sent`, `simulated`, `failed`) con `created_at` anterior al suyo. **No toca una entrega `pending`** (es la cola) ni una entrega que aún tenga acuse, aunque haya pasado su ventana: la clave foránea es `RESTRICT` y la respuesta no debe perderse. Las retenciones son `PUSH_RECEIPT_RETENTION_DAYS` (90 días por defecto) y `PUSH_DELIVERY_RETENTION_DAYS` (365), entre 1 y 3650 cada una, o `--receipt-days` y `--delivery-days` para una corrida puntual; `--dry-run` cuenta sin borrar. No toca la bandeja ni el push web del personal.
- `purge_inbox_data.py` poda la bandeja y las colas del personal (ADR-075): borra los avisos del socio **ya leídos** y los del personal **cerrados** anteriores al corte, y las entregas terminales (`sent`, `simulated`, `failed`) de correo y de push web del personal anteriores al suyo. Nunca borra un aviso del socio sin leer, un aviso del personal con trabajo pendiente —sin `resolved_at` en los tipos que se cierran— ni la advertencia de token del kiosco, que se regenera mientras el dispositivo siga ahí. Borra primero las entregas y después los avisos, y salta cualquiera que conserve una entrega o un acuse: las claves foráneas son `RESTRICT`. Las retenciones son `NOTIFICATION_INBOX_RETENTION_DAYS` (365 días por defecto, de 30 a 3650) y `STAFF_DELIVERY_RETENTION_DAYS` (365, de 1 a 3650), o `--inbox-days` y `--delivery-days` para una corrida puntual; `--dry-run` cuenta sin borrar.
- `sync_push_receipts.py` no borra nada: pregunta a Expo por los tickets de los push `sent` y escribe su acuse en `member_push_delivery_receipts` (ADR-062). Un acuse con error distinto de `DeviceNotRegistered` deja un aviso `member_push_receipt_failed` para quien opera la cola y el script drena la cola de correos al terminar, porque el cron no tiene una respuesta donde colgarla (ADR-064). Acepta `--database-url`, `--limit` y `--preview`; en vista previa informa la pasada como diferida porque no hay tickets reales. Un fallo de Expo interrumpe la corrida sin escribir acuses y la siguiente la retoma.
- `flush_staff_push.py` envía las entregas `pending` del push web del personal que un proceso caído dejó sin mandar (ADR-070): usa la misma pasada del gancho, con el compare-and-set sobre `attempts`, y **no reintenta las `failed`** —esas siguen esperando a una persona— (ADR-071). Acepta `--database-url`, `--limit` (1 a 100, 20 por defecto) y `--preview`, que usa `gym_preview.db` y simula las entregas sin contactar al servicio de push. Sin URL sale con código 2 y una base inalcanzable con código 1.
- `flush_staff_email.py` envía las entregas de correo del personal que quedaron `pending` cuando el proceso murió antes de la pasada que viaja con la respuesta (ADR-079): usa la misma pasada del gancho y del botón «Enviar pendientes», con el compare-and-set sobre `attempts`, y **no reintenta las `failed`** —esas siguen esperando a una persona—. Respeta el interruptor del club al drenar: con el correo apagado no envía nada y deja las filas pendientes. Acepta `--database-url`, `--limit` (1 a 100, 20 por defecto) y `--preview`, que usa `gym_preview.db` y marca las entregas como simuladas sin contactar al servidor de correo. Sin URL sale con código 2 y una base inalcanzable con código 1.
- `emit_deferred_notices.py` escribe los avisos que se vuelven ciertos con el tiempo sin esperar a que alguien abra la bandeja (ADR-076): los recordatorios de membresía por vencer, de clase próxima y de cita de fisioterapia, más el escalamiento de una solicitud de asistencia vencida y la advertencia del token del kiosco por caducar. Reutiliza los productores de las rutas de lectura y sus claves de deduplicación, así que una segunda corrida no repite nada; solo revisa a los socios con una fuente en ventana. Desde ADR-078 los tres recordatorios del socio encolan su push y el script drena la cola en la misma corrida: respeta la preferencia de categoría, la ventana de silencio del club y la del socio, simula en `--preview` y deja los fallos al reintento normal; `--push-limit` (1 a 100, 20 por defecto) limita los envíos por corrida y lo que sobra sale en la siguiente. Acepta `--database-url` y `--preview` (crea el esquema en `gym_preview.db`). Sin URL sale con código 2 y una base inalcanzable con código 1. El cron del host es lo único que hace sonar ese push: sin `--install` el aviso se sigue escribiendo al abrir la bandeja, pero el teléfono no suena.
- `close_physio_day.py` cierra el día anterior de la agenda de fisioterapia con el mismo servicio del botón «Cerrar día» (ADR-073): deja `no_show` lo que terminó sin marca, sin cobrar ni descontar, y no toca las citas ya marcadas. Acepta `--date AAAA-MM-DD` para recuperar un día perdido, `--database-url` y `--preview` (que **escribe** en `gym_preview.db`). Sin URL sale con código 2 y una base inalcanzable con código 1.

Las nueve son idempotentes: una segunda corrida seguida no duplica trabajo. Una configuración inválida sale con código 2 y no modifica el crontab. En la vista previa se prueban con `--preview` (o sin `--database-url` si `DATABASE_URL` apunta a `gym_preview.db`); las purgas conviene estrenarlas con `--dry-run`.

El instalador no configura **rotación de bitácoras** ni **bloqueo de solapamiento**: usa `--log-dir` para llevarlas a la carpeta que ya rote el servidor y revisa las bitácoras cuando una tarea falle, porque el cron no avisa por correo.

## Riesgos

- integraciones con pagos y PAC
- errores en auditoría o permisos
- conectividad intermitente en el kiosco

⚠️ La implementación final de despliegue requiere revisarse con infraestructura real y costes del hosting.
