# ADR-021: El socio recibe avisos del estado de su factura

- Fecha: 2026-10-28
- Estado: propuesta inicial

## Contexto

El ADR-020 llevó a la app la solicitud de facturas y dejó escrito el límite: «no se avisa al socio cuando cambia el estado de la factura». El socio pide el CFDI, la app le muestra `requested` y, desde ese momento, solo se entera de que ya está timbrada —o de que falló, o de que fue cancelada— si vuelve a abrir Facturas y desliza para actualizar. El club ya tiene una bandeja de avisos con deduplicación, texto congelado y lectura desde la app (ADR-016), así que el problema no es crear un canal nuevo sino decidir **cuándo** escribe facturación en él.

El timbrado y la cancelación son acciones del personal (`billing.manage`) que ocurren días después de la solicitud. El emisor natural es el servicio de facturación, que ya conoce el estado final y el importe, y que en ese punto aún tiene abierta la transacción del cambio.

## Decisión

- **Tres tipos nuevos en `member_notifications`**: `invoice_stamped`, `invoice_failed` e `invoice_cancelled`, añadidos a `NOTIFICATION_KINDS` y al `CHECK ck_member_notifications_kind`. La migración `20261028_0039_invoice_status_notifications.py` suelta y recrea la restricción con el mismo nombre y se niega a revertir si existen filas de los tipos nuevos. `preview_patch.py` encadena la lista de seis a siete y de siete a diez, de modo que una base de vista previa atrasada también llega al esquema actual.
- **Se emite dentro de la transacción del cambio de estado**, justo antes del `commit()` que ya existía, igual que rutinas, clases y mantenimiento: el aviso no puede sobrevivir a un cambio que revierte, y si la inserción falla, el timbrado o la cancelación tampoco se confirman. No hay cola, worker ni reintento.
- **Solo si la factura tiene socio.** `_notify_invoice_status` sale en cuanto `invoice.member_id is None`: las ventas de público en general y la factura global no tienen destinatario. La decisión queda en un único helper del servicio de facturación; los emisores de `notifications` solo redactan e insertan.
- **`requested` no avisa.** El socio acaba de pedir la factura y ve el resultado en la tarjeta de la solicitud; avisarle de su propia acción sería ruido. Sí avisan los tres estados que él no provoca: timbrada, fallida y cancelada.
- **El fallo avisa por los tres caminos que lo producen.** El rechazo del PAC, la nota de crédito cuya factura relacionada ya no está timbrada y la nota que excede el saldo acreditable dejan la factura en `failed`; los tres escriben `invoice_failed` antes de responder el error al panel. Un reintento posterior puede timbrar la misma factura y entonces llega `invoice_stamped`.
- **Dedupe por factura y estado**, no por factura: `invoice_stamped:<id>`, `invoice_failed:<id>` e `invoice_cancelled:<id>`. Así un fallo y una recuperación son dos hechos y dejan dos avisos, mientras repetir el mismo fallo o volver a timbrar una factura ya timbrada no duplica nada. El índice único parcial sobre `dedupe_key` sigue siendo la garantía en concurrencia.
- **Texto congelado con folio e importe.** El cuerpo dice «Tu factura A-000123 por $1,160.00 MXN ya está lista. Descarga el PDF o el XML desde Facturas.» y, si el timbre es simulado, agrega «Es un comprobante de prueba sin validez fiscal.». El fallo pide revisar los datos fiscales en Facturas o acercarse a recepción; la cancelación remite a recepción. `ref_id` guarda el `invoice_id` para que la app abra la pantalla correcta.
- **La app abre Facturas al tocar el aviso.** `NotificationsScreen` gana `onOpenInvoices`; tras marcar el aviso como leído, si el `kind` empieza con `invoice_` llama a `App.tsx` para cambiar a la etapa `invoices`. El `accessibilityLabel` pasa a «Abrir facturas: …». Las tres etiquetas de tipo son «Factura» y no cambia el resto de la bandeja.

## Consecuencias y límites

- El socio ya no depende de volver a Facturas para enterarse del resultado, y el aviso lleva al comprobante en un toque.
- **El aviso no es un recibo fiscal ni un canal de entrega.** Sigue sin haber push ni correo: si el socio no abre la app, no lo ve, y el CFDI no se adjunta.
- **Un fallo al notificar revierte la acción de facturación.** Es la contrapartida de la misma transacción: una base sin el `CHECK` actualizado, por ejemplo, impediría timbrar. La migración y el parche de vista previa son parte del incremento, no un extra.
- **La cancelación solo avisa cuando la factura estaba timbrada.** Una factura `failed` no se cancela; se reintenta. Las notas de crédito y los complementos de pago no generan avisos propios.
- **No hay aviso de «factura solicitada»** ni de cambios de datos fiscales, y el aviso no distingue el motivo de la cancelación (01–04).
- **Sin política de retención propia**: los avisos viven en la misma bandeja que crece indefinidamente, con los límites ya documentados del módulo de notificaciones.
- Antes de producción: decidir un canal push/correo, la retención de la bandeja y si el aviso de cancelación debe llevar el motivo y el UUID sustituto.

## Referencias

- `backend/src/app/modules/notifications/models.py`, `service.py` (`notify_invoice_stamped`, `notify_invoice_failed`, `notify_invoice_cancelled`, `_money_label`)
- `backend/src/app/modules/billing/service.py` (`_notify_invoice_status`, `stamp_invoice`, `cancel_invoice`)
- `backend/alembic/versions/20261028_0039_invoice_status_notifications.py`, `backend/preview_patch.py`
- `backend/tests/test_invoice_notifications.py`
- `mobile/src/screens/NotificationsScreen.tsx`, `mobile/App.tsx`, `mobile/src/format.ts`
- ADR-016 (notificaciones del socio), ADR-018 (aviso de equipo fuera de servicio), ADR-019 (facturas del socio), ADR-020 (solicitud de facturas del socio)
