# ADR-058: Retención de los acuses de entrega del correo

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Cierra el límite de ADR-051 («Sin retención definida»)

## Contexto

`staff_notification_delivery_receipts` guarda lo que el proveedor de correo dice de un mensaje que ya salió: que el buzón lo aceptó, que la dirección rebotó o que el destinatario lo marcó como spam. La tabla es append-only y crece con cada reporte, mientras el panel solo lee **el más reciente por entrega** para pintar la columna «ACUSE». Un acuse viejo sirve para responder una disputa durante un tiempo razonable, no para siempre: a los tres meses nadie pregunta por la entrega de un aviso de asistencia, y las filas solo acumulan la dirección del destinatario y el detalle del proveedor.

ADR-051 dejó ese hueco anotado como límite —«los acuses se guardan indefinidamente; purgarlos exigirá una política de retención como la del kiosco»—. Este corte lo cierra con la misma forma que ADR-040: una política configurable, un script externo y ningún programador dentro de la aplicación.

## Decisión

- **Se purgan solo los acuses.** `staff_notification_delivery_receipts` se borra por antigüedad; `staff_notification_deliveries` y la bandeja del personal no se tocan. La entrega conserva lo que el club envió y a quién —es su registro del aviso—, y el acuse es la parte operativa que el proveedor puede repetir.
- **El corte se aplica sobre `received_at`.** La purga usa la fecha en que el club guardó el reporte, no el `occurred_at` que manda el proveedor: un evento con fecha vieja pero recibido ayer se conserva, y uno con fecha reciente pero almacenado hace meses se borra. La retención cuenta desde que el dato entró a la base, que es lo que el club controla.
- **La retención nunca es menor que la ventana del webhook.** `RECEIPT_MAX_AGE` (siete días, ADR-056) rechaza cualquier evento nuevo más antiguo que eso, así que con una retención de al menos siete días un acuse purgado **no puede volver** por un reintento tardío del mismo `provider_event_id`. El mínimo se importa de esa constante (`MIN_RETENTION_DAYS`), no se escribe aparte, y un valor menor se rechaza con un mensaje que explica el riesgo.
- **90 días por defecto, 1 a 3650 configurables.** `STAFF_RECEIPT_RETENTION_DAYS` o `--days` en una corrida puntual. Noventa días cubren una disputa de entrega de un trimestre sin guardar direcciones de correo más tiempo del necesario. El máximo coincide con el del kiosco (ADR-040) y un valor inválido no toca la base.
- **La purga es una tarea externa.** La lógica vive en `notifications.retention.purge_expired_receipts` y el punto de entrada es `backend/purge_email_receipts.py`, con las mismas banderas que el de accesos (`--preview`, `--database-url`, `--dry-run`, más `--days`). Se programa por cron junto al de accesos; no hay hilo ni tabla de trabajos.
- **Un índice por fecha de recepción.** El índice existente es `(delivery_id, received_at)` y no sirve para un corte global por fecha; la migración `20261031_0070` agrega `ix_staff_notification_delivery_receipts_received` para que el borrado recorra solo lo vencido.

## Consecuencias y límites

- **La traza de entrega deja de ser perpetua.** Pasados los 90 días el panel sigue mostrando el estado del envío, pero un acuse viejo ya no está: si el club necesitaba conservarlo más, debe subir la variable o archivar antes de la purga. La purga no sustituye al respaldo.
- **Un acuse purgado no se puede recuperar del proveedor.** Si se borra y el proveedor vuelve a reportar el mismo evento, la ventana de ADR-056 lo rechaza con `422`; no se reescribe la historia. Es el comportamiento buscado.
- **`ack_status` puede volver a «Sin acuse».** Una entrega cuya única recepción se purgó vuelve a mostrarse sin acuse, igual que un código del kiosco purgado vuelve a `none` (ADR-040). A los 90 días el panel ya no está mirando esa entrega.
- **No hay retención de las entregas ni de la bandeja.** `staff_notification_deliveries` y `staff_notifications` siguen creciendo sin purga; su retención es una decisión de negocio aparte, como la bitácora de accesos.
- **Actualización de ADR-075 (2026-10-31).** La retención de las entregas y de la bandeja ya existe: `backend/purge_inbox_data.py` poda los avisos leídos o cerrados y las entregas terminales del correo y del push web del personal. Esta ADR sigue purgando solo acuses, y un acuse vivo protege a su entrega del nuevo script. Esta nota sustituye al límite anterior.
- **No hay auditoría de la purga más allá del log.** El script imprime el corte y cuántas filas borró; el cron deja su salida en el archivo de log. No se escribe una fila de auditoría ni se registra quién cambió la retención.
- **La ventana de la tarea es diaria.** Entre dos corridas los acuses existen hasta un día más de lo configurado; irrelevante para el panel, que solo lee el último.
- **La retención es del club, no por proveedor.** Un solo valor para toda la tabla; si un proveedor concreto necesita más historia, se sube el global o se archiva fuera.

## Referencias

- `backend/src/app/modules/notifications/retention.py` (`purge_expired_receipts`, `receipt_retention_policy_from_env`, `ReceiptRetentionPolicy`, `ReceiptPurgeResult`, `MIN_RETENTION_DAYS`, `MAX_RETENTION_DAYS`)
- `backend/purge_email_receipts.py` (`--dry-run`, `--preview`, `--database-url`, `--days`)
- `backend/alembic/versions/20261031_0070_receipt_retention_index.py`
- `backend/tests/test_staff_receipt_retention.py` (13 pruebas)
- ADR-040 (retención de los datos del kiosco), ADR-051 (acuse de entrega), ADR-056 (ventana de tiempo del acuse)
- `docs/06-operacion/despliegue.md` (mantenimiento programado)
