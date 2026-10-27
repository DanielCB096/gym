# Documentación del sistema

Esta carpeta contiene la memoria del proyecto: contexto de negocio, arquitectura, módulos, procesos, integraciones, decisiones de diseño, operación y pruebas.

## Índice

### 00-contexto
- [vision-y-alcance.md](00-contexto/vision-y-alcance.md)
- [glosario.md](00-contexto/glosario.md)
- [actores-y-permisos.md](00-contexto/actores-y-permisos.md)

### 01-arquitectura
- [arquitectura-general.md](01-arquitectura/arquitectura-general.md)
- [stack-tecnologico.md](01-arquitectura/stack-tecnologico.md)
- [modelo-de-datos.md](01-arquitectura/modelo-de-datos.md)
- [estrategia-offline-y-rendimiento.md](01-arquitectura/estrategia-offline-y-rendimiento.md)
- [seguridad-y-privacidad.md](01-arquitectura/seguridad-y-privacidad.md)

### 02-modulos
- [membresias-y-cobro-recurrente.md](02-modulos/membresias-y-cobro-recurrente.md)
- [control-de-acceso.md](02-modulos/control-de-acceso.md)
- [personal-y-roles.md](02-modulos/personal-y-roles.md)
- [clases-y-reservaciones.md](02-modulos/clases-y-reservaciones.md)
- [rutinas-y-progreso.md](02-modulos/rutinas-y-progreso.md)
- [punto-de-venta-e-inventario.md](02-modulos/punto-de-venta-e-inventario.md)
- [facturacion-y-reportes.md](02-modulos/facturacion-y-reportes.md)
- [mantenimiento-equipo.md](02-modulos/mantenimiento-equipo.md)
- [servicios-extra.md](02-modulos/servicios-extra.md)

### 03-procesos

Disponibles:
- [alta-de-socio-y-primer-pago.md](03-procesos/alta-de-socio-y-primer-pago.md)
- [renovacion-y-cobro-recurrente.md](03-procesos/renovacion-y-cobro-recurrente.md)
- [cobro-fallido-y-suspension.md](03-procesos/cobro-fallido-y-suspension.md)
- [congelamiento-y-cancelacion.md](03-procesos/congelamiento-y-cancelacion.md)
- [acceso-con-y-sin-internet.md](03-procesos/acceso-con-y-sin-internet.md)
- [facturacion-y-factura-global.md](03-procesos/facturacion-y-factura-global.md)
- [conciliacion-bancaria.md](03-procesos/conciliacion-bancaria.md)
- [alta-y-baja-de-empleado.md](03-procesos/alta-y-baja-de-empleado.md)
- [venta-en-mostrador-y-corte-de-caja.md](03-procesos/venta-en-mostrador-y-corte-de-caja.md)
- [reabastecimiento-de-inventario.md](03-procesos/reabastecimiento-de-inventario.md)

Pendientes de documentar:
- reporte-y-resolucion-de-falla-de-equipo.md
- mantenimiento-preventivo.md
- cierre-de-nomina.md
- apertura-y-cierre-del-gimnasio.md
- atencion-de-derechos-arco.md
- respaldo-y-recuperacion.md

### 04-integraciones
- pasarela-de-pago.md
- facturacion-cfdi.md
- hardware-acceso.md
- whatsapp.md

### 05-decisiones
- ADR-001-stack.md
- ADR-002-base-de-datos.md
- ADR-003-pasarela-de-pago.md
- ADR-004-hardware-acceso.md
- ADR-005-modelo-de-permisos.md
- ADR-006-migraciones.md
- ADR-007-cache-local-acceso.md
- ADR-008-autenticacion-rbac.md
- ADR-009-autenticacion-socio.md

### 06-operacion
- despliegue.md
- respaldos-y-recuperacion.md
- monitoreo.md
- manual-de-incidentes.md
- manual-usuario-recepcion.md
- manual-usuario-entrenador.md
- manual-usuario-gerente.md
- manual-usuario-mantenimiento.md

### 07-pruebas
- plan-de-pruebas.md
- casos-criticos.md
- pruebas-de-carga.md

## Regla de mantenimiento

Cada cambio de regla de negocio, entidad o flujo debe dejar evidencia actualizada en la documentación y en el changelog del proyecto. La documentación es parte del entregable y debe mantenerse viva.

## Estado del proyecto

- Fase actual: identidad/RBAC de Personal y roles (con alta de colaborador y su cuenta, asignación de roles por usuario, edición de la matriz de permisos por rol, habilitar/deshabilitar cuentas, gestión de sesiones y turnos/asistencia del personal desde el panel), directorio de Socios (con ordenamiento, filtros, alta con consentimiento y ficha del socio con cobro manual/renovación en efectivo, tarjeta declarada o transferencia, activación sin cobro como cortesía, congelar/reanudar/cancelar y edición de datos), bitácora de Accesos (incluido el registro manual), resumen operativo, los nueve incrementos de Punto de venta e inventario (catálogo, inventario con historial, ventas en mostrador, corte de caja, devoluciones y mermas ligadas a la venta original, proveedores con órdenes de compra y recepción, venta a cuenta del socio con cobros y estado de cuenta, venta sin conexión con sincronización idempotente, límite de crédito con antigüedad de saldos, estado de cuenta exportable en PDF/CSV con envío por correo y bitácora, historial de envíos con reintento de fallidos o simulados, y recordatorios de cobranza para saldos vencidos con cooldown), primer incremento de Clases y reservaciones (catálogo de clases y salones, agenda con cupo y lista de espera, reservas, asistencia e inasistencias), cuatro incrementos de Rutinas y seguimiento de progreso (biblioteca de ejercicios, rutinas con versionado y archivado, asignaciones con versión fija, entrenamientos, medidas, metas con línea base congelada y cierre automático, fotos de progreso con almacenamiento local validado por firma y galería con eliminación explícita, gráfica de evolución de medidas con meta activa de referencia, y progreso) y primer incremento de Mantenimiento de equipo e instalaciones (flota con estado y baja, tickets con bloqueo y restauración, bitácora técnica, rondas de limpieza e inspección y estado de servicio por área) y los cuatro incrementos de reportes del módulo 7 (resumen, ingresos, socios, operación, mantenimiento e inventario, con filtro de periodo, MRR esperado separado del dinero cobrado, neteo de devoluciones del POS en base de caja, fronteras de día y series en la zona horaria del gimnasio, valorización de inventario al corte con movimientos y compras del periodo, y exportación CSV) y el primer incremento fiscal del módulo 7 (CFDI 4.0 individual para ventas y cobros de membresía, con perfil fiscal del socio, desglose de IVA, folio por serie, idempotencia, timbrado simulado sin validez fiscal, cancelación con motivo del SAT, descarga de XML y vista Facturación) el segundo incremento fiscal (representación impresa en PDF generada al momento, con marca de agua para simuladas y canceladas, y envío del PDF y el XML por correo con auditoría en la factura) el tercer incremento fiscal (factura global mensual de público en general, con elegibilidad recalculada, `InformacionGlobal`, lote trazable por venta, una global viva por mes y sustitución tras cancelar), el cuarto incremento fiscal (notas de crédito / CFDI de egreso parciales o totales ligadas a una factura de ingreso timbrada, con saldo controlado, relación `TipoRelacion="01"`, cancelación que restaura saldo y auditoría), el quinto incremento fiscal (complementos de pago PPD con parcialidades y saldo, CFDI tipo P con relación `TipoRelacion="07"`, timbrado simulado y cancelación de la última parcialidad vigente), la cartera PPD por antigüedad (saldo abierto por tramos desde el timbrado, complementos timbrados frente a solicitados y fallidos, resumen con fecha de corte, integrada al reporte de ingresos y sin migración) y la conciliación bancaria (cuentas con últimos cuatro dígitos, importación CSV idempotente de hasta 500 líneas, sugerencias de cobros, ventas, abonos, devoluciones electrónicas y complementos PPD timbrados, conciliación uno a uno con diferencia documentada, marcado para revisión y bitácora append-only con `finance.manage`) conectados al backend, junto con la app móvil del socio (acceso sin contraseña con código OTP por correo, sesión de 30 días separada del personal, y consulta de perfil, membresía, acceso habilitado y saldo); el cobro recurrente con pasarela real (el cobro manual en mostrador ya existe), el adaptador de un PAC real (el timbrado actual es solo de vista previa), el cobro de clases premium, la nómina, la conexión bancaria y la conciliación agrupada, el saldo PPD en los demás reportes financieros y en el cierre de conciliación, la cola de correo con confirmación de entrega, los reportes programados o por correo, la mensajería entrenador-socio, los avisos de equipo fuera de servicio a socios/kiosco y el resto de la app del socio (reservas, rutinas, pagos, facturas y notificaciones) permanecen pendientes
- Estado general: backend inicial y preview local con bitácora de accesos persistida (`access_events`), ledger de inventario con ventas, turnos de caja, devoluciones, compras y cuentas por cobrar (`sales`, `sale_items`, `sale_returns`, `sale_return_items`, `suppliers`, `purchase_orders`, `purchase_order_items`, `member_account_payments`, `member_account_statement_deliveries`, `payments` con periodo/turno/cobrador del cobro manual y el límite de crédito en `members`), agenda de clases con reservas y lista de espera (`class_*`), rutinas con asignaciones, entrenamientos, medidas y metas (`exercises`, `routines`, `routine_*`, `workout_logs`, `body_measurements`, `member_goals`), fotos de progreso con metadatos en `progress_photos` y archivos en `PROGRESS_PHOTOS_DIR` y mantenimiento con flota, tickets, bitácora y rondas (`equipment`, `maintenance_*`), la facturación CFDI 4.0 con perfiles fiscales, facturas, conceptos, eventos, el lote de la factura global y las notas de crédito con su relación y los complementos de pago PPD (`member_fiscal_profiles`, `invoices`, `invoice_items`, `invoice_events`, `global_invoice_sales`, `invoice_payments`, `invoice_payment_events`), con entrega del comprobante en PDF y por correo auditada en los mismos eventos, la conciliación bancaria con cuentas, líneas de estado de cuenta y bitácora (`bank_accounts`, `bank_movements`, `bank_movement_events`), el portal del socio con códigos de acceso, sesiones y bitácora (`member_login_codes`, `member_sessions`, `member_auth_events`) y la app Expo del socio, más los reportes de solo lectura calculados sobre esas tablas; Conekta, MFA, aforo, hardware, terminal bancaria y sincronización productiva siguen pendientes de validación
