# ADR-002: Base de datos

- Fecha: 2026-10-15
- Estado: propuesta inicial

## Contexto

El sistema requiere trazabilidad de pagos, accesos, historial operativo, inventario, nómina y CFDI. La base de datos debe soportar transacciones, auditoría y consultas analíticas sin sobreingeniería.

## Opciones consideradas

1. PostgreSQL únicamente
2. PostgreSQL + Redis
3. PostgreSQL + ClickHouse para analítica

## Decisión

Se usa PostgreSQL como base de datos principal con Redis para caché y colas. La analítica pesada se resuelve con vistas materializadas o esquema de reporting más adelante, antes de introducir otra base de datos.

## Consecuencias

- buen equilibrio entre simplicidad y potencia
- soporte robusto para transacciones y relaciones complejas
- fácil integración con FastAPI y migraciones
- la analítica avanzada se manejará con agregaciones y reportes en segundo plano

⚠️ Si el volumen de reportes o la complejidad de reporting crece mucho, se evaluará una base analítica adicional.
