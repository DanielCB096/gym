# ADR-048: Cola de correos de los avisos de asistencia y su interruptor de club

- Fecha: 2026-10-30
- Estado: propuesta inicial

## Contexto

El ciclo de asistencia habla solo por la campana del panel: al colaborador cuya marca se corrigió o anuló, al supervisor con una solicitud esperando y al dueño con una solicitud vencida les llega un aviso en `staff_notifications` que solo ven si abren el panel. El club pidió que esos avisos también salgan por correo. El transporte ya existe —`app.mailer.send_email`, con configuración SMTP por entorno y modo simulado en la vista previa—, pero enviar desde el camino de la marca acoplaría la transacción del dominio a la red: un SMTP lento no debe mantener abierta la transacción que registra la corrección, y un fallo del correo no debe revertirla.

El primer corte que se aprobó separa las dos partes que tienen que ser transaccionales del envío, que vendrá después: el **esquema** (una entrega por aviso, el estado del envío y el interruptor del club) y el **encolado** (escribir la entrega junto con el aviso, sin contactar al servidor). Este ADR documenta el diseño completo del incremento y este primer corte.

## Decisión

- **Una tabla de entregas, una fila por aviso.** `staff_notification_deliveries` guarda `notice_id` (FK `RESTRICT` a `staff_notifications`), `recipient` —la dirección copiada al emitir—, `status` (`pending`, `sent`, `simulated`, `failed`), `attempts` (no negativo), `error`, `last_attempt_at`, `sent_at` y `created_at`. La unicidad `uq_staff_notification_deliveries_notice` impide dos entregas para el mismo aviso y el índice `(status, created_at)` es el que usará el envío para tomar lo pendiente por antigüedad. `simulated` se reserva para la vista previa, igual que `send_email` ya distingue «simulated» en su respuesta.
- **Se encola en el único punto de escritura.** `create_staff_notification` es la función por la que pasan todos los avisos del personal, así que la entrega se crea ahí, dentro de la misma transacción: un cambio revertido no deja correo que enviar y uno confirmado no puede olvidar el suyo. Solo se encola cuando el aviso es **nuevo** —`_append` devuelve el aviso que ya existía cuando la clave de dedupe coincide—, de modo que un reintento idempotente de la marca no encola un segundo correo.
- **Solo el ciclo de asistencia sale hoy.** `STAFF_NOTIFICATION_EMAIL_KINDS` enumera los seis tipos del ciclo (`attendance_corrected`, `attendance_voided`, `attendance_request_pending`, `attendance_request_approved`, `attendance_request_rejected`, `attendance_request_overdue`). Los demás avisos del personal se quedan en la campana hasta su propio corte, y añadir uno es una línea en esa tupla.
- **El destinatario es la cuenta, no el expediente.** El correo va a la dirección de la cuenta activa del panel a la que apunta el aviso (`app_users.email`), que es la que ya usa el aviso, no el correo del expediente del colaborador. Si la cuenta no existe, está deshabilitada o no tiene dirección, el aviso se escribe igual y no se encola nada: el canal es un extra, no un requisito del aviso.
- **Interruptor del club, apagado por olvido no.** `staffing_settings.attendance_email_enabled` (booleano, `true` por defecto) decide si los avisos del ciclo se encolan. Se edita con el mismo `PATCH /admin/staff/settings`, queda auditado con `previous_attendance_email_enabled`/`attendance_email_enabled` en `staffing_settings_events` y el campo del `PATCH` es opcional: omitirlo conserva el valor guardado, así que un cliente anterior no lo apaga ni lo enciende sin querer. Sin fila de configuración vale `true`, igual que el resto de la política.
- **Se envía después, nunca dentro de la transacción.** Este corte no llama a `send_email`: la entrega nace `pending`, con `attempts = 0` y sin fecha de intento. El corte de envío leerá las pendientes por `(status, created_at)`, intentará una vez por pasada, escribirá `sent`/`simulated`/`failed` con su error y ofrecerá el reintento; la tarjeta de entregas en el panel y la documentación llegan con él. `sent` significará que el servidor SMTP aceptó el mensaje, no que haya llegado a la bandeja.
- **La cola ya escrita no se borra al apagar el interruptor.** Apagar detiene las entregas nuevas; las que ya esperan se quedan y el corte de envío decidirá si respeta el interruptor en el momento de enviar. Como todavía no hay envío, hoy no hay diferencia observable.
- **La reversión de la migración se niega con cola.** `20261031_0065` quita la tabla y las tres columnas al revertir, pero solo si no existe ninguna entrega: perder la cola en silencio sería peor que negarse con un mensaje. La vista previa reproduce las columnas en `preview_patch.py`; la tabla nueva la crea `create_all` al arrancar.

## Consecuencias y límites

- **Nadie recibe correo todavía.** Este corte deja el esquema y la cola; el correo sale cuando llegue el envío. El interruptor ya se puede apagar desde la API y su cambio queda auditado.
- **Un aviso puede quedar sin entrega.** Una cuenta deshabilitada en el momento del aviso no recibe correo aunque se reactive después; la fila no se crea, porque el destinatario se congela al emitir y no se reintenta resolver. Si se quiere cubrir ese hueco, será con una política explícita en el corte de envío.
- **El destinatario es una foto.** Editar la dirección de la cuenta después no reescribe las entregas ya encoladas; cambiar la dirección de una cuenta no reenvía lo pendiente a la nueva.
- **La aprobación no duplica.** Aprobar una solicitud escribe el aviso de la decisión —no el de corrección, que el camino de aprobación silencia con `notify_employee=False`—, así que el colaborador recibe un correo por decisión y no dos por el mismo cambio.
- **La cola no es un registro de intenciones.** Un aviso resuelto o leído no cancela su entrega pendiente: el correo cuenta lo que pasó en el momento del aviso, igual que el texto congelado de la campana.

## Referencias

- `backend/src/app/modules/notifications/models.py` (`StaffNotificationDelivery`, `STAFF_NOTIFICATION_EMAIL_KINDS`)
- `backend/src/app/modules/notifications/service.py` (`create_staff_notification`, `_enqueue_staff_notification_email`)
- `backend/src/app/modules/staffing/models.py`, `backend/src/app/modules/staffing/service.py` (`read_attendance_email_enabled`, `update_staffing_settings`)
- `backend/alembic/versions/20261031_0065_staff_notification_deliveries.py`
- `backend/preview_patch.py` (`ensure_added_columns`)
- `backend/tests/test_attendance_requests.py`, `backend/tests/test_preview_patch.py`
- `docs/05-decisiones/ADR-044-avisos-solicitudes-y-auditoria-de-politica.md`, `docs/05-decisiones/ADR-045-plazo-y-escalado-de-solicitudes.md`
