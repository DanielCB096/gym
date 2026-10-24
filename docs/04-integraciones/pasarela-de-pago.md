# Pasarela de pago

## Contexto

La pasarela debe soportar cobros recurrentes, tokenización, reintentos, Webhooks y conciliación con bancas y SPEI.

## Opciones comparadas

| Proveedor | Fortalezas | Consideraciones |
|---|---|---|
| Conekta | muy fuerte en México, suscripciones, tokens | requiere integración con API y webhooks |
| Stripe México | robusto global, excelente API | puede ser más costoso y con complejidad más global |
| OpenPay | popular en México y local | validación de infraestructura y soporte |
| Mercado Pago | local y muy conocida | suscripciones tienen matices propios y soporte variable |

## Recomendación

Se recomienda Conekta por su enfoque local, soporte de suscripción, tokenización y compatibilidad con pagos recurrentes en México.

## Reglas de diseño
- el sistema no guarda números de tarjeta
- se usa token del proveedor
- cada cobro genera event log y idempotency key
- los reintentos y webhooks quedan en cola y reintentos automáticos

⚠️ La decisión final debe validarse con el negocio y con el proveedor antes de producción.
