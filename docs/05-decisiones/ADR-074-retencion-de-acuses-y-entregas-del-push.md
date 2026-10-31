# ADR-074 · Retención de los acuses y de las entregas terminadas del push

- **Fecha:** 2026-10-31
- **Estado:** propuesta inicial
- **Cierra el límite (3) de ADR-062** («sin retención: una fila por entrega enviada, pero la tabla y `member_push_deliveries` siguen creciendo sin purga»).

## Contexto

ADR-062 dejó el acuse del push del socio en `member_push_delivery_receipts`, una fila por entrega con la respuesta de Expo, y el panel solo lee el acuse más reciente de cada entrega. Las entregas (`member_push_deliveries`) también crecen con cada aviso y cada token activo. Hasta hoy ninguna de las dos tablas se podaba: el volumen es bajo, pero crece sin techo y el despliegue no tenía forma de acordar una retención.

La operación ya estrena un patrón para esto: `purge_access_data.py` (ADR-040) y `purge_email_receipts.py` (ADR-058) borran por fecha de corte, son idempotentes, aceptan `--preview` y `--dry-run` y `ops_cron.py` las programa en el mismo bloque idempotente (ADR-063).

## Decisión

- **Un script propio, `backend/purge_push_data.py`**, con dos ventanas independientes y una sola corrida: los acuses primero, las entregas terminadas después. Comparte banderas con las otras purgas (`--preview`, `--database-url`, `--dry-run`) y añade `--receipt-days` y `--delivery-days` para una corrida puntual.
- **Los acuses se cuentan desde `received_at`**, el reloj del club al guardar la respuesta, no desde el ticket ni desde la entrega: un acuse que llega tarde se conserva desde que llega. La retención por defecto es de **90 días** (`PUSH_RECEIPT_RETENTION_DAYS`), entre 1 y 3650. El mínimo es de un día porque la pasada de acuses pregunta el ticket dentro de las 24 horas y una purga más corta podría borrar la respuesta antes de que el panel la lea; no hay webhook externo, así que no aplica el mínimo de siete días de ADR-058.
- **Las entregas se cuentan desde `created_at` y solo si están terminadas** (`sent`, `simulated` o `failed`): `pending` es la cola y no se toca. La retención por defecto es de **365 días** (`PUSH_DELIVERY_RETENTION_DAYS`), entre 1 y 3650.
- **Una entrega con acuse vivo no se borra.** La clave foránea del acuse es `RESTRICT`; si la ventana de acuses fuera más larga que la de entregas, borrar la entrega dejaría el acuse huérfano o fallaría. La purga de entregas excluye con `NOT EXISTS` a las que aún tienen un acuse, así que configurar ventanas cruzadas no rompe la corrida ni pierde la respuesta: la entrega espera a que su acuse se purgue.
- **No hay migración.** `ix_member_push_delivery_receipts_received` (ADR-062) e `ix_member_push_deliveries_status_created` ya cubren las dos búsquedas.
- **Se programa con el bloque de ADR-063.** `ops_cron.py` pasa a seis entradas: la purga del push corre a las `04:15` por defecto, treinta minutos después de la del correo y sesenta después de la de accesos, derivada de `--daily-at` con el mismo escalonado; escribe `purge-push.log` y `--install` exige también `purge_push_data.py`.
- **Idempotente y honesta en los códigos de salida.** Una segunda corrida borra `0`; sin URL el script sale con código 2, una configuración inválida con 2 y una base inalcanzable con 1. `--dry-run` cuenta sin borrar y `--preview` crea el esquema en `gym_preview.db` y no contacta a nadie.

## Consecuencias y límites

- **La retención es una decisión operativa, no legal.** El club debe fijar las dos ventanas según cuánto quiera conservar la evidencia de entrega; una ventana menor ahorra espacio pero borra el acuse de una disputa.
- **Solo poda lo terminado.** Un `pending` antiguo no se toca: si la cola se quedó detenida, la purga no la limpia, y hacerlo exigiría una decisión distinta sobre entregas atascadas.
- **La purga no reescribe el estado de la entrega ni la bandeja.** Borra acuses y entregas terminadas; la tabla `member_notifications` y el historial del token quedan intactos.
- **Depende del cron del host.** Sin `ops_cron.py` instalado, la retención es una capacidad del script y no una tarea que ocurra sola; la bitácora `purge-push.log` es la única señal de fallo.
- **No hay retención de `staff_push_deliveries` ni de las notificaciones.** Esta decisión solo cubre las dos tablas del push del socio; el push web del personal y las bandejas siguen creciendo sin poda.

## Referencias

- ADR-052 (push del socio), ADR-062 (acuses de Expo), ADR-058 (retención de los acuses del correo), ADR-040 (retención del kiosco), ADR-063 (cron de operación).
- Implementación: `app/modules/notifications/push_retention.py`, `backend/purge_push_data.py`, `backend/ops_cron.py`.
- Pruebas: `backend/tests/test_push_retention.py` (17 casos) y `backend/tests/test_ops_cron.py` (32).
