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

- Implementado en backend y panel: identidad/RBAC, socios y membresías con cobro manual, accesos, personal y turnos, punto de venta e inventario (incluidas devoluciones, compras, cuentas por cobrar, offline y recordatorios), clases, rutinas, mantenimiento, reportes y CFDI 4.0 individual con timbrado simulado, representación impresa (PDF), envío por correo, factura global mensual de público en general, notas de crédito (CFDI de egreso) y conciliación bancaria asistida con importación CSV.
- Fuera de producción: pasarela de pago real, PAC real, terminal bancaria, conexión bancaria real, hardware de acceso, MFA y las funciones fiscales pendientes (complemento PPD, conciliación agrupada o parcial, estado de conciliación en reportes y cola de correo con confirmación de entrega).
- Siguiente foco del MVP: validar los flujos con operación real, cerrar la integración del PAC y de la pasarela, y completar la app del socio.
