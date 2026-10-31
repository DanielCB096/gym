# ADR-062: Acuses de entrega del push del socio

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Cierra el límite de ADR-052 y ADR-053 («solo el ticket de Expo, sin acuse de entrega»)

## Contexto

Un push `sent` solo dice que Expo **aceptó** el mensaje: el ticket que devuelve el envío no prueba que el teléfono lo recibiera. La respuesta de entrega llega después, atada a ese ticket, y el club hoy no la guarda: la cola del panel enseña el estado del envío y el error de transporte, pero no si el dispositivo llegó a tener el aviso.

ADR-051 resolvió esa mitad para el correo con un **webhook** que el proveedor empuja. Expo no ofrece webhook: publica los acuses por una API de consulta (`getReceipts`), así que la decisión es la misma —guardar el acuse al lado de la entrega, sin reescribir su estado— pero el camino es **pull**: una pasada pregunta por los tickets que la cola conservó.

## Decisión

- **El ticket del envío se conserva.** `member_push_deliveries` gana `expo_ticket_id` (hasta 100 caracteres), el identificador que Expo devuelve al aceptar; `send_expo_push` pasa a devolver un `PushSendResult` con su estado y su ticket, y la entrega lo guarda junto con el estado `sent`. Una entrega `pending`/`failed`/`simulated` no tiene ticket y nunca se le pregunta nada.
- **El acuse es una tabla aparte y append-only.** `member_push_delivery_receipts` guarda `delivery_id` (FK `RESTRICT`), `ticket_id`, `status` (`ok`/`error`/`expired`), `detail` (hasta 500) y `received_at`. El estado de la entrega **no se reescribe**: el acuse es información al lado de la cola, igual que ADR-051 y ADR-058.
- **Un acuse por entrega y uno por ticket.** Un ticket se responde una sola vez —entregado o con error— y Expo no cambia esa respuesta después, así que `delivery_id` y `ticket_id` son únicos. A diferencia del correo, no hay historial de eventos que el panel deba reducir al más reciente: la fila es la respuesta final. La excepción es `expired`, que registra que la pregunta ya no tendrá respuesta.
- **La pasada es de consulta, no de envío.** `sync_member_push_receipts(session, *, limit, now)` toma las entregas `sent` con ticket y sin acuse, respeta `receipt_checked_at` para no preguntar dos veces en quince minutos (`RECEIPT_RECHECK`), y manda los tickets a `POST /‑‑/api/v2/push/getReceipts` en un lote de 200 por defecto (máximo 1000, el tope de Expo). Un ticket que la respuesta no trae **aún no tiene acuse**: se marca la consulta y se deja para la siguiente pasada; no es un error.
- **A las 24 horas se registra `expired` sin preguntar.** Expo deja de conservar el acuse pasado ese plazo (`RECEIPT_EXPIRY`); una entrega más vieja se guarda como `expired` con su detalle y no se vuelve a consultar nunca. Es la única respuesta que el club puede dar por una entrega demasiado vieja.
- **Un `DeviceNotRegistered` en el acuse retira el dispositivo.** Si Expo responde con ese código, la misma pasada desactiva el token del socio —la misma acción que ya hace el envío (ADR-052)— y lo cuenta en `deactivated`.
- **Un fallo de la consulta no inventa acuses.** Si Expo no responde, responde `5xx` o devuelve un cuerpo ilegible, la pasada lanza `PushReceiptsFailed` sin escribir nada: los tickets siguen sin acuse, sin `receipt_checked_at` y se reintentan en la siguiente pasada. El backend traduce el fallo a `502`.
- **Se ejecuta en dos sitios, como el resto del proyecto.** `POST /admin/notifications/push-deliveries/receipts` (con `attendance.manage`) corre la pasada bajo demanda desde la tarjeta «Push del socio», y `backend/sync_push_receipts.py` la corre por cron con `--preview`, `--database-url` y `--limit`, igual que `purge_email_receipts.py`. No hay worker ni hilo.
- **La vista previa difiere sin contactar a Expo.** `PREVIEW_MODE=true` simula los envíos y nunca acumula tickets, así que la pasada devuelve `deferred: true` con el número de entregas `sent` con ticket que encontraría una pasada real, sin hacer red.
- **El panel muestra el acuse.** El listado `GET /admin/notifications/push-deliveries` une la entrega con su acuse y publica `receipt_status`, `receipt_detail` y `receipt_at`; la tarjeta suma la columna «ACUSE» —«Entregado» con su hora, «Con error» con el detalle, «Caducado», «Sin acuse» para una entrega `sent` sin respuesta o «—»— y el botón «Consultar acuses» para no esperar a la pasada programada.
- **Sin cambio de permisos.** La consulta de acuses usa `attendance.manage`, el mismo permiso que ya exigía enviar o reintentar la cola; leerlos dentro del listado sigue pidiendo `attendance.read`. No hay permiso nuevo.

## Consecuencias y límites

- **`sent` sigue significando «Expo lo aceptó».** El acuse no es un quinto estado de la entrega: una fila `sent` con acuse `error` sigue contando como enviada en los conteos y en el reintento, que solo acepta `failed`. El acuse es información aparte, como en ADR-051.
- **Un acuse `error` no reintenta por sí solo.** Retirar un dispositivo desinstalado ya está; un error de otro tipo (por ejemplo un payload rechazado) queda a la vista del operador, pero no cambia el estado ni vuelve a encolar el aviso. El push del socio sigue siendo at-least-once en la cola, no en el acuse.
- **El club no pregunta por un ticket cuya respuesta ya guardó.** Si el acuse llegó `ok`, no hay segunda consulta; si llegó `error`, tampoco. Es un registro final, no una cola de eventos.
- **No hay retención definida todavía.** Las filas de acuse son una por entrega enviada, más pequeñas que la propia entrega; purgarlas tiene sentido solo junto con una retención de `member_push_deliveries`, que sigue sin política. La decisión queda anotada como límite, no implementada.
- **La pasada depende de que alguien la dispare.** Sin worker, si nadie abre la tarjeta ni corre el cron, los acuses esperan; a las 24 horas de todos modos quedan `expired`. La tecnología es la del resto del proyecto (ADR-052).
- **Un ticket no se puede reconstruir.** Una entrega que ya estaba `sent` antes de esta migración no tiene `expo_ticket_id` y nunca tendrá acuse; el panel la muestra «—». No se inventan tickets retroactivos.
- **Actualización de ADR-074 (2026-10-31).** El límite de retención queda cerrado: `backend/purge_push_data.py` borra los acuses por `received_at` (90 días por defecto) y las entregas terminadas por `created_at` (365 días por defecto), nunca una `pending` ni una entrega cuyo acuse siga vivo, y `ops_cron.py` lo programa como tercera purga diaria. Sin migración.
- **La consulta es una llamada externa más.** El lote acota el costo (200 por defecto), pero un fallo de red al consultar no afecta a los envíos: la cola sigue como estaba y la pasada se puede repetir.
- **La vista previa no demuestra el acuse real.** Simular un envío no produce ticket; para ver «Entregado» en una demo hacen falta filas sintéticas o una instancia real contra Expo, como ya pasa con el push.

## Referencias

- `backend/src/app/modules/notifications/push_receipts.py` (`sync_member_push_receipts`, `fetch_expo_receipts`, `PushReceiptPass`, `PushReceiptsFailed`, `RECEIPT_EXPIRY`, `RECEIPT_RECHECK`, `MAX_RECEIPT_BATCH`)
- `backend/src/app/modules/notifications/push.py` (`PushSendResult`, `expo_ticket_id`, el acuse en `MemberPushDeliveryItem` y el join del listado)
- `backend/src/app/modules/notifications/models.py` (`MemberPushDeliveryReceipt`, `PUSH_RECEIPT_STATUSES`)
- `backend/alembic/versions/20261031_0072_member_push_receipts.py`
- `backend/sync_push_receipts.py` (`--preview`, `--database-url`, `--limit`)
- `backend/src/app/main.py` (`POST /admin/notifications/push-deliveries/receipts` con `attendance.manage`)
- `web/src/app/page.tsx` (columna «ACUSE» y botón «Consultar acuses»)
- `backend/tests/test_member_push_receipts.py` (11 pruebas)
- ADR-051 (acuse de entrega del correo), ADR-052 (push del socio), ADR-053 (cola de push en el panel), ADR-054 (reintento automático), ADR-058 (retención de acuses del correo)
