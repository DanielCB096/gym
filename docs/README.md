# Documentación del sistema

Esta carpeta contiene la memoria del proyecto: contexto de negocio, arquitectura, módulos, procesos, integraciones, decisiones de diseño, operación y pruebas.

Para retomar el trabajo donde se quedó, empieza por [TRASPASO.md](TRASPASO.md).

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
- [servicios-extra.md](02-modulos/servicios-extra.md) — arquitectura genérica de servicios futuros; la fisioterapia ya tiene documento propio
- [fisioterapia.md](02-modulos/fisioterapia.md) — consultorio de fisioterapia: cobro solo por asistencia, agenda de recepción y paquete mensual (ADR-039)
- [notificaciones-del-socio.md](02-modulos/notificaciones-del-socio.md) — cubre también la bandeja del personal, el aviso de equipo fuera de servicio, los avisos de estado de factura y la confirmación de la reserva propia

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
- ADR-010-reservas-clases-app.md
- ADR-011-rutinas-socio-lectura.md
- ADR-012-pagos-socio-lectura.md
- ADR-013-registro-entrenamientos-medidas-app.md
- ADR-014-series-de-entrenamiento.md
- ADR-015-metas-desde-la-app.md
- ADR-016-notificaciones-del-socio.md
- ADR-017-avisos-del-personal.md
- ADR-018-aviso-equipo-fuera-de-servicio.md
- ADR-019-facturas-del-socio-en-la-app.md
- ADR-020-solicitud-de-facturas-del-socio.md
- ADR-021-avisos-de-estado-de-factura.md
- ADR-022-adaptador-finkok.md
- ADR-023-fotos-de-progreso-desde-la-app.md
- ADR-024-codigo-rotativo-y-kiosco-de-recepcion.md
- ADR-025-limite-diario-de-entradas-por-plan.md
- ADR-026-control-de-duplicados-antipassback.md
- ADR-027-caducidad-y-rotacion-del-token-del-kiosco.md
- ADR-028-aviso-de-vencimiento-del-token-del-kiosco.md
- ADR-029-consumo-diario-visible-en-la-app.md
- ADR-030-decision-de-entrada-serializada-por-socio.md
- ADR-031-horario-de-acceso-por-plan.md
- ADR-032-aforo-estimado-del-club.md
- ADR-033-cobro-de-clases-premium.md
- ADR-034-devolucion-de-servicios-desde-caja.md
- ADR-035-recordatorios-de-clase-y-lista-de-espera.md
- ADR-036-confirmacion-de-reserva-en-la-bandeja.md
- ADR-037-avisos-de-clase-cancelada-o-reprogramada.md
- ADR-038-cierre-del-aviso-de-revision.md
- ADR-039-fisioterapia-cobro-por-asistencia.md
- ADR-040-retencion-de-datos-del-kiosco.md
- ADR-041-auto-marcaje-y-marcas-faltantes.md
- ADR-042-correccion-de-marcas-registradas.md
- ADR-043-tolerancia-anulacion-y-bitacora.md
- ADR-044-avisos-solicitudes-y-auditoria-de-politica.md
- ADR-045-plazo-y-escalado-de-solicitudes.md
- ADR-046-vinculo-solicitud-evento-y-csv-de-anulaciones.md
- ADR-047-relleno-del-vinculo-solicitud-evento.md
- ADR-048-cola-de-correos-de-los-avisos-de-asistencia.md
- ADR-049-envio-y-reintento-de-la-cola-de-correos-de-asistencia.md

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

- Fase actual: identidad/RBAC de Personal y roles (con alta de colaborador y su cuenta, asignación de roles por usuario, edición de la matriz de permisos por rol, habilitar/deshabilitar cuentas, gestión de sesiones, turnos/asistencia del personal desde el panel con la pestaña «Mi jornada» para el auto-marcaje —ADR-041—, la corrección de marcas faltantes y la edición de una marca ya registrada con motivo auditado y la marca anterior conservada en la bitácora —ADR-042—, más la tolerancia de retardo configurable, la anulación de una marca —de salida o de entrada— y el visor de la bitácora del turno —ADR-043—, y el aviso al colaborador cuando se le corrige o anula una marca, las solicitudes de cambio con justificación y decisión del supervisor, la auditoría de la política con su historial de cambios y el reporte de anulaciones por operador —ADR-044—, y el plazo configurable para decidir una solicitud, congelado en cada solicitud y escalado a la dirección cuando vence —ADR-045—, y el vínculo explícito entre la solicitud aprobada y su evento de bitácora junto con la exportación CSV del reporte de anulaciones —ADR-046—, y el relleno de ese vínculo en los eventos anteriores a la columna —ADR-047—, y la cola de correos de esos avisos con su interruptor de club, escrita junto con el aviso —ADR-048—, y el envío real de esa cola tras la respuesta, su reintento y la tarjeta de entregas del panel —ADR-049—), directorio de Socios (con ordenamiento, filtros, alta con consentimiento y ficha del socio con cobro manual/renovación en efectivo, tarjeta declarada o transferencia, activación sin cobro como cortesía, congelar/reanudar/cancelar y edición de datos), bitácora de Accesos (incluido el registro manual, el kiosco de recepción con código rotativo —ADR-024—, token de 90 días con rotación desde el panel —ADR-027— y su aviso de vencimiento en la campana —ADR-028— el consumo del código reflejado en la app (2026-10-29), el consumo diario de entradas visible en la pantalla del código —ADR-029— y la decisión de entrada serializada por socio —ADR-030—, el límite diario de entradas por plan con su tarjeta en «Kiosco» —ADR-025— y el control de duplicados del club con su ventana configurable —ADR-026— y el horario de acceso por plan con ventanas configurables que solo restringen cuando el club las define —ADR-031— y el aforo del club estimado con ventana de estancia configurable, apagado por defecto —ADR-032—, y la retención configurable de códigos e intentos del kiosco con su script de purga —ADR-040—), resumen operativo, los nueve incrementos de Punto de venta e inventario (catálogo, inventario con historial, ventas en mostrador, corte de caja, devoluciones y mermas ligadas a la venta original, proveedores con órdenes de compra y recepción, venta a cuenta del socio con cobros y estado de cuenta, venta sin conexión con sincronización idempotente, límite de crédito con antigüedad de saldos, estado de cuenta exportable en PDF/CSV con envío por correo y bitácora, historial de envíos con reintento de fallidos o simulados, y recordatorios de cobranza para saldos vencidos con cooldown), Clases y reservaciones (catálogo de clases y salones, agenda con cupo y lista de espera, reservas, asistencia e inasistencias, y el cobro del extra de una clase premium al marcar la asistencia con su reembolso —ADR-033—, más la devolución de ese cobro desde la caja con un permiso propio para gerencia —ADR-034—, y el recordatorio de la clase próxima a 24 y 2 horas junto con el asiento automático de la lista de espera cuando se libera un lugar —ADR-035—, más la confirmación de la reserva propia en la bandeja del socio —ADR-036—, y el aviso de clase cancelada o reprogramada a toda reserva viva —ADR-037—), los tres incrementos de Fisioterapia (catálogo de servicios y paquetes, agenda de recepción, cita ligada al paquete o como sesión suelta, cobro solo al marcar asistencia con corrección dentro de la ventana, cierre del día que no toca saldos —ADR-039—; consulta de solo lectura `GET /member/physio` en la app, los tres avisos de la cita —agendada, movida y cancelada— y el recordatorio de 24 horas; y consultorios y especialidades con el perfil del fisioterapeuta, extensión y anulación del paquete con `physio.adjust` y su bitácora, y reporte del consultorio con ocupación, inasistencia, ingresos, ajustes y exportación CSV), nueve incrementos de Rutinas y seguimiento de progreso (biblioteca de ejercicios, rutinas con versionado y archivado, asignaciones con versión fija, entrenamientos, medidas, metas con línea base congelada y cierre automático, fotos de progreso con almacenamiento local validado por firma y galería con eliminación explícita, gráfica de evolución de medidas con meta activa de referencia, progreso, consulta desde la app, registro de entrenamientos y medidas desde la app con origen y revisión del entrenador, detalle por serie con `workout_sets` validado contra el plan de la versión fijada y editor en la app y en el panel, alta y cancelación de metas propias desde la app con `member_goals.origin`, y carga, consulta y eliminación de fotos de progreso desde la app con consentimiento, origen y enlaces firmados —ADR-023—) y primer incremento de Mantenimiento de equipo e instalaciones (flota con estado y baja, tickets con bloqueo y restauración, bitácora técnica, rondas de limpieza e inspección y estado de servicio por área, con el aviso de equipos no disponibles en la app, el kiosco y el cartel de recepción), los tres incrementos del módulo transversal de avisos (tablas `member_notifications` y `staff_notifications` alimentadas por los servicios de rutinas, clases y mantenimiento en la misma transacción del evento, con el recordatorio de vencimiento de la membresía calculado al leer la bandeja y deduplicado en base de datos, la bandeja de auto-servicio `/member/notifications*` en la app, la campana real `/admin/notifications*` del panel —esta última resuelta por ADR-017—, el aviso al socio cuando el equipo que necesita su plan vigente queda fuera de servicio, con la audiencia buscada en mantenimiento casando la versión congelada de la asignación con `exercises.equipment_id` según ADR-018, y el recordatorio de la clase próxima con el asiento de la lista de espera al liberarse un lugar —ADR-035—, más la confirmación de la reserva propia escrita junto con la reserva —ADR-036—, los avisos de clase cancelada o reprogramada —ADR-037— y el cierre del aviso de revisión cuando el entrenador revisa —ADR-038—) y los cuatro incrementos de reportes del módulo 7 (resumen, ingresos, socios, operación, mantenimiento e inventario, con filtro de periodo, MRR esperado separado del dinero cobrado, neteo de devoluciones del POS en base de caja, fronteras de día y series en la zona horaria del gimnasio, valorización de inventario al corte con movimientos y compras del periodo, y exportación CSV) y el primer incremento fiscal del módulo 7 (CFDI 4.0 individual para ventas y cobros de membresía, con perfil fiscal del socio, desglose de IVA, folio por serie, idempotencia, timbrado simulado sin validez fiscal, cancelación con motivo del SAT, descarga de XML y vista Facturación) el segundo incremento fiscal (representación impresa en PDF generada al momento, con marca de agua para simuladas y canceladas, y envío del PDF y el XML por correo con auditoría en la factura) el tercer incremento fiscal (factura global mensual de público en general, con elegibilidad recalculada, `InformacionGlobal`, lote trazable por venta, una global viva por mes y sustitución tras cancelar), el cuarto incremento fiscal (notas de crédito / CFDI de egreso parciales o totales ligadas a una factura de ingreso timbrada, con saldo controlado, relación `TipoRelacion="01"`, cancelación que restaura saldo y auditoría), el quinto incremento fiscal (complementos de pago PPD con parcialidades y saldo, CFDI tipo P con relación `TipoRelacion="07"`, timbrado simulado y cancelación de la última parcialidad vigente), la cartera PPD por antigüedad (saldo abierto por tramos desde el timbrado, complementos timbrados frente a solicitados y fallidos, resumen con fecha de corte, integrada al reporte de ingresos y sin migración) y la conciliación bancaria (cuentas con últimos cuatro dígitos, importación CSV idempotente de hasta 500 líneas, sugerencias de cobros, ventas, abonos, devoluciones electrónicas y complementos PPD timbrados, conciliación uno a uno con diferencia documentada, marcado para revisión y bitácora append-only con `finance.manage`) conectados al backend, junto con la app móvil del socio (acceso sin contraseña con código OTP por correo, sesión de 30 días separada del personal, consulta de perfil, membresía, acceso habilitado y saldo, y reserva/cancelación de clases con lista de espera, consulta de rutinas asignadas, entrenamientos, medidas y metas, registro de entrenamientos (pendientes de revisión del entrenador), de medidas y de metas propias —que también cancela— desde la app, consulta de pagos de membresía y estado de cuenta, y la consulta de sus facturas con descarga de PDF y XML por enlaces firmados de 10 minutos (ADR-019) y la solicitud de factura de sus propias compras y cobros con perfil fiscal recordado (ADR-020), la consulta de su fisioterapia (saldo del paquete, próxima cita e historial, con tarjeta en el inicio, avisos de la cita y recordatorio de 24 horas), con su bandeja de avisos del club y la insignia de no leídos en el inicio); el cobro recurrente con pasarela real (el cobro manual en mostrador ya existe), el adaptador de un PAC real ya existe para Finkok y está probado con respuestas simuladas (ADR-022), pero falta validarlo con credenciales y cuenta reales, la reserva y el cobro de clases premium desde la app (hoy se cobra en recepción —ADR-033—), la nómina, la conexión bancaria y la conciliación agrupada, el saldo PPD en los demás reportes financieros y en el cierre de conciliación, el acuse de entrega de la cola de correo de asistencia (hoy «enviado» significa que el servidor de correo aceptó el mensaje, no que el colaborador lo leyó) y el envío de los demás avisos del personal, los reportes programados o por correo, la mensajería entrenador-socio, la validación del cartel de recepción en una TV real (ya existe `kiosk/cartel.html` desde 2026-10-28, ADR-018) y el resto de la app del socio (pago en línea), los avisos push y el correo de los demás avisos del personal permanecen pendientes; la campana del panel dejó de ser dato de muestra ese mismo día (ADR-017)
- Fisioterapia (módulo 10, ADR-039): **tres incrementos implementados** —catálogo, paquetes prepagados, agenda de recepción, cobro solo por asistencia y cierre del día, con su página «Fisioterapia» en el panel; consulta de solo lectura y tarjeta en la app del socio, los tres avisos de la cita y el recordatorio de 24 horas; consultorios y especialidades con el perfil del fisioterapeuta, extensión y anulación del paquete con `physio.adjust` y bitácora, y reporte del consultorio con exportación CSV—. Sigue fuera de alcance la devolución del paquete y la reserva desde la app. Detalle en [fisioterapia.md](02-modulos/fisioterapia.md).
- Estado general: backend inicial y preview local con bitácora de accesos persistida (`access_events`), el límite diario por plan (`plans.daily_entry_limit`), la ventana de antipassback (`access_settings`) y los tokens de kiosco con caducidad de 90 días y rotación (`kiosk_devices.token_expires_at`) que el kiosco aplica, ledger de inventario con ventas, turnos de caja, devoluciones, compras y cuentas por cobrar (`sales`, `sale_items`, `sale_returns`, `sale_return_items`, `suppliers`, `purchase_orders`, `purchase_order_items`, `member_account_payments`, `member_account_statement_deliveries`, `payments` con periodo/turno/cobrador del cobro manual y el límite de crédito en `members`), agenda de clases con reservas y lista de espera (`class_*`), consultorio de fisioterapia con su catálogo, paquetes prepagados y citas (`physio_services`, `physio_offers`, `physio_packs`, `physio_appointments`, `physio_rooms`, `physio_specialties`, `physio_therapist_profiles`, `physio_pack_adjustments`, más `sales.physio_appointment_id` para ligar el cobro de una sesión suelta), rutinas con asignaciones, entrenamientos con su detalle por serie, medidas y metas (`exercises`, `routines`, `routine_*`, `workout_logs`, `workout_sets`, `body_measurements`, `member_goals`; `workout_logs`, `body_measurements`, `member_goals` y `progress_photos` llevan la columna `origin` `staff`/`app`), fotos de progreso con metadatos en `progress_photos` (con `origin` `staff`/`app`) y archivos en `PROGRESS_PHOTOS_DIR` y mantenimiento con flota, tickets, bitácora y rondas (`equipment`, `maintenance_*`), la facturación CFDI 4.0 con perfiles fiscales, facturas, conceptos, eventos, el lote de la factura global y las notas de crédito con su relación y los complementos de pago PPD (`member_fiscal_profiles`, `invoices`, `invoice_items`, `invoice_events`, `global_invoice_sales`, `invoice_payments`, `invoice_payment_events`), con entrega del comprobante en PDF y por correo auditada en los mismos eventos, la conciliación bancaria con cuentas, líneas de estado de cuenta y bitácora (`bank_accounts`, `bank_movements`, `bank_movement_events`), el portal del socio con códigos de acceso, sesiones, bitácora y su bandeja de avisos y la del personal (`member_login_codes`, `member_sessions`, `member_auth_events`, `member_notifications`, `staff_notifications`, `staff_notification_deliveries`) y la app Expo del socio (perfil, reservas de clases, consulta de rutinas, entrenamientos, medidas y metas, registro de entrenamientos, medidas y metas propias con la columna `origin` en `workout_logs`, `body_measurements`, `member_goals` y `progress_photos`, carga de fotos de progreso con consentimiento y enlaces firmados, consulta de pagos y estado de cuenta sobre las tablas ya existentes, la solicitud de facturas propias sobre `invoices` y `member_fiscal_profiles` y la lectura de sus avisos, que emiten los servicios de rutinas, clases, mantenimiento y fisioterapia en la misma transacción del evento —incluido `equipment_out_of_service`, el aviso a los socios cuyo plan vigente usa una máquina que acaba de quedar parada (ADR-018)—; la campana del panel ya no es dato de muestra: lee `staff_notifications` de la cuenta activa, alimentada por `log_workout` desde la app y por la asignación de tickets de mantenimiento), más los reportes de solo lectura calculados sobre esas tablas; Conekta, MFA, aforo, hardware, terminal bancaria y sincronización productiva siguen pendientes de validación
