# Modelo de datos

## Principios del modelo

- Este diagrama es conceptual; nombres y cardinalidades deben convertirse en un esquema físico y migraciones antes de implementar.
- Cada entidad persistente usa identificador estable. Las fechas se almacenan en UTC y se presentan en la zona horaria del gimnasio.
- Los importes se guardan en centavos enteros o decimal exacto, nunca en `float`; cada monto conserva moneda.
- Los eventos históricos, pagos, accesos y comprobantes no se eliminan. Se conserva su estado y las relaciones de corrección o cancelación.
- Un intento de cobro no equivale a un pago confirmado; un pago confirmado tampoco equivale a un CFDI timbrado.
- El stock se explica con movimientos de inventario; cualquier saldo materializado debe poder reconciliarse contra esos movimientos.
- Los estados fiscales, cobros, ventas y accesos son dominios separados, aunque se relacionen mediante claves explícitas.

## Diagrama ER conceptual (Mermaid)

```mermaid
erDiagram
SOCIO ||--o{ MEMBRESIA_SOCIO : tiene
PLAN ||--o{ MEMBRESIA_SOCIO : define
SOCIO ||--o{ CREDENCIAL_ACCESO : usa
SOCIO ||--o{ ACCESO_REGISTRO : genera
LECTOR_ACCESO ||--o{ ACCESO_REGISTRO : registra
MEMBRESIA_SOCIO ||--o{ INTENTO_COBRO : programa
MEMBRESIA_SOCIO ||--o{ PAGO : recibe
SOCIO ||--o{ PAGO : realiza
VENTA ||--o{ PAGO : cobra
TURNO_CAJA ||--o{ VENTA : registra
TURNO_CAJA ||--o| CORTE_CAJA : cierra
SOCIO o|--o{ VENTA : compra
VENTA ||--|{ DETALLE_VENTA : contiene
PRODUCTO ||--o{ DETALLE_VENTA : vende
UBICACION_INVENTARIO ||--o{ INVENTARIO : contiene
PRODUCTO ||--o{ INVENTARIO : controla
INVENTARIO ||--o{ MOVIMIENTO_INVENTARIO : registra
PROVEEDOR ||--o{ ORDEN_COMPRA : surte
ORDEN_COMPRA ||--|{ DETALLE_ORDEN_COMPRA : incluye
PRODUCTO ||--o{ DETALLE_ORDEN_COMPRA : solicita
VENTA ||--o{ DEVOLUCION : origina
SOCIO o|--o{ CLIENTE_FISCAL : identifica
CLIENTE_FISCAL ||--o{ SOLICITUD_FACTURACION : solicita
VENTA ||--o{ SOLICITUD_FACTURACION : puede_facturarse
PAGO ||--o{ SOLICITUD_FACTURACION : puede_facturarse
SOLICITUD_FACTURACION ||--o| COMPROBANTE_FISCAL : produce
COMPROBANTE_FISCAL ||--o{ EVENTO_FISCAL : conserva
LOTE_FACTURA_GLOBAL ||--|{ DETALLE_LOTE_GLOBAL : agrupa
COMPROBANTE_FISCAL ||--o| LOTE_FACTURA_GLOBAL : timbra
PAGO ||--o{ PARTIDA_CONCILIACION : concilia
MOVIMIENTO_BANCARIO ||--o{ PARTIDA_CONCILIACION : concilia
CONCILIACION ||--|{ PARTIDA_CONCILIACION : contiene
EMPLEADO o|--o| USUARIO : tiene_acceso
USUARIO ||--o{ ASIGNACION_ROL : recibe
ROL ||--o{ ASIGNACION_ROL : asigna
ROL ||--o{ ROL_PERMISO : define
PERMISO ||--o{ ROL_PERMISO : integra
EMPLEADO ||--o{ ASISTENCIA_EMPLEADO : marca
EMPLEADO ||--o{ NOMINA : tiene
EMPLEADO ||--o{ CLASE : imparte
CLASE ||--o{ RESERVA_CLASE : ofrece
SOCIO ||--o{ RESERVA_CLASE : reserva
RESERVA_CLASE ||--o| ASISTENCIA_CLASE : registra
SOCIO ||--o{ RUTINA : recibe
EMPLEADO ||--o{ RUTINA : crea
EQUIPO ||--o{ TICKET_MANTENIMIENTO : reporta
EMPLEADO ||--o{ TICKET_MANTENIMIENTO : atiende
TICKET_MANTENIMIENTO ||--o{ HISTORIAL_MANTENIMIENTO : documenta
```

## Entidades por dominio

### Socios, membresías, pagos y acceso
- `Socio`, `Plan`, `MembresiaSocio`, `MetodoPago`, `IntentoCobro`, `Pago` y `ReintentoCobro` soportan el ciclo comercial y de cobro recurrente.
- `CredencialAcceso`, `LectorAcceso` y `AccesoRegistro` soportan credenciales, lecturas autorizadas/denegadas y sincronización offline.
- La plantilla biométrica cifrada se mantiene separada del registro de acceso; no se almacena imagen biométrica.

### Punto de venta e inventario
- `Producto`, `VarianteProducto`, `Inventario`, `UbicacionInventario` y `MovimientoInventario` modelan catálogo, existencias y trazabilidad de stock.
- `Venta`, `DetalleVenta`, `Devolucion`, `TurnoCaja` y `CorteCaja` modelan operaciones del mostrador y cierre por turno.
- `CuentaSocio` no almacena saldo: se calcula con ventas a cuenta, devoluciones abonadas y `CobroCuentaSocio`; el límite vive en `members.credit_limit_cents`.
- `EnvioEstadoCuenta` audita cada envío del estado de cuenta o recordatorio de cobranza (socio, usuario, destinatario, formato, propósito `statement`/`reminder`, fecha de corte, estado, error y `retry_of_id` cuando es un reintento). No es un movimiento de la cuenta y es append-only: reintentar agrega una fila nueva enlazada con la anterior (`20261019_0021`); el propósito y el índice por socio/propósito/fecha llegan con `20261021_0022`.
- `Proveedor`, `OrdenCompra` y `DetalleOrdenCompra` modelan el abastecimiento.

### Facturación y conciliación
- `ClienteFiscal`, `SolicitudFacturacion`, `ComprobanteFiscal` y `EventoFiscal` conservan datos fiscales, solicitud, resultado y auditoría del PAC. En el primer incremento fiscal se materializan como `member_fiscal_profiles`, `invoices` (solicitud y resultado en una fila) e `invoice_events`; separar la solicitud del comprobante queda para cuando el PAC real lo exija.
- `RelacionComprobante` vincula comprobantes corregidos, notas de crédito o cancelaciones sin borrar el original. Desde el cuarto incremento fiscal, una nota de crédito es una fila de `invoices` con `origin_type = "credit_note"` que apunta a la factura ajustada con `related_invoice_id`, registra el motivo y la nota, y conserva receptor, tasa e importes desglosados como cualquier comprobante.
- `LoteFacturaGlobal` y `DetalleLoteGlobal` se materializan desde el tercer incremento fiscal como la factura `origin_type = "global"` (periodo en `global_year`/`global_month`) y `global_invoice_sales`, que congela folio, fecha y total de cada venta incluida.
- `ComplementoPago` y `EventoComplementoPago` se materializan desde el quinto incremento fiscal como `invoice_payments` e `invoice_payment_events`: cada parcialidad de una factura PPD tiene folio, UUID y cancelación propios, conserva sus saldos y su XML, y no crea un segundo libro de cobros. La factura original no cambia de importe; su saldo se deriva de los complementos timbrados.
- `MovimientoBancario`, `Conciliacion` y `PartidaConciliacion` modelan la conciliación conceptual. El primer incremento materializa una versión **uno a uno**: `bank_accounts`, `bank_movements` y `bank_movement_events` vinculan cada línea del estado de cuenta con una sola operación interna (pago de membresía, venta, abono o devolución) y documentan la diferencia. Los depósitos agrupados, pagos divididos y partidas explícitas siguen siendo diseño futuro.

### Operación, personal y mantenimiento
- `Clase`, `ReservaClase`, `ListaEsperaClase` y `AsistenciaClase` registran agenda, cupo y participación.
- `Rutina` mantiene su relación con socio y entrenador.
- `Empleado`, `Usuario`, `Rol`, `Permiso`, `AsistenciaEmpleado`, `Nomina` y entidades relacionadas soportan personal, autorización y nómina.
- `Equipo`, `TicketMantenimiento` e `HistorialMantenimiento` registran disponibilidad, atención y costos técnicos.

## Relaciones importantes

- un socio puede tener varias membresías históricas; una sola puede habilitar acceso según las reglas vigentes
- cada `Pago` confirmado tiene un origen de cobro identificable: una membresía o una venta; los intentos fallidos se conservan como `IntentoCobro`
- una venta puede tener varios pagos (por ejemplo, pago dividido) y varias líneas; las líneas conservan descripción, precio e impuestos aplicados en el momento de venta
- cada solicitud de facturación refiere exactamente a una venta o a un pago; puede haber varios eventos/reintentos de PAC, pero no más de un CFDI vigente incompatible para el mismo origen
- una factura de ingreso puede tener varias notas de crédito parciales; la suma de las timbradas y no canceladas nunca excede su total, y una nota siempre refiere a una factura de ingreso existente
- una factura PPD puede tener varias parcialidades; solo las **timbradas** reducen su saldo y la suma nunca excede el total. Cada complemento refiere a una sola factura y solo la última parcialidad timbrada vigente se puede cancelar
- cada movimiento de inventario registra cantidad, ubicación, motivo y referencia de origen; el saldo actual no reemplaza el historial
- la factura global guarda el detalle de operaciones incluidas y evita duplicar las ya facturadas individualmente
- en el esquema implementado, una línea del banco se vincula con **una sola** operación interna y una operación interna con **una sola** línea viva; la conciliación agrupada (varios pagos por un depósito) y las partidas explícitas quedan como diseño futuro
- cada reserva pertenece a un socio y una clase; la asistencia se registra contra la reserva
- un usuario recibe roles con vigencia y contexto; cada acción sensible conserva actor y fecha en auditoría

## Reglas de integridad por definir en el esquema físico

- Restricción exclusiva de origen para `Pago` (membresía o venta) y para `SolicitudFacturacion` (pago o venta), con excepciones de factura global representadas por su detalle de lote.
- Unicidad de SKU por alcance definido, UUID de CFDI, referencia externa idempotente y reserva activa por socio/clase.
- Los cambios de estado de pago, acceso y comprobante se registran como eventos; no se sobrescriben de forma que se pierda el historial.
- Las operaciones offline deben incluir identificador idempotente del dispositivo/origen para evitar duplicados al sincronizar.
- La retención de documentos fiscales y datos personales se configura con validación legal y fiscal, no se deriva de este modelo conceptual.

⚠️ El modelo es una base de diseño, no un dictamen fiscal ni un esquema final de producción. Debe mantenerse consistente con el glosario y los documentos de módulo.

## Esquema físico inicial: socios y cobro recurrente

La migración inicial materializa únicamente el flujo prioritario de socios, planes y cobros. Los nombres físicos usan `snake_case` en inglés, conforme a la convención de código; las entidades del dominio conservan los términos del glosario.

| Tabla | Responsabilidad | Restricciones principales |
|---|---|---|
| `members` | identidad y contacto mínimo del socio | UUID, correo normalizado único cuando existe, estado de perfil separado del estado de membresía, `credit_limit_cents` nullable (`NULL` = sin tope, `>= 0`) |
| `plans` | configuración vendible de un plan | código único, duración positiva, importe en centavos y moneda, `daily_entry_limit` nullable (`NULL` = sin límite, `>= 1`) |
| `memberships` | vigencia y estado del plan asignado | FKs restrictivas a socio/plan, periodo válido, estado controlado y máximo de una membresía no terminal por socio |
| `member_consents` | aceptación y revocación de documentos | historial con versión y fecha; no almacena datos médicos |
| `payment_methods` | referencia tokenizada del proveedor | token del proveedor cifrado, nunca PAN/CVV; un solo método predeterminado activo por socio |
| `payment_attempts` | cada intento de cobro e idempotencia | clave idempotente y huella de solicitud, número de intento positivo, estados controlados; un cobro manual con tarjeta declarada puede no tener `payment_method_id` ni proveedor |
| `payments` | cobros confirmados | un pago por intento exitoso, monto y moneda como snapshot; desde el cobro manual guarda periodo, turno de caja, cobrador y nota (los campos de periodo/turno son nulos en cobros de pasarela antiguos) |
| `payment_attempt_events` | historial de transiciones | eventos históricos vinculados al intento |
| `provider_webhook_events` | deduplicación y seguimiento de webhooks | evento único por proveedor, digest del payload y estado de procesamiento |
| `membership_events` | auditoría de cambios de membresía | estado anterior/nuevo, actor, fecha y metadatos sin secretos |

La migración está en `backend/alembic/versions/20261015_0001_memberships_billing.py`. La activación inicial de la membresía y la creación del pago confirmado deben ejecutarse en una sola transacción después de confirmar el pago; la respuesta HTTP de la pasarela por sí sola no es confirmación durable.

El cobro manual en mostrador (`20261021_0023_membership_manual_payments.py`) reutiliza `payment_attempts` y `payments` en vez de crear un libro paralelo: el intento queda `succeeded` con `provider = NULL` y el pago guarda `period_starts_at`, `period_ends_at`, `cash_session_id`, `collected_by` y `note`. El turno de caja no duplica el pago: al leer el corte suma los `payments` vinculados por `cash_session_id`, y solo el método `cash` entra al efectivo esperado.

## Esquema físico: facturación CFDI 4.0

La migración `20261023_0024_billing_cfdi.py` materializa el primer incremento fiscal, la `20261024_0025_global_invoices.py` el tercero, la `20261025_0026_credit_notes.py` el cuarto (notas de crédito), la `20261025_0028_ppd_payments.py` el quinto (complementos de pago PPD) y la `20261028_0040_invoice_cancellation_tracking.py` agrega el seguimiento de una cancelación que el SAT deja en proceso. La solicitud y el comprobante comparten fila porque el estado distingue ambos momentos; el historial de intentos vive en `invoice_events`. Los complementos viven en dos tablas propias porque una factura PPD tiene varias parcialidades, cada una con su folio, UUID, XML y cancelación.

| Tabla | Responsabilidad | Restricciones principales |
|---|---|---|
| `member_fiscal_profiles` | datos fiscales del socio para prellenar la siguiente solicitud | un perfil por socio (`uq_member_fiscal_profiles_member`), RFC de 12–13 caracteres, FK restrictiva al socio |
| `invoices` | solicitud y resultado del CFDI, con snapshot del receptor, importes, timbrado y cancelación; también la factura global con su periodo, la nota de crédito con su relación y la factura PPD que se liquida con complementos | `origin_type` (`sale`/`membership_payment`/`global`/`credit_note`) y `status` (`requested`/`failed`/`stamped`/`cancelled`) con CHECK; `payment_method` (`PUE` por defecto o `PPD`; PPD usa `payment_form = '99'`); total positivo y `subtotal + impuesto = total`; `(series, folio)`, `idempotency_key` y `uuid` únicos; `request_fingerprint` de la solicitud; actor de alta, timbrado y cancelación; XML y referencias del PAC opcionales; `cancellation_requested_at`/`cancellation_checked_at` nulos salvo cuando el SAT dejó la cancelación en proceso; `global_year`/`global_month` nulos salvo en `global` (`ck_invoices_global_period`); `related_invoice_id`, `credit_note_reason` y `credit_note_note` solo en `credit_note` (`ck_invoices_credit_note`), con FK autorreferente `RESTRICT` e índice `ix_invoices_related` |
| `invoice_items` | conceptos del comprobante con su parte gravable | posición y cantidad positivas, `subtotal + impuesto = total`, unicidad `(invoice_id, position)`, FK en cascada; el unitario de la global se deriva del subtotal entre la cantidad de operaciones |
| `invoice_events` | bitácora append-only de solicitudes, intentos y cancelaciones | tipo de evento, estado anterior/nuevo, actor, detalle JSON sin secretos y fecha; índice por factura y fecha |
| `global_invoice_sales` | trazabilidad de cada venta incluida en una factura global | unicidad `(invoice_id, sale_id)`, total positivo, FK en cascada a la factura y restrictiva a la venta; folio, fecha y total congelados; índices por factura y por venta |
| `invoice_payments` | una parcialidad (complemento de pago) de una factura PPD, con su folio, XML, saldos y cancelación | FK restrictiva a la factura; serie `P` por defecto; estados `requested`/`failed`/`stamped`/`cancelled`; `(series, folio)`, `idempotency_key` y `uuid` únicos; importe, parcialidad y folio positivos; `prior_balance > 0`, `amount <= prior_balance` y `outstanding = prior_balance − amount`; forma de pago real de dos caracteres; fecha de pago; tasa de IVA congelada; `request_fingerprint`; actores de alta, timbrado y cancelación; índices por factura/tiempo, factura/parcialidad y estado/tiempo |
| `invoice_payment_events` | bitácora append-only del complemento | evento (`payment_requested`/`payment_stamped`/`payment_stamp_failed`/`payment_cancelled`), estado anterior/nuevo, actor, detalle JSON sin secretos y fecha; FK en cascada al complemento e índice por complemento/fecha |

El índice único parcial `uq_invoices_active_origin` (`origin_type`, `origin_id` donde `status <> 'cancelled'` y `origin_type <> 'credit_note'`) impide dos facturas vivas para la misma venta o pago; cancelar conserva la fila y libera el origen para emitir la sustitución. Las notas de crédito quedan fuera del índice porque una factura admite varias parciales: su saldo —total de la factura menos notas timbradas y no canceladas— se controla en el servicio con `SELECT ... FOR UPDATE` sobre la factura original, tanto al crear como al timbrar. La nota apunta a la factura ajustada con `related_invoice_id` (FK autorreferente restrictiva), de modo que el comprobante relacionado no puede borrarse, y no crea tabla propia: sus conceptos viven en `invoice_items` y sus eventos en `invoice_events`. Para la global, `uq_invoices_active_global_period` (`global_year`, `global_month` donde la factura no está cancelada) impide dos globales vivas del mismo mes; la global usa un `origin_id` UUIDv5 determinista (`GLOBAL-YYYY-MM`) y la tabla `global_invoice_sales` impide además incluir la misma venta en dos globales vivas. El folio, la fecha y el total de la venta se copian al lote: cancelar o editar la factura global no reescribe la historia de la venta original. `invoices.uuid` es nulo en las facturas simuladas (no hay timbre del SAT) y se llena solo con un PAC real. El XML timbrado se guarda completo en `invoices.xml_content`; no hay tabla de archivos. La representación impresa (PDF) **no se almacena**: se genera al momento desde la factura, sus conceptos y el emisor, y solo se entrega para facturas timbradas o canceladas. Los envíos por correo no crean una tabla propia: se registran como eventos `invoice_email_sent`/`invoice_email_failed` en `invoice_events`, con destinatario, adjuntos (`pdf`, `xml`), estado de entrega y error. El emisor no se duplica en base de datos: se configura por entorno (`GYM_RFC`, `GYM_LEGAL_NAME`, `GYM_TAX_REGIME`, `GYM_POSTAL_CODE`, `CFDI_CERTIFICATE_NUMBER`, `CFDI_SERIES`, `CFDI_TAX_RATE_PERCENT`, `CFDI_PRODUCT_CODE`, `CFDI_SERVICE_CODE`).

El complemento de pago **no** modifica `invoices.total_cents`, no crea una fila en `payments` ni mueve caja: documenta fiscalmente una parcialidad que el operador declara. El saldo de una factura PPD es `total_cents − suma de complementos timbrados` (los cancelados no cuentan), y una solicitud `requested` o `failed` no lo consume; el timbrado bloquea la factura y el complemento, revalida el importe y recalcula `partiality_number`, `prior_balance_cents` y `outstanding_balance_cents`, de modo que las parcialidades timbradas quedan numeradas 1, 2, 3… sin huecos aunque se hayan registrado solicitudes fuera de orden. Solo se cancela la **última parcialidad timbrada vigente** y una factura con complementos timbrados no se cancela hasta cancelarlos; una factura PPD no acepta notas de crédito en esta versión. La FK restrictiva a `invoices` impide borrar una factura con complementos. El XML se guarda en `invoice_payments.xml_content` y la representación impresa se genera al momento desde el complemento y la factura; no hay tabla de archivos. Un complemento simulado deja `uuid` nulo y `is_simulated = true`. Los bloqueos `SELECT ... FOR UPDATE` son efectivos en PostgreSQL y no-op en SQLite, así que la garantía de saldo y numeración en concurrencia depende del motor de producción.

## Esquema físico: conciliación bancaria

La migración `20261025_0027_bank_reconciliation.py` agrega las cuentas, las líneas del estado de cuenta y su bitácora, además del permiso `finance.manage` para dueño y contador. La cuenta es un catálogo, no un libro: el «saldo» que muestra el panel es la suma de las líneas importadas.

| Tabla | Responsabilidad | Restricciones principales |
|---|---|---|
| `bank_accounts` | cuenta bancaria cuyas líneas se concilian | UUID, `lower(name)` único (`uq_bank_accounts_name_lower`), últimos cuatro dígitos (`account_last4`, longitud 4), moneda de tres letras, estado `active`/`inactive` con CHECK y `created_by` con FK `RESTRICT`; no guarda número completo, CLABE ni credenciales |
| `bank_movements` | una línea del estado de cuenta con signo | fecha, importe `BIGINT` distinto de cero, moneda, referencia y descripción; estado `pending`/`reconciled`/`difference`/`reviewing`; vínculo polimórfico `matched_source`/`matched_id` con CHECK de par completo, `reconciled` exige `matched_id`, `difference_cents` solo existe con vínculo y estado `difference`; unicidad `(bank_account_id, import_hash)`; índices por cuenta/fecha, estado y fecha; índices de actores con FK `RESTRICT` |
| `bank_movement_events` | bitácora append-only de la línea | `imported`/`matched`/`unmatched`/`flagged`/`reopened` con CHECK, detalle de hasta 400 caracteres, actor FK `RESTRICT`, fecha e índice por movimiento/fecha; no se actualiza ni se borra |

El índice único parcial `uq_bank_movements_match` sobre `(matched_source, matched_id)` donde `matched_id IS NOT NULL` impide que dos líneas del banco reclamen la misma operación interna. `matched_id` **no** es una FK real porque apunta a cuatro tablas distintas (`payments`, `sales`, `member_account_payments`, `sale_returns`); la existencia, el método electrónico, la moneda y el sentido del movimiento se validan en el servicio antes de vincular. Desvincular limpia el vínculo y devuelve la línea a `pending`, conservando el evento. El `import_hash` es SHA-256 de cuenta, fecha, importe, referencia y descripción (sin distinguir mayúsculas), de modo que reimportar el mismo estado no duplica; dos líneas legítimamente idénticas se consideran duplicadas. El `downgrade` de la migración se niega a ejecutarse si existen movimientos bancarios. Los bloqueos `SELECT ... FOR UPDATE` de las conciliaciones son efectivos en PostgreSQL y no-op en SQLite, así que la garantía de concurrencia en producción depende del motor. No hay eventos de auditoría para cambios de cuenta y no se permite borrar una cuenta con historial.

## Esquema físico: portal del socio

La migración `20261027_0031_member_portal.py` agrega la autenticación de la app móvil. El socio no tiene contraseña: recibe un código temporal por correo y obtiene una sesión propia, separada de `user_sessions` del personal.

| Tabla | Responsabilidad | Restricciones principales |
|---|---|---|
| `member_login_codes` | código OTP de un solo uso enviado al correo del socio | FK `RESTRICT` al socio, `code_hash` SHA-256/HMAC de 64 caracteres, `created_at`/`expires_at` (10 minutos), `consumed_at` nullable, `attempts` entero no negativo (máximo 5 en el servicio), `ck_member_login_codes_attempts` y `ck_member_login_codes_expiry_order`; índice por socio y fecha de creación |
| `member_sessions` | sesión opaca de la app del socio | `token_sha256` único, `expires_at` (30 días), `revoked_at` y `last_seen_at`; `ck_member_sessions_expiry_order`; índice por socio y vencimiento |
| `member_auth_events` | bitácora de autenticación del socio | FK nullable al socio, `event_type` (`code_requested`/`code_delivery`/`code_verified`/`login`/`logout`), `result` (`success`/`failure`), `reason_code` y `occurred_at`; índice por socio y fecha; nunca guarda código ni token |

El código se almacena solo como HMAC-SHA256 calculado con `SECRET_KEY` sobre el id del código, el id del socio y el código; la sesión solo conserva el SHA-256 del token. La base de vista previa crea estas tablas con `create_all`; en producción se aplican con Alembic. No hay relación con `app_users`, `user_sessions` ni la matriz RBAC: el portal solo expone las rutas `/member/*` y el socio autenticado únicamente puede leer su propio perfil.

Las **reservas de clases desde la app** no agregan tablas ni columnas: reutilizan `class_sessions` y `class_reservations` con `origin = "app"`, y la capa `app.modules.portal.classes` solo filtra por el socio de la sesión antes de delegar en el servicio de clases. `cancelled_by` sigue siendo una FK a `app_users`, así que una cancelación hecha por el socio lo deja en `NULL`; el origen distingue la reserva, no al actor de la cancelación.

Las **rutinas y el progreso del socio** leen `routine_assignments` (con la `routine_version` fijada), `routine_items` de esa versión, `workout_logs`, `workout_sets`, `body_measurements` y `member_goals` a través de `app.modules.portal.routines`, que acota todo por el socio de la sesión. El registro de entrenamientos y medidas desde la app agrega la migración `20261027_0032_member_activity_origin.py`, que da a `workout_logs` y `body_measurements` la columna `origin` (`'staff'` | `'app'`, CHECK `ck_workout_logs_origin` / `ck_body_measurements_origin`, `server_default 'staff'`). Los entrenamientos de la app nacen `logged` y el entrenador los pasa a `reviewed`; las medidas son append-only y se aplican de inmediato a las metas. `logged_by`/`measured_by` siguen siendo FK a `app_users` y quedan en `NULL` en los registros de origen `app`, porque el socio no es un usuario del personal: `origin` distingue el canal, no al actor.

El **alta y cancelación de metas desde la app** agrega la migración `20261027_0034_member_goal_origin.py`, que da a `member_goals` la columna `origin` (`'staff'` | `'app'`, CHECK `ck_member_goals_origin`, `server_default 'staff'`); las metas anteriores quedan como `staff`. El socio solo crea metas con origen `app` y solo puede cancelar las que él mismo creó: una meta del personal responde `409` en la app y se administra en el panel con `routines.manage`. El baseline se sigue tomando de la última medición al crear la meta y se conserva congelado, y `created_by` queda en `NULL` en las metas de la app por la misma razón que `logged_by`/`measured_by`. El cierre de asignaciones sigue escribiéndose solo desde el panel.

Las **fotos de progreso desde la app** agregan la migración `20261028_0041_progress_photo_origin.py`, que da a `progress_photos` la columna `origin` (`'staff'` | `'app'`, CHECK `ck_progress_photos_origin`, `server_default 'staff'`); las fotos anteriores quedan como `staff`. La app reutiliza `progress_photos` y el almacenamiento fuera de la base: no hay tabla ni columna nuevas aparte de `origin`, y `uploaded_by` sigue siendo una FK a `app_users` que queda en `NULL` en las cargas del socio. El consentimiento se guarda en `member_consents` con `consent_type = 'progress_photos'` y `document_version = 'fotos-progreso-v1'`; es una precondición de la primera carga, se escribe una sola vez y se revierte si la imagen se rechaza. La app solo ve y elimina fotos de su `member_id` (una ajena responde `404`), y la descarga usa un enlace firmado con HMAC-SHA256 de `photo:<id>:<exp>` y `SECRET_KEY` —vigencia de 10 minutos—, sin Bearer en la URL, igual que las facturas del socio (ADR-019, ADR-023).

El **detalle por serie** vive en `workout_sets` (migración `20261027_0033_workout_sets.py`): una fila por serie ejecutada, con FK en cascada al entrenamiento y FK restrictiva al ejercicio, índice único `(workout_id, exercise_id, set_number)` e índice por entrenamiento. El servicio valida que el ejercicio pertenezca al plan de la `routine_version` de la asignación; la lectura ordena por `routine_items.position` y `set_number`. Las series se escriben en la misma transacción que el entrenamiento y no se editan después.

| Tabla | Responsabilidad | Restricciones principales |
|---|---|---|
| `workout_sets` | una serie ejecutada dentro de un entrenamiento (ejercicio, número, repeticiones y peso) | FK `CASCADE` a `workout_logs` y `RESTRICT` a `exercises`; único `(workout_id, exercise_id, set_number)`; `ck_workout_sets_number_positive`, `ck_workout_sets_reps_range` (1–100) y `ck_workout_sets_weight_range` (0–1000 o `NULL`); máximo 60 series por entrenamiento en el servicio; `created_at` igual al `performed_at` |

Los **pagos y el estado de cuenta del socio** reutilizan `payments` (con su `membership_id` y el plan de la membresía) y el estado de cuenta calculado por `member_account_statement` sobre las ventas a cuenta, las devoluciones abonadas y `member_account_payments`. `app.modules.portal.payments` solo filtra por el socio de la sesión, pagina los pagos y recorta a 100 los movimientos más recientes; no crea tablas, columnas ni movimientos, y deja fuera los datos internos del personal (turno, cobrador y límite de crédito).

Los **avisos** viven en dos tablas espejo del módulo transversal `app.modules.notifications`: `member_notifications` (migración `20261027_0035_member_notifications.py`) para los socios y `staff_notifications` (migración `20261027_0036_staff_notifications.py`) para las **cuentas del panel**. Es un **mensaje congelado**, no una referencia a datos vivos: el título y el cuerpo se redactan al producirse el evento, así que editar o borrar el origen nunca deja un aviso incomprensible; `ref_id` guarda el identificador de origen **sin FK** porque puede apuntar a distintas tablas según el `kind`. La audiencia del personal se resuelve leyendo `AppUser.employee_id`, el vínculo único empleado → cuenta que ya existía desde el módulo de identidad. La audiencia del aviso de equipo caído la resuelve **mantenimiento**, uniendo `routine_assignments` → `routine_items` por la versión congelada de la asignación → `exercises.equipment_id`, y pasa la lista de socios al emisor: `notifications` no consulta tablas de rutinas. El aviso de estado de factura lo emite **facturación** desde `Invoice.member_id`, dentro de la misma transacción que cambia el estado: el aviso no puede sobrevivir a un timbrado revertido.

| Tabla | Responsabilidad | Restricciones principales |
|---|---|---|
| `member_notifications` | un aviso para un socio, con su texto congelado y su fecha de lectura | FK `RESTRICT` al socio; `kind` con CHECK `ck_member_notifications_kind` (`workout_reviewed`/`goal_achieved`/`goal_updated_by_staff`/`goal_cancelled_by_staff`/`class_waitlist_promoted`/`membership_expiring`/`equipment_out_of_service`/`invoice_stamped`/`invoice_failed`/`invoice_cancelled`, ensanchado por las migraciones `20261027_0037_equipment_out_of_service_notice.py` y `20261028_0039_invoice_status_notifications.py`); `title` 1–140 y `body` 1–500 con CHECK; `ref_id` UUID sin FK; `dedupe_key` hasta 120 con **índice único parcial** donde no es nulo; `created_at` con `server_default now()`; `read_at` nullable; índices `(member_id, created_at)` y `(member_id, read_at)` |
| `staff_notifications` | un aviso para una cuenta del panel (entrenador o técnico), con su texto congelado, su fecha de lectura y su fecha de cierre | FK `RESTRICT` a `app_users`; `kind` con CHECK `ck_staff_notifications_kind` (`workout_pending_review`/`maintenance_ticket_assigned`/`kiosk_token_expiring`); `title` 1–140 y `body` 1–500 con CHECK; `ref_id` UUID sin FK; `dedupe_key` hasta 120 con **índice único parcial** donde no es nulo; `created_at` con `server_default now()`; `read_at` nullable; `resolved_at` nullable (migración `20261029_0054_staff_notification_resolved.py`); índices `(user_id, created_at)` y `(user_id, read_at)` |

| Relación | Regla |
|---|---|
| un socio o una cuenta recibe muchos avisos y un aviso pertenece a un solo destinatario | borrar un socio o una cuenta con avisos está bloqueado por la FK `RESTRICT`: el borrado de socios sigue siendo lógico |
| un aviso describe un evento de otro módulo | no hay FK al origen: `ref_id` es una pista, y la integridad del texto no depende de que el origen siga existiendo |
| dos avisos iguales no pueden coexistir | lo impide el índice único parcial sobre `dedupe_key`; `_append` hace `flush()` de los cambios pendientes del llamante antes de abrir el savepoint y devuelve la fila existente si pierde la carrera, así que una colisión nunca revierte el ticket o el entrenamiento que se estaba insertando |
| un aviso no se edita ni se borra | `read_at` y `resolved_at` son las únicas columnas que cambian después del alta; ambas bandejas son historial |
| un aviso del personal deja de deber trabajo | `resolved_at` lo escribe el servicio que completa la tarea anunciada —`review_workout` al revisar— dentro de su transacción; el lector nunca lo toca y los conteos de no leídos lo excluyen (ADR-038) |
| un empleado puede no tener cuenta del panel | si `staff_user_for_employee` no encuentra una cuenta **activa**, el aviso se omite en silencio y la operación de dominio se completa igual |

Los **recordatorios** no necesitan programador: `_ensure_membership_expiring` lo calcula al leer la bandeja sobre la membresía `active` que termina primero y lo escribe con `dedupe_key = membership_expiring:<membership_id>:<7|3|1>`, de modo que hay **un aviso por ventana** y no uno por día; `_ensure_class_reminders` hace lo mismo con cada reserva `reserved` de una clase `scheduled` que empieza en 24 o 2 horas, con `dedupe_key = class_reminder:<reservation_id>:<24|2>` (ADR-035). Los demás avisos los escriben los servicios de `routines` y `classes` dentro de la misma transacción del cambio que anuncian: la confirmación `class_reserved` se inserta en `reserve_seat` junto con la reserva y solo cuando queda `reserved` (ADR-036); la cancelación de una clase escribe un `class_cancelled` por cada reserva viva —sentada o en espera, resuelta por `_live_reservations`— y un cambio de inicio o fin escribe `class_rescheduled` con las dos ventanas (ADR-037). El único aviso que se cierra solo es el pendiente de revisión: `review_workout` sella `resolved_at` en su misma transacción y desde ahí el aviso deja de contar para el panel pero sigue en la lista (ADR-038).

## Esquema físico: turnos y asistencia del personal

El módulo de personal lleva operando desde su incremento en `employees`/`app_users`, y sus tres tablas de turnos y asistencia existían **solo en los modelos**: la base de vista previa las crea `create_all` y el panel las consulta sin problema, pero **ninguna migración las definía**, así que una base PostgreSQL construida con `alembic upgrade head` no las tenía y cualquier consulta de turnos habría caído con `relation does not exist`. La migración `20261027_0038_staffing_shifts_and_attendance.py` las agrega con la forma exacta que los modelos publican; la detectó `alembic check` en su primera corrida (ver `backend/README.md`).

| Tabla | Responsabilidad | Restricciones principales |
|---|---|---|
| `staff_shifts` | un turno programado a un empleado, con su ventana horaria | FK `RESTRICT` a `employees` y a `app_users` (quien lo programó); `ck_staff_shifts_period_valid` (`ends_at > starts_at`) y `ck_staff_shifts_status` (`scheduled`/`cancelled`, con `server_default 'scheduled'`); `created_at`/`updated_at` con `server_default now()`; índices `(employee_id, starts_at)` y `(starts_at, status)` |
| `staff_attendance` | el marcaje real de un turno: entrada, salida y estado | FK `RESTRICT` a `staff_shifts` con **única** `uq_staff_attendance_shift` (un marcaje por turno), a `employees` y a `app_users` para los actores de entrada y salida; `ck_staff_attendance_status` (`present`/`late`) y `ck_staff_attendance_checkout_order` (`check_out_at IS NULL OR check_out_at >= check_in_at`); salida y su actor/fuente son nullable; índice `(employee_id, check_in_at)` |
| `staff_attendance_events` | bitácora append-only de cada marcaje | FK `RESTRICT` a `staff_attendance` y a `app_users`; `uq_staff_attendance_events_request` sobre `request_id` es la **idempotencia** del alta, con `request_sha256` (64) para detectar la misma clave con otros datos; `ck_staff_attendance_events_type` (`check_in`/`check_out`) y `ck_staff_attendance_events_source` (`staff_app`/`manual`/`access_reader`); `reason` nullable; índices `(attendance_id, occurred_at)` y `request_id` |

Hoy el único `source` que se escribe es `staff_app`, el que pasan `POST /staff/attendance/clock-in` y `clock-out` (auto-servicio con `attendance.self`); `manual` y `access_reader` están declarados en el `CHECK` pero sin llamador: el primero sería el marcaje corregido por el supervisor y el segundo el lector físico del control de acceso, que todavía no está conectado. El alta de turnos desde el panel es `POST /admin/staff/{employee_id}/shifts` con `attendance.manage`. Nómina y tolerancia a retardos no viven en el esquema.

## Persistencia local de acceso offline

La primera implementación usa un archivo SQLite local para el caché de decisiones en el lector/controlador, separado de PostgreSQL central:

- `access_snapshots`: snapshot por socio con estado/vigencia, adeudo, horario y `valid_until`.
- `access_outbox`: decisiones autorizadas/denegadas con `event_id` único, lector, dirección, motivo, timestamp y estado `pending`/`synced`.
- Los eventos se insertan transaccionalmente y el mismo `event_id` con solicitud distinta se rechaza.
- El preview puede marcar eventos como sincronizados para probar el flujo; la integración real de transporte al backend y el hardware siguen pendientes.

## Esquema físico: kiosco de recepción y código rotativo

La migración `20261028_0042_kiosk_access.py` agrega tres tablas para el primer canal de entrada autónomo del socio. El código no se guarda en claro y el token del dispositivo tampoco: ambos se almacenan como hash, igual que las sesiones y los códigos OTP.

| Tabla | Responsabilidad | Restricciones principales |
|---|---|---|
| `kiosk_devices` | tablet autorizada de recepción | etiqueta de 1–80 caracteres, `token_sha256` único (64), `token_expires_at` (`TIMESTAMP WITH TIME ZONE`, nulo = creado antes de la columna y sin caducidad), estado `active`/`revoked` con CHECK, `created_by` FK `RESTRICT` a `app_users`, `revoked_at` solo en `revoked` (`ck_kiosk_devices_revoked`) y `last_seen_at` refrescado como máximo una vez por minuto |
| `member_access_codes` | código rotativo de seis dígitos emitido por la app | FK en cascada al socio, `code_hash` HMAC-SHA256 (64), `issued_at`, `expires_at` con CHECK `expires_at > issued_at`, `consumed_at` nulo mientras está vigente; índices por socio/emisión y por expiración; emitir un código marca como consumidos los anteriores no usados |
| `kiosk_attempts` | intentos fallidos del dispositivo, sin el código capturado | FK en cascada al kiosco, resultado `invalid` con CHECK, `occurred_at` e índice por dispositivo/fecha; el límite de 10 por minuto se calcula sobre esta tabla |

El código solo prueba identidad: la decisión de entrada la sigue tomando `evaluate_access` con un `AccessSnapshot` armado desde la membresía más reciente, y el resultado se persiste en `access_events` (no en una tabla nueva) con `source = "reader"` y `reader_id = "Kiosco <etiqueta>"`. Un código solo se consume si el `UPDATE ... WHERE consumed_at IS NULL` afecta una fila, así que dos kioscos que lo capturen a la vez no pueden conceder dos entradas. Los intentos válidos no se copian a `kiosk_attempts`, y ni el código en claro ni el token aparecen en la tabla ni en la respuesta del listado de dispositivos; el token se devuelve una sola vez al crear el dispositivo o al rotarlo. La vista previa crea estas tablas con `create_all` y no necesita parche porque son tablas nuevas. El kiosco también lee la tabla `equipment` de mantenimiento a través de `GET /kiosk/equipment` (solo lectura, sin tablas nuevas) para mostrar los equipos en mantenimiento o fuera de servicio.

La caducidad del token no agrega tablas: `20261028_0045_kiosk_token_expiry.py` añade `kiosk_devices.token_expires_at` (`TIMESTAMP WITH TIME ZONE` nullable) y rellena las filas existentes con `now() + INTERVAL '90 days'`, para que una tablet en turno no quede cortada por el despliegue. El alta y la rotación escriben `ahora + 90 días` y la autenticación rechaza un valor vencido con el mismo `401` que un token revocado. Un `NULL` solo existe en filas antiguas o insertadas fuera del servicio y conserva el comportamiento de «sin caducidad». En la vista previa, `preview_patch.py` agrega la columna y hace el relleno con `datetime('now', '+90 days')`.

El límite diario de entradas no agrega tablas: la migración `20261028_0043_plan_daily_entry_limit.py` añade `plans.daily_entry_limit` (`INTEGER` nullable, CHECK `ck_plans_daily_entry_limit`: `NULL` o `>= 1`) y el conteo se calcula sobre `access_events` (entradas autorizadas del socio dentro del día local del club), de modo que no hay contador que reiniciar ni job nocturno. Un plan con `NULL` conserva el comportamiento sin límite.

El control de duplicados agrega una tabla de política, no de eventos: `20261028_0044_access_antipassback_settings.py` crea `access_settings` con una sola fila (`id = 1`) y `antipassback_seconds` (`INTEGER NOT NULL`, `server_default 0`, CHECK `ck_access_settings_antipassback_range`: `0`–`3600`), más `updated_at`. `0` desactiva la regla y es el valor que siembra la migración, así que no cambia el comportamiento existente. La última entrada del socio se sigue leyendo de `access_events` (`authorized = true`, `direction = entry`, sin importar `source`); no hay contador ni tabla nueva de eventos.

| Tabla | Responsabilidad | Restricciones principales |
|---|---|---|
| `access_settings` | política global del club que no depende del socio ni del plan | fila única `id = 1`, `antipassback_seconds` entre `0` y `3600` con CHECK (donde `0` desactiva), `updated_at` con `server_default now()`; se edita con `GET/PATCH /admin/access/settings` y `settings.manage` |

## Identidad y autorización inicial

- `employees` mantiene el directorio operativo básico; `app_users` es la identidad de acceso y se vincula opcionalmente con un empleado por `employee_id` (único, FK `RESTRICT`). Ese vínculo es el que usa `staff_user_for_employee` para decidir a qué cuenta del panel llega un aviso de entrenador o de técnico.
- `roles`, `permissions` y `role_permissions` definen el catálogo RBAC granular `recurso.acción`.
- `user_role_assignments` conserva actor, fecha, vencimiento y revocación de cada asignación.
- `user_sessions` almacena solo SHA-256 del token opaco, con vencimiento y revocación server-side.
- `auth_events` registra login exitoso/fallido, logout, creación de usuario y cambios de rol sin guardar contraseñas ni tokens.
- Los roles predeterminados se siembran en la migración Alembic; MFA, rate limiting, recuperación de contraseña y nómina no forman parte de esta primera revisión.
