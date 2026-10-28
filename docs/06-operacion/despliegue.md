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

## Riesgos

- integraciones con pagos y PAC
- errores en auditoría o permisos
- conectividad intermitente en el kiosco

⚠️ La implementación final de despliegue requiere revisarse con infraestructura real y costes del hosting.
