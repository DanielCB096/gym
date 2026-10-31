# Apertura y cierre del gimnasio

## Objetivo

Definir el flujo mínimo de operación para dejar el gimnasio listo al iniciar la jornada y cerrar la operación sin perder trazabilidad, control de efectivo, permisos ni estado del club.

## Alcance

Este proceso aplica a:
- recepción y operación del club
- control de acceso
- personal y turnos
- punto de venta y caja
- mantenimiento básico y equipos disponibles
- sincronización y respaldo operativo

## Criterios de cumplimiento

- La apertura no puede dejar el club sin personal responsable asignado.
- La caja debe quedar con el monto inicial documentado.
- El acceso debe estar habilitado solo para socios con membresía vigente.
- La operación de cierre debe registrar cortes de caja y cambios de estado de equipos.
- Las tareas no ejecutadas deben quedar en una lista de seguimiento y asignadas a responsable.

## Apertura del día

### 1. Verificación de sistema
1. Confirmar que el backend, la base de datos y Redis están disponibles.
2. Validar que la app web del panel y el kiosco de recepción responden.
3. Revisar alertas de seguridad, permisos y avisos pendientes.
4. Verificar que el servicio de notificaciones y el cron de purga/receipts esté operativo.

### 2. Personal y turnos
1. Revisar la programación del personal del día.
2. Confirmar asistencia del supervisor de recepción y del responsable de mantenimiento.
3. Validar que cada colaborador tenga rol activo y sesión válida.
4. Revisar avisos del personal y solicitudes abiertas con vencimiento.

### 3. Control de acceso
1. Confirmar que los dispositivos autorizados del kiosco de recepción estén activos.
2. Revisar el estado del token del kiosco y su vencimiento.
3. Verificar que no haya equipos bloqueados por mantenimiento ni incidencias.
4. Comprobar que el aforo y el horario por plan estén activos según la configuración del club.

### 4. Punto de venta y caja
1. Abrir el turno de caja con el monto inicial autorizado.
2. Confirmar que el inventario base se encuentra disponible y sin alertas críticas.
3. Revisar ventas pendientes, devoluciones, cargos a cuenta y cobros en espera.
4. Confirmar que las formas de pago habilitadas correspondan al día de operación.

### 5. Mantenimiento y operación física
1. Revisar el estado de equipos, áreas y salas.
2. Confirmar que los equipos fuera de servicio aparezcan marcados en app y kiosco.
3. Registrar incidencias si hay equipos críticos que requieren bloqueo.

## Cierre del día

### 1. Cierre operativo
1. Cerrar las ventas abiertas y validar que no queden turnos activos.
2. Registrar el corte de caja y compararlo con el total de ventas del día.
3. Confirmar que todas las operaciones de cobro quedaron asentadas y no pendientes.
4. Revisar devoluciones, cargos a cuenta, pagos pendientes y notificaciones enviadas.

### 2. Cierre de acceso
1. Revisar eventos de entrada/salida del día.
2. Validar duplicados, accesos bloqueados y anulaciones de marcas.
3. Confirmar que se dejó la bitácora de acceso consistente y sin inconsistencias de turno.

### 3. Mantenimiento y seguridad
1. Marcar equipos con observaciones relevantes y dejar estado final visible.
2. Revisar tickets abiertos y decidir si quedan en operación o en espera.
3. Confirmar que la auditoría de cambios sensibles quedó registrada.

### 4. Cierre administrativo
1. Guardar respaldo de la base de datos y de archivos críticos si aplica.
2. Verificar que el cron de limpieza y sync de recibos está programado.
3. Dejar un resumen del día con ventas, incidencias, accesos y actividad de personal.

## Responsables

- Recepción o supervisor del turno: apertura/cierre del establecimiento y control de caja.
- Encargado de acceso: revisión del estado del kiosco, códigos y alertas de acceso.
- Personal de mantenimiento: equipos y estado de servicio.
- Gerencia o administración: revisión final de cierre, incidencias relevantes y autorizaciones.

## Registro y trazabilidad

Todo cierre debe dejar evidencia en:
- bitácora de turnos del personal
- registro de venta/corte de caja
- bitácora de acceso y eventos
- tickets de mantenimiento
- cambios de configuración o permisos ejecutados durante la jornada

## Riesgos y excepciones

- Si falla la base de datos o Redis, no se cierra la operación como si todo estuviera bien: se documenta la incidencia y se deja en espera.
- Si hay discrepancias de caja, la diferencia debe quedar reportada antes de cerrar el día.
- Si un equipo crítico queda fuera de servicio, debe quedar visible en panel, app y kiosco.
- Si hay una incidencia de seguridad o acceso anómalo, se notifica al responsable del club y queda registrada en auditoría.

## Estado de implementación

- El flujo operativo general ya está representado en el modelo de negocio del proyecto y en los procesos de acceso, ventas y personal.
- La parte técnica real de cierre operativo se apoya en las funciones de corte de caja, bitácora de acceso, mantenimientos, cron de purgas y sincronización de acuses.
- Esta documentación deja un estándar mínimo para operación diaria sin entrar en los flujos de push o entrega de notificaciones del socio, que siguen siendo un trabajo más reciente y activo.

## KPIs operativos sugeridos

- tiempo de apertura
- ventas cerradas sin diferencias de caja
- incidencias de acceso no resueltas
- equipos fuera de servicio activos
- turnos finalizados sin tareas pendientes
