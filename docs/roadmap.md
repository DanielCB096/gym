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

- servicios extra (nutrición, entrenador personalizado, casilleros, eventos)
- optimización de rendimiento y multi-sucursal
- automatización avanzada de cumplimiento y reporting

## Estado actual

- Implementado en backend y panel: identidad/RBAC, socios y membresías con cobro manual, accesos (incluido el código rotativo del socio y el kiosco PWA de recepción con dispositivos autorizados, ADR-024), personal y turnos (con sus tablas `staff_shifts`/`staff_attendance`/`staff_attendance_events`, que solo llegaron al esquema de Alembic el 2026-10-27 al detectarlo `alembic check`), punto de venta e inventario (incluidas devoluciones, compras, cuentas por cobrar, offline y recordatorios), clases, rutinas con metas del socio, detalle por serie en los entrenamientos, fotos de progreso y gráficas de evolución, mantenimiento, reportes y CFDI 4.0 individual con timbrado simulado y adaptador de PAC Finkok, representación impresa (PDF), envío por correo, factura global mensual de público en general, notas de crédito (CFDI de egreso), complementos de pago PPD con parcialidades y saldo, cartera PPD por antigüedad integrada al reporte de ingresos, seguimiento en el panel de las cancelaciones que el SAT deja en proceso (`202`, consulta manual con `get_sat_status`), y conciliación bancaria asistida con importación CSV que acepta complementos PPD como candidatos. También el módulo transversal de avisos: la bandeja del personal con su campana real en el panel (`staff_notifications`, alimentada por los entrenamientos que el socio registra desde la app y por la asignación de tickets) y la bandeja del socio en la app (`member_notifications`, hoy con los diez tipos: revisión, metas, lista de espera, vencimiento, el equipo de su plan que quedó fuera de servicio y el estado de sus facturas).
- Implementado en la app móvil del socio (Expo/React Native): acceso sin contraseña con código OTP por correo, sesión de 30 días separada del personal, consulta de perfil, membresía, acceso habilitado y saldo, un código de entrada rotativo de seis dígitos para el kiosco de recepción (ADR-024), reserva/cancelación de clases con lista de espera, consulta de rutinas asignadas, entrenamientos (con detalle por serie), medidas y metas, registro de entrenamientos con series (pendientes de revisión del entrenador), de medidas y de metas propias —con cancelación de esas últimas— desde la app, carga, consulta y eliminación de sus fotos de progreso con consentimiento y enlaces firmados, consulta de pagos de membresía y estado de cuenta, la consulta de sus facturas CFDI con descarga de PDF y XML por enlaces firmados, la solicitud de factura de sus propias compras y cobros con perfil fiscal recordado (ADR-019 y ADR-020) y el aviso cuando esa factura se timbra, falla o se cancela (ADR-021), además de la bandeja de avisos del club (revisiones de sus entrenamientos, cambios que el personal hace en sus metas, lugares que se liberan, el vencimiento de su membresía y el estado de sus facturas) con insignia de no leídos en el inicio. No incluye todavía pago en línea ni avisos push o por correo.
- Fuera de producción: pasarela de pago real, PAC real validado con credenciales, terminal bancaria, conexión bancaria real, hardware de acceso, MFA y las funciones fiscales pendientes (notas de crédito sobre facturas PPD, consulta automática programada de cancelaciones en proceso, seguimiento de la cancelación de complementos, conciliación agrupada o parcial, estado de conciliación en reportes y cola de correo con confirmación de entrega).
- Siguiente foco del MVP: validar los flujos con operación real, validar el PAC de Finkok y la pasarela con credenciales reales, y ampliar la app del socio (pago en línea, aprobación de metas por el entrenador y avisos push o por correo). Para el PAC ya está listo `backend/finkok_demo.py`: un CFDI de prueba con el constructor real que se timbra y, opcionalmente, se cancela contra el ambiente demo, sin tocar la base ni consumir folios.
