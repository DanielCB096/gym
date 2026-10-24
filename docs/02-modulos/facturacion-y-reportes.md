# Módulo 7: Facturación y reportes financieros

## 1. Resumen y alcance

Este módulo administra la solicitud y emisión de CFDI 4.0 para los cobros del gimnasio, la consulta de comprobantes, las cancelaciones y notas de crédito bajo las reglas fiscales vigentes, la conciliación de pagos y los reportes financieros de operación. El cobro y la emisión fiscal son eventos relacionados, pero separados: un pago confirmado no debe aparecer como facturado hasta que el PAC certifique el comprobante.

### Incluye
- captura y validación de datos fiscales del receptor
- emisión de CFDI y factura global mediante PAC
- almacenamiento y entrega de XML y representación PDF
- seguimiento de cancelaciones y notas de crédito
- conciliación de pagos de pasarela, banco y caja
- reportes de ingresos, cobros, devoluciones y membresías

### No incluye
- cálculo o presentación de impuestos ni asesoría contable
- gestión de nómina y recibos de nómina, que pertenecen al módulo de Personal y roles
- contabilidad general o sustitución del sistema contable del negocio

Las reglas, catálogos y supuestos fiscales deberán ser revisados por el contador del gimnasio y el PAC antes de producción. El sistema conservará configuración versionada para conceptos, impuestos y tratamientos fiscales, sin codificar tasas o criterios como universales.

## 2. Actores y permisos

| Actor | Objetivo | Permisos clave |
|---|---|---|
| Contador | supervisar comprobantes y conciliaciones | revisar datos, emitir, solicitar cancelación, conciliar y exportar |
| Gerente | consultar operación financiera | revisar ventas, cobros, devoluciones y reportes autorizados |
| Dueño | evaluar resultados del gimnasio | consultar indicadores financieros consolidados |
| Recepción | resolver solicitudes de facturación | capturar datos fiscales y consultar comprobantes vinculados a una venta |
| Socio / cliente | solicitar y recibir comprobantes | proporcionar datos fiscales y descargar sus comprobantes |

La autorización para emitir, cancelar o ajustar comprobantes se valida en backend y queda auditada; no depende únicamente de ocultar controles en la interfaz.

## 3. Flujos de usuario paso a paso

### Flujo de solicitud y emisión
1. Se confirma la venta o el pago de membresía y se guarda su referencia de origen.
2. El cliente solicita CFDI e indica o confirma sus datos fiscales y el concepto que se facturará.
3. El sistema valida que la operación no tenga ya un comprobante vigente incompatible y valida los datos obligatorios según la configuración fiscal vigente.
4. Un usuario autorizado confirma la solicitud y el sistema envía la emisión al PAC con una clave de idempotencia.
5. Se registra la respuesta del PAC. Cuando se confirma el timbrado, se guardan UUID, XML, metadatos y representación PDF; si falla o queda incierto, se conserva el estado para consulta o reintento controlado.
6. El cliente recibe acceso seguro a sus archivos y el comprobante queda ligado al cobro original.

### Flujo de factura global
1. Se identifican las operaciones de público en general elegibles conforme a la política fiscal validada.
2. Se excluyen operaciones ya facturadas individualmente y operaciones anuladas o en revisión.
3. El contador revisa periodo, totales, impuestos y referencias fuente antes de solicitar el timbrado.
4. El sistema emite mediante PAC, conserva el detalle de las operaciones incluidas y registra el resultado.
5. Una solicitud posterior de factura individual se atiende mediante el flujo fiscal de sustitución o ajuste que indique el contador/PAC; no se altera silenciosamente la factura global.

### Flujo de cancelación o nota de crédito
1. Un usuario autorizado solicita el ajuste, registra motivo y referencia al CFDI y a la operación de origen.
2. El sistema valida el estado actual y solicita la operación correspondiente al PAC, incluyendo relación o aceptación cuando aplique.
3. Se guarda la solicitud, respuesta y estado final confirmado por PAC/SAT.
4. El comprobante original permanece en el historial; los reportes reflejan la relación y el efecto del ajuste sin borrar eventos previos.

### Flujo de conciliación
1. Se importan o consultan movimientos de la pasarela, banco y cierres de caja.
2. El sistema propone coincidencias usando referencia, monto, moneda y fecha.
3. El contador confirma coincidencias o marca diferencias para revisión.
4. Cada movimiento queda conciliado, pendiente o en excepción, con responsable y resolución.

## 4. Pantallas / espacios

### 1. Bandeja de facturación
- Objetivo: atender solicitudes nuevas y excepciones
- Componentes: fecha, cliente, referencia de venta, monto, estado fiscal, alertas de datos
- Estados: datos pendientes, listo para emitir, en proceso, timbrado, error, cancelación pendiente

### 2. Detalle del comprobante
- Objetivo: consultar trazabilidad y archivos fiscales
- Componentes: UUID, receptor, concepto, referencias de pago, XML, PDF, eventos PAC/SAT y comprobantes relacionados
- Acciones según permiso: descargar, reenviar, solicitar cancelación, revisar historial

### 3. Perfil fiscal del cliente
- Objetivo: capturar los datos del receptor necesarios para facturar
- Componentes: RFC, nombre o razón social, régimen fiscal, código postal fiscal, uso del CFDI y correo de entrega
- Estados: incompleto, por validar, validado, requiere actualización

### 4. Conciliación de pagos
- Objetivo: comparar cobros y depósitos con ventas y devoluciones
- Componentes: origen, referencia, fecha, monto, estado de coincidencia, diferencia y asignación
- Estados: conciliado, sugerido, pendiente, diferencia, en revisión

### 5. Factura global
- Objetivo: preparar, revisar y dar seguimiento al lote de operaciones elegibles
- Componentes: periodo, operaciones incluidas/excluidas, totales, revisión y respuesta del PAC
- Estados: borrador, revisión, enviado, timbrado, error, ajuste pendiente

### 6. Reportes financieros
- Objetivo: consultar cifras operativas con filtros y fuentes identificables
- Componentes: periodo, concepto, método de pago, venta, devolución, ingreso cobrado y estado de conciliación
- Estados: procesando, disponible, error de generación

## 5. Reglas de negocio y casos límite

### Reglas clave
- Un comprobante fiscal timbrado nunca se elimina ni se modifica directamente; cualquier corrección usa el proceso fiscal correspondiente y conserva la relación con el original.
- El pago confirmado y el CFDI timbrado son estados independientes y se reportan por separado.
- Los reintentos ante timeout del PAC deben consultar el resultado previo o reutilizar una clave idempotente para evitar duplicar comprobantes.
- Un CFDI debe conservar datos fiscales, conceptos, impuestos, versión de configuración, UUID, fechas, XML y respuestas relevantes del PAC.
- La cancelación y las notas de crédito requieren motivo, permisos, trazabilidad y confirmación del estado final; las reglas concretas se validan con contador/PAC.
- Las operaciones incluidas en factura global deben poder rastrearse hasta sus ventas originales y no duplicarse con facturación individual.
- Las diferencias de conciliación no se ajustan automáticamente ni se ocultan del reporte.
- Los archivos fiscales se almacenan con control de acceso, respaldo y retención definida por asesoría fiscal y política de datos.

### Casos límite
- El PAC recibe la solicitud, pero la respuesta se pierde por timeout.
- El pago se reembolsa o revierte después de emitido el CFDI.
- El cliente cambia sus datos fiscales después de solicitar la factura.
- Dos operadores solicitan al mismo tiempo la factura de una misma venta.
- Un pago aparece en la pasarela, pero todavía no en el banco, o el depósito llega agrupado.
- Una operación de factura global ya fue solicitada individualmente.
- Se solicita cancelar un comprobante y el PAC/SAT lo deja pendiente o requiere aceptación.

## 6. Entidades de datos

- ComprobanteFiscal
- ClienteFiscal
- SolicitudFacturacion
- EventoFiscal
- RelacionComprobante
- NotaCredito
- CancelacionCFDI
- ConciliacionPago
- MovimientoFinanciero
- LoteFacturaGlobal
- ReporteFinanciero

### Campos clave
- ComprobanteFiscal: id, uuid, tipo, estado, cliente_fiscal_id, origen_tipo, origen_id, subtotal, impuestos, total, moneda, emitido_en
- ClienteFiscal: id, socio_id opcional, RFC, nombre_razon_social, regimen_fiscal, codigo_postal_fiscal, uso_cfdi
- SolicitudFacturacion: id, venta_id, cliente_fiscal_id, estado, idempotency_key, solicitada_por, creada_en
- EventoFiscal: id, comprobante_id, tipo, respuesta_pac, ocurrido_en, usuario_id
- ConciliacionPago: id, movimiento_id, origen, referencia, monto, estado, diferencia, revisado_por
- LoteFacturaGlobal: id, periodo, estado, total_operaciones, comprobante_id, revisado_por

## 7. Integraciones con otros módulos

- Membresías y cobro recurrente: origen de cargos, pagos, reembolsos y solicitudes de factura.
- Punto de venta e inventario: ventas y devoluciones de productos como origen fiscal y financiero.
- Pasarela y bancos: referencias de pago, contracargos, depósitos y conciliación.
- Personal y roles: recibos de nómina quedan fuera de este módulo, aunque pueden compartir infraestructura de integración con el PAC bajo permisos y flujos independientes.
- Reportes: datos conciliados y eventos fiscales alimentan indicadores sin alterar el libro de eventos de origen.

## 8. Notificaciones y automatizaciones

- solicitud de facturación pendiente de datos o revisión
- resultado de timbrado, error del PAC o cancelación pendiente
- comprobante disponible para descarga
- pago sin depósito conciliado o movimiento bancario sin venta asociada
- resumen periódico de solicitudes, errores y conciliaciones pendientes
- generación de reportes recurrentes para usuarios autorizados

## 9. Consideraciones de rendimiento específicas del módulo

- emitir y consultar PAC fuera del request interactivo mediante tareas asíncronas, con estado visible al usuario
- usar claves de idempotencia y restricciones únicas para prevenir solicitudes duplicadas
- ejecutar reportes agregados y exportaciones grandes en segundo plano
- filtrar por periodo, UUID, RFC, origen, estado y referencia de pago con índices adecuados
- conservar por separado los archivos XML/PDF y la información consultable, con recuperación respaldada
- mostrar cifras con fecha de corte y estado de conciliación para evitar presentar estimaciones como cifras finales

## 10. KPIs

- porcentaje de solicitudes timbradas correctamente
- tiempo medio desde solicitud completa hasta timbrado
- CFDI con error, cancelación o ajuste pendiente
- porcentaje de movimientos conciliados
- monto y antigüedad de diferencias por origen
- ingresos cobrados, devoluciones y cargos pendientes por periodo
- ingreso recurrente mensual (MRR) y cancelación de membresías, según definición documentada en reportes

## 11. Preguntas abiertas

- ¿qué política y ventana operativa se adoptarán para solicitudes de factura individual y factura global?
- ¿quién aprueba cancelaciones y notas de crédito según monto o tipo de operación?
- ¿qué fuentes de banco y pasarela estarán disponibles para conciliación automática?
- ¿qué sistema contable recibirá exportaciones y con qué formato?
- ¿cuál será la política de retención y acceso a XML/PDF, validada con asesoría fiscal?

## 12. Criterios de aceptación

- Cada CFDI queda ligado a su solicitud y operación de origen, conserva UUID, archivos y eventos de PAC.
- La emisión distingue claramente cobro confirmado de timbrado confirmado.
- Reintentar una solicitud ante respuesta incierta no duplica el comprobante.
- Cancelaciones y notas de crédito quedan ligadas al comprobante original y conservan su estado final.
- Factura global permite rastrear las operaciones incluidas y evita duplicarlas con facturación individual.
- Conciliación muestra coincidencias, diferencias y pendientes sin aplicar ajustes silenciosos.
- Los reportes permiten identificar periodo, fuentes y estado de conciliación.
- Permisos y accesos a datos y archivos fiscales quedan auditados.

## 13. Implementación actual y límites

Primer incremento entregado (2026-10-18) y **de solo lectura** para la parte de reportes: agrega reportes sobre los datos que ya escribieron los demás módulos y **no** crea tablas de reportes ni migración. La parte fiscal avanzó con el **quinto incremento (2026-10-23): CFDI 4.0 individual con timbrado simulado** y la migración `20261023_0024_billing_cfdi.py`. Lo que sigue en diseño es el resto del ciclo fiscal (factura global, notas de crédito, complemento PPD, conciliación bancaria, PDF/envío) y el adaptador de un PAC real.

### CFDI 4.0 individual (quinto incremento, 2026-10-23)

- **Entidades**: `member_fiscal_profiles` guarda los datos fiscales de un socio para prellenar la siguiente solicitud (un perfil por socio); `invoices` guarda la solicitud y su resultado en una sola fila (estado `requested`, `failed`, `stamped` o `cancelled`), con el snapshot del receptor, el desglose de IVA, la serie/folio, la forma de pago, los datos del timbrado y los de la cancelación; `invoice_items` guarda los conceptos con su parte gravable; `invoice_events` es la bitácora **append-only** de solicitudes, intentos de timbrado y cancelaciones. El borrador de `SolicitudFacturacion`/`ComprobanteFiscal` se colapsa en `invoices` para este incremento; se puede separar si el PAC exige varios comprobantes por solicitud.
- **Origen**: solo se factura una venta del POS (`origin_type = "sale"`) o un cobro de membresía confirmado (`origin_type = "membership_payment"`). Un origen inexistente responde `404`; uno no facturable (cancelado, no confirmado o ya facturado) responde `409`/`422`. El listado `/admin/billing/origins` ofrece solo las operaciones facturables (ventas completadas o devueltas y pagos confirmados), con búsqueda y paginación.
- **Montos e impuestos**: los precios del club se cobran con IVA incluido, así que el desglose se deriva del total (`base = round(total / (1 + tasa))`, `impuesto = total − base`, con `CFDI_TAX_RATE_PERCENT`, 16 por defecto). La suma de líneas cuadra con el total cobrado; si no cuadra, la solicitud se rechaza (`422`). El método de pago es `PUE` y la forma de pago del SAT se deriva del método de cobro (`cash` → 01, `transfer` → 03, `card` → 04, `account` → 99) o puede declararse.
- **Validación fiscal**: se validan RFC (forma 12/13), razón social, régimen fiscal, código postal y uso de CFDI contra los catálogos del SAT incluidos en `cfdi.py`; los datos se normalizan y se guardan como snapshot en la factura, de modo que editar el perfil después no altera un comprobante emitido. El emisor se configura por entorno (`GYM_RFC`, `GYM_LEGAL_NAME`, `GYM_TAX_REGIME`, `GYM_POSTAL_CODE`, `CFDI_CERTIFICATE_NUMBER`, `CFDI_SERIES`, `CFDI_TAX_RATE_PERCENT`, `CFDI_PRODUCT_CODE`, `CFDI_SERVICE_CODE`); los valores por defecto son marcadores con forma válida y **deben sustituirse** antes de un timbrado real.
- **Idempotencia y unicidad**: `POST /admin/billing/invoices` exige `idempotency_key`; repetir la misma clave con la misma solicitud devuelve la factura original con `idempotent_replay: true` y no consume folio ni duplica eventos; reutilizarla con otros datos responde `409`. Un índice único parcial (`uq_invoices_active_origin`, `status <> 'cancelled'`) impide una segunda factura viva por origen; una factura cancelada libera el origen para la sustitución y conserva folio e historial. El folio se asigna por serie (`A-000001`) con unicidad `(series, folio)`.
- **Timbrado**: `POST /admin/billing/invoices/{id}/stamp` (`billing.manage`) construye el XML CFDI 4.0 **pre-timbre** y lo envía al PAC; `GET .../{id}/xml` (`billing.read`) descarga el XML con `Content-Disposition` y `Cache-Control: no-store`. En `PREVIEW_MODE` o con `PAC_PROVIDER=simulated` se usa `SimulatedPac`, que devuelve el mismo XML con un comentario «SIMULACION» visible, **sin UUID ni TimbreFiscalDigital**, y marca la factura `is_simulated = true`. Un proveedor real sin adaptador responde `503`; un rechazo del PAC deja la factura `failed` con su evento y permite reintentar; una factura `stamped` no se vuelve a timbrar (devuelve la misma); una `cancelled` no se puede timbrar (`409`).
- **Cancelación**: `POST .../{id}/cancel` (`billing.manage`) solo acepta una factura `stamped`, exige un motivo del SAT (`01` sustitución, `02` error con relación, `03` no se llevó a cabo, `04` operación nominativa) y, si el motivo es `01`, el UUID del comprobante que sustituye; valida el formato y que sea distinto del cancelado, acepta una nota de hasta 300 caracteres y conserva la factura con su estado final, su motivo y su evento. No se elimina ningún comprobante.
- **Permisos**: `billing.read` (consultar facturas, orígenes y datos fiscales), `billing.request` (solicitar la factura y capturar el perfil fiscal) y `billing.manage` (timbrar y cancelar). Dueño, gerente y contador tienen los tres; recepción solo lectura y solicitud; entrenador y mantenimiento no participan.
- **API**: ocho rutas bajo `/admin/billing/*` (resumen, listado con filtros, alta, detalle, timbrado, cancelación, XML y orígenes) más `GET/PUT /admin/members/{member_id}/fiscal-profile`. El listado pagina, busca por folio/UUID/receptor/origen y filtra por estado; el resumen cuenta por estado y suma los importes timbrados y cancelados.
- **Panel web**: vista **Facturación** con indicadores, filtros, búsqueda y paginación; alta de factura con pestañas de origen (venta/cobro de membresía), búsqueda paginada de la operación, prellenado del perfil fiscal del socio, receptor de público en general (`XAXX010101000`), opción de guardar el perfil y de timbrar al momento; detalle con receptor, importes, conceptos, datos del timbrado, motivo de cancelación, línea de tiempo de eventos, descarga del XML y acciones de timbrar/reintentar y cancelar. La UI marca las facturas simuladas como **SIMULACIÓN** y advierte que no tienen validez fiscal. Rutas BFF bajo `/api/admin/billing/*` y `/api/admin/members/[memberId]/fiscal-profile`.
- **Datos de ejemplo**: `backend/seed_billing.py` crea cuatro facturas (venta timbrada, cobro de membresía timbrado, solicitud pendiente y factura cancelada) y un perfil fiscal de prellenado; es idempotente y solo siembra si no hay facturas.

### Reportes (incrementos primero a cuarto)

- **Entidades del borrador**: `ReporteFinanciero` **no** se creó como tabla. Los reportes son consultas agregadas que se calculan en cada petición sobre `sales`/`sale_items`/`sale_returns`/`cash_sessions`/`products`/`inventory_stock`/`inventory_movements`/`suppliers`/`purchase_orders`/`purchase_order_items` (Punto de venta e inventario), `payments`/`payment_attempts`/`memberships`/`membership_events`/`plans`/`members` (Membresías), `access_events` (Control de acceso), `class_sessions`/`class_reservations` (Clases), `workout_logs`/`body_measurements` (Rutinas) y `maintenance_records`/`maintenance_tickets`/`equipment` (Mantenimiento).
- **Seis reportes** despachados por nombre: `overview` (resumen del periodo), `revenue` (ingresos por día, método, categoría, producto y caja), `memberships` (socios, membresías, planes y cobros), `operations` (accesos por día y hora, clases y entrenamientos), `maintenance` (costo por tipo y equipo, tickets y preventivos) e `inventory` (valorización de existencias al corte, movimientos del periodo y compras por estado y proveedor). Cada uno devuelve el periodo resuelto en la respuesta.
- **Periodo**: `date_from` y `date_to` son **ambos inclusivos**, por defecto los últimos 30 días y con un máximo de 730, y se expresan en el **calendario del gimnasio** (`APP_TIMEZONE`, por defecto `America/Mexico_City`), no en UTC. La respuesta de cada reporte incluye `period.timezone` con la zona aplicada. Un rango invertido o demasiado largo responde `422` (`InvalidReportPeriod`); un reporte desconocido, `404` (`UnknownReport`). Las series diarias **rellenan todos los días** del periodo —días locales, incluidos los sin actividad— para que las gráficas no salten fechas.
- **Dinero cobrado vs. esperado**: los reportes separan lo **cobrado** —ventas de mostrador del POS más cobros de membresía confirmados— del **ingreso recurrente esperado** (`mrr_expected_cents`), que es el valor mensual de las membresías activas y **no** un cobro. Se etiqueta así en el panel para no presentar una estimación como ingreso real.
- **Regla de MRR**: equivalente mensual = `price_cents * 30 / interval_days`, donde `interval_days = billing_interval_days` o, si es nulo, `duration_days`. Los planes con `duration_days < 7` (por ejemplo `PLAN-DIA`) se excluyen por no ser recurrentes y se marcan `recurring = false`.
- **Devoluciones del POS**: los ingresos de mostrador son **netos** de las devoluciones. Se cuentan **todas** las ventas del periodo (también las que están en `refunded`: una venta devuelta sigue siendo una venta que se cobró) y se restan los reembolsos **por el periodo en que se pagaron** (`sale_returns.returned_at`), no por la fecha de la venta original —el mismo criterio de caja con que el turno de caja baja el efectivo esperado—. La respuesta expone `pos_gross_cents`, `refunds_cents` y `refunds_count` junto al `pos_cents` neto, y el neteo se aplica a la serie diaria, `pos_by_method`, `by_category` y `top_products`, de modo que las cinco desagregaciones (total, día, método, categoría y producto) **suman siempre `pos_cents`**. Un día con más devoluciones que ventas puede quedar negativo: la gráfica lo dibuja por debajo de la línea de cero y el CSV conserva el signo. `average_ticket_cents` es `ingresos brutos / ventas`. Como es base de caja, un reembolso pagado en un periodo para una venta de otro periodo resta en el periodo del pago; re-ejecutar un periodo ya consultado puede cambiar su neto si después se reembolsa una venta de ese periodo (los reportes son de consulta, no un cierre contable congelado).
- **Ventas sin conexión**: una venta sincronizada desde la cola offline entra a los reportes por su `sold_at` original (el instante en que se cobró), no por el momento en que se sincronizó; una venta del viernes enviada el lunes cae en el viernes. El campo `origin` (`online`/`offline`) no cambia los totales ni el neteo; solo permite auditarlas.
- **Ventas a cuenta del socio**: desde 2026-10-19 una venta puede tenderse con `payment_method = "account"`. Para los reportes es **ingreso devengado** (entra en `pos_gross_cents`/`pos_cents`) y aparece como una fila más en `pos_by_method` («Cuenta del socio»), pero **no es dinero cobrado**: no entra en el efectivo esperado del turno. Las devoluciones de una venta a cuenta se registran como `refund_method = "account"` y también restan en el neteo del periodo, igual que cualquier reembolso, aunque no muevan la caja. El saldo pendiente por cobrar es un **corte vivo** que se consulta en `GET /admin/member-accounts`, no un dato del periodo; desde el sexto incremento ese directorio expone la **antigüedad FIFO** del saldo y el **límite de crédito** por socio, con filtro de cuentas sobre límite.
- **Ocupación de clases**: `(reservadas + asistencias) / cupo * 100`, la misma definición del módulo de Clases; las **inasistencias** se reportan por separado y no cuentan como ocupación.
- **Accesos**: `manual` cuenta los eventos con `source = "manual"` (autorizados o no desde recepción) y `denegados` los que tienen `authorized = false`. El histograma por hora usa la hora local del gimnasio (`APP_TIMEZONE`).
- **Reporte de inventario** (`inventory`): la **valorización** —`stock_value_cents` (existencia × costo), `retail_value_cents` (× precio), `by_category` y `by_product`— es un **corte del estado actual** y **no** depende del periodo: el club guarda la existencia vigente en `inventory_stock`, no su valor día a día. El resto sí se acota a la ventana: los **movimientos** del ledger (`movements_by_type` con la cantidad neta por tipo, más `units_in`/`units_out` separando el signo) y las **compras** (`orders_created` y `orders_value_cents` por `created_at`, excluyendo canceladas; `orders_received`/`orders_received_value_cents` por `received_at`, de modo que solo cuentan las órdenes completadas dentro del periodo porque una recepción parcial no se fecha) y los **proveedores** (`suppliers_total`/`suppliers_active` al corte y `by_supplier` del periodo). «Bajo mínimo» y «agotado» usan la regla del resumen del POS: solo productos activos, `low` si `0 < existencia <= stock_min` y `out` si `existencia <= 0`. Un producto sin costo (`cost_cents` nulo) valoriza a cero.
- **Exportación CSV**: `GET /admin/reports/export` aplana la tabla principal de cada reporte (resumen → indicadores; ingresos → días; socios → planes; operación → días; mantenimiento → equipos; inventario → productos valorizados) y responde `text/csv` con `Content-Disposition` `reporte-{reporte}-{desde}-{hasta}.csv`. El CSV de ingresos lleva la columna `Devoluciones (MXN)` (el `Mostrador (MXN)` ya es neto) y el de resumen las filas `Ventas de mostrador` y `Devoluciones de mostrador` junto al neto.
- **Permisos**: se reutiliza `finance.read` ("Consultar reportes financieros"), ya sembrado y otorgado a dueño, gerente y contador, por lo que **no hay migración de RBAC**. Recepción, entrenador y mantenimiento reciben `403`. La exportación usa el mismo permiso (simplificación documentada).
- **API**: 7 rutas bajo `/admin/reports/*` (los seis reportes y la exportación), todas de solo lectura.
- **Panel web**: nueva entrada **Reportes** en la navegación de administración, visible con `finance.read`. La vista tiene pestañas Resumen / Ingresos / Socios / Operación / Mantenimiento / Inventario, un selector de periodo (7, 30, 90 días o personalizado), tarjetas de indicador, gráficas de barras por día y por hora, tablas de plan, de equipo y de existencias valorizadas, y descarga CSV a través de las rutas BFF bajo `/api/admin/reports/*`.
- **Datos de ejemplo**: `backend/seed_reports.py` backdatea 30 días de historia para que las gráficas tengan forma: abre y cierra un turno de caja por día registrando ventas por el servicio de inventario, escribe accesos con una curva horaria realista y reparte cobros y eventos de membresía. Es idempotente por bloque (se salta si ya hay filas con más de una semana de antigüedad).

Pendiente (documentado en `docs/deuda-tecnica.md`): reportes programados o por correo, el adaptador de un PAC real (el CFDI 4.0 individual existe, pero el timbrado actual es simulado y sin validez fiscal), factura global, notas de crédito, complemento de pago PPD, conciliación bancaria, PDF y envío por correo del CFDI, cobro recurrente real para que el MRR sea cobro y no valor esperado, desglose por sucursal, valorización histórica del inventario (el reporte de inventario es al corte) y exportación a otros formatos.

## 14. Estado

Primer incremento de reportes implementado, probado y conectado al panel (seis reportes, exportación CSV, permisos con `finance.read`, seeder de vista previa). El dinero de mostrador ya es **neto de devoluciones** (segundo incremento, 2026-10-18), las ventanas y cortes diarios ya usan **el calendario del gimnasio** (`APP_TIMEZONE`), no UTC (tercer incremento, 2026-10-18), y el **reporte de inventario** (cuarto incremento, 2026-10-19) lleva la valorización del stock, los movimientos del ledger y las compras al panel de Reportes. El **CFDI 4.0 individual** (quinto incremento, 2026-10-23) está implementado con perfiles fiscales, facturas para ventas y cobros de membresía, desglose de IVA, idempotencia, timbrado **simulado** y cancelación con motivo del SAT; el adaptador de un PAC real, la factura global, las notas de crédito, el complemento PPD y la conciliación de pagos siguen en diseño / validación contable.

## 15. Historial de cambios

- 2026-10-23: quinto incremento (CFDI 4.0 individual con timbrado simulado). Migración `20261023_0024_billing_cfdi.py`: tablas `member_fiscal_profiles`, `invoices`, `invoice_items` e `invoice_events`; permisos `billing.read`, `billing.request` y `billing.manage` (recepción consulta y solicita; dueño, gerente y contador timbran y cancelan). Se pueden facturar ventas del POS y cobros de membresía confirmados, con desglose de IVA incluido, folio por serie, idempotencia por clave y huella, una sola factura viva por origen y cancelación con motivo del SAT (01–04). El timbrado usa `SimulatedPac` en vista previa: XML pre-timbre con aviso de simulación, sin UUID ni validez fiscal; un PAC real sin adaptador responde `503`. Se agregó la vista Facturación con alta, detalle, descarga de XML y cancelación, el seeder `seed_billing.py` y `tests/test_billing_api.py` (suite de 112 pruebas). Siguen pendientes el PAC real, la factura global, las notas de crédito, el complemento PPD, la conciliación, el PDF y el envío por correo.
- 2026-10-19: se documentó el efecto de la **venta a cuenta del socio** en los reportes: entra como ingreso devengado y como método `account` en `pos_by_method`, pero no como efectivo cobrado; sus devoluciones restan en el neteo con `refund_method = "account"`. El saldo por cobrar se consulta aparte (corte vivo) y no forma parte del periodo.
- 2026-10-19: cuarto incremento de reportes (reporte de inventario). Se agregó el reporte `inventory`, de solo lectura y sin migración: **valorización al corte** del stock (`stock_value_cents` al costo, `retail_value_cents` a venta, desglose por categoría y por producto, más los conteos de activos/bajo mínimo/agotados con la regla del resumen del POS), **movimientos del periodo** del ledger (`movements_by_type` con cantidad neta, `units_in`/`units_out`) y **compras del periodo** (`orders_created`/`orders_value_cents` por `created_at` excluyendo canceladas, `orders_received`/`orders_received_value_cents` por `received_at`, órdenes abiertas y valor comprometido, proveedores activos y compra por proveedor). La valorización es un corte actual, no histórica: el periodo solo acota movimientos y compras. Se agregó la pestaña **Inventario** al panel (tarjetas de valor, tabla de existencias y listas de categoría, movimientos, órdenes y proveedores), la ruta BFF `/api/admin/reports/inventory` y la exportación CSV `reporte-inventory-…`. Prueba de API `test_inventory_report_valuates_stock_and_purchases`; la suite queda en 85 pruebas.

- 2026-10-18: tercer incremento de reportes (fronteras de día en la zona del gimnasio). Las ventanas `date_from`/`date_to`, la serie diaria y el histograma por hora se calculan en `APP_TIMEZONE` (por defecto `America/Mexico_City`) en vez de UTC; así una venta o devolución de la tarde cae en el día local correcto y un rango que termina «hoy» la incluye. La respuesta expone `period.timezone` y el panel lo muestra («Días y horas en …»). Se agregaron pruebas de los límites del periodo y del agrupamiento por día local.

- 2026-10-18: segundo incremento de reportes (neteo de devoluciones del POS). El mostrador cuenta todas las ventas del periodo y resta los reembolsos por el periodo en que se pagaron (base de caja), exponiendo brutos, devoluciones y neto; el neteo baja a la serie diaria, método, categoría y producto, con series que pueden quedar negativas. Se añadió la columna de devoluciones al CSV, se actualizó el panel (tarjetas de «Devoluciones», gráfica con línea de cero) y se agregó una prueba de API del neteo.
- 2026-10-18: primer incremento de reportes (resumen, ingresos, socios, operación y mantenimiento; filtro de periodo inclusivo; MRR esperado separado del dinero cobrado; exportación CSV; vista Reportes en el panel; permisos con `finance.read` sin migración; pruebas de API y seeder de vista previa). En ese momento el CFDI y la conciliación seguían en diseño (el CFDI individual se entregaría el 2026-10-23).
- 2026-10-15: documento ampliado con ciclo CFDI, factura global, conciliación, reportes y límites de alcance.
