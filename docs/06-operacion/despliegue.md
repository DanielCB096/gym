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

La purga de los datos operativos y la consulta de acuses **no corren solas**: no hay programador dentro de la aplicación y dependen del cron del servidor. El bloque de las tres tareas se genera desde el repositorio con `backend/ops_cron.py` (ADR-063); no se copia a mano.

Primero se revisa lo que se va a escribir y después se instala, con el usuario de la aplicación y después del respaldo:

```bash
cd /srv/gimnasio/backend
DATABASE_URL="postgresql+psycopg://gym:...@db:5432/gym" .venv/bin/python ops_cron.py --print
DATABASE_URL="postgresql+psycopg://gym:...@db:5432/gym" .venv/bin/python ops_cron.py --install
```

- `--print` es el valor por defecto y no toca nada: imprime el bloque delimitado por `# BEGIN gimnasio-ops` / `# END gimnasio-ops`. **No pegues esa salida con una URL real en un ticket ni en un chat**: la URL de la base queda escrita en el crontab del usuario, que el propio cron protege con modo `600`.
- `--install` crea la carpeta de bitácoras (`<backend>/logs` por defecto), comprueba que los tres scripts existan y **reemplaza** el bloque marcado en el crontab del usuario actual; las demás entradas se conservan. Volver a instalarlo con los mismos valores deja el crontab igual, así que cambiar la contraseña de la base o mover la carpeta se resuelve reinstalando, no editando a mano.
- `--uninstall` retira solo el bloque marcado y deja el resto del crontab intacto.
- Sin el comando `crontab` (Windows, un contenedor mínimo) la instalación no inventa un programador: explica que hay que instalar cron o usar `--print` y sale con código 1.
- Las horas son **locales del servidor**: el cron no interpreta `APP_TIMEZONE`. Fija la zona del host o ajusta `--daily-at` al desplegar.

Valores por defecto y banderas:

| Tarea | Cuándo | Script | Bitácora |
| --- | --- | --- | --- |
| Purga de accesos | diaria a las `03:15` | `purge_access_data.py` | `logs/purge-access.log` |
| Purga de acuses del correo | diaria a las `03:45` | `purge_email_receipts.py` | `logs/purge-email.log` |
| Acuses del push | cada 30 minutos (`*/30`) | `sync_push_receipts.py --limit 200` | `logs/push-receipts.log` |

- `--daily-at HH:MM` mueve la primera purga y la segunda queda 30 minutos después para no solaparse.
- `--receipts-every` acepta de 5 a 59 minutos (`*/N`) o 60 (`0 * * * *`): un acuse de Expo vence a las 24 horas, así que no se programa a diario.
- `--limit` va de 1 a 1000 tickets por corrida (el tope de Expo); 200 por defecto.
- `--app-dir`, `--python`, `--log-dir` y `--database-url` ajustan la ruta del backend, el intérprete, la carpeta de bitácoras y la URL sin depender del entorno.

Qué hace cada tarea:

- `purge_access_data.py` borra los códigos rotativos cuyo `expires_at` quedó antes del corte —vencidos o consumidos hace días, nunca uno vigente— y los intentos del kiosco anteriores al corte. **No toca `access_events`**: la bitácora es registro de negocio y su retención debe acordarse con el club. La retención del kiosco se ajusta con `KIOSK_CODE_RETENTION_DAYS` (7 días por defecto) y `KIOSK_ATTEMPT_RETENTION_DAYS` (30), enteros entre 1 y 3650; `--codes-days` y `--attempts-days` permiten una corrida puntual sin cambiar el entorno.
- `purge_email_receipts.py` borra de `staff_notification_delivery_receipts` los acuses con `received_at` anterior al corte. **No toca las entregas ni la bandeja**: solo los reportes del proveedor de correo. La retención es `STAFF_RECEIPT_RETENTION_DAYS` (90 días por defecto) o `--days`, entre 7 —la ventana del webhook, para que un acuse purgado no vuelva por un reintento tardío— y 3650.
- `sync_push_receipts.py` no borra nada: pregunta a Expo por los tickets de los push `sent` y escribe su acuse en `member_push_delivery_receipts` (ADR-062). Un acuse con error distinto de `DeviceNotRegistered` deja un aviso `member_push_receipt_failed` para quien opera la cola y el script drena la cola de correos al terminar, porque el cron no tiene una respuesta donde colgarla (ADR-064). Acepta `--database-url`, `--limit` y `--preview`; en vista previa informa la pasada como diferida porque no hay tickets reales. Un fallo de Expo interrumpe la corrida sin escribir acuses y la siguiente la retoma.

Las tres son idempotentes: una segunda corrida seguida no duplica trabajo. Una configuración inválida sale con código 2 y no modifica el crontab. En la vista previa se prueban con `--preview` (o sin `--database-url` si `DATABASE_URL` apunta a `gym_preview.db`); las purgas conviene estrenarlas con `--dry-run`.

El instalador no configura **rotación de bitácoras** ni **bloqueo de solapamiento**: usa `--log-dir` para llevarlas a la carpeta que ya rote el servidor y revisa los tres archivos cuando una tarea falle, porque el cron no avisa por correo.

## Riesgos

- integraciones con pagos y PAC
- errores en auditoría o permisos
- conectividad intermitente en el kiosco

⚠️ La implementación final de despliegue requiere revisarse con infraestructura real y costes del hosting.
