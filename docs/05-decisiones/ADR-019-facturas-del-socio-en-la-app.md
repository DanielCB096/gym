# ADR-019: Facturas del socio en la app, con enlaces de descarga firmados

- Fecha: 2026-10-28
- Estado: propuesta inicial

## Contexto

El módulo de facturación ya emite, timbra (con PAC simulado), cancela y envía por correo CFDI 4.0 individuales, facturas globales, notas de crédito y complementos PPD. Todo vive detrás de los permisos del personal (`billing.read` / `billing.manage`) y el panel es el único lugar donde se consultan y descargan los comprobantes.

El socio tiene sesión propia (ADR-009) y una app con perfil, clases, rutinas, medidas, metas, pagos y avisos. El ADR-012 dejó explícito el pendiente: «el socio consulta, pero no paga ni descarga facturas desde la app». Si necesita su comprobante, hoy depende de que alguien en recepción se lo reenvíe por correo o lo descargue desde el panel.

El obstáculo técnico no es leer la tabla: `Invoice` ya tiene `member_id` y el socio solo necesita una proyección reducida. El obstáculo es la descarga. La app abre documentos con el navegador del sistema (`Linking.openURL`), y ese navegador **no envía el `Authorization: Bearer`** de la sesión de 30 días. Meter el token de sesión en la URL lo expondría en el historial, los logs del proxy y las cabeceras `Referer`. Y no había que agregar dependencias de descarga: la app no incluye `expo-file-system` ni `expo-sharing`.

## Decisión

- **Sin migración ni tabla nueva.** `backend/src/app/modules/portal/invoices.py` es una capa delgada y de solo lectura sobre `invoices`. No duplica el cálculo fiscal ni genera documentos: delega en `invoice_pdf` e `invoice_xml` del módulo de facturación.
- **Alcance por `Invoice.member_id`.** La lista trae las facturas de ingreso (`sale`, `membership_payment`) y las notas de crédito emitidas al socio, más recientes primero (`created_at`, luego `folio` como desempate), paginadas (`page ≥ 1`, `page_size` 1–50, por defecto 20). La factura global de público en general queda fuera por construcción: su `member_id` es `NULL`.
- **`GET /member/invoices`** devuelve por factura folio (`A-000123`), estado, origen, importes (subtotal, IVA y total en centavos), forma y método de pago SAT, UUID (si existe), `is_simulated`, fechas de emisión/timbre/cancelación y los dos enlaces de descarga. El `member_id` sale siempre de la sesión; un socio desconocido responde `404` y un token de personal `401`.
- **Los enlaces viajan en el listado, ya firmados.** En vez de una ruta que emita enlaces bajo demanda —lo que obligaba a una segunda llamada antes de abrir el documento y favorecía bloqueos de ventana emergente en Expo web—, cada elemento trae `pdf_path` y `xml_path` con la forma `/member/invoices/{id}/{kind}?exp=<epoch>&sig=<hex>`. La firma es HMAC-SHA256 sobre `"{invoice_id}:{kind}:{exp}"` con el `SECRET_KEY` del portal, recortada a hexadecimal. `verify_download_link` rechaza `kind` desconocido, enlaces vencidos (`exp < ahora`) y firmas distintas con `hmac.compare_digest`; todo eso responde `403`.
- **Vida de 10 minutos, regenerada en cada listado.** Abrir la pantalla o deslizar para actualizar produce enlaces nuevos. Los enlaces caducan aunque la sesión siga viva, así que una URL filtrada deja de servir sola.
- **Solo se entrega lo timbrado o cancelado.** `pdf_path` y `xml_path` quedan en `null` para `requested` y `failed`: sin timbre no hay representación impresa que el PAC pueda reproducir ni comprobante con validez. La app muestra «El comprobante estará disponible cuando el timbrado se complete» en lugar de botones muertos. Cancelada sí se descarga: el comprobante cancelado existe y el socio tiene derecho a conservarlo.
- **Las rutas de descarga no piden Bearer.** La firma es la credencial y está atada a **un** documento y **un** tipo; un enlace de PDF no sirve para el XML ni para otra factura. Se responden con `Content-Disposition: attachment` y `Cache-Control: no-store`.
- **La app gana una pantalla, no un flujo.** `InvoicesScreen` lista folio, estado, total, origen, fecha, IVA y método/forma de pago, folio fiscal, aviso de simulación y la fecha de cancelación cuando aplica; los botones «Descargar PDF» y «Descargar XML» abren el navegador con `Linking.openURL(API_URL + path)`. Sin `expo-file-system`, sin `expo-sharing` y sin permisos nuevos. El inicio gana la tarjeta «Facturas».

## Consecuencias y límites

- El socio ya descarga sus comprobantes sin pasar por recepción; el panel y la app leen la misma factura, así que no hay dos verdades fiscales.
- **El enlace es equivalente a una credencial temporal.** Quien lo intercepte durante 10 minutos descarga ese PDF o XML, y la descarga no se audita: no escribe `invoice_events` ni deja rastro del socio que la hizo. Mitigado por la vida corta, el alcance a un solo documento y la regeneración constante; antes de producción conviene decidir si se registra la descarga.
- **Rotar `SECRET_KEY` invalida los enlaces vigentes**, igual que los códigos OTP y con el mismo aviso: la lista se regenera al refrescar. Las sesiones sobreviven porque solo guardan su SHA-256.
- **No se solicita una factura desde la app.** Solo se listan las ya emitidas; pedir una nueva sigue siendo un trámite en recepción o en el panel. Tampoco se reenvía por correo ni se descarga el complemento PPD o la factura global del socio —esta última no le pertenece individualmente—.
- **Sin paginación infinita en la app.** Pide la primera página de 20 y muestra el total; un socio con más de 20 facturas no ve las antiguas hasta que se agregue «cargar más».
- **El importe se muestra en MXN.** El backend devuelve `currency`, pero `formatMoney` de la app asume pesos; hoy el módulo fiscal solo emite MXN.
- **El PDF se genera al momento** y no se almacena (igual que en el panel): una descarga repetida vuelve a construirlo con ReportLab.
- En vista previa el timbrado es simulado, así que el PDF y el XML descargados **no tienen validez fiscal**; la pantalla lo advierte con el aviso de simulación.
- Antes de producción: PAC real con CSD válido, bitácora de descargas, límite de tasa por socio o IP sobre las rutas firmadas, y decidir si la app debe permitir solicitar la factura de un pago.

## Referencias

- `backend/src/app/modules/portal/invoices.py` (`list_member_invoices`, `verify_download_link`, `download_member_invoice`, `_signed_path`, `_sign`)
- `backend/src/app/modules/portal/service.py` (`signing_secret`)
- `backend/src/app/modules/billing/service.py` (`invoice_pdf`, `invoice_xml`)
- `backend/src/app/main.py` (`/member/invoices`, `/member/invoices/{id}/pdf`, `/member/invoices/{id}/xml`)
- `backend/tests/test_member_invoices_api.py`
- `mobile/src/screens/InvoicesScreen.tsx`, `mobile/src/api.ts` (`getMemberInvoices`), `mobile/src/format.ts`
- ADR-009 (autenticación del socio), ADR-012 (pagos y estado de cuenta del socio)
