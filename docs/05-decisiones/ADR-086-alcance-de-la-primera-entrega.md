# ADR-086: Alcance de la primera entrega

- Fecha: 2026-11-02
- Estado: aceptada para planificación; implementación y salida a producción pendientes
- Complementa ADR-003, ADR-004 y ADR-066

## Contexto

El checkout actual de Conekta permite un pago inicial de membresía solo en
sandbox. La documentación previa dejaba la renovación automática fuera del
primer incremento técnico. Para planear una primera entrega integral se
necesitaba fijar qué se incluye y separar las decisiones de alcance de las
capacidades ya implementadas.

## Decisiones

- La primera entrega incluye renovación automática de membresías. ADR-066 sigue
  describiendo el alcance técnico ya implementado (pago único en sandbox); no
  se considera que la renovación esté implementada por esta decisión.
- No se guardan datos de tarjeta sin procesar. Antes de cobrar automáticamente
  se requiere un flujo diseñado y revisado para consentimiento explícito,
  revocación/cancelación, intentos fallidos y conciliación. Los cargos reales
  permanecen deshabilitados hasta validar el flujo con el proveedor y aprobar
  producción.
- El acceso inicial conserva el código numérico de seis dígitos capturado en el
  kiosco. No se integra lector QR, RFID, biométrico ni torniquete en esta
  entrega; esta decisión acota la recomendación de hardware de ADR-004.
- No se integra terminal bancaria física. Los cobros externos se registran por
  el flujo manual existente.
- El lanzamiento aprobado es para todos los socios, sin un piloto productivo
  limitado. Antes de abrirlo deben completarse las pruebas internas en staging,
  la recuperación, la revisión de seguridad y la autorización formal.
- El módulo fiscal queda fuera de esta entrega: CFDI, PAC/Finkok y flujos
  fiscales relacionados no son criterio de salida.
- Los objetivos de recuperación son RPO máximo de 15 minutos y RTO máximo de 4
  horas. Son objetivos por demostrar, no una afirmación sobre la infraestructura
  actual.
- Se eligió VPS. El proveedor, región/plan, presupuesto y dominio quedan por
  seleccionar antes de provisionar staging.
- El dueño asume los roles de aprobación de negocio, operación técnica y
  autorización de recuperaciones.

## Consecuencias

- La renovación automática amplía el alcance: requiere diseño funcional,
  consentimiento, cancelación, idempotencia, avisos, pruebas de fallos y
  aprobación del proveedor. No se deriva de la implementación del checkout
  único.
- El código numérico permite usar el kiosco actual, pero no automatiza una
  puerta o torniquete.
- Abrir a todos los socios desde el primer despliegue aumenta el impacto de
  errores; staging, aceptación interna, monitoreo, respaldo y reversa son
  barreras obligatorias.
- El RPO de 15 minutos requiere una estrategia distinta de un respaldo diario
  aislado, como recuperación a un punto en el tiempo, y una restauración
  verificable.
- La selección del proveedor, región/plan y dominio bloquea la configuración
  de staging y la concreción del respaldo.

## Referencias

- [Alcance y preparación de la primera entrega](../06-operacion/primera-entrega.md)
- [ADR-003: Pasarela de pago](ADR-003-pasarela-de-pago.md)
- [ADR-004: Hardware de acceso](ADR-004-hardware-acceso.md)
- [ADR-066: Primer pago en línea con checkout alojado](ADR-066-primer-pago-en-linea.md)
- [Integración de pasarela de pago](../04-integraciones/pasarela-de-pago.md)
- [Despliegue](../06-operacion/despliegue.md)
- [Respaldos y recuperación](../03-procesos/respaldo-y-recuperacion.md)
