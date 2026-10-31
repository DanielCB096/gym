# ADR-051: Acuse de entrega del correo del personal por webhook firmado

- Fecha: 2026-10-30
- Estado: propuesta inicial
- Cierra el límite de ADR-049 («`sent` es que el servidor aceptó el mensaje, no que llegara»)

## Contexto

La cola de correo del personal ya sabe lo que respondió el servidor SMTP al aceptar el mensaje, y eso es todo lo que el club puede saber por su cuenta. Que la cuenta exista, que el buzón no esté lleno o que el destinatario marque el correo como spam ocurre después, en el proveedor, y hasta ahora el panel no tenía forma de enterarse: una entrega `sent` podía llevar días rebotando sin que nadie lo supiera.

Conectar un proveedor concreto (Resend, SendGrid, SES…) traería su propio modelo de eventos y su propia firma. El club todavía no ha elegido proveedor, así que el corte deja preparada la **forma** de recibir el acuse —el identificador que el mensaje deja al salir, la tabla donde se guardan los eventos y un webhook firmado con un contrato estable— y deja la conexión real para un adaptador.

## Decisión

- **El mensaje sale con identificador propio.** `new_message_id()` genera `<uuid>@<dominio>` (dominio `EMAIL_MESSAGE_ID_DOMAIN`, por defecto `centro-fit.local`) y `_enqueue_staff_notification_email` lo congela en `staff_notification_deliveries.message_id` (VARCHAR(320), índice único). `send_email` lo escribe como cabecera `Message-ID` envolviéndolo en `<>`. El identificador no se recalcula: es el que el proveedor devolverá en su acuse.
- **Los acuses son una tabla aparte y solo se agregan.** `staff_notification_delivery_receipts` guarda `delivery_id`, `provider_event_id` (único), `event_type` (`delivered`/`bounced`/`complained`), `occurred_at`, `detail` (hasta 500) y `received_at`. Un acuse **nunca** reescribe el estado del transporte: `sent` sigue significando que el servidor aceptó el mensaje, y el acuse dice qué pasó después. Así una entrega puede tener varios eventos —entregado y luego una queja— sin perder ninguno.
- **El webhook es genérico y firmado.** `POST /webhooks/email/delivery` recibe un JSON con `message_id`, `event_id`, `event`, `occurred_at` y `detail` opcional; el cuerpo se firma con HMAC-SHA256 y la cabecera `X-Email-Signature: sha256=<hex>` usando `EMAIL_WEBHOOK_SECRET`. Sin secreto configurado responde `503`, firma ausente o distinta `401`, cuerpo inválido `422`, mensaje desconocido `404` y un evento que no puede aplicarse `409` (la entrega no está `sent` o el `event_id` ya pertenece a otro mensaje). La comparación usa `compare_digest`.
- **Idempotencia por identificador de evento.** El proveedor puede reintentar el mismo webhook; el índice único de `provider_event_id` y el savepoint hacen que la segunda entrega del mismo evento devuelva la fila existente con `duplicate: true` en lugar de duplicar la historia. Un `event_id` no puede moverse entre mensajes: si el evento ya existe ligado a otra entrega, se rechaza con `409`.
- **El panel muestra el último acuse.** `GET /admin/staff/notifications/deliveries` añade `ack_status`, `ack_at` y `ack_detail` con el evento más reciente por `received_at` y luego `id`; la tarjeta «Correos del personal» suma la columna «ACUSE» con «Entregado», «Rebotado» o «Queja», su fecha y su detalle, y «Sin acuse» cuando todavía no llegó nada. Una entrega simulada o fallida nunca recibe acuse porque nunca salió a un proveedor.
- **El adaptador llega después.** El contrato es el que el club controla; conectar un proveedor real será traducir sus eventos a este JSON y firmar con el mismo secreto, sin tocar la tabla, el webhook ni el panel.

## Consecuencias y límites

- **No hay verificación de ventana temporal.** La firma cubre el cuerpo, no la fecha: un webhook capturado puede reenviarse mientras el secreto no cambie. Como el evento es idempotente y solo agrega filas, el impacto es acotado; rotar el secreto es manual.
- **El acuse no dispara acciones.** Ni reintentos ni avisos al remitente: el panel enseña el estado y la persona decide. El club no pidió automatizar rebotes.
- **Solo se acusa lo enviado.** Una entrega en cola o simulada no admite acuse, y una entrega fallida tampoco; si el proveedor responde por un mensaje que el club nunca envió, se rechaza.
- **El orden depende del proveedor.** El panel muestra el último evento por fecha de recepción; un `delivered` que llegue después de un `bounced` será el que se vea. Se conservan todos los eventos para auditar.
- **Sin retención definida.** Los acuses se guardan indefinidamente; purgarlos exigirá una política de retención como la del kiosco (ADR-040).
- **El secreto es del club.** `EMAIL_WEBHOOK_SECRET` vive en el entorno; no hay endpoint para generarlo ni rotarlo.

## Referencias

- `backend/src/app/modules/notifications/models.py` (`StaffNotificationDeliveryReceipt`, `message_id`)
- `backend/src/app/modules/notifications/receipts.py` (`parse_delivery_report`, `record_email_receipt`, `verify_signature`)
- `backend/src/app/modules/notifications/service.py` (`new_message_id`), `backend/src/app/mailer.py` (cabecera `Message-ID`)
- `backend/src/app/modules/notifications/delivery.py` (`_latest_receipts`, `ack_status`)
- `backend/src/app/main.py` (`email_delivery_webhook`)
- `backend/alembic/versions/20261031_0066_staff_email_delivery_receipts.py`
- `backend/tests/test_staff_email_receipts.py`
- `web/src/app/page.tsx` (columna «ACUSE» de «Correos del personal»)
