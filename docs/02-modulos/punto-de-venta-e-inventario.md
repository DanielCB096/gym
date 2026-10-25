# Módulo 6: Punto de venta e inventario

## 1. Resumen y alcance

Este módulo cubre la operación de caja del gimnasio, la venta de productos y accesorios, el control de inventario, las devoluciones, la compra a proveedores y el cierre del turno. También soporta ventas desde la recepción con operación offline y sincronización posterior cuando hay cortes de conexión.

### Incluye
- catálogo de productos con SKU, variantes, precios y códigos de barras
- ventas por mostrador y cobro a cuenta del socio
- límite de crédito por socio y antigüedad de saldos (aging)
- estado de cuenta exportable (PDF/CSV) y envío por correo al socio
- historial de envíos del estado de cuenta y reintento de intentos fallidos o simulados
- recordatorios de cobranza para saldos con cargos de más de 30 días, con control de frecuencia
- corte de caja por turno
- devoluciones, ajustes y mermas
- inventario por ubicación y proveedor
- orden de compra y alertas por mínimo de stock

### No incluye
- compras de maquinaria pesada o gastos de operación general
- facturación avanzada de múltiples sucursales
- gestión de alimentos con regulación sanitaria compleja
- envío programado o automatizado por calendario; los recordatorios actuales se disparan manualmente en lote desde el panel
- reenvío de un estado de cuenta ya entregado (el historial solo reintenta intentos `failed` o `simulated`)

## 2. Actores y permisos

| Actor | Objetivo | Permisos clave |
|---|---|---|
| Recepcionista | vender y devolver productos | abrir caja, cobro, devoluciones y consultoría de inventario (sin `sales.credit`) |
| Gerente | supervisar ventas e inventario | ver ventas, ajustes, stock mínimo, órdenes y límites de crédito (`sales.credit`) |
| Contador | cierre y conciliación | revisar cortes, pagos, devoluciones y conciliación de caja |
| Socio | comprar producto por app o mostrador | seleccionar y pagar si la compra está habilitada |
| Proveedor | entregar mercancía | registrar entradas y entregas por orden de compra |

El límite de crédito se administra con el permiso `sales.credit` (dueño y gerente). Recepción conserva `sales.read`/`sales.manage` para vender y cobrar, pero no puede fijar ni quitar límites. Descargar el estado de cuenta y consultar su historial de envíos usa `sales.read` (también el contador puede auditarlo); **enviarlo, reintentarlo o enviar recordatorios de cobranza** usa `sales.manage`, porque son acciones operativas que salen del gimnasio y dejan bitácora.

## 3. Flujos de usuario paso a paso

### Flujo principal: venta en recepción
1. La recepcionista abre la caja y selecciona el turno activo.
2. Busca el producto por nombre, SKU o código de barras.
3. Agrega cantidades, aplica promociones si existen y valida stock disponible.
4. El sistema presenta el total y acepta forma de pago: tarjeta, efectivo, transferencia o cuenta del socio.
5. Se registra la venta, se descuenta el inventario y se cierra la venta con comprobante o ticket si aplica.
6. Al final del turno, el gerente o recepcionista hace el corte de caja.

### Flujo alterno: venta a cuenta del socio
1. El socio tiene pendiente un consumo adicional por producto o suplemento.
2. La recepción registra la venta y la carga a la cuenta del socio.
3. El sistema exige que el socio exista y esté activo y valida el límite de crédito: el cargo se acepta solo si `saldo + total <= límite`. Un límite vacío (`NULL`) significa «sin tope»; un límite `0` bloquea todo cargo. Si el cargo excede el límite, la venta se rechaza (`409`) y no se descuenta stock.
4. La operación queda reflejada en el estado de cuenta del socio y en la cuenta por cobrar; el panel muestra el crédito disponible, bloquea el cobro a cuenta cuando el carrito lo excede y agrupa el saldo por antigüedad (0–30, 31–60, 61–90 y +90 días) aplicando pagos y devoluciones FIFO a los cargos más antiguos. El pago posterior se registra contra la cuenta y queda vinculado al turno de caja.
5. Si el límite se reduce por debajo del saldo vigente, la cuenta queda «sobre límite»: la deuda se conserva y se bloquean nuevos cargos hasta cobrar o ampliar el límite.
6. Desde el estado de cuenta se puede descargar el corte en PDF o CSV o enviarlo al correo del socio. El envío registra destinatario, formato, fecha de corte, usuario y resultado (enviado, simulado o fallido) en `member_account_statement_deliveries`; en modo vista previa nunca se contacta un SMTP real.
7. El historial del estado de cuenta muestra los últimos intentos con su resultado, usuario, fecha y error. Un intento fallido o simulado se puede reintentar: se conservan el destinatario, el formato y la fecha de corte originales, y se agrega una fila nueva enlazada con `retry_of_id`; un envío ya entregado no se reintenta desde el historial para no duplicar correos financieros.
8. La pestaña «Cuentas por cobrar» ofrece «Recordatorios»: selecciona socios con cargos de más de 30 días, confirma el lote y el sistema envía el estado de cuenta con un texto de cobranza. Cada socio se procesa por separado; los que no tienen correo, ya pagaron o recibieron un recordatorio en los últimos 7 días se omiten con el motivo visible. Un fallo de transporte no cancela el resto del lote.

### Flujo de devolución
1. El cliente presenta el producto y la nota de compra.
2. El sistema valida si cumple la política de devolución.
3. Se generan el reembolso o saldo a favor según la política.
4. Se registra la devolución y el ajuste del inventario.

### Flujo de inventario y reabastecimiento
1. El gerente o recepción detecta stock bajo.
2. Se genera una orden de compra a proveedor.
3. Se registra la entrada cuando llega la mercancía.
4. Se ajusta el inventario y se actualizan las alertas.

### Flujo offline
1. Si hay corte de internet, el panel conserva el catálogo, los precios y el turno abierto en `localStorage` (se refrescan en cada carga exitosa).
2. La venta se arma y se cobra en efectivo, tarjeta o transferencia; la **cuenta del socio y las devoluciones quedan bloqueadas** porque requieren validar el saldo o las cantidades contra el servidor.
3. Al confirmar, la venta se guarda en una cola local con un identificador generado por el dispositivo (`client_reference`) y la marca de tiempo real de la operación; el stock local se descuenta para no prometer existencias que ya no hay.
4. La cola se muestra en un aviso del módulo con el total y el detalle de cada venta. El cierre del turno queda deshabilitado mientras haya ventas pendientes.
5. Al reconectar (o con el botón «Sincronizar»), el panel envía el lote a `POST /admin/sales/offline`. El backend registra cada venta con su fecha original, descuenta el stock y la vincula al turno abierto.
6. La sincronización es idempotente: reintentar el mismo lote devuelve `duplicate` para las ventas que ya entraron, sin volver a cobrar ni descontar stock. Las ventas rechazadas (por ejemplo, sin stock suficiente o un socio inactivo) se quedan en la cola con el motivo y se pueden descartar.


## 4. Pantallas / espacios

### 1. Catálogo de productos
- Objetivo: consultar artículos, variantes y precios
- Componentes: búsqueda, filtros, precios, stock, código de barras, categoría
- Estados: disponible, sin stock, inactivo, agotado

### 2. Carrito de venta
- Objetivo: sumar productos y cerrar la transacción
- Componentes: lista de productos, cantidades, descuentos, subtotal, total, forma de pago
- Estados: en edición, validado, pagado, pendiente

### 3. Caja / terminal bancaria
- Objetivo: cobrar con efectivo, tarjeta o transferencia
- Componentes: opciones de pago, terminal, monto, cambio, mensaje de aceptación
- Estados: abierta, cerrada, sincronizando, error

### 4. Inventario por ubicación
- Objetivo: revisar stock por salón, mostrador, almacén o bodega
- Componentes: nivel de stock, SKU, fecha última entrada, ventas del producto
- Estados: normal, mínimo, crítico, sin stock

### 5. Orden de compra y proveedores
- Objetivo: administrar abastecimiento
- Componentes: proveedor, costo, cantidad, fecha estimada, estado de orden
- Estados: creada, enviada, recibida, cancelada

### 6. Corte de caja
- Objetivo: cerrar turno y revisar diferencias
- Componentes: ventas por método de pago, efectivo en caja, diferencias, cierre final
- Estados: abierto, en validación, cerrado

### 7. Cuentas por cobrar y crédito
- Objetivo: consultar el saldo de los socios, su antigüedad y su límite de crédito
- Componentes: total por cobrar y saldo a favor, banda de antigüedad (0–30/31–60/61–90/+90 días), fecha de corte, filtro «sobre límite», columna de crédito, búsqueda de cualquier socio para asignar límite, estado de cuenta con editor de límite, descarga PDF/CSV, envío por correo con bitácora, historial de envíos con reintento y modal de recordatorios de cobranza por lote
- Estados: al corriente, sobre límite, sin límite, saldo a favor; envío enviado, simulado o fallido; reintento permitido solo para fallido o simulado; recordatorio enviado, simulado, omitido o fallido

## 5. Reglas de negocio y casos límite

### Reglas clave
- No se permite vender un producto si el stock disponible es menor a la cantidad solicitada.
- Cada movimiento de inventario debe quedar asociado a una venta, devolución, entrada, ajuste o merma.
- El turno de caja no se puede cerrar si hay ventas pendientes de sincronización o sin conciliación. El panel bloquea el cierre mientras la cola local tenga ventas; el backend no puede ver una cola que vive en el navegador.
- Una venta sin conexión se guarda en el navegador con un `client_reference` único; reintentar la sincronización no duplica el cobro ni el descuento de stock.
- Sin conexión solo se cobra en efectivo, tarjeta o transferencia: la cuenta del socio y las devoluciones requieren conexión.
- Las ventas sin conexión se vinculan al turno que está abierto cuando llegan al backend; los turnos cerrados son inmutables. Por eso el panel impide cerrar el turno con ventas pendientes.
- Una devolución requiere usuario responsable y motivo válido.
- Las ventas a cuenta del socio deben quedar vinculadas a su saldo y a la historia de pagos.
- Una devolución de una venta a cuenta se abona siempre a la cuenta: nunca sale efectivo por dinero que no se cobró.
- Un pago contra la cuenta no puede superar el saldo pendiente ni registrar montos negativos.
- La diferencia en efectivo debe quedar explicada por el operador en el cierre del turno.
- El límite de crédito es un tope del saldo resultante: un cargo a cuenta se acepta solo si `saldo + total <= límite`. `NULL` significa sin tope, `0` bloquea todo cargo y un límite negativo se rechaza (`422`).
- Reducir el límite por debajo del saldo no borra deuda: la cuenta queda «sobre límite» y los nuevos cargos se rechazan (`409`) hasta que se cobre o se amplíe el límite.
- La antigüedad del saldo se calcula al vuelo aplicando pagos y devoluciones FIFO a los cargos más antiguos; los cuatro tramos suman el saldo positivo y no se almacenan. Un saldo a favor deja todos los tramos en cero.
- La validación del límite también aplica a las ventas a cuenta que llegan por la sincronización offline; si el cargo excede el límite, esa venta se rechaza y el resto del lote continúa.
- El estado de cuenta se puede descargar en PDF o CSV con `sales.read`; el archivo se genera al momento y refleja el corte consultado, no una foto almacenada.
- Enviar el estado de cuenta exige `sales.manage` y un correo del socio (o un destinatario explícito); sin correo responde `422`. Cada intento queda en `member_account_statement_deliveries` con estado `sent`, `simulated` (vista previa) o `failed` y el error cuando aplica.
- El historial de envíos (`GET /admin/member-accounts/{member_id}/statement/deliveries`) se consulta con `sales.read`, devuelve los intentos del socio del más reciente al más antiguo con paginación (`page`/`page_size`), el correo del usuario que envió y `retry_of_id` cuando es un reintento.
- Reintentar (`POST /admin/member-accounts/{member_id}/statement/deliveries/{delivery_id}/retry`) exige `sales.manage`. Solo se aceptan intentos `failed` o `simulated`; un envío `sent` responde `409` para no duplicar correos financieros. El reintento conserva destinatario, formato, propósito y fecha de corte originales, crea una fila nueva (nunca modifica la anterior) y la enlaza con `retry_of_id`. Un envío de otro socio responde `404`. Si el propósito es `reminder`, el reintento se rechaza (`409`) cuando el socio ya no tiene saldo vencido.
- Los recordatorios de cobranza (`POST /admin/member-accounts/reminders`, `sales.manage`) aceptan hasta 50 socios por lote y un formato `pdf`/`csv`. Solo se envían si el socio tiene saldo positivo con algún cargo de más de 30 días, correo registrado y ningún recordatorio exitoso (`sent` o `simulated`) en los últimos 7 días. El lote procesa a cada socio por separado: los omitidos y fallidos se reportan con su motivo, y un fallo de transporte no cancela los demás.
- Cada recordatorio se guarda como una fila nueva con `purpose = "reminder"` en la misma bitácora append-only del estado de cuenta; no modifica el saldo ni los movimientos de la cuenta. El correo incluye el saldo total, el desglose vencido por antigüedad y el estado de cuenta adjunto.
- En modo vista previa el envío se simula incluso si hay SMTP configurado. En producción, si falta `SMTP_HOST` responde `503`; si el servidor SMTP falla, responde `502` y el fallo queda auditado.

### Casos límite
- Un producto llega con cantidad menor a la pedida por el proveedor. **Resuelto (2026-10-18):** la orden guarda la cantidad recibida por línea; una entrega parcial deja la orden abierta con el pendiente visible, y recibir más de lo pedido se rechaza (`409`).
- Hay dos ventas simultáneas del mismo SKU con stock bajo.
- Un socio intenta pagar con saldo insuficiente en su cuenta. **Resuelto (2026-10-19):** cada cargo a cuenta valida el límite de crédito (`saldo + venta <= límite`; `409` si lo excede). Sin límite (`NULL`) el saldo se acumula; con límite `0` no se acepta ningún cargo. El pago posterior también valida y rechaza superar el saldo pendiente (`409`).
- Se baja el límite de un socio por debajo del saldo que ya tiene. **Resuelto (2026-10-19):** se permite; la cuenta queda «sobre límite», se bloquean nuevos cargos y la deuda existente no se altera. El directorio permite filtrar por «sobre límite».
- Un pago o una devolución deja saldo a favor. **Resuelto (2026-10-19):** la antigüedad devuelve todos sus tramos en cero mientras el saldo sea negativo y el estado de cuenta muestra el saldo a favor.
- Una venta a cuenta se queda sin cupo mientras está en la cola offline. **Resuelto (2026-10-19):** el panel no permite cargar a cuenta sin red; si el lote llegara a enviar una venta a cuenta, el backend vuelve a validar el límite y la rechaza sin tumbar el resto del lote.
- Una venta a cuenta sin socio seleccionado o a un socio inactivo. **Resuelto (2026-10-19):** la venta exige socio (`422`) y rechaza a un socio inactivo (`404`).
- Se intenta devolver en efectivo una venta que se cargó a la cuenta. **Resuelto (2026-10-19):** se rechaza (`422`); la devolución se abona siempre a la cuenta (`refund_method = "account"`).
- La terminal bancaria falla en medio del cobro.
- Un trabajador intenta cerrar la caja sin no registrar una venta pendiente.
- Se corta internet a media venta. **Resuelto (2026-10-19):** la venta se guarda en la cola local con su fecha real y se envía al reconectar; el panel muestra el aviso y el total pendiente.
- Se reintenta sincronizar el mismo lote (doble clic, recarga o reintento tras un timeout). **Resuelto (2026-10-19):** `sales.client_reference` es único; el backend responde `duplicate` con el folio existente y no vuelve a cobrar ni a descontar stock.
- Una venta sin conexión ya no tiene stock suficiente al sincronizar. **Resuelto (2026-10-19):** se rechaza solo esa venta con el motivo; las demás del lote se registran y la rechazada queda en la cola para revisarla o descartarla.
- Se intenta cerrar el turno con ventas pendientes de sincronizar. **Resuelto (2026-10-19):** el panel deshabilita «Cerrar turno» mientras la cola tenga ventas, porque el backend no puede conocer una cola guardada en el navegador.
- Se intenta enviar el estado de cuenta a un socio sin correo. **Resuelto (2026-10-19):** la API responde `422` y el panel deshabilita los botones de envío; se puede indicar un destinatario explícito por API.
- El SMTP falla o no está configurado. **Resuelto (2026-10-19):** el intento se registra como `failed` con el error y la API responde `502` (fallo del servidor) o `503` (sin configuración). En vista previa se registra como `simulated` sin enviar datos reales.
- Se reintenta un envío que ya fue entregado. **Resuelto (2026-10-19):** el historial muestra el estado y la API responde `409`; para no duplicar un correo financiero, el reenvío de un `sent` requerirá un flujo explícito de confirmación (pendiente).
- Se intenta reintentar el envío de otro socio o un identificador inexistente. **Resuelto (2026-10-19):** la API responde `404` y no crea ninguna fila.
- Se intenta enviar un recordatorio a un socio sin correo, sin saldo o con saldo solo corriente. **Resuelto (2026-10-21):** el lote lo omite y devuelve el motivo (`skipped`); no crea fila de envío ni falla el resto de los socios.
- Se repite el recordatorio al mismo socio en pocos días. **Resuelto (2026-10-21):** se omite si ya hay un recordatorio `sent` o `simulated` en los últimos 7 días. Un intento `failed` no inicia el plazo y puede reintentarse.
- Falla el transporte para un socio dentro de un lote de recordatorios. **Resuelto (2026-10-21):** se registra `failed` con el error para ese socio y el lote continúa con los demás; la respuesta trae el resultado por socio.
- Se intenta reintentar un recordatorio después de que el socio pagó. **Resuelto (2026-10-21):** la API responde `409` y no envía un aviso de cobro obsoleto.

## 6. Entidades de datos

- Producto
- VarianteProducto
- CategoriaProducto
- Inventario
- MovimientoInventario
- Proveedor
- OrdenCompra
- DetalleOrdenCompra
- Venta
- DetalleVenta
- Devolucion
- Cortecaja
- MetodoPago
- CuentaSocio
- CobroCuentaSocio
- EnvioEstadoCuenta
- AntigüedadSaldo (calculada, no almacenada)

### Campos clave
- Producto: id, nombre, sku, categoria, precio_base, precio_venta, codigo_barras, stock_minimo
- Inventario: producto_id, ubicacion, stock_actual, stock_minimo, ultimo_movimiento
- Proveedor: id, nombre, contacto, telefono, correo, activo
- OrdenCompra: id, folio, proveedor_id, estado, subtotal, total, fecha_estimada, creada_por, recibida_por
- DetalleOrdenCompra: orden_id, producto_id, cantidad, cantidad_recibida, costo_unitario, importe
- Venta: id, socio_id, cajero_id, total, subtotal, impuesto, estado, metodo_pago, fecha, origen (`online`/`offline`), referencia_cliente
- Socio: id, nombre, contacto, estado, `credit_limit_cents` (`NULL` = sin límite; `0` = sin crédito)
- CuentaSocio: saldo calculado (cargos − devoluciones abonadas − pagos), `credit_limit_cents`, `credit_available_cents`, `over_limit` y antigüedad por tramos (0–30, 31–60, 61–90, +90 días)
- EnvioEstadoCuenta: id, socio_id, usuario_id, canal (`email`), destinatario, formato (`pdf`/`csv`), propósito (`statement`/`reminder`), fecha de corte, estado (`sent`/`simulated`/`failed`), error, `retry_of_id` (envío original cuando es un reintento) y fecha de creación
- CorteCaja: id, turno_id, apertura, cierre, efectivo_real, efectivo_esperado, diferencia, estado

## 7. Integraciones con otros módulos

- Membresías: venta de productos a cuenta del socio y saldo por cargo.
- Facturación: ventas y devoluciones pueden emitirse como CFDI cuando aplica.
- Comunicación: mensajes de stock bajo, promociones y confirmación de compra.
- Mantenimiento: productos o consumibles de limpieza se reflejan en inventario y costos.
- Control de acceso: si el socio compra un servicio o producto adicional, el sistema lo refleja en la app.

## 8. Notificaciones y automatizaciones

- Alertas por stock mínimo y stock crítico.
- Recordatorio de orden de compra pendiente.
- Aviso de corte de caja con diferencia.
- Envío manual del estado de cuenta del socio por correo (con bitácora de entregas).
- Recordatorios manuales de cobranza por lote para saldos con cargos de más de 30 días, con frecuencia máxima de un envío exitoso cada 7 días por socio.
- Promoción automática por categoría o producto.
- Confirmación de compra a socio por app o Notificación push.

## 9. Consideraciones de rendimiento específicas del módulo

- caché del catálogo con precios y stock para recepción y app
- validación del stock en backend para evitar doble venta
- transacciones para ventas y actualizaciones de inventario
- índices por `producto_id`, `categoria_id`, `ubicacion_id`, `fecha_venta`, `corte_id`
- procesamiento de reportes y cierres en segundo plano para no bloquear la caja
- tablas de venta con partición por mes si crece mucho el volumen

## 10. KPIs

- ticket promedio por venta
- ventas por categoría y producto
- rotación de inventario
- diferencia de caja por turno
- porcentaje de ventas a cuenta del socio
- socios sobre límite de crédito y crédito disponible agregado
- antigüedad del saldo por cobrar por tramo
- estados de cuenta enviados, fallos de entrega y reintentos
- recordatorios de cobranza enviados, omitidos por frecuencia y fallos
- tiempo de cierre de caja

## 11. Preguntas abiertas

- ¿la compra por app se habilitará en la primera fase o solo en mostrador?
- ~~¿se permiten devoluciones parciales o solo totales?~~ **Resuelto (2026-10-18):** se permiten por línea y en cualquier cantidad hasta lo vendido; la venta pasa a `refunded` solo cuando todas las líneas quedan totalmente devueltas.
- ¿deben contarse los productos de limpieza y consumibles dentro del inventario total del gimnasio?

## 12. Criterios de aceptación

- La venta solo se ejecuta si hay stock disponible y el cobro está validado.
- El inventario se actualiza después de cada transacción y cada movimiento queda registrado.
- El corte de caja no cierra si hay diferencias no explicadas o ventas pendientes.
- Las devoluciones quedan vinculadas al movimiento original y al ajuste de inventario.
- La venta offline queda sincronizada cuando regresa la conectividad.
- Ningún cargo a cuenta se registra si deja el saldo del socio por encima de su límite.
- La antigüedad del saldo aplica pagos y devoluciones FIFO y sus cuatro tramos suman el saldo positivo.
- El estado de cuenta se descarga en PDF/CSV con `sales.read` y se envía por correo con `sales.manage`, dejando bitácora del intento.
- El historial de envíos muestra los intentos del socio con su resultado, usuario, fecha y error; un intento fallido o simulado se puede reintentar sin modificar la fila original.
- Los recordatorios de cobranza solo se envían a socios con saldo positivo y cargos de más de 30 días, omiten a quienes no tienen correo o recibieron un recordatorio exitoso en los últimos 7 días, y reportan el resultado individual sin abortar el lote por un fallo.
- La caja, el inventario y la facturación quedan vinculados en una misma auditoría.

## 13. Implementación actual y límites

Primer incremento entregado (2026-10-17), limitado a operación en mostrador sin pasarela ni sincronización offline:

- **Persistencia**: seis tablas nuevas (`products`, `inventory_stock`, `inventory_movements`, `cash_sessions`, `sales`, `sale_items`) creadas por la migración `20261017_0008_pos_inventory.py`. El dinero se maneja siempre en centavos enteros.
- **Catálogo e inventario**: alta/edición de productos (`inventory.manage`), con SKU único sin distinguir mayúsculas, código de barras único y estado activo/inactivo. El stock vive en `inventory_stock` (una sola ubicación, `Mostrador`) y cada cambio se registra además en `inventory_movements` (tipos `intake`, `adjustment`, `waste`, `sale`), de modo que el saldo siempre se puede conciliar contra su historial. Un ajuste o merma exige motivo.
- **Ventas**: `POST /admin/sales` (`sales.manage`) valida stock y descuenta con un `UPDATE ... WHERE quantity + delta >= 0` atómico, así que dos ventas simultáneas del mismo SKU no pueden dejar el stock en negativo (`409`). Cada venta genera folio único `V-YYYYMMDD-XXXXXX` (la fecha es el **día local del gimnasio**, `APP_TIMEZONE`, no el día UTC: una venta de la tarde no cambia de fecha en el folio), guarda sus líneas y sus movimientos de inventario de tipo `sale`. Formas de pago: `cash`, `card` y `transfer`; el cobro es local (no toca terminal bancaria).
- **Turno de caja (corte)**: `POST /admin/cash-sessions` abre el turno (solo uno abierto a la vez) con fondo inicial; `POST /admin/cash-sessions/{id}/close` calcula el efectivo esperado (fondo + ventas en efectivo − devoluciones en efectivo + cobros de cuenta en efectivo + cobros de membresía en efectivo), registra el contado y la diferencia, y exige `notes` cuando la diferencia no es cero. Las ventas solo se registran con un turno abierto; sin turno responden `409`.
- **Permisos**: `inventory.read` / `inventory.manage` (catálogo) y `sales.read` / `sales.manage` (ventas y corte). Recepción vende, devuelve y consulta inventario; gerente administra catálogo y también vende; el contador solo lee. El catálogo de productos queda fuera del alcance de recepción, según la sección 2.
- **Panel web**: la vista Inventario muestra el catálogo con filtros y resumen, sus modales de alta/edición y de movimiento de stock, el carrito de venta con cobro, la apertura/cierre de turno, el historial de ventas y la pestaña de devoluciones, todo mediante rutas BFF.

Segundo incremento entregado (2026-10-18), cierra el ciclo de la venta con devoluciones y mermas:

- **Persistencia**: dos tablas nuevas (`sale_returns`, `sale_return_items`) creadas por la migración `20261018_0015_sale_returns.py`. Son append-only: una devolución nunca reescribe la venta, la referencia y guarda el precio al que se vendió cada línea. No se creó ningún permiso nuevo; el registro se opera con `sales.read` / `sales.manage`, que recepción ya tenía (sección 2).
- **Devoluciones**: `POST /admin/sales/{sale_id}/returns` (`sales.manage`) exige un turno de caja abierto (`409` si no lo hay), folio único `D-YYYYMMDD-XXXXXX` (fecha del **día local del gimnasio**, igual que las ventas), motivo obligatorio y una forma de reembolso (`cash`, `card`, `transfer`; por defecto la de la venta). Cada línea se identifica por `sale_item_id` y no puede devolver más unidades que las vendidas menos las ya devueltas (`409`). La fila de la venta se bloquea con `SELECT ... FOR UPDATE` para que dos devoluciones simultáneas no sobrepasen lo vendido.
- **Reingreso o merma**: cada línea devuelta elige destino `restock` (reingresa al inventario: movimiento `return` con signo positivo) o `write_off` (mercancía recibida y descartada: movimiento `return` `+qty` seguido de un `waste` `−qty`, de modo que el saldo neto no cambia pero el historial conserva la merma). El ledger de `inventory_movements` sigue cuadrando contra `inventory_stock`.
- **Estado de la venta**: una venta pasa a `refunded` solo cuando todas sus líneas quedaron totalmente devueltas; una devolución parcial la deja en `completed` y suma a su `refunded_cents`. Las devoluciones se listan en `GET /admin/sales/returns` (`sales.read`) con filtro por `sale_id` y búsqueda por folio, venta, socio o motivo.
- **Panel web**: la pestaña «Devoluciones» del módulo Inventario muestra el resumen acumulado por forma de reembolso y el historial de reembolsos y mermas; el botón «Devolver» de cada venta abre un modal para elegir cantidades y destino por producto. El turno muestra las devoluciones y el efectivo esperado ya neto.

El mostrador de los reportes financieros ya es **neto**: cada reembolso se resta del periodo en que se pagó (base de caja), no del periodo de la venta original. Ver `docs/02-modulos/facturacion-y-reportes.md` §13.

Tercer incremento entregado (2026-10-18), completa la mitad entrante del inventario con proveedores y órdenes de compra:

- **Persistencia**: tres tablas nuevas (`suppliers`, `purchase_orders`, `purchase_order_items`) creadas por la migración `20261018_0016_suppliers_purchase_orders.py`. No se creó ningún permiso nuevo: se opera con `inventory.read` / `inventory.manage`. La recepción de mercancía reutiliza el ledger existente con movimientos tipo `intake` marcados con `reference_type = "purchase_order"`, así que no hizo falta tocar el `CHECK` de tipos de movimiento (ni la base de vista previa).
- **Proveedores**: `POST/PATCH /admin/suppliers` (`inventory.manage`) y `GET /admin/suppliers` (`inventory.read`) con nombre único sin distinguir mayúsculas, contacto, teléfono, correo, notas y estado activo/inactivo. Un proveedor inactivo conserva su historial pero no acepta órdenes nuevas (`422`).
- **Órdenes de compra**: `POST /admin/purchase-orders` (`inventory.manage`) crea la orden en estado `created` con folio único `OC-YYYYMMDD-XXXXXX` (día local del gimnasio, igual que `V-` y `D-`), valida que haya al menos una línea, que cada producto exista, que la cantidad sea positiva y que un producto no se repita en la misma orden. Guarda un snapshot de nombre y SKU por línea y el total como suma de `cantidad × costo_unitario`. Estados: `created → sent → received`, con `cancelled` mientras nada se haya recibido.
- **Envío y cancelación**: `POST /admin/purchase-orders/{id}/send` marca `sent` (solo desde `created`); `POST /admin/purchase-orders/{id}/cancel` cancela solo si no hay mercancía recibida (`409` en caso contrario).
- **Recepción**: `POST /admin/purchase-orders/{id}/receive` acepta cantidades por línea (`item_id`), rechaza líneas ajenas a la orden y recibir más de lo pedido (`409`), sube `inventory_stock` con un movimiento `intake`, actualiza el `received_quantity` de la línea y refresca el costo de reposición del producto al último costo recibido. Cuando todas las líneas quedan completas la orden pasa a `received` y registra quién y cuándo; una entrega parcial la deja abierta (y la marca `sent` si aún estaba `created`).
- **Consulta**: `GET /admin/purchase-orders` (`inventory.read`) pagina y filtra por estado y proveedor, con búsqueda por folio o proveedor, y resume por estado un valor comprometido que excluye las órdenes canceladas. `GET /admin/purchase-orders/{id}` devuelve el detalle con sus líneas.
- **Panel web**: la pestaña «Compras» del módulo Inventario muestra los indicadores por estado, la tabla de órdenes con acciones Enviar/Recibir/Cancelar, el directorio de proveedores y los modales de alta/edición de proveedor, de nueva orden (líneas con producto, cantidad y costo) y de recepción con cantidades por línea.

Cuarto incremento entregado (2026-10-19), cierra el ciclo de la venta a cuenta del socio (cuentas por cobrar):

- **Persistencia**: una tabla nueva (`member_account_payments`) creada por la migración `20261019_0017_member_accounts.py`, más la ampliación de dos `CHECK` existentes para aceptar `account` como forma de pago de la venta (`sales.payment_method`) y de la devolución (`sale_returns.refund_method`). No se creó ningún permiso nuevo: la consulta usa `sales.read` y el cobro `sales.manage`.
- **Cargo a cuenta**: `POST /admin/sales` acepta `payment_method = "account"`. Exige un socio (`422` si falta) que no esté inactivo (`404`) y descuenta el stock igual que una venta normal. El importe **no** suma a efectivo, tarjeta ni transferencia del turno; el turno lo muestra aparte como «ventas a cuenta».
- **Saldo**: no se guarda un saldo. Se calcula al vuelo como `Σ ventas a cuenta − Σ devoluciones abonadas a la cuenta − Σ pagos`, de modo que la cuenta no puede desviarse de los documentos que la originaron. Un saldo negativo (a favor del socio) solo puede nacer de una devolución, nunca de un pago.
- **Devolución**: la devolución de una venta a cuenta se abona **siempre** a la cuenta (`refund_method = "account"`); pedir efectivo, tarjeta o transferencia responde `422` porque el dinero nunca se cobró. El importe reduce el saldo del socio y no toca el efectivo esperado.
- **Cobro**: `POST /admin/member-accounts/{member_id}/payments` (`sales.manage`) registra un pago con método `cash`, `card` o `transfer`, monto positivo y nota opcional. Exige un turno de caja abierto (`409`), se vincula a ese turno y rechaza pagos que superen el saldo (`409`) o cuando no hay saldo pendiente (`409`). Un pago en efectivo sube el efectivo esperado del corte; tarjeta y transferencia solo bajan la cuenta por cobrar.
- **Consulta**: `GET /admin/member-accounts` (`sales.read`) pagina y busca socios con saldo distinto de cero, y resume el total por cobrar y el saldo a favor. `GET /admin/member-accounts/{member_id}` devuelve el estado de cuenta con cada cargo, devolución y pago y el saldo corrido después de cada movimiento (más reciente primero); el sexto incremento agrega la antigüedad por tramos, el límite y el filtro por sobre límite.
- **Panel web**: la pestaña «Cuentas por cobrar» del módulo Inventario muestra el total por cobrar, los socios con saldo y el estado de cuenta en un modal con formulario de cobro. El carrito agrega la forma de pago «Cuenta del socio» (exige socio y muestra su saldo); el modal de devolución bloquea la forma de reembolso a «Cuenta del socio» cuando la venta original fue a cuenta.

Quinto incremento entregado (2026-10-19), habilita la venta sin conexión con sincronización posterior:

- **Persistencia**: dos columnas nuevas en `sales` (`origin` con CHECK `online`/`offline` y `client_reference` único) creadas por la migración `20261019_0018_offline_sales.py`. No hay tabla de cola en el servidor: la cola vive en el navegador del mostrador. No se creó ningún permiso nuevo.
- **Sincronización**: `POST /admin/sales/offline` (`sales.manage`) recibe un lote de hasta 100 ventas con `client_reference`, `sold_at`, líneas, forma de pago, socio y nota. Exige un turno abierto (`409`) y procesa cada venta por separado: `created`, `duplicate` o `rejected`, de modo que una venta mala no tumba al resto del lote. La respuesta es `200` si el lote se pudo procesar; el detalle por venta va en `results`.
- **Idempotencia**: `client_reference` es único. Reintentar un lote devuelve `duplicate` con el folio ya creado; no se duplican ventas, stock ni efectivo.
- **Fecha original**: cada venta conserva el `sold_at` capturado por el dispositivo; el folio `V-…` usa el día local de esa fecha, así que una venta del viernes sincronizada el lunes queda con folio del viernes. El turno que la recibe es el que está abierto al sincronizar (los turnos cerrados no se reabren ni se recalculan).
- **Validaciones**: se rechazan fechas con más de 5 minutos en el futuro (reloj mal configurado). El resto de las reglas es el mismo `register_sale`: stock atómico, socio activo y límite de crédito para `account`, etc. Una venta rechazada conserva su lugar en la cola con el motivo.
- **Consulta**: `GET /admin/sales` acepta `origin=online|offline` para auditar el origen, y cada venta expone `origin` y `client_reference` en la respuesta.
- **Panel web**: el POS detecta la falta de red (evento `offline` o respuesta `502/503/504`), guarda la venta en `localStorage` y muestra un aviso con el pendiente. Al reconectar sincroniza automáticamente y ofrece un botón manual. El catálogo y el turno se cachean; sin conexión se bloquean la cuenta del socio y las devoluciones, y el cierre del turno queda deshabilitado. Las ventas sincronizadas se marcan «Offline» en el historial.

Sexto incremento entregado (2026-10-19), agrega **límite de crédito por socio y antigüedad de saldos**:

- **Persistencia**: `members.credit_limit_cents` (BIGINT nullable; `NULL` = sin límite, `0` = sin crédito) con el CHECK `ck_members_credit_limit` (`>= 0`), creado por la migración `20261019_0019_credit_limits.py`. La antigüedad **no** crea tabla ni se almacena: se calcula al leer la cuenta desde las ventas a cuenta, las devoluciones abonadas y los pagos. Se agregó el permiso `sales.credit` («Administrar límites de crédito de socios»), otorgado solo a dueño y gerente; recepción conserva `sales.read`/`sales.manage`.
- **Validación del cargo**: `register_sale` —tanto en línea como en la sincronización offline— calcula el saldo actual y exige `saldo + total <= límite` cuando hay límite. Un exceso responde `409` con el disponible y el tope; un límite negativo responde `422`. `NULL` mantiene el comportamiento anterior (sin tope), de modo que los socios existentes no quedan bloqueados por la migración.
- **Sobre límite**: bajar el límite por debajo de un saldo existente se permite. La cuenta queda `over_limit` y el backend rechaza nuevos cargos (`409`) hasta que se cobre o se amplíe el límite; la deuda no se borra ni se renegocia automáticamente. El directorio ordena primero las cuentas sobre límite.
- **Antigüedad**: `AccountAging` agrupa el saldo en `current_cents` (0–30 días), `days_31_60_cents` (31–60), `days_61_90_cents` (61–90) y `over_90_cents` (+90), calculados con la **fecha local del gimnasio** (`club_date`). Pagos y devoluciones se aplican **FIFO** a los cargos más antiguos; la suma de los tramos es el saldo positivo y un saldo a favor deja todo en cero. Se expone por socio y agregada en el directorio.
- **Consulta**: `GET /admin/member-accounts` acepta `over_limit=true|false`, devuelve `aging`, `over_limit_members` y `as_of` (fecha local del corte), y cada socio incluye `credit_limit_cents`, `credit_available_cents` (puede ser negativo si está excedido), `over_limit` y su `aging`. `GET /admin/member-accounts/{member_id}` devuelve lo mismo en el estado de cuenta.
- **Administración del límite**: `PATCH /admin/member-accounts/{member_id}/credit-limit` (`sales.credit`) recibe `credit_limit_cents` (`>= 0` o `null` para quitar el tope) y devuelve el resumen actualizado. Responde `404` si el socio no existe y `422` si el límite es negativo. No exige que el socio tenga saldo: el panel busca en todo el directorio de socios para fijar el primer límite.
- **Panel web**: la pestaña «Cuentas por cobrar» agrega la columna CRÉDITO, el filtro «Sobre límite», la banda de antigüedad y la fecha de corte; el botón «Asignar límite» busca cualquier socio (también sin saldo) y abre su cuenta. El estado de cuenta muestra límite, disponible, antigüedad y un formulario para fijar o quitar el límite (solo con `sales.credit`). El POS muestra «Crédito disponible…» al elegir la cuenta y deshabilita «Cargar a cuenta» cuando el carrito excede el disponible; el backend vuelve a validar el límite.
- Se agregó `backend/tests/test_credit_limits_api.py` (permisos y ciclo del límite, bloqueo y liberación de crédito, FIFO con fronteras de antigüedad, límite reducido/sobre límite y rechazo de una venta offline por límite); la suite queda en **95 pruebas** (98 al cierre del séptimo incremento).

Séptimo incremento entregado (2026-10-19), agrega el **estado de cuenta exportable y el envío al socio**:

- **Persistencia**: tabla `member_account_statement_deliveries` creada por la migración `20261019_0020_statement_deliveries.py`, con destinatario, formato (`pdf`/`csv`), fecha de corte, estado (`sent`/`simulated`/`failed`), error y usuario. No se creó ningún permiso nuevo: exportar usa `sales.read` y enviar `sales.manage`.
- **Exportación**: `GET /admin/member-accounts/{member_id}/statement.pdf` y `.csv` (`sales.read`) generan el documento al momento con el resumen, el límite, la antigüedad y los movimientos (del más antiguo al más reciente). El PDF se arma con ReportLab y el CSV es UTF-8 con BOM para Excel; las celdas de texto del CSV neutralizan fórmulas (prefijo `'` ante `=`, `+`, `-`, `@`, tabulador, retorno de carro o salto de línea) y ambos responden `Content-Disposition` con `estado-cuenta-{socio}-{corte}.{ext}` y `Cache-Control: no-store`.
- **Envío**: `POST /admin/member-accounts/{member_id}/statement/send` (`sales.manage`) acepta `format` (`pdf`/`csv`) y un `recipient` opcional; por defecto usa el correo del socio. Sin correo responde `422`. Configura el transporte con `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS`, `SMTP_USE_SSL` y `SMTP_TIMEOUT`; sin `SMTP_HOST` en producción responde `503`, un fallo SMTP responde `502` y el intento queda como `failed`.
- **Vista previa**: con `PREVIEW_MODE=true` el envío se registra como `simulated` y nunca contacta un servidor real, para no enviar estados financieros durante una demo.
- **Panel web**: el modal de estado de cuenta agrega «Descargar PDF», «Descargar CSV», «Enviar PDF» y «Enviar CSV» (los envíos solo con `sales.manage` y correo disponible), con aviso del resultado y mensaje de error. Rutas BFF nuevas `/api/admin/member-accounts/{memberId}/statement` y `/statement/send`; la descarga reenvía los bytes tal cual (sin decodificar el PDF) y conserva `no-store`.
- Se agregó `backend/tests/test_member_statement_api.py` (exportación CSV/PDF y permisos, simulación con bitácora, destinatario explícito, rechazos, envío SMTP con transporte simulado y fallo auditado); la suite del backend queda en **98 pruebas** al cierre del séptimo incremento.

Octavo incremento entregado (2026-10-19), agrega el **historial de envíos y el reintento del estado de cuenta**:

- **Persistencia**: la migración `20261019_0021_statement_delivery_retries.py` agrega `retry_of_id` a `member_account_statement_deliveries`, una FK autorreferente con `ON DELETE SET NULL`. El historial sigue siendo append-only: un reintento crea una fila nueva y enlaza la anterior; nunca reescribe el intento fallido o simulado.
- **Consulta**: `GET /admin/member-accounts/{member_id}/statement/deliveries` (`sales.read`) pagina con `page` y `page_size` (máximo 100), ordena del más reciente al más antiguo y devuelve destinatario, formato, fecha de corte, estado, error, `retry_of_id` y el correo del usuario que envió. Un socio inexistente responde `404`.
- **Reintento**: `POST /admin/member-accounts/{member_id}/statement/deliveries/{delivery_id}/retry` (`sales.manage`) reutiliza destinatario, formato y fecha de corte del intento original. Solo acepta `failed` o `simulated`; un `sent` responde `409` y un envío de otro socio o inexistente responde `404`. Si el transporte vuelve a fallar, se registra otro `failed` enlazado.
- **Panel web**: el modal de estado de cuenta agrega el historial de los últimos 10 intentos con etiqueta de estado, destinatario, formato, fecha, corte, usuario y error; los intentos fallidos o simulados muestran «Reintentar» solo con `sales.manage`. Rutas BFF nuevas `/api/admin/member-accounts/{memberId}/statement/deliveries` y `/deliveries/{deliveryId}/retry`.
- Se amplió `backend/tests/test_member_statement_api.py` (historial paginado y ordenado, permisos de lectura, reintento de un fallo SMTP real, reintento simulado, enlace `retry_of_id`, rechazo de `sent` y de un envío ajeno); la suite del backend queda en **99 pruebas**.

Noveno incremento entregado (2026-10-21), agrega los **recordatorios de cobranza para saldos vencidos**:

- **Persistencia**: la migración `20261021_0022_statement_reminders.py` agrega `purpose` (`statement`/`reminder`) a `member_account_statement_deliveries`, con `CHECK`, valor por defecto `statement` e índice por socio, propósito y fecha. Los envíos existentes quedan como estados de cuenta; la bitácora sigue siendo append-only.
- **Elegibilidad**: un recordatorio solo se envía si el socio tiene saldo positivo con algún cargo de más de 30 días, correo registrado y ningún recordatorio exitoso (`sent` o `simulated`) en los últimos 7 días. Un intento `failed` no inicia el plazo. El backend vuelve a validar el saldo y la antigüedad al enviar, de modo que un reintento después de pagar responde `409`.
- **API**: `POST /admin/member-accounts/reminders` (`sales.manage`) acepta `member_ids` (1 a 50, se deduplican) y `format` (`pdf`/`csv`). Procesa cada socio por separado y devuelve `requested`, `sent`, `simulated`, `skipped`, `failed` y el resultado individual con saldo, importe vencido, motivo y envío creado. Un socio inexistente, sin correo, sin saldo vencido o en periodo de espera se reporta como `skipped`; un fallo de transporte se registra como `failed` y no cancela el lote.
- **Correo**: el recordatorio usa el mismo estado de cuenta adjunto y un texto de cobranza con el saldo total y el desglose 31–60, 61–90 y +90 días. En vista previa se registra como `simulated` y no contacta SMTP.
- **Panel web**: la pestaña «Cuentas por cobrar» agrega «Recordatorios», un modal que lista los socios con saldo vencido, preselecciona a los que tienen correo, permite elegir formato, exige una segunda confirmación y muestra el resultado por socio. El historial del estado de cuenta distingue «Estado de cuenta» de «Recordatorio». Ruta BFF nueva `/api/admin/member-accounts/reminders`.
- Se agregó `backend/tests/test_collection_reminders_api.py` (permisos y validación del lote, elegibilidad por antigüedad, omisión por correo y cooldown, envío simulado, reintento con propósito preservado y bloqueo tras el pago, y continuación del lote ante un fallo de transporte); la suite del backend queda en **103 pruebas**.

Décimo incremento entregado (2026-10-21), agrega el **cobro manual y la renovación de membresía en mostrador**:

- **Persistencia**: la migración `20261021_0023_membership_manual_payments.py` agrega `period_starts_at`, `period_ends_at`, `cash_session_id`, `collected_by` y `note` a `payments`, y relaja el CHECK de `payment_attempts` para aceptar tarjeta declarada sin token (`method <> 'card' OR payment_method_id IS NOT NULL OR provider IS NULL`). El intento manual usa `provider = NULL`; no se creó una tabla de pagos paralela.
- **API**: `POST /admin/members/{member_id}/membership/payments` (`members.manage`) registra el cobro, confirma el pago y crea o renueva la membresía en una sola transacción. Acepta `plan_id` opcional (si falta conserva el plan actual), `payment_method` (`cash`/`card`/`transfer`), `idempotency_key` obligatoria, `note` y `auto_renew`. Activa al socio pendiente, crea la membresía si no existe o extiende `ends_at` desde `max(ahora, vencimiento)`; no permite cobrar membresías `frozen`, `suspended` o `pending_payment` (`409`).
- **Turno de caja**: todo cobro manual exige un turno abierto (`409`) y se vincula con `cash_session_id`. Solo el efectivo entra al efectivo esperado; tarjeta y transferencia se registran como declaradas y quedan en el indicador de membresías del turno. El cierre suma los cobros de membresía en efectivo y también corrige la suma de los cobros de cuenta en efectivo.
- **Idempotencia**: repetir la misma clave devuelve el pago original con `idempotent_replay: true`; reutilizarla con otro socio, plan, método o nota responde `409`. El panel conserva la clave mientras no cambie el formulario, para que un reintento tras una respuesta perdida no cobre dos veces.
- **Panel web**: la ficha del socio agrega forma de pago, importe, nota y los botones **Cobrar y activar/Cobrar renovación**, con confirmación previa. La activación o el cambio de plan sin cobro queda como cortesía secundaria y auditada. El turno muestra `MEMBRESÍAS` por separado; los totales POS (`sales_count`, `total_sales_cents`) siguen contando solo ventas de productos.
- Se agregó `backend/tests/test_membership_payments_api.py` (activación y renovación con efectivo/tarjeta, idempotencia, efecto en el turno y cierre, permisos, turno obligatorio, plan/método inválidos, membresía congelada y conflicto de clave); la suite del backend queda en **105 pruebas**.

Pendiente (documentado en `docs/deuda-tecnica.md`): códigos de barras/variantes avanzadas, promociones e impuestos, terminal bancaria real, facturación automática al cerrar la venta (hoy la venta se factura manualmente desde Facturación y puede acreditarse con nota de crédito), CFDI de compras, sincronización multi-dispositivo, resolución asistida de ventas rechazadas, reenvío confirmado de estados ya entregados, envío programado/automático por calendario y automatización de cobranza con reglas por antigüedad o promesas de pago.

## 14. Estado

Diez incrementos implementados y probados: catálogo, inventario con historial, ventas en mostrador y corte de caja (2026-10-17); devoluciones y mermas vinculadas a la venta original y al ajuste de inventario (2026-10-18); proveedores con órdenes de compra y recepción de mercancía que sube el stock y ajusta el costo de reposición (2026-10-18); venta a cuenta del socio con estado de cuenta, cobros vinculados al turno y devoluciones que abonan a la cuenta (2026-10-19); venta sin conexión con cola local, sincronización idempotente y bloqueo del cierre de turno (2026-10-19); límite de crédito por socio, bloqueo de cargos sobre el límite y antigüedad de saldos FIFO (2026-10-19); estado de cuenta exportable en PDF/CSV y envío por correo con bitácora (2026-10-19); historial de envíos con reintento de intentos fallidos o simulados (2026-10-19); recordatorios de cobranza por lote con control de frecuencia (2026-10-21); y cobro manual y renovación de membresía en mostrador con turno obligatorio (2026-10-21). Todos los flujos descritos en este documento quedan cubiertos.

## 15. Historial de cambios

- 2026-10-21: décimo incremento: cobro manual y renovación de membresía en mostrador. Migración `20261021_0023` (`payments` con periodo, turno, cobrador y nota; `payment_attempts` acepta tarjeta declarada sin token); `POST /admin/members/{member_id}/membership/payments` (`members.manage`, idempotente, con turno abierto y renovación desde el vencimiento); el cierre del turno suma los cobros de membresía y de cuenta en efectivo; botones **Cobrar y activar/Cobrar renovación** y confirmación en la ficha del socio; pruebas de API (105 en total).
- 2026-10-21: noveno incremento: recordatorios de cobranza para saldos vencidos. `member_account_statement_deliveries.purpose` (`statement`/`reminder`, migración `20261021_0022`); `POST /admin/member-accounts/reminders` (`sales.manage`, hasta 50 socios, elegibilidad por antigüedad/correo/cooldown de 7 días, resultado individual); correo de cobranza con desglose de antigüedad y estado de cuenta adjunto; modal «Recordatorios» en cuentas por cobrar; etiqueta de propósito en el historial; pruebas de API.
- 2026-10-19: octavo incremento: historial de envíos del estado de cuenta y reintento. `member_account_statement_deliveries.retry_of_id` (migración `20261019_0021`); `GET /admin/member-accounts/{member_id}/statement/deliveries` (`sales.read`, paginado, más reciente primero, con correo del usuario); `POST .../deliveries/{delivery_id}/retry` (`sales.manage`, solo `failed`/`simulated`, conserva destinatario/formato/corte y enlaza el intento original); historial con acción «Reintentar» en el modal del panel; pruebas de API.
- 2026-10-19: séptimo incremento: estado de cuenta exportable (PDF/CSV) y envío al socio. Tabla `member_account_statement_deliveries` (migración `20261019_0020`); `GET /admin/member-accounts/{member_id}/statement.pdf|.csv` (`sales.read`); `POST /admin/member-accounts/{member_id}/statement/send` (`sales.manage`) con SMTP configurable o simulación en vista previa; bitácora de envíos y botones de descarga/envío en el panel; ReportLab como dependencia; pruebas de API.
- 2026-10-19: sexto incremento: límite de crédito por socio y antigüedad de saldos. `members.credit_limit_cents` con CHECK y permiso `sales.credit` (migración `20261019_0019`); validación `saldo + total <= límite` en ventas en línea y offline (`409`); cuentas sobre límite bloqueadas; antigüedad FIFO 0–30/31–60/61–90/+90 calculada con la fecha local; filtro `over_limit`; `PATCH /admin/member-accounts/{member_id}/credit-limit`; columna, banda, editor de límite y bloqueo del POS; pruebas de API.
- 2026-10-19: quinto incremento: venta sin conexión con sincronización posterior. `sales.origin` y `sales.client_reference` único (migración `20261019_0018`); `POST /admin/sales/offline` procesa lotes con resultado por venta (`created`/`duplicate`/`rejected`); fecha original y folio por día local; cola en `localStorage` con aviso, sincronización automática/manual, caché de catálogo y turno, bloqueo de cuenta/devoluciones sin red y del cierre de turno con pendientes; marca «Offline» en el historial; pruebas de API.
- 2026-10-19: cuarto incremento: venta a cuenta del socio (cuentas por cobrar). `sales.payment_method` y `sale_returns.refund_method` aceptan `account`; tabla `member_account_payments`; saldo calculado como cargos − devoluciones − pagos; cobros con turno abierto y vínculo al efectivo esperado; estado de cuenta y pestaña «Cuentas por cobrar» en el panel; pruebas de API.
- 2026-10-19: el módulo de reportes suma el reporte `inventory` (valorización al corte del stock de estos datos, movimientos del ledger y compras del periodo). Es de solo lectura y no cambia nada de este módulo (ver `docs/02-modulos/facturacion-y-reportes.md` §13).
- 2026-10-18: tercer incremento: proveedores y órdenes de compra (tablas `suppliers`/`purchase_orders`/`purchase_order_items`, migración `20261018_0016`), folio `OC-…` con día local, estados creada/enviada/recibida/cancelada, recepción parcial con actualización del costo de reposición, pestaña «Compras» en el panel y pruebas de API.
- 2026-10-18: los folios `V-…` y `D-…` pasan a usar la fecha del **día local del gimnasio** (`APP_TIMEZONE`) en vez de UTC, para que coincidan con el día que ve el operador y con los reportes; el instante guardado sigue en UTC. Se agregó una prueba del folio con una venta «de la tarde» y su devolución.
- 2026-10-18: el módulo de reportes ya netea las devoluciones del POS (base de caja, por `returned_at`); se retira el límite de que las devoluciones parciales no aparecían en los reportes (ver `docs/02-modulos/facturacion-y-reportes.md`).
- 2026-10-18: segundo incremento: devoluciones y mermas de venta (tablas `sale_returns`/`sale_return_items`, migración `20261018_0015`), reingreso a stock o baja con merma, folio `D-…`, vínculo al turno de caja y neteo del efectivo esperado, estado `refunded` en devolución total, pestaña de devoluciones en el panel y pruebas de API.
- 2026-10-17: primer incremento de implementación (catálogo, inventario con ledger, ventas en mostrador y corte de caja) con permisos `inventory.read/manage` y `sales.read/manage`, migración `20261017_0008`, API, panel web y pruebas de API.
- 2026-10-15: documento ampliado con flujos, pantallas, políticas, integraciones y criterios de aceptación.
