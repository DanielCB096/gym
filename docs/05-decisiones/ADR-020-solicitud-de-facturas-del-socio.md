# ADR-020: El socio solicita sus facturas desde la app

- Fecha: 2026-10-28
- Estado: propuesta inicial

## Contexto

El ADR-019 llevó a la app la consulta y descarga de las facturas ya emitidas, y dejó escrito el pendiente: «No se solicita una factura desde la app. Solo se listan las ya emitidas; pedir una nueva sigue siendo un trámite en recepción o en el panel». El socio que compra en mostrador o paga su membresía sigue dependiendo de recepción para que alguien capture sus datos fiscales y emita el CFDI.

El backend ya tiene todo lo necesario para emitir: `create_invoice` resuelve el origen (`sale` o `membership_payment`), valida elegibilidad, calcula IVA, timbra con el PAC simulado, asigna folio, respeta la idempotencia y registra `invoice_events`. El perfil fiscal ya se guarda en `member_fiscal_profiles` (`save_fiscal_profile`), y la app ya sabe leerlo.

El riesgo no está en crear la factura, sino en **quién** la pide. `create_invoice` recibe un `origin_id` y no conoce al socio: si la ruta del portal se limitara a reenviar el cuerpo, un socio con sesión podría facturar la venta o el pago de otro. La autorización tiene que ocurrir antes de que el servicio de facturación vea el origen, y el evento debe distinguir una solicitud del socio de una del personal.

## Decisión

- **Sin migración ni tabla nueva.** La solicitud reutiliza `member_fiscal_profiles`, `invoices` e `invoice_events`. El único cambio de esquema habría sido guardar un `created_by` de socio, pero esa columna es una FK a cuentas del personal; se deja en `NULL`, igual que los registros creados desde la app en rutinas y metas.
- **Autorización en la capa de portal, antes de facturar.** `backend/src/app/modules/portal/invoices.py` gana `_require_owned_origin`, que carga la venta o el pago y compara su `member_id` con el de la sesión. Un origen ajeno, inexistente o de tipo desconocido responde `404` con el mismo mensaje («La operación no existe o no pertenece al socio»), sin revelar si existe. Solo después de esa comprobación se llama a `create_invoice`.
- **Defensa extra en el replay.** Como la idempotencia devuelve la factura de la clave original sin volver a resolver el origen, `request_member_invoice` comprueba además que `view.member_id` sea el socio de la sesión; si no, responde `404`. Así una clave filtrada o repetida no expone la factura de otra persona.
- **Dos lecturas nuevas para armar la pantalla.** `GET /member/invoices/origins` lista las operaciones propias **pendientes de facturar** (`page ≥ 1`, `page_size` 1–50, 20 por defecto, filtro opcional `origin_type`). `GET /member/fiscal-profile` devuelve el perfil guardado o `{"profile": null}`. Ambas derivan el socio del Bearer y responden `404` si el socio no existe.
- **Elegibilidad calcada del módulo de facturación.** Ventas: `member_id` propio, `status = completed`, método distinto de `account`, total positivo, sin factura de venta viva, sin devolución registrada y fuera de una factura global viva. Cobros: importe positivo y sin factura de membresía viva. Una factura cancelada deja la operación elegible otra vez. Si la regla cambia en facturación, la lista puede desviarse (ver límites).
- **Paginación en Python.** Ventas y cobros se consultan por separado, se unen por fecha descendente y se cortan en memoria. El volumen por socio es pequeño y evita una consulta `UNION` dependiente del motor; los datetimes ingenuos de SQLite se normalizan como UTC antes de ordenar.
- **`POST /member/invoices` (201).** Recibe `origin_type`, `origin_id`, `idempotency_key`, datos del receptor (`rfc`, `legal_name`, `tax_regime`, `postal_code`, `cfdi_use` con `G03` por defecto y `email` opcional) y, opcionalmente, `payment_form`/`payment_method`. Primero guarda el perfil fiscal —aunque la factura se rechace después, los datos quedan para el siguiente intento—, luego factura con `actor_id=None` y `channel="member_app"`. La respuesta envuelve la factura con los mismos campos y enlaces firmados del listado, más `idempotent_replay`.
- **La auditoría dice de dónde vino.** El evento `invoice_requested` ya incluía importe, origen y método; ahora agrega `"channel": "staff" | "member_app"`. El panel conserva el actor; la solicitud del socio queda con `actor_id = NULL` y `created_by = NULL`, identificable por el canal.
- **La app gana una pantalla de solicitud.** `InvoiceRequestScreen` se abre desde el botón «Solicitar factura» de `InvoicesScreen`. Carga en paralelo las operaciones pendientes y el perfil fiscal; si hay perfil, prellena los campos y muestra «Usamos los datos que guardaste». El socio elige una operación, revisa o corrige RFC, razón social, régimen, código postal, uso del CFDI y correo, y envía. El cliente valida formato (RFC 12–13 caracteres, nombre de al menos 2, régimen de 3 dígitos, CP de 5, uso de 3 y correo con `@`) para no gastar la llamada en errores obvios.
- **Idempotencia estable desde la app.** La clave se deriva con FNV-1a del origen y del formulario normalizado. Reintentar el mismo envío reutiliza la clave y el backend responde la misma factura con `idempotent_replay: true`; corregir cualquier dato produce otra clave y otra solicitud.
- **Después de enviar** la tarjeta de resultado muestra folio, estado e importe, la operación desaparece de la lista y el botón «Ver mis facturas» vuelve al listado, donde la nueva factura aparece como `requested` hasta que el personal la timbre. «Solicitar otra factura» conserva el perfil y recarga las operaciones.

## Consecuencias y límites

- El socio ya factura sin pasar por recepción y sin credenciales fiscales del club; el panel y la app usan el mismo `create_invoice`, así que folio, IVA, XML y eventos no tienen dos verdades.
- **El socio no timbra.** La solicitud crea la factura en `requested`; el timbrado sigue siendo una acción del personal (`billing.manage`) o el flujo simulado de vista previa. La app lo dice en la tarjeta de resultado.
- **Solo sus operaciones.** El origen se comprueba contra `Sale.member_id` y `Payment.member_id`. Una venta de público en general (sin socio) no aparece ni se puede facturar desde la app; se factura en el panel o en la global.
- **La lista duplica la regla de elegibilidad** (venta completada, no a cuenta, no devuelta, fuera de global viva, sin factura activa). Si facturación cambia esa regla y la lista no, el socio verá una operación que el POST rechaza con `409`; la fuente de verdad sigue siendo `create_invoice`, no el listado.
- **El perfil se guarda antes de facturar.** Una solicitud rechazada por `409` deja los datos fiscales persistidos: es intencional para no perder la captura, pero implica que el perfil puede cambiar sin que exista una factura nueva.
- **La app no ofrece PPD.** No expone `payment_form` ni `payment_method`, así que toda solicitud sale como PUE con la forma derivada del método de cobro. El API acepta ambos campos y las pruebas cubren PPD (`99`/`PPD`), pero un cobro que deba documentarse como PPD hoy se solicita desde el panel.
- **Sin comprobante inmediato.** La pantalla no descarga el PDF/XML de la solicitud recién creada: `requested` no tiene enlaces y el socio debe volver cuando esté timbrada. No hay aviso al socio cuando cambia el estado de la factura.
- **Sin límite de tasa propio.** La ruta usa la sesión de 30 días y la idempotencia evita duplicados de una misma solicitud, pero no hay un tope de solicitudes por socio ni por IP; un cliente malicioso con sesión válida podría crear muchas facturas en `requested`.
- **El perfil fiscal son datos personales** sin política de retención o borrado asociada al socio (igual que antes de este incremento). La app no permite consultarlos ni borrarlos fuera de la pantalla de solicitud.
- Antes de producción: definir la traza del actor socio, el límite de solicitudes, el aviso de cambio de estado, la retención del perfil fiscal y la elección de PPD cuando el cobro lo requiera.

## Referencias

- `backend/src/app/modules/portal/invoices.py` (`list_billable_origins`, `request_member_invoice`, `member_fiscal_profile`, `_require_owned_origin`, `_billable_sales`, `_billable_payments`)
- `backend/src/app/modules/billing/service.py` (`create_invoice` con `actor_id`/`channel`, `save_fiscal_profile`, `get_fiscal_profile`)
- `backend/src/app/main.py` (`/member/invoices/origins`, `/member/fiscal-profile`, `POST /member/invoices`)
- `backend/tests/test_member_invoice_requests_api.py`
- `mobile/src/screens/InvoiceRequestScreen.tsx`, `mobile/src/screens/InvoicesScreen.tsx`, `mobile/src/api.ts` (`getMemberBillableOrigins`, `getMemberFiscalProfile`, `requestMemberInvoice`), `mobile/src/types.ts`
- ADR-009 (autenticación del socio), ADR-012 (pagos del socio), ADR-019 (facturas del socio y enlaces firmados)
