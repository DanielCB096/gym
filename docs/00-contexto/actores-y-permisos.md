# Actores y permisos

## Matriz general

| Actor | Objetivo principal | Permisos clave |
|---|---|---|
| Socio | usar el servicio, reservar y consultar información | ver su perfil, clases, facturas, estado de pago y acceso |
| Recepcionista | atención en mostrador | alta de socios, pagos, check-in, ventas, reingreso manual |
| Entrenador | dar clases y seguimiento | agenda, asistentes, rutinas, medidas y seguimiento |
| Personal de mantenimiento | resolver fallas y limpiar | equipos asignados, reportes de falla, checklist y estado de instalaciones |
| Gerente | operar la sucursal | todos los permisos operativos, reportes y gestión de personal |
| Dueño / administrador | supervisión global | permisos completos, configuración del sistema y auditoría |
| Contador | cierre financiero y comprobantes | reportes finanzas, CFDI y conciliación |

## Principios de permisos

- mínimo privilegio
- permisos por rol y por área
- validación en backend
- registro de acciones sensibles en bitácora
- MFA para administradores y acceso financiero

## Reglas de acceso por rol

- socios no pueden ver datos de otros socios ni gestionar la operación del gimnasio. La app del socio no usa la matriz RBAC del personal: se autentica con un código OTP enviado a su correo y solo puede leer su propio perfil, membresía, estado de acceso y saldo. Su token de sesión vive en `member_sessions` y no sirve para ninguna ruta `/admin/*`; a la inversa, un token de personal no sirve en `/member/*`
- recepción no puede alterar nodos financieros ni cambiar roles críticos
- el cobro manual de membresía (efectivo, tarjeta declarada o transferencia) usa `members.manage` y exige un turno de caja abierto; recepción, gerente y dueño pueden cobrar, mientras contabilidad e instructor solo consultan. El pago queda ligado al turno y al usuario, y solo el efectivo entra al arqueo
- el límite de crédito de los socios lo fijan dueño y gerente (`sales.credit`); recepción puede vender a cuenta y cobrar, pero no modificar el límite
- el estado de cuenta se consulta, descarga y su historial de envíos se lee con `sales.read` (dueño, gerente, recepción y contabilidad); **enviarlo, reintentarlo o enviar recordatorios de cobranza** exige `sales.manage` y deja bitácora del destinatario, formato, propósito, corte, resultado y usuario. Solo se reintentan intentos `failed` o `simulated`; uno `sent` responde `409`. Los recordatorios exigen saldo con cargos de más de 30 días y respetan un cooldown de 7 días por socio
- la facturación CFDI separa responsabilidades: `billing.read` consulta facturas, orígenes facturables, datos fiscales y descarga el PDF; `billing.request` solicita la factura, captura el perfil fiscal del socio y la envía por correo; `billing.manage` timbra, cancela, emite notas de crédito y registra, timbra o cancela complementos de pago PPD. Dueño, gerente y contador tienen los tres; recepción solo consulta, solicita y envía (no timbra, no cancela, no emite notas ni registra complementos); entrenador y mantenimiento no participan. La validación se hace siempre en el backend y cada solicitud, intento, cancelación, nota, complemento y envío queda en `invoice_events` o `invoice_payment_events` con su actor
- una factura emitida no se edita ni se borra: corregir datos del receptor exige cancelarla (motivo del SAT y, si aplica, UUID sustituto) y emitir otra. La descarga del XML y del PDF usa `billing.read`; el envío por correo exige `billing.request`, solo aplica a facturas timbradas y deja bitácora del destinatario, adjuntos (PDF/XML) y resultado. La factura global (mes cerrado, receptor de público en general) se revisa con `billing.read` y **solo se emite o cancela con `billing.manage`**; recepción puede consultarla, pero no emitirla ni cancelarla. Una global viva bloquea la factura individual de sus ventas hasta que se cancele. La nota de crédito (CFDI de egreso) se consulta y descarga con `billing.read` y **solo se emite, timbra y cancela con `billing.manage`**; el importe se limita al saldo de la factura original (total menos notas timbradas vigentes) y una factura con notas vigentes no se cancela hasta cancelarlas. Una factura PPD se liquida con complementos de pago: se leen con `billing.read` y **solo se registran, timbran o cancelan con `billing.manage`**; solo la última parcialidad vigente se cancela, una factura con complementos timbrados no se cancela y en esta versión una factura PPD no admite notas de crédito. El timbrado simulado de vista previa (y su PDF) no tiene validez fiscal y no debe presentarse como comprobante real
- la conciliación bancaria se consulta con `finance.read` (dueño, gerente y contador); **crear cuentas, activarlas/desactivarlas, importar estados de cuenta, conciliar, desvincular y marcar líneas** exigen `finance.manage` (solo dueño y contador). Recepción no tiene acceso. La conciliación **no crea ni edita** pagos, ventas, abonos o devoluciones: solo vincula una línea del banco con una operación interna existente y deja bitácora con actor, fecha y motivo; una diferencia de importe exige nota y no se ajusta automáticamente. El vínculo es uno a uno y una operación interna no puede reclamarse desde dos líneas
- contabilidad no puede modificar membresías ni eliminar accesos sin auditoría
- dueño y gerente pueden crear configuración, pero los cambios sensibles quedan en registro histórico
