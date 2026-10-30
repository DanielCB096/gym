# Roadmap

## MVP

- base del proyecto y repositorio
- autenticación,
- roles y permisos
- membresías, socios y cobro recurrente
- control de acceso con modo offline
- punto de venta básico
- facturación y reportes básicos

## Fase 2

- clases y reservas
- rutinas y progreso
- mantenimiento de equipo
- notificaciones avanzadas
- panel de analítica y dashboards

## Fase 3

- servicios extra (nutrición, entrenador personalizado, fisioterapia —con sus incrementos 1 y 2 implementados el 2026-10-29, ADR-039—, casilleros, eventos)
- optimización de rendimiento y multi-sucursal
- automatización avanzada de cumplimiento y reporting

## Estado actual

- Implementado en backend y panel: identidad/RBAC, socios y membresías con cobro manual, accesos (incluido el código rotativo del socio, el kiosco PWA de recepción con token de 90 días, rotación desde el panel y aviso de vencimiento en la campana —ADR-027 y ADR-028—, el límite diario de entradas configurable por plan y el consumo del día visible en la app —ADR-025 y ADR-029—, el control de duplicados del club —ADR-026—, el horario de acceso por plan con ventanas configurables desde el panel —ADR-031—, el aforo del club estimado por tiempo de estancia y apagado por defecto —ADR-032— y la decisión de entrada serializada por socio para que dos kioscos no autoricen dos veces la misma entrada —ADR-030— y el cartel de recepción con dispositivos autorizados y su aviso de equipos no disponibles, ADR-024), personal y turnos (con sus tablas `staff_shifts`/`staff_attendance`/`staff_attendance_events`, que solo llegaron al esquema de Alembic el 2026-10-27 al detectarlo `alembic check`), punto de venta e inventario (incluidas devoluciones, compras, cuentas por cobrar, offline y recordatorios), clases, rutinas con metas del socio, detalle por serie en los entrenamientos, fotos de progreso y gráficas de evolución, mantenimiento, el primer incremento de fisioterapia (catálogo, paquetes prepagados, agenda de recepción con cobro solo por asistencia y cierre del día, ADR-039) y su segundo incremento (`GET /member/physio`, pantalla de solo lectura en la app y los tres avisos de la cita), reportes y CFDI 4.0 individual con timbrado simulado y adaptador de PAC Finkok, representación impresa (PDF), envío por correo, factura global mensual de público en general, notas de crédito (CFDI de egreso), complementos de pago PPD con parcialidades y saldo, cartera PPD por antigüedad integrada al reporte de ingresos, seguimiento en el panel de las cancelaciones que el SAT deja en proceso (`202`, consulta manual con `get_sat_status`), y conciliación bancaria asistida con importación CSV que acepta complementos PPD como candidatos. También el módulo transversal de avisos: la bandeja del personal con su campana real en el panel (`staff_notifications`, alimentada por los entrenamientos que el socio registra desde la app, la asignación de tickets y el vencimiento del token de un kiosco, y con el pendiente de revisión que se cierra solo al revisar —ADR-038—) y la bandeja del socio en la app (`member_notifications`, hoy con los diecisiete tipos: revisión, metas, confirmación de la reserva propia, lista de espera, recordatorio de la clase próxima, cancelación y reprogramación de la clase, vencimiento, el equipo de su plan que quedó fuera de servicio, el estado de sus facturas y los tres de fisioterapia).
- Implementado en la app móvil del socio (Expo/React Native): acceso sin contraseña con código OTP por correo, sesión de 30 días separada del personal, consulta de perfil, membresía, acceso habilitado y saldo, un código de entrada rotativo de seis dígitos para el kiosco de recepción (ADR-024), reserva/cancelación de clases con lista de espera, consulta de rutinas asignadas, entrenamientos (con detalle por serie), medidas y metas, registro de entrenamientos con series (pendientes de revisión del entrenador), de medidas y de metas propias —con cancelación de esas últimas— desde la app, carga, consulta y eliminación de sus fotos de progreso con consentimiento y enlaces firmados, consulta de pagos de membresía y estado de cuenta, la consulta de sus facturas CFDI con descarga de PDF y XML por enlaces firmados, la solicitud de factura de sus propias compras y cobros con perfil fiscal recordado (ADR-019 y ADR-020) y el aviso cuando esa factura se timbra, falla o se cancela (ADR-021), la consulta de solo lectura de su fisioterapia (saldo del paquete, próxima cita e historial) con su tarjeta en el inicio y el aviso de la cita agendada, movida o cancelada, además de la bandeja de avisos del club (revisiones de sus entrenamientos, cambios que el personal hace en sus metas, la confirmación de su reserva, lugares que se liberan, el recordatorio de su clase próxima, la cancelación o el cambio de horario de una clase, el vencimiento de su membresía, el estado de sus facturas y sus citas de fisioterapia) con insignia de no leídos en el inicio. No incluye todavía pago en línea ni avisos push o por correo.
- Fuera de producción: pasarela de pago real, PAC real validado con credenciales, terminal bancaria, conexión bancaria real, hardware de acceso, MFA y las funciones fiscales pendientes (notas de crédito sobre facturas PPD, consulta automática programada de cancelaciones en proceso, seguimiento de la cancelación de complementos, conciliación agrupada o parcial, estado de conciliación en reportes y cola de correo con confirmación de entrega).
- Siguiente foco del MVP: validar los flujos con operación real, validar el PAC de Finkok y la pasarela con credenciales reales, y ampliar la app del socio (pago en línea, aprobación de metas por el entrenador y avisos push o por correo). Para el PAC ya está listo `backend/finkok_demo.py`: un CFDI de prueba con el constructor real que se timbra y, opcionalmente, se cancela contra el ambiente demo, sin tocar la base ni consumir folios.
