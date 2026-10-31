# ADR-075 · Retención de la bandeja de avisos y de las entregas del personal

- **Fecha:** 2026-10-31
- **Estado:** propuesta inicial
- **Cierra el pendiente «retención de la bandeja de avisos y del push web del personal»** del módulo de notificaciones y revisa el límite de ADR-058 («las entregas y la bandeja no se tocan»).

## Contexto

Las dos bandejas crecen con cada evento del club: `member_notifications` guarda un aviso por cada reserva, factura, rutina revisada o recordatorio, y `staff_notifications` uno por cada ticket, solicitud de asistencia o aviso de la cola. A su lado, cada aviso del personal deja una entrega de correo (`staff_notification_deliveries`) y una de push web por navegador (`staff_push_deliveries`).

ADR-058 podó los acuses del correo y ADR-074 los acuses y las entregas del push del socio, pero las bandejas y las dos colas del personal seguían sin retención. El lector solo ve una página de veinte filas, así que el historial viejo ya no se consulta y solo ocupa espacio. El push del socio ya tiene su purga; faltaba la del personal y la de los avisos que las dos colas referencian.

La operación ya tiene el patrón: un script por tabla o familia de tablas, ventanas por entorno con bandera de una corrida, `--dry-run`, `--preview`, código de salida 2 para una configuración inválida y 1 para una base inalcanzable, y el bloque idempotente de `ops_cron.py` (ADR-040, ADR-058, ADR-063, ADR-074).

## Decisión

- **Un script propio, `backend/purge_inbox_data.py`**, con una corrida y dos ventanas independientes: la bandeja y las entregas. Borra primero las entregas y luego los avisos, porque las claves foráneas de aviso son `RESTRICT` y el orden inverso fallaría.
- **La ventana de la bandeja es de 365 días por defecto** (`NOTIFICATION_INBOX_RETENTION_DAYS` o `--inbox-days`), entre 30 y 3650. El mínimo de un mes evita que un valor pequeño borre avisos que el club todavía consulta; el máximo de diez años deja margen para una política conservadora.
- **Solo se borra el aviso que ya no tiene trabajo pendiente.** Del socio, el que fue leído; del personal, el que está cerrado: `resolved_at` si era accionable (`workout_pending_review`, `attendance_request_pending`, `attendance_request_overdue`) o `read_at` si solo informaba. Un aviso sin leer del socio y una tarea sin resolver del panel son la bandeja misma y nunca son candidatos, por viejos que sean.
- **La advertencia del token del kiosco no se poda nunca.** Es un aviso del personal que se materializa al abrir la bandeja, deduplicado por dispositivo, fecha de vencimiento y cuenta (ADR-028); si se borrara mientras el dispositivo conserva ese token vencido, el mismo aviso volvería a escribirse. Es una fila por dispositivo y fase, no el grueso del crecimiento.
- **La ventana de las entregas del personal es de 365 días por defecto** (`STAFF_DELIVERY_RETENTION_DAYS` o `--delivery-days`), entre 1 y 3650, y solo alcanza a las terminadas (`sent`, `simulated` o `failed`). `pending` es la cola del correo o del push y se queda; el reintento manual del panel sigue encontrando lo que falta enviar.
- **Un aviso no se borra mientras lo apunte una entrega, y una entrega no se borra mientras la apunte un acuse.** Las dos condiciones usan `NOT EXISTS` como ADR-074: la entrega de correo o de push se borra primero, y en la misma corrida el aviso queda libre; si el acuse sobrevive a la ventana de su propia purga (ADR-058), la entrega espera y su aviso también, y la siguiente corrida después de que el acuse venza los alcanza. Configurar ventanas cruzadas no rompe ninguna clave foránea ni pierde un acuse.
- **No hay migración.** `ix_member_notifications_member_time`, `ix_staff_notifications_user_time`, `ix_staff_notification_deliveries_status_created` e `ix_staff_push_deliveries_status_created` ya cubren las cuatro búsquedas.
- **Séptima entrada del bloque de cron.** `ops_cron.py` programa la purga a las `04:45` por defecto, treinta minutos después de la del push y noventa después de la de accesos, derivada de `--daily-at` con el mismo escalonado. Escribe `purge-inbox.log` y `--install` exige también `purge_inbox_data.py`. El orden importa: la purga del push del socio (ADR-074) corre antes y libera las entregas del socio que esta purga necesita para borrar sus avisos.
- **Idempotente y honesta en los códigos de salida.** Una segunda corrida borra `0`; sin URL el script sale con código 2, una configuración inválida con 2 y una base inalcanzable con 1. `--dry-run` cuenta sin borrar y `--preview` crea el esquema en `gym_preview.db` y no contacta a nadie.

## Consecuencias y límites

- **La retención es una decisión operativa, no legal.** El aviso es una copia del mensaje, no el registro del evento —el evento sigue en su tabla—, pero el club debe fijar la ventana según cuánto quiera conservar el historial de la bandeja. Una ventana corta ahorra espacio y borra el contexto que un socio o un colaborador podría reclamar.
- **No es un archivado.** No hay exportación ni respaldo de los avisos que se borran; si el club necesita conservarlos, debe copiarlos antes de la ventana.
- **Las filas con acuse o entrega viva se quedan.** Una ventana de acuses más larga que la de entregas, o una de entregas más larga que la de la bandeja, retrasa el borrado hasta que la fila que bloquea desaparezca; no hay una segunda pasada forzada.
- **No poda los tokens ni las suscripciones.** Las tablas `member_push_tokens` y `staff_push_subscriptions` conservan su historial de dispositivos; esta decisión solo cubre avisos y entregas.
- **Depende del cron del host.** Sin `ops_cron.py` instalado, la retención es una capacidad del script y no una tarea que ocurra sola; la bitácora `purge-inbox.log` es la única señal de fallo.
- **El push del socio y su acuse tienen otra purga.** Esta no toca `member_push_deliveries` ni sus acuses (ADR-074); su orden en el cron es lo que permite que el aviso del socio quede libre en la misma noche.

## Referencias

- ADR-016 y ADR-017 (bandejas del socio y del personal), ADR-028 (aviso del token del kiosco), ADR-040 (retención del kiosco), ADR-058 (acuses del correo), ADR-070 y ADR-071 (push web del personal), ADR-074 (retención del push del socio), ADR-063 (cron de operación).
- Implementación: `app/modules/notifications/inbox_retention.py`, `backend/purge_inbox_data.py`, `backend/ops_cron.py`.
- Pruebas: `backend/tests/test_inbox_retention.py` (26 casos) y `backend/tests/test_ops_cron.py` (32).
