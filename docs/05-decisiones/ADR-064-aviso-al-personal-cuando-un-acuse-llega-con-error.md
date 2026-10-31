# ADR-064: Aviso al personal cuando el acuse del push llega con error

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Cierra el límite de ADR-062 («un acuse con error no alerta»)

## Contexto

ADR-062 guardó la respuesta de Expo junto a cada entrega: `ok` cuando el teléfono recibió el aviso, `error` cuando el servicio lo rechazó y `expired` cuando la pregunta ya no tendrá respuesta. El acuse `error` quedaba a la vista del operador en la columna «ACUSE» de la tarjeta «Push del socio», pero nadie se enteraba si no abría el panel: el socio tenía el aviso en su bandeja, el teléfono no sonó y el club no lo sabía.

Los dos extremos no son iguales. Un `ok` cierra el ciclo y no pide nada; un `expired` tampoco es una falla —Expo dejó de conservar la respuesta—. `DeviceNotRegistered` ya lo cubre ADR-052: es el retiro esperado de una app desinstalada, la pasada retira el token y alertar sería ruido. Un `error` de otro tipo (payload rechazado, credenciales del proyecto, un límite del servicio) sí es trabajo para quien opera la cola, y hasta ahora era invisible.

La infraestructura para avisar existe desde ADR-055: `create_staff_notification` escribe la campana y la entrega de correo en la misma transacción, y la audiencia se resuelve con `user_ids_with_permission(..., "attendance.manage")`.

## Decisión

- **Un tipo de aviso nuevo.** `ck_staff_notifications_kind` suma `member_push_receipt_failed` (migración `20261031_0073_member_push_receipt_failed_kind.py`; `preview_patch.py` encadena el mismo salto). Entra en `STAFF_NOTIFICATION_KINDS`, así que también viaja por correo y el panel lo rotula «Avisos · acuse con error».
- **Solo un error accionable alerta.** La pasada escribe el aviso cuando el acuse llega `error` **y** el código no es `DeviceNotRegistered`; `ok`, `expired` y el dispositivo desinstalado siguen en silencio. Es la misma regla de ADR-055: se avisa de lo que alguien puede corregir, no de lo que ya se resolvió solo.
- **La audiencia es la de la cola.** El aviso va a las cuentas activas con `attendance.manage` —las que abren la tarjeta y pueden actuar—, no a un rol nominal. Se deduplica por `member_push_receipt_failed:{entrega}:{cuenta}`, con `ref_id` a la entrega, así que una pasada repetida sobre el mismo ticket no escribe dos veces la misma alerta.
- **El texto dice qué falló y dónde mirar.** Título «Acuse de push con error»; cuerpo con el socio, el título del aviso, el código y el mensaje de Expo recortados y la indicación de revisar la tarjeta «Push del socio» de la pestaña Equipo. El correo hereda el prefijo `[Avisos] ` y la misma ubicación que el aviso de push agotado.
- **El acuse se guarda primero.** La pasada confirma los acuses de Expo y solo después escribe los avisos: un problema al crear una alerta no puede costar la respuesta que el servicio ya dio. Cada alerta se confirma por su cuenta, como en ADR-055.
- **La alerta se envía por donde pasa la pasada.** El endpoint del panel usa `AttendanceEmailFlush`, así que el correo sale después de la respuesta; `backend/sync_push_receipts.py` drena la cola de correos al terminar su corrida, porque el cron no tiene una respuesta donde colgarla. La vista previa difiere la pasada completa, así que tampoco alerta.

## Consecuencias y límites

- **No hay reintento del push por un acuse con error.** La entrega sigue `sent` y el aviso no se vuelve a encolar; el acuse es información al lado de la cola (ADR-062). El operador decide si reenvía desde la tarjeta.
- **El aviso puede llegar tarde.** La pasada corre por cron cada 30 minutos o cuando alguien pulsa «Consultar acuses»; entre el envío y la alerta puede pasar una ventana, y hasta 24 horas si Expo tarda en responder.
- **Una alerta por entrega y cuenta.** Corregir el problema no la cierra sola: queda en la campana como historial hasta que se marca leída, igual que el resto de los avisos del personal. No hay estado «resuelto» ligado al acuse.
- **El mensaje de Expo se recorta.** El detalle guardado admite 500 caracteres y el cuerpo de la alerta usa una versión corta; un error con mucha información pierde el resto.
- **Depende del interruptor de correo del club.** Con `attendance_email_enabled` apagado la campana recibe el aviso pero no se envía el correo; la fila queda `pending` hasta volver a encenderlo (ADR-048, ADR-049).
- **Sin tabla ni columna nuevas.** El cambio de esquema es el `CHECK` de tipos; el downgrade se niega mientras existan avisos de este tipo, como en ADR-055.
- **El dispositivo desinstalado sigue siendo silencioso.** Retirar el token ya deja el panel en el estado correcto; avisar además convertiría cada desinstalación en una notificación que nadie puede atender.

## Referencias

- `backend/src/app/modules/notifications/push_receipts.py` (`_alert_receipt_error`)
- `backend/src/app/modules/notifications/models.py` (`STAFF_NOTIFICATION_KINDS`, `ck_staff_notifications_kind`)
- `backend/alembic/versions/20261031_0073_member_push_receipt_failed_kind.py`
- `backend/src/app/modules/notifications/delivery.py` (`SUBJECT_PREFIXES`, `NOTICE_LOCATIONS`)
- `backend/src/app/main.py` (endpoint de acuses con `AttendanceEmailFlush`), `backend/sync_push_receipts.py`
- `backend/tests/test_member_push_receipts.py` (15 pruebas)
- `web/src/app/page.tsx` (etiqueta del tipo)
- ADR-048 y ADR-049 (cola y envío del correo del personal), ADR-055 (aviso de push agotado), ADR-062 (acuses de entrega del push)
