# Respaldos y recuperación

## Objetivo

Mantener continuidad del negocio con copias periódicas y una estrategia de recuperación clara.

## Recomendación

- respaldo diario completo de PostgreSQL
- almacenamiento en repositorio seguro y cifrado
- retención escalonada por tipo de dato
- purga diaria de códigos rotativos e intentos del kiosco con `backend/purge_access_data.py` (no toca la bitácora de accesos; ver `despliegue.md`)
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
