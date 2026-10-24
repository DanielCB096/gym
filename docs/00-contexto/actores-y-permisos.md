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

- socios no pueden ver datos de otros socios ni gestionar la operación del gimnasio
- recepción no puede alterar nodos financieros ni cambiar roles críticos
- el cobro manual de membresía (efectivo, tarjeta declarada o transferencia) usa `members.manage` y exige un turno de caja abierto; recepción, gerente y dueño pueden cobrar, mientras contabilidad e instructor solo consultan. El pago queda ligado al turno y al usuario, y solo el efectivo entra al arqueo
- el límite de crédito de los socios lo fijan dueño y gerente (`sales.credit`); recepción puede vender a cuenta y cobrar, pero no modificar el límite
- el estado de cuenta se consulta, descarga y su historial de envíos se lee con `sales.read` (dueño, gerente, recepción y contabilidad); **enviarlo, reintentarlo o enviar recordatorios de cobranza** exige `sales.manage` y deja bitácora del destinatario, formato, propósito, corte, resultado y usuario. Solo se reintentan intentos `failed` o `simulated`; uno `sent` responde `409`. Los recordatorios exigen saldo con cargos de más de 30 días y respetan un cooldown de 7 días por socio
- la facturación CFDI separa responsabilidades: `billing.read` consulta facturas, orígenes facturables y datos fiscales; `billing.request` solicita la factura y captura el perfil fiscal del socio; `billing.manage` timbra y cancela. Dueño, gerente y contador tienen los tres; recepción solo consulta y solicita (no timbra ni cancela); entrenador y mantenimiento no participan. La validación se hace siempre en el backend y cada solicitud, intento y cancelación queda en `invoice_events` con su actor
- una factura emitida no se edita ni se borra: corregir datos del receptor exige cancelarla (motivo del SAT y, si aplica, UUID sustituto) y emitir otra. La descarga del XML usa `billing.read`; el timbrado simulado de vista previa no tiene validez fiscal y no debe presentarse como comprobante real
- contabilidad no puede modificar membresías ni eliminar accesos sin auditoría
- dueño y gerente pueden crear configuración, pero los cambios sensibles quedan en registro histórico
