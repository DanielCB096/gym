# Facturación CFDI

## Estado implementado (2026-10-24)

El **CFDI 4.0 individual** ya está implementado para una venta del POS o un cobro de membresía confirmado, y la **factura global mensual** para ventas de público en general. La migración `20261023_0024_billing_cfdi.py` crea `member_fiscal_profiles`, `invoices`, `invoice_items` e `invoice_events`; la migración `20261024_0025_global_invoices.py` agrega el origen `global`, el periodo global y `global_invoice_sales`. Los permisos son `billing.read` (consultar), `billing.request` (solicitar, capturar perfil fiscal y enviar por correo) y `billing.manage` (timbrar, cancelar y emitir la global).

- **Flujo**: `POST /admin/billing/invoices` valida los datos fiscales contra los catálogos del SAT, congela el snapshot del receptor, deriva el IVA incluido (`base = round(total / 1.16)`, impuesto = total − base), asigna folio por serie y deja la factura en `requested`. `POST .../{id}/stamp` construye el XML pre-timbre y lo envía al PAC; `GET .../{id}/xml` descarga el XML; `GET .../{id}/pdf` genera la representación impresa; `POST .../{id}/send` envía PDF y XML por correo; `POST .../{id}/cancel` cancela una factura timbrada con motivo del SAT (01–04).
- **Factura global**: `GET /admin/billing/global-invoices/eligible?year=&month=` (`billing.read`) muestra las ventas de público en general de un mes **cerrado** que pueden agruparse, con totales, IVA y conteos de exclusión; `POST /admin/billing/global-invoices` (`billing.manage`) emite una sola global viva por mes con receptor fijo `XAXX010101000`, régimen `616`, uso `S01`, forma de pago `99` y `InformacionGlobal Periodicidad="03" Meses="MM" Año="YYYY"`. Solo incluye ventas completadas, sin devolución, con total positivo, sin socio, no cobradas a cuenta y no facturadas individualmente ni en otra global. La elegibilidad se recalcula al emitir; un mes abierto, un periodo ya facturado o un lote vacío responden `409`. `global_invoice_sales` conserva el folio, la fecha y el total de cada venta incluida; cancelar libera el periodo y la sustitución reutiliza el mismo flujo de timbrado.
- **PAC**: en vista previa (`PREVIEW_MODE=true` o `PAC_PROVIDER=simulated`) se usa `SimulatedPac`, que devuelve el XML con un comentario «SIMULACION» y **sin** UUID ni `TimbreFiscalDigital`; la factura queda `is_simulated = true` y **no tiene validez fiscal**. El adaptador de un PAC real **no está implementado**: con cualquier otro proveedor el timbrado responde `503`; un rechazo del PAC responde `502` y deja la factura `failed` para reintento.
- **Configuración**: el emisor se lee de `GYM_RFC`, `GYM_LEGAL_NAME`, `GYM_TAX_REGIME`, `GYM_POSTAL_CODE`, `CFDI_CERTIFICATE_NUMBER`, `CFDI_SERIES`, `CFDI_TAX_RATE_PERCENT`, `CFDI_PRODUCT_CODE` y `CFDI_SERVICE_CODE`; las credenciales del PAC (`PAC_PROVIDER`, `PAC_USER`, `PAC_PASSWORD`, `PAC_PRODUCTION`) viven solo en variables de entorno. Los valores por defecto del emisor son marcadores con forma válida y deben sustituirse antes de un timbrado real.
- **Representación impresa y correo**: `GET /admin/billing/invoices/{id}/pdf` (`billing.read`) genera el PDF **al momento** (ReportLab, tamaño carta) solo para facturas timbradas o canceladas; no se guarda ni se cachea. Lleva la marca de agua **SIMULADA** (sin validez fiscal) o **CANCELADA**, los datos congelados del emisor y el receptor, los conceptos con códigos del SAT, los totales y, si aplica, el motivo de cancelación. `POST /admin/billing/invoices/{id}/send` (`billing.request`) envía el PDF y el XML adjuntos al correo del receptor o a un destinatario explícito; solo acepta facturas timbradas y responde `503` sin SMTP o `502` si el transporte falla.
- **SMTP**: el envío usa `app/mailer.py`, compartido con los estados de cuenta, configurado con `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS`, `SMTP_USE_SSL` y `SMTP_TIMEOUT`; en `PREVIEW_MODE` se registra como `simulated` sin contactar un servidor. El envío es síncrono y sin cola ni confirmación de entrega.
- **Almacenamiento y auditoría**: el XML timbrado se guarda en `invoices.xml_content`, la global conserva su lote en `global_invoice_sales` (con folio, fecha y total congelados de cada venta) y cada solicitud, intento, cancelación y envío se agrega a `invoice_events` (append-only). Un envío registra `invoice_email_sent` con destinatario, adjuntos, estado de entrega y simulación, o `invoice_email_failed` con el motivo y el error. El comprobante nunca se borra: una cancelación conserva folio, UUID (si existe), motivo y actor. Las descargas y el PDF responden `Cache-Control: no-store` y no se cachean.
- **Fuera de alcance todavía**: notas de crédito, complemento de pago PPD/PUE, conciliación bancaria, consulta del estado final de la cancelación ante el PAC real y una cola de correo con reintento automático y confirmación de entrega. La validación legal y contable sigue siendo necesaria antes de usar el flujo en producción.

## Contexto

La facturación del gimnasio debe seguir el marco del SAT para México, con RFC, régimen fiscal, uso de CFDI, notas de crédito y cancelaciones bajo las reglas vigentes.

## Reglas críticas
- CFDI 4.0
- IVA 16%
- uso de CFDI según el cliente
- notas de crédito y cancelación con trazabilidad
- factura global para público general
- complemento de pago PPD/PUE cuando aplique

## Integración recomendada

Se recomienda un PAC con API robusta y atención local. Finkok es una opción válida por la práctica común y la capacidad de emitir XML y reteniendo información administrativa.

## Consideraciones
- el XML se almacena con seguridad; el PDF se genera al momento y se entrega con control de acceso
- el cobro y la emisión se registran como eventos separados
- nunca se elimina un comprobante emitido

⚠️ La validación legal y contable es necesaria antes del uso en producción.
