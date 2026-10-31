# ADR-055: Aviso al personal cuando un push del socio se agota

- Fecha: 2026-10-30
- Estado: propuesta inicial
- Extiende ADR-052, ADR-053 y ADR-054 (push del socio, su cola y su reintento automático)

## Contexto

ADR-054 dejó la pasada reintentando sola y marcando «Sin reintentos» cuando se acaban los tres intentos, pero el aviso seguía cayendo en un agujero: la fila quedaba `failed` en una tarjeta que nadie miraba, el socio tenía el aviso en su bandeja y el teléfono nunca sonó. Un fallo que sobrevive a los tres intentos ya no es pasajero —suele ser un token roto, una cuota del proveedor o un cambio de configuración— y el club necesita enterarse sin abrir la pestaña por casualidad.

## Decisión

- **Un tipo de aviso nuevo del personal: `member_push_failed`.** Se suma a `STAFF_NOTIFICATION_KINDS` y al `CHECK` de `staff_notifications` (migración `20261031_0069`), así que entra por la campana y por la bandeja como cualquier otro aviso del personal.
- **La audiencia es quien opera la cola.** `_alert_exhausted_push` escribe un aviso por cada cuenta activa con `attendance.manage` —`user_ids_with_permission`— y ninguno más: es el mismo permiso que exige la tarjeta «Push del socio», así que quien recibe el aviso es quien puede reintentar o revisar el token. Un rol con solo `attendance.read` lee la cola pero no recibe el aviso.
- **Solo se avisa cuando se agotan los intentos.** La alerta se escribe en la rama final de `_schedule_retry`, con `attempts >= MAX_PUSH_ATTEMPTS`; los intentos programados, el primer fallo y las filas pendientes no avisan. Un dispositivo desinstalado tampoco: `DeviceNotRegistered` retira el token y ya no hay trabajo que hacer con esa fila.
- **Una vez por entrega y por cuenta.** La clave es `member_push_failed:{delivery_id}:{user_id}`. Reintentar a mano una fila ya agotada y volver a fallar no repite el aviso, y un segundo dispositivo del mismo aviso es una fila distinta que sí avisa por su cuenta. `ref_id` guarda la entrega, de modo que el aviso se puede rastrear hasta la fila de la cola.
- **El texto dice qué, a quién y cuántas veces.** Título «Push del socio sin entregar» y cuerpo con el título del aviso original, el nombre del socio, el total de intentos y el último error truncado, más la ubicación de la tarjeta. Nada se recalcula después: el aviso es un retrato del momento del agotamiento.
- **El correo sale con el resto del canal del personal.** `member_push_failed` entra en `SUBJECT_PREFIXES` con `[Avisos] ` y en `NOTICE_LOCATIONS` con la tarjeta «Push del socio» de la pestaña Equipo, y respeta el interruptor del correo del personal: si está apagado, se escribe el aviso pero no la entrega de correo (ADR-048–ADR-050).
- **La pasada de fondo también vacía el correo.** Hasta ahora el correo del personal se encolaba al escribir el aviso y salía en la pasada que dispara la respuesta; el push corre después de la respuesta, así que nadie la habría disparado. `send_pending_member_push_deliveries_from_engine` ejecuta la pasada de correo al terminar, y los dos endpoints del panel (`POST …/send` y `…/retry`) la encolan como tarea de fondo. El correo del aviso sale sin esperar a otra petición.
- **El panel pone nombre al tipo.** `member_push_failed` se muestra como «Avisos · push sin entregar» en la cola del correo del personal y en la campana.

## Consecuencias y límites

- **El aviso es de la fila, no del aviso del socio.** Si el mismo aviso falla en tres dispositivos, el personal recibe tres avisos distintos; agruparlos exigiría una clave por notificación y perdería el detalle de qué token falló.
- **Una cuenta nueva no ve el pasado.** El aviso se escribe para quien tenía `attendance.manage` en el momento del agotamiento; conceder el permiso después no crea avisos retroactivos.
- **El correo hereda los límites de ADR-051.** Sin proveedor real solo hay `simulated`, y el acuse de entrega depende de que el proveedor lo envíe.
- **No cambia el estado de la entrega.** La fila sigue `failed` y el reintento manual sigue disponible; el aviso es una señal, no una transición.
- **Sigue sin haber planificador.** El aviso se escribe cuando la pasada agota la fila; si nadie provoca una pasada, la fila se queda con reintentos programados y no se agota, así que tampoco avisa. Es el mismo límite de ADR-054.
- **El interruptor del correo apaga el correo, no la campana.** Con el canal apagado el aviso se ve en el panel y no sale por correo, porque la fila de entrega no se crea.

## Referencias

- `backend/src/app/modules/notifications/push.py` (`_alert_exhausted_push`, `FAILURE_ALERT_PERMISSION`, `send_pending_member_push_deliveries_from_engine`)
- `backend/src/app/modules/notifications/models.py` (`STAFF_NOTIFICATION_KINDS`)
- `backend/src/app/modules/notifications/service.py` (`create_staff_notification`)
- `backend/src/app/modules/notifications/delivery.py` (`SUBJECT_PREFIXES`, `NOTICE_LOCATIONS`)
- `backend/alembic/versions/20261031_0069_member_push_failed_kind.py`
- `backend/preview_patch.py` (CHECK de la vista previa)
- `backend/src/app/main.py` (pasada de correo tras enviar o reintentar desde el panel)
- `backend/tests/test_member_push.py`, `backend/tests/test_member_push_admin.py`, `backend/tests/test_attendance_email_delivery.py`, `backend/tests/test_preview_patch.py`
- `web/src/app/page.tsx`
- `docs/05-decisiones/ADR-052-push-del-socio-desde-la-app.md`, `ADR-053-cola-de-push-del-socio-en-el-panel.md`, `ADR-054-reintento-automatico-del-push-del-socio.md`
