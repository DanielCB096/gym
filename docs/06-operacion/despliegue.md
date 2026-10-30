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

La purga de los datos operativos del kiosco **no corre sola**: no hay programador dentro de la aplicación y depende de una tarea externa. Programa a diario `backend/purge_access_data.py`, con el usuario de la aplicación y después del respaldo:

```bash
cd /srv/gimnasio/backend
DATABASE_URL="postgresql+psycopg://gym:...@db:5432/gym" .venv/bin/python purge_access_data.py --dry-run
DATABASE_URL="postgresql+psycopg://gym:...@db:5432/gym" .venv/bin/python purge_access_data.py >> /var/log/gimnasio-purge.log 2>&1
```

- Borra los códigos rotativos cuyo `expires_at` quedó antes del corte —vencidos o consumidos hace días, nunca uno vigente— y los intentos del kiosco anteriores al corte. **No toca `access_events`**: la bitácora es registro de negocio y su retención debe acordarse con el club.
- La retención se ajusta con `KIOSK_CODE_RETENTION_DAYS` (7 días por defecto) y `KIOSK_ATTEMPT_RETENTION_DAYS` (30), enteros entre 1 y 3650; las banderas `--codes-days` y `--attempts-days` permiten una corrida puntual sin cambiar el entorno.
- Es idempotente: una segunda corrida seguida borra `0`. Una configuración inválida sale con código 2 y no modifica nada.
- En la vista previa se ejecuta con `--preview` (o sin `--database-url` si `DATABASE_URL` apunta a `gym_preview.db`); la primera corrida conviene hacerla con `--dry-run`.

## Riesgos

- integraciones con pagos y PAC
- errores en auditoría o permisos
- conectividad intermitente en el kiosco

⚠️ La implementación final de despliegue requiere revisarse con infraestructura real y costes del hosting.
