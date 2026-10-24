# ADR-005: Modelo de permisos

- Fecha: 2026-10-15
- Estado: propuesta inicial

## Contexto

El sistema tiene múltiples actores con permisos distintos, y la validación debe estar presente en backend, no solo en la interfaz.

## Opciones consideradas

1. permisos por rol fijo
2. permisos por rol + área funcional
3. permisos granulares por acción y recurso

## Decisión

Se usa un modelo basado en roles con permisos granulares por acción y recurso. Esto permite mantener una seguridad clara y una auditoría de cambios sensibles sin sobrecomplicar la operación del gimnasio.

## Consecuencias

- mejor control para recepción, gerente, contador y dueño
- mejor trazabilidad de acciones sensibles
- requiere mantenimiento organizado de permisos y validación en backend

⚠️ Si se agregan sucursales o más roles, este modelo deberá mantenerse y ampliarse sin romper la base actual.
