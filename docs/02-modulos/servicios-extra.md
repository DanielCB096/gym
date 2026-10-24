# Módulo 9: Servicios extra (extensible)

## 1. Resumen y alcance

Este módulo define la arquitectura base para servicios futuros que no están activos hoy, pero que pueden añadirse sin rediseñar la plataforma. El enfoque es un modelo genérico de servicio/producto con recurso, agenda y precio.

## 2. Actores y permisos

- gerente: activar servicios y definir precios
- socio: contratar y agendar
- entrenador o especialista: gestionar agenda y citas
- dueño: control de catálogo y crecimiento del servicio

## 3. Flujos de ejemplo

### Entrenamiento personalizado
1. El socio solicita sesión.
2. El sistema agenda con un entrenador y asigna horario.
3. El pago se gestiona como un servicio con precio asociado.

### Nutrición
1. El usuario agenda consulta.
2. El especialista registra historial y objetivos.
3. Se genera seguimiento y recordatorios.

### Casilleros
1. Se asigna casillero por renta mensual o diaria.
2. El cobro se genera según la política del servicio.
3. La liberación requiere confirmación y auditoría.

## 4. Pantallas

- catálogo de servicios
- detalle de servicio y recurso
- agenda de especialistas
- contratos y asignación de recursos

## 5. Reglas de negocio y casos límite

- cada servicio se define con recurso, duración, precio y disponibilidad
- la agenda debe soportar reservas y bloqueo por disponibilidad del recurso
- el pago puede ser recurrente o por uso según el tipo de servicio

## 6. Entidades de datos

- Servicio
- RecursoServicio
- AgendaServicio
- ReservaServicio
- PrecioServicio
- CobroServicio
- ClienteServicio

## 7. Integraciones

- socios y cobros
- personal y especialidades
- notificaciones y comunicación
- reportes y facturación

## 8. Notificaciones y automatizaciones

- recordatorio de cita
- confirmación de pago
- aviso de recurso ocupado o no disponible

## 9. Consideraciones de rendimiento

- agenda optimizada por fecha y recurso
- caché de servicios activos
- validación de disponibilidad en el momento de reserva

## 10. KPIs

- demanda por servicio
- tasa de ocupación del recurso
- tasa de cancelación y no asistencia

## 11. Preguntas abiertas

- ¿qué servicio se activará primero?
- ¿debe existir un catálogo unificado de productos y servicios?

## 12. Criterios de aceptación

- el sistema permite activar un servicio nuevo sin rediseñar el núcleo
- cada recurso tiene disponibilidad y precio asociado
- las reservas quedan trazadas y auditable

## 13. Estado

En diseño

## 14. Historial de cambios

- 2026-10-15: documento inicial de módulo
