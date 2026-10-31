# ADR-057: Rotación del secreto del webhook con periodo de gracia

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Cierra el límite de ADR-051 («El secreto es uno solo y manual»)

## Contexto

El webhook del acuse se autentica con un único `EMAIL_WEBHOOK_SECRET` que vive en el entorno. Cambiarlo de golpe invalida las firmas que el proveedor todavía tiene en vuelo: sus reintentos llegan con el secreto viejo, reciben `401` y el acuse se pierde aunque la entrega exista. Rotar exigía coordinar el corte a mano, sin margen para que los reintentos terminaran.

ADR-051 dejó ese hueco anotado como límite: «no hay segundo secreto para transiciones». Este corte lo cierra sin tocar la tabla, el contrato de campos ni la firma.

## Decisión

- **Un segundo secreto solo para verificar.** `EMAIL_WEBHOOK_SECRET_PREVIOUS` es opcional y se acepta únicamente al comprobar la firma; nunca se usa para firmar. `webhook_secret()` sigue devolviendo el actual y `signature_for` sigue recibiendo el secreto explícito, así que el club firma siempre con el nuevo.
- **El secreto actual es obligatorio.** Si `EMAIL_WEBHOOK_SECRET` falta o está vacío, el webhook responde `503` aunque haya un secreto anterior configurado: el anterior es una gracia, no una configuración válida.
- **Verificación en dos pasos y aviso.** `verify_signature` compara primero con el secreto actual y, si no coincide y hay uno anterior, compara con ese. Cuando la firma la produce el anterior, escribe un `warning` que nombra `EMAIL_WEBHOOK_SECRET_PREVIOUS` y pide retirarlo cuando terminen los reintentos. Si ninguno coincide, sigue respondiendo `401` con el mismo mensaje genérico.
- **La gracia no caduca sola.** No hay fecha de rotación ni plazo máximo: el operador retira la variable cuando el proveedor ya reintentó todo. El `warning` de cada petición firmada con el secreto viejo es el recordatorio.
- **El parámetro `previous_secret` permite probarlo.** `verify_signature(..., previous_secret=...)` inyecta el anterior; `None` lee el entorno y `""` lo desactiva, igual que el parámetro `secret` que ya existía para las pruebas.

## Consecuencias y límites

- **Un `warning` por petición durante la gracia.** Es intencional —recuerda retirar el secreto— pero puede llenar el registro mientras el proveedor reintenta; el operador lo retira en cuanto deja de aparecer.
- **Sin expiración automática.** Si se olvida, el secreto anterior sigue valiendo indefinidamente; nada en la base ni en el proceso lo detecta. La rotación es un cambio de entorno más un reinicio, no un flujo del panel.
- **Dos comparaciones por petición.** No hay identificador de clave (`key id`) en la cabecera, así que cada firma se prueba contra los dos secretos; el costo es un HMAC adicional, despreciable.
- **El secreto anterior también debe ser fuerte.** Un valor débil en cualquiera de las dos variables debilita el canal durante la transición.
- **El proveedor se reconfigura a mano.** El club debe cambiar el secreto en el proveedor y mantener el anterior hasta que sus reintentos se drenen; el sistema no habla con el proveedor para coordinarlo.
- **Los límites de ADR-051 que siguen abiertos** son la falta de identificador de webhook en la firma y las preferencias por tipo de aviso; la retención de los acuses quedó resuelta por ADR-058.

## Referencias

- `backend/src/app/modules/notifications/receipts.py` (`WEBHOOK_PREVIOUS_SECRET_ENV`, `webhook_previous_secret`, `verify_signature`)
- `backend/src/app/main.py` (`email_delivery_webhook`)
- `backend/tests/test_staff_email_receipts.py`
- ADR-051 (acuse de entrega por webhook firmado), ADR-056 (ventana de tiempo del acuse)
