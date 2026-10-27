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

- Implementado en backend y panel: identidad/RBAC, socios y membresías con cobro manual, accesos, personal y turnos, punto de venta e inventario (incluidas devoluciones, compras, cuentas por cobrar, offline y recordatorios), clases, rutinas con metas del socio, detalle por serie en los entrenamientos, fotos de progreso y gráficas de evolución, mantenimiento, reportes y CFDI 4.0 individual con timbrado simulado, representación impresa (PDF), envío por correo, factura global mensual de público en general, notas de crédito (CFDI de egreso), complementos de pago PPD con parcialidades y saldo, cartera PPD por antigüedad integrada al reporte de ingresos, y conciliación bancaria asistida con importación CSV que acepta complementos PPD como candidatos.
- Implementado en la app móvil del socio (Expo/React Native): acceso sin contraseña con código OTP por correo, sesión de 30 días separada del personal, consulta de perfil, membresía, acceso habilitado y saldo, reserva/cancelación de clases con lista de espera, consulta de rutinas asignadas, entrenamientos (con detalle por serie), medidas y metas, registro de entrenamientos con series (pendientes de revisión del entrenador), de medidas y de metas propias —con cancelación de esas últimas— desde la app, y consulta de pagos de membresía y estado de cuenta. No incluye todavía pago en línea, facturas ni notificaciones.
- Fuera de producción: pasarela de pago real, PAC real, terminal bancaria, conexión bancaria real, hardware de acceso, MFA y las funciones fiscales pendientes (notas de crédito sobre facturas PPD, conciliación agrupada o parcial, estado de conciliación en reportes y cola de correo con confirmación de entrega).
- Siguiente foco del MVP: validar los flujos con operación real, cerrar la integración del PAC y de la pasarela, y ampliar la app del socio (pago en línea, facturas, fotos de progreso, aprobación de metas por el entrenador y notificaciones).
