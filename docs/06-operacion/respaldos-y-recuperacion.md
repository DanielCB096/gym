# Respaldos y recuperación

## Objetivo

Mantener continuidad del negocio con copias periódicas y una estrategia de recuperación clara.

## Recomendación

- respaldos cifrados de PostgreSQL con recuperación a un punto en el tiempo suficiente para demostrar el RPO máximo de 15 minutos aprobado en ADR-086
- recuperación completa en un máximo objetivo de 4 horas (RTO aprobado en ADR-086), demostrada mediante restauración aislada
- almacenamiento en repositorio seguro y cifrado
- retención escalonada por tipo de dato
- incluir los archivos críticos fuera de la base, como fotos de progreso, según `PROGRESS_PHOTOS_DIR`
- purga diaria de códigos rotativos e intentos del kiosco con `backend/purge_access_data.py` (no toca la bitácora de accesos; ver `despliegue.md`)
- purga diaria de los acuses del correo con `backend/purge_email_receipts.py` (no toca las entregas ni la bandeja; ver `despliegue.md`)
- prueba de restauración al menos mensual

## Flujos críticos

- recuperar base de datos tras falla
- restaurar configuración de acceso y notificaciones
- reconstruir caché y sincronización post-incident

## Riesgos

- pérdida de historial de cobros y accesos
- pérdida de auditoría
- retraso en recuperación de la caja y del acceso

⚠️ Se recomienda una validación con proveedor de infraestructura real antes de producción.

Los objetivos son requisitos de la primera entrega, no capacidades ya configuradas.
Un respaldo diario completo sin recuperación a un punto en el tiempo no satisface
el RPO de 15 minutos.
