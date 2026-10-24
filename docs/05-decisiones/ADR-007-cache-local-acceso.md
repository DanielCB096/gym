# ADR-007: Caché local de acceso offline

- Fecha: 2026-10-15
- Estado: propuesta para validación con hardware

## Contexto

El lector/controlador debe seguir decidiendo entradas durante cortes de conectividad y conservar eventos hasta confirmar su sincronización. El backend central de PostgreSQL no está disponible durante esos cortes.

## Decisión

Usar SQLite como almacenamiento local del snapshot de membresía y del outbox de eventos en la primera implementación. Las decisiones se calculan con snapshots con vencimiento explícito; una entrada con snapshot ausente o vencido se deniega. Las salidas no dependen del estado de membresía. Cada evento usa `event_id` idempotente y permanece pendiente hasta una confirmación explícita de sincronización.

## Consecuencias

- No requiere operar un servidor de base de datos en el controlador local.
- La escritura del outbox es transaccional y tolera reintentos idempotentes.
- SQLite no sustituye el protocolo de sincronización ni la autenticación del dispositivo.
- Hardware, retención, vigencia de snapshots, concurrencia del aforo y apertura del torniquete requieren validación antes de producción.
- La decisión de bloquear ante caché vencido favorece seguridad; cualquier excepción requiere una regla de negocio aprobada y auditada.

## Alternativas consideradas

1. Depender solo de PostgreSQL central: descartado porque falla con cortes de red.
2. Mantener la caché únicamente en memoria: descartado porque se perdería ante reinicio o corte de energía.

## Referencias

- `backend/src/app/modules/access/offline_store.py`
- `docs/02-modulos/control-de-acceso.md`
- `docs/03-procesos/acceso-con-y-sin-internet.md`