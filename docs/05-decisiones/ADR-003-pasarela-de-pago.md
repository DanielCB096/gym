# ADR-003: Pasarela de pago

- Fecha: 2026-10-15
- Estado: propuesta inicial

## Contexto

El sistema requiere cobro recurrente, tokenización, confirmación de estado y reintentos automáticos.

## Opciones consideradas

1. Conekta
2. Stripe México
3. OpenPay
4. Mercado Pago

## Decisión

Se recomienda Conekta como pasarela principal para la fase inicial por su enfoque local, idempotencia y soporte de cobro recurrente. La solución usa tokenización y nunca guarda la tarjeta del cliente.

## Consecuencias

- buena experiencia para suscripciones mensuales
- integración clara con webhooks y reintentos
- requiere mantenimiento de sincronización del estado de los pagos

⚠️ La intención es simplificar la operación para un solo gimnasio sin perder capacidad de crecimiento.
