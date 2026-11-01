# ADR-081: Correo de avisos del socio

- **Fecha:** 2026-10-31
- **Estado:** aceptada
- **Relacionada con:** ADR-016 (bandeja del socio), ADR-052 (push del socio), ADR-059 (preferencias por categoría), ADR-075 (retención) y ADR-079 (cola de correo).

## Contexto

La app conserva los avisos del gimnasio en la bandeja y ya puede enviarlos por push. Algunos socios quieren recibir por correo ciertos avisos, pero el consentimiento debe ser explícito, independiente del push y revocable por categoría. Los mensajes pueden incluir información de membresía, pagos, clases o fisioterapia; no deben enviarse por defecto ni a una dirección que haya cambiado desde que se encoló el aviso.

## Decisión

- **Correo apagado por defecto y separado del push.** `member_notification_preferences.email_enabled` solo se activa cuando el socio autenticado cambia expresamente el interruptor en la app. Una fila ausente significa `email_enabled = false`; el valor de `push_enabled` no se altera al cambiar correo.
- **Cinco categorías habilitadas.** Solo `membership`, `classes`, `billing`, `equipment` y `physio` admiten correo. `training` (rutinas y metas) permanece únicamente en la bandeja y puede conservar su preferencia de push.
- **Dirección disponible antes del opt-in.** La app recibe `email_available` como indicador booleano, nunca la dirección; si no hay una dirección en el perfil, deshabilita el interruptor y explica cómo resolverlo. El backend también rechaza el opt-in sin correo.
- **Consentimiento auditable.** Cada cambio real de `email_enabled` escribe una fila append-only en `member_notification_email_preference_events` con socio, categoría, estado y versión del texto de consentimiento. Una repetición sin cambio no crea evento. El historial no incluye el cuerpo de los avisos ni la dirección.
- **Una entrega por aviso.** Al crear un aviso nuevo, la misma transacción encola `member_notification_email_deliveries` únicamente si la categoría está habilitada y existe correo. Se conserva una instantánea del destinatario y un `Message-ID`; el aviso sigue en la bandeja aunque no tenga entrega o el correo falle.
- **Envío inmediato fuera de la transacción.** Las rutas que crean avisos ejecutan la pasada después de responder. El cron de avisos diferidos también drena el correo en la misma corrida. `backend/flush_member_email.py` recupera pendientes y reintentos si el proceso cayó; el cron lo ejecuta cada 15 minutos por defecto.
- **Reintento automático limitado.** Un fallo queda auditado y se reintenta hasta completar cinco intentos, con espera de 5, 15, 60 y 360 minutos. El `Message-ID` se mantiene entre intentos. `PREVIEW_MODE` registra `simulated` sin conectarse a SMTP. Un fallo agotado permanece en la base y la corrida informa el conteo.
- **Revalidación al enviar.** Antes de tocar SMTP se verifica de nuevo el consentimiento y que la dirección actual siga coincidiendo con la instantánea. Apagar el correo cancela filas `pending` y detiene reintentos programados, sin borrar fallos previos ni cambiar el aviso. Una entrega ya reclamada puede terminar durante la breve carrera con el opt-out.
- **Retención.** Las entregas terminales y canceladas del socio usan la ventana de entregas de ADR-075; no se purgan pendientes ni fallos con reintento programado. La bitácora de consentimiento se conserva como evidencia.
- **Sin marketing ni SMS.** El canal entrega copias de los avisos que el gimnasio ya registra; no se agregan campañas, mensajes libres, enlaces de baja en el correo ni suscripciones promocionales.

## Consecuencias y límites

- El cambio de preferencia no reescribe el contenido de la bandeja y no cambia los tokens ni las entregas push.
- Un aviso deduplicado no produce un segundo correo. El envío es al menos una vez: si SMTP acepta un mensaje y el proceso cae antes de guardar el resultado, el reintento podría duplicarlo; el `Message-ID` estable ayuda a correlacionar, pero no garantiza deduplicación del proveedor.
- El correo se envía en texto plano mediante el transporte SMTP existente. No se envían adjuntos.
- No hay una pantalla del panel para reintentar un fallo agotado. El estado y el error truncado quedan en la tabla de entregas, y el drenado informa los conteos; se puede añadir una herramienta operativa si el club necesita revisión manual.

## Implementación

- Migración `20261031_0078_member_notification_emails.py`.
- Preferencias y consentimiento en `member_notification_preferences` y `member_notification_email_preference_events`.
- Cola y entrega en `member_notification_email_deliveries`, con envío desde `app/modules/notifications/member_email.py`.
- API autenticada `GET/PATCH /member/notification-preferences` y controles en `mobile/src/screens/NotificationsScreen.tsx`.
- Recuperación y retención mediante `backend/flush_member_email.py`, `backend/ops_cron.py` y `backend/purge_inbox_data.py`.
