# ADR-056: Ventana de tiempo para el acuse de entrega del correo

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Cierra el límite de ADR-051 («No hay verificación de ventana temporal»)

## Contexto

La firma del webhook cubre el cuerpo, no el momento que ese cuerpo describe. Un `delivered` o un `bounced` con un `occurred_at` de hace semanas se aceptaba igual que uno recién ocurrido, así que el historial de la entrega podía crecer con un evento viejo que nadie había recibido antes —el reenvío de un cuerpo capturado, un reloj mal configurado en el proveedor o un reintento que llega tarde—. La idempotencia por `provider_event_id` evita duplicar un evento ya guardado, pero no dice nada sobre la plausibilidad de uno nuevo.

ADR-051 dejó ese hueco anotado como límite antes de producción: «añadir una tolerancia y registrar el rechazo». Este corte lo cierra sin tocar la tabla ni el contrato de campos.

## Decisión

- **Dos tolerancias fijas.** `RECEIPT_MAX_AGE` es de 7 días: un evento nuevo con más antigüedad no entra. `RECEIPT_MAX_FUTURE_SKEW` es de 15 minutos: un evento con fecha futura más allá de ese adelanto tampoco. Las dos viven en `receipts.py` y se aplican sobre `occurred_at` normalizado a UTC; el reloj de referencia es el del club (`utc_now()` o el `now` que inyectan las pruebas).
- **Solo se valida lo nuevo.** La comprobación ocurre **después** de buscar el `provider_event_id`. Un evento ya guardado sigue respondiendo a sus reintentos con `200` y `duplicate: true` aunque su fecha haya quedado fuera de la ventana, de modo que los recibos anteriores a este corte y los reintentos legítimos del proveedor no se rompen.
- **Un evento fuera de ventana responde `422`.** `ReceiptStale` hereda de `ReceiptInvalid`, así que el endpoint la mapea a `422` sin ramas nuevas y el `detail` explica el motivo en español: «demasiado antiguo» o «demasiado en el futuro». No se escribe ninguna fila.
- **Sin fecha no hay forma de colocarlo.** Un evento nuevo cuyo `occurred_at` falta o llega nulo no se puede situar en el tiempo y se rechaza con el mismo `422`; el adaptador del proveedor debe enviarlo. Los eventos ya guardados sin fecha siguen respondiendo como repetidos.
- **El rechazo deja rastro.** Cada descarte escribe un `warning` en el logger del módulo con el `message_id`, el `provider_event_id` y el motivo, sin volcar el cuerpo ni el detalle del proveedor.

## Consecuencias y límites

- **La ventana acota el evento nuevo, no autentica.** El límite real sigue siendo el HMAC: quien tenga el secreto puede firmar un evento con cualquier fecha dentro de la tolerancia, y la idempotencia por evento evita que un cuerpo capturado y reenviado agregue una fila. La ventana reduce la superficie de un reenvío viejo y de un reloj desbocado, no sustituye a rotar el secreto.
- **Las tolerancias son constantes, no configuración.** Si un proveedor real necesita más de siete días para reportar un rebote, se ajusta la constante en código y se documenta; no hay variable de entorno ni endpoint.
- **Un rebote legítimo y muy tardío se descarta.** El caso queda fuera por diseño; los proveedores suelen reintentar en horas, no en semanas, y el adaptador siempre puede reenviar con la fecha original si el club lo necesita.
- **La ventana depende del reloj del club.** Un servidor con la hora mal puesta rechazaría eventos válidos o aceptaría viejos; el club ya valida `APP_TIMEZONE` al arrancar, pero el reloj del sistema queda fuera del alcance de la aplicación.
- **Los recibos siguen sin retención.** Sigue pendiente purgar `staff_notification_delivery_receipts` con una política como la del kiosco (ADR-040). La rotación de `EMAIL_WEBHOOK_SECRET` con periodo de gracia quedó resuelta por ADR-057.

## Referencias

- `backend/src/app/modules/notifications/receipts.py` (`RECEIPT_MAX_AGE`, `RECEIPT_MAX_FUTURE_SKEW`, `ReceiptStale`, `record_email_receipt`)
- `backend/src/app/main.py` (`email_delivery_webhook`)
- `backend/tests/test_staff_email_receipts.py`
- ADR-051 (acuse de entrega por webhook firmado)
