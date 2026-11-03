# ADR-088: Respaldo y recuperación local del staging

- Fecha: 2026-11-03
- Estado: aceptada para staging; producción pendiente

## Contexto

La primera entrega exige RPO máximo de 15 minutos y RTO máximo de 4 horas,
incluyendo fotos de progreso almacenadas fuera de PostgreSQL. El proyecto
todavía no tiene una infraestructura productiva definida.

## Decisión

- PostgreSQL de staging se respalda con `pg_dump --format=custom`.
- Las fotos se copian desde el volumen de la API como un archivo comprimido.
- Cada copia incluye un manifiesto UTC con SHA-256 de sus archivos.
- Por defecto la restauración usa PostgreSQL y volúmenes temporales.
- `-Apply` solo permite reemplazar explícitamente el staging sintético.
- El ensayo mide el tiempo desde el respaldo hasta la restauración aislada.
- Ninguno de estos scripts se considera cumplimiento productivo del RPO/RTO.

## Consecuencias

- El equipo puede ensayar restauración sin tocar el entorno activo.
- La producción deberá incorporar cifrado, ubicación externa y PITR o un
  mecanismo equivalente para acercarse al objetivo de 15 minutos.
- Redis se excluye porque contiene caché reconstruible.
