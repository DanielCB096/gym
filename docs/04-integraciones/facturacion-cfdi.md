# Facturación CFDI

## Estado implementado (2026-10-23)

El **CFDI 4.0 individual** ya está implementado para una venta del POS o un cobro de membresía confirmado. La migración `20261023_0024_billing_cfdi.py` crea `member_fiscal_profiles`, `invoices`, `invoice_items` e `invoice_events`; los permisos son `billing.read` (consultar), `billing.request` (solicitar y capturar perfil fiscal) y `billing.manage` (timbrar y cancelar).

- **Flujo**: `POST /admin/billing/invoices` valida los datos fiscales contra los catálogos del SAT, congela el snapshot del receptor, deriva el IVA incluido (`base = round(total / 1.16)`, impuesto = total − base), asigna folio por serie y deja la factura en `requested`. `POST .../{id}/stamp` construye el XML pre-timbre y lo envía al PAC; `GET .../{id}/xml` descarga el XML; `POST .../{id}/cancel` cancela una factura timbrada con motivo del SAT (01–04).
- **PAC**: en vista previa (`PREVIEW_MODE=true` o `PAC_PROVIDER=simulated`) se usa `SimulatedPac`, que devuelve el XML con un comentario «SIMULACION» y **sin** UUID ni `TimbreFiscalDigital`; la factura queda `is_simulated = true` y **no tiene validez fiscal**. El adaptador de un PAC real **no está implementado**: con cualquier otro proveedor el timbrado responde `503`; un rechazo del PAC responde `502` y deja la factura `failed` para reintento.
- **Configuración**: el emisor se lee de `GYM_RFC`, `GYM_LEGAL_NAME`, `GYM_TAX_REGIME`, `GYM_POSTAL_CODE`, `CFDI_CERTIFICATE_NUMBER`, `CFDI_SERIES`, `CFDI_TAX_RATE_PERCENT`, `CFDI_PRODUCT_CODE` y `CFDI_SERVICE_CODE`; las credenciales del PAC (`PAC_PROVIDER`, `PAC_USER`, `PAC_PASSWORD`, `PAC_PRODUCTION`) viven solo en variables de entorno. Los valores por defecto del emisor son marcadores con forma válida y deben sustituirse antes de un timbrado real.
- **Almacenamiento y auditoría**: el XML timbrado se guarda en `invoices.xml_content` y cada solicitud, intento y cancelación se agrega a `invoice_events` (append-only). El comprobante nunca se borra: una cancelación conserva folio, UUID (si existe), motivo y actor. La descarga responde `Cache-Control: no-store` y no se cachea.
- **Fuera de alcance todavía**: factura global, notas de crédito, complemento de pago PPD/PUE, conciliación bancaria, representación impresa (PDF), envío por correo y consulta del estado final de la cancelación ante el PAC real. La validación legal y contable sigue siendo necesaria antes de usar el flujo en producción.

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
- el XML y PDF deben almacenarse con seguridad
- el cobro y la emisión se registran como eventos separados
- nunca se elimina un comprobante emitido

⚠️ La validación legal y contable es necesaria antes del uso en producción.
