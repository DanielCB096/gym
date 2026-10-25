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

- Fase actual: identidad/RBAC de Personal y roles (con alta de colaborador y su cuenta, asignación de roles por usuario, edición de la matriz de permisos por rol, habilitar/deshabilitar cuentas, gestión de sesiones y turnos/asistencia del personal desde el panel), directorio de Socios (con ordenamiento, filtros, alta con consentimiento y ficha del socio con cobro manual/renovación en efectivo, tarjeta declarada o transferencia, activación sin cobro como cortesía, congelar/reanudar/cancelar y edición de datos), bitácora de Accesos (incluido el registro manual), resumen operativo, los nueve incrementos de Punto de venta e inventario (catálogo, inventario con historial, ventas en mostrador, corte de caja, devoluciones y mermas ligadas a la venta original, proveedores con órdenes de compra y recepción, venta a cuenta del socio con cobros y estado de cuenta, venta sin conexión con sincronización idempotente, límite de crédito con antigüedad de saldos, estado de cuenta exportable en PDF/CSV con envío por correo y bitácora, historial de envíos con reintento de fallidos o simulados, y recordatorios de cobranza para saldos vencidos con cooldown), primer incremento de Clases y reservaciones (catálogo de clases y salones, agenda con cupo y lista de espera, reservas, asistencia e inasistencias), primer incremento de Rutinas y seguimiento de progreso (biblioteca de ejercicios, rutinas con versionado y archivado, asignaciones con versión fija, entrenamientos, medidas y progreso) y primer incremento de Mantenimiento de equipo e instalaciones (flota con estado y baja, tickets con bloqueo y restauración, bitácora técnica, rondas de limpieza e inspección y estado de servicio por área) y los cuatro incrementos de reportes del módulo 7 (resumen, ingresos, socios, operación, mantenimiento e inventario, con filtro de periodo, MRR esperado separado del dinero cobrado, neteo de devoluciones del POS en base de caja, fronteras de día y series en la zona horaria del gimnasio, valorización de inventario al corte con movimientos y compras del periodo, y exportación CSV) y el primer incremento fiscal del módulo 7 (CFDI 4.0 individual para ventas y cobros de membresía, con perfil fiscal del socio, desglose de IVA, folio por serie, idempotencia, timbrado simulado sin validez fiscal, cancelación con motivo del SAT, descarga de XML y vista Facturación) el segundo incremento fiscal (representación impresa en PDF generada al momento, con marca de agua para simuladas y canceladas, y envío del PDF y el XML por correo con auditoría en la factura) y el tercer incremento fiscal (factura global mensual de público en general, con elegibilidad recalculada, `InformacionGlobal`, lote trazable por venta, una global viva por mes y sustitución tras cancelar) conectados al backend; el cobro recurrente con pasarela real (el cobro manual en mostrador ya existe), el adaptador de un PAC real (el timbrado actual es solo de vista previa), el cobro de clases premium, la nómina, las notas de crédito, el complemento de pago PPD, la conciliación bancaria, la cola de correo con confirmación de entrega, los reportes programados o por correo, las metas, las fotos de progreso, la mensajería entrenador-socio y los avisos de equipo fuera de servicio a socios/kiosco permanecen pendientes
- Estado general: backend inicial y preview local con bitácora de accesos persistida (`access_events`), ledger de inventario con ventas, turnos de caja, devoluciones, compras y cuentas por cobrar (`sales`, `sale_items`, `sale_returns`, `sale_return_items`, `suppliers`, `purchase_orders`, `purchase_order_items`, `member_account_payments`, `member_account_statement_deliveries`, `payments` con periodo/turno/cobrador del cobro manual y el límite de crédito en `members`), agenda de clases con reservas y lista de espera (`class_*`), rutinas con asignaciones, entrenamientos y medidas (`exercises`, `routines`, `routine_*`, `workout_logs`, `body_measurements`) y mantenimiento con flota, tickets, bitácora y rondas (`equipment`, `maintenance_*`), la facturación CFDI 4.0 con perfiles fiscales, facturas, conceptos, eventos y el lote de la factura global (`member_fiscal_profiles`, `invoices`, `invoice_items`, `invoice_events`, `global_invoice_sales`), con entrega del comprobante en PDF y por correo auditada en los mismos eventos, más los reportes de solo lectura calculados sobre esas tablas; Conekta, MFA, aforo, hardware, terminal bancaria y sincronización productiva siguen pendientes de validación
