# Módulo 3: Personal y roles

## 1. Resumen y alcance

Este módulo cubre la gestión de personal del gimnasio: alta y baja de empleados, expedientes, calendarios de turnos, asistencias, permisos, vacaciones, nómina, comisiones, evaluaciones y control de roles. Está diseñado para que el negocio pueda operar sin depender del dueño para cada decisión de día a día.

### Incluye
- expediente del colaborador con documentos y contratos
- asignación de roles y permisos granulares
- turnos, horarios y asistencias
- faltas, permisos, vacaciones y licencias
- nómina, aguinaldo, prima, ISR, IMSS y CFDI
- evaluaciones y capacitaciones

### No incluye
- gestión de contratación compleja para varias sucursales
- planillas de nómina con varias estructuras de empresa simultáneamente
- recursos humanos con módulos de payroll avanzados fuera de la operación del gimnasio

## 2. Actores y permisos

| Actor | Objetivo | Permisos clave |
|---|---|---|
| Empleado | consultar horario, recibos y permisos | ver su información laboral y asistencias |
| Recepcionista | organizar turnos básicos | registrar asistencia y consultar schedule |
| Entrenador | coordinar clases y agenda | ver agenda, alumnos y faltas |
| Gerente | gestionar operación de personal | alta/baja, turnos, permisos, evaluaciones, cierre de nómina |
| Dueño / administrador | control total del negocio | permisos globales, configuración de roles y auditoría |
| Contador | conciliación y comprobantes | revisar nómina, recibos y CFDI |

## 3. Flujos de usuario paso a paso

### Flujo principal: alta de empleado
1. El gerente o dueño captura el expediente del empleado.
2. Se valida RFC, CURP, NSS, contrato, puesto y horario.
3. Se asigna rol y permisos según el área: recepción, mantenimiento, trainer, gerente o administración.
4. Se activa el usuario en el sistema con MFA si aplica para administración.
5. El sistema registra la creación con bitácora de quién la autorizó.

### Flujo alterno: cambio de turno o permiso
1. El gerente o recepcionista crea una modificación de horario.
2. El sistema valida si el cambio cumple la política de turno mínimo y horario del área.
3. Se notifica al empleado y se registra el cambio en bitácora.

### Flujo de asistencia
1. El empleado marca entrada/salida por QR, RFID o app del personal.
2. El sistema valida ubicación y horario del empleado.
3. Si falta un registro, el gerente puede corregirlo con motivo y justificación.
4. El cierre del día provoca el resumen de asistencia y faltas.

### Flujo de cierre de nómina
1. El contador valida nómina del periodo.
2. Se calculan percepciones, deducciones, bonos y prestaciones.
3. El sistema genera CFDI y recibos para el empleado.
4. Se almacena el comprobante y se notifica por correo o WhatsApp.

## 4. Pantallas / espacios

### 1. Expediente de empleado
- Objetivo: administrar datos personales, contrato, puesto y documentos
- Componentes: datos básicos, RFC, CURP, NSS, perfil, foto, contrato, documentos, nómina y evaluaciones
- Estados: cargando, vacío, error, activo, dado de baja

### 2. Calendario de turnos
- Objetivo: visualizar horarios del personal y asignaciones por área
- Componentes: vista semanal/mensual, turnos por empleado, conflictos, vacaciones y permisos
- Estados: horario normal, conflicto de turno, permiso, vacaciones

### 3. Asistencia del personal
- Objetivo: marcar entrada/salida y revisar faltas
- Componentes: lista de empleados, turno actual, marcaje, faltas, observaciones
- Estados: presente, tarde, ausente, permiso

### 4. Nómina y recibos
- Objetivo: manejar percepciones, deducciones, cierre y generación de recibos
- Componentes: resumen quincenal/mensual, nomina, ISR, IMSS, bonos, deducciones, CFDI
- Estados: borrador, validada, cerrada, emitida

### 5. Evaluaciones y capacitaciones
- Objetivo: llevar registro del desempeño y certificaciones requeridas
- Componentes: evaluaciones, cursos y vencimientos de certificación
- Estados: pendiente, en curso, vencido, aprobado

## 5. Reglas de negocio y casos límite

### Reglas clave
- Un empleado no puede tener permisos contradictorios ni áreas incompatibles.
- Las asistencias se registran con usuario, fecha y método de marcaje.
- La nómina no puede cerrarse sin validación de pagos, horas y deducciones.
- Las vacaciones y prima vacacional siguen la LFT.
- Los recibos de nómina se emiten con soporte fiscal según la normativa vigente.
- Los instructores por honorarios y los contratados por nómina deben diferenciarse claramente.

### Casos límite
- Empleado con asistencia faltante y justificación tardía.
- Cambio de horario en última hora con conflicto de turnos.
- Empleado con permiso no autorizado o fuera de la política.
- Deducción de nómina que cambia el salario neto.
- Certificación de instructor vencida o no renovada.

## 6. Entidades de datos

- Empleado
- ExpedienteEmpleado
- Rol
- PermisoRol
- ContratoTrabajo
- HorarioTurno
- AsistenciaEmpleado
- FaltaEmpleado
- PermisoEmpleado
- VacacionEmpleado
- EvaluacionDesempeno
- Certificacion
- Nomina
- Percepcion
- Deduccion
- ReciboNomina
- Comision

### Campos clave
- Empleado: nombre, fecha de nacimiento, RFC, CURP, NSS, telefonos, dirección
- ContratoTrabajo: tipo, fecha inicio, fecha fin, sueldo, horario, modalidad (nomina/honorarios)
- AsistenciaEmpleado: empleado_id, fecha, hora_entrada, hora_salida, origen, estado
- Nomina: periodo, subtotal, deducciones, neto, estado, usuario_cierre

## 7. Integraciones con otros módulos

- Membresías: comisiones por ventas y referencia de nuevos socios.
- Clases: el instructor se asocia a agenda, asistencia y comisiones por clase.
- Control de acceso: el personal también tiene asistencia por puerta/lector.
- Facturación: los recibos de nómina y pagos de honorarios se acompañan de CFDI.
- Comunicación: avisos de vacaciones, cambios de horario y fin de contrato. **Ninguno está implementado**; lo que sí existe es la bandeja del personal (`staff_notifications`, ADR-017), que hoy solo recibe avisos de otros módulos (entrenamientos del socio pendientes de revisión y tickets de mantenimiento asignados).

## 8. Notificaciones y automatizaciones

- Bandeja real del panel (campana con insignia de no leídos) alimentada por eventos del dominio: ver `docs/02-modulos/notificaciones-del-socio.md` y ADR-017. El destinatario se resuelve con `employee_id`, así que el aviso llega a la cuenta del colaborador y no al rol.
- Lo demás de esta lista sigue siendo diseño, sin emisor ni tabla: aviso de faltas o retrasos.
- Recordatorio de vencimiento de capacitación o certificación.
- Nómina cerrada y recibo disponible para revisión.
- Notificación de vacaciones solicitadas y aprobadas.
- Recordatorio de cumplimiento de horario para turnos críticos.

## 9. Consideraciones de rendimiento específicas del módulo

- carga de asistencia con paginación por fecha y empleado
- caché de turnos activos y roles por usuario
- índices para `empleado_id`, `periodo_nomina`, `turno_id`, `fecha_asistencia`
- generación de nómina y CFDI en workers asíncronos para no bloquear el proceso
- almacenamiento histórico de cambios de rol y su auditoría

## 10. KPIs

- ausentismo promedio por mes
- cumplimiento de horario
- promedio de permisos por empleado
- costo de nómina por turno
- productividad por instructor o recepcionista
- tasa de certificaciones vencidas

## 11. Preguntas abiertas

- ¿se manejan instructores como honorarios o como empleados de planta?
- ¿las comisiones por clases y ventas deben calcularse automáticamente o manualmente?
- ¿el gimnasio requiere control de vacaciones y permisos por departamento o por personal?

## 12. Criterios de aceptación

- Cada empleado tiene expediente, rol, permisos y horario definidos.
- La asistencia se registra y audita correctamente.
- Los permisos y vacaciones quedan rastreables.
- La nómina puede cerrarse y generar recibos o CFDI según la figura laboral.
- Los cambios de rol y permisos quedan registrados con responsable y fecha.
- Los instructores con certificaciones vencidas aparecen en alertas visibles para el gerente.

## 13. Estado

Roles, usuarios, directorio de personal, turnos y asistencia: implementación inicial. Nómina, contratos y expedición de recibos o CFDI: pendientes. Los avisos del panel ya existen (ADR-017) pero los del propio módulo Personal (faltas, certificaciones, vacaciones, nómina) no.

## 14. Historial de cambios

- 2026-10-15: documento ampliado con actores, permisos, flujos, pantallas, reglas, entidades, KPIs y criterios de aceptación.
- 2026-10-17: se conectó la consulta y programación de turnos y la lectura de asistencias desde la pestaña «Equipo y turnos».

## 15. Implementación inicial

- `Employee` almacena el directorio operativo; `AppUser` es la identidad de inicio de sesión y se asocia a un empleado por la columna `employee_id` (única, FK `RESTRICT` a `employees`), que `POST /admin/users` llena al crear la cuenta. Ese vínculo es **el único mapeo empleado → cuenta** y es lo que resuelve a quién llega un aviso del panel (`staff_user_for_employee`, ADR-017): sin cuenta enlazada, o con la cuenta desactivada, no hay bandeja aunque sí expediente, y el emisor omite el aviso en silencio.
- Los roles y permisos son entidades persistidas; el backend calcula permisos efectivos en cada sesión y los exige en las rutas administrativas.
- Las contraseñas se hashean con Argon2. Los tokens Bearer son aleatorios, expiran en 8 horas y solo se conserva su hash SHA-256.
- Los inicios de sesión fallidos, cierres de sesión, creación de cuentas y cambios de rol generan eventos auditables.
- El primer dueño se crea manualmente con un comando local después de aplicar migraciones; no existe contraseña inicial predeterminada.
- La pantalla web ya inicia sesión a través de un BFF Next.js con cookie `HttpOnly`; la navegación se filtra por permisos.
- La pestaña Personal obtiene directorio y roles desde endpoints protegidos del backend. La pestaña "Usuarios" ya lista las cuentas con sus roles activos, permite asignar o retirar roles (`GET /admin/users`, `POST /admin/users/{id}/roles`, `DELETE /admin/users/{id}/roles/{role_code}`) y habilita o deshabilita cuentas (`PATCH /admin/users/{id}`, que revoca las sesiones abiertas al deshabilitar); el backend impide dejar al club sin ningún dueño.
- La pestaña "Roles y permisos" ya permite editar la matriz: otorga y retira permisos por rol (`POST /admin/roles/{code}/permissions`, `DELETE /admin/roles/{code}/permissions/{permission_code}`, permiso `roles.manage`). El rol `owner` está protegido (permisos fijos) para no dejar al club sin administración, y cada cambio queda auditado (`role_permission_granted`/`role_permission_revoked`). El seed de vista previa solo otorga los defaults a los roles que crea, así que las ediciones persisten entre arranques.
- La pestaña "Sesiones" (permiso `sessions.manage`) lista las sesiones con token vigente (`GET /admin/sessions`) y permite revocarlas (`DELETE /admin/sessions/{session_id}`); cada revocación se registra como evento auditable con el administrador responsable. La rotación automática de tokens y las alertas de sesión siguen pendientes.
- La pestaña «Equipo y turnos» consulta los turnos del personal (`GET /admin/staff/shifts`), muestra cuántos están programados y cuántas asistencias hay registradas, la siguiente jornada de cada colaborador en la columna «Horario» y una tabla de turnos con su estado y marcaje de entrada/salida. El botón «Programar turno» (permiso `attendance.manage`) agenda un turno (`POST /admin/staff/{employee_id}/shifts`); el backend rechaza traslapes (`409`) y horarios inválidos o sin zona horaria (`422`). El auto-marcaje del empleado ya existe como API de auto-servicio (`POST /staff/attendance/clock-in|clock-out`, permiso `attendance.self`), pero todavía no tiene interfaz en el panel web.
- Las tres tablas del turno y del marcaje (`staff_shifts`, `staff_attendance`, `staff_attendance_events`) **existieron solo en los modelos hasta el 2026-10-27**: la vista previa las creaba `create_all`, por eso el panel funcionaba, pero ninguna migración las definía y una base PostgreSQL con `alembic upgrade head` no las tenía. La migración `20261027_0038_staffing_shifts_and_attendance.py` las agrega con la forma que los modelos publican; la detectó `alembic check`, que desde ese día corre en CI. Reglas que quedan en la base: un turno no puede terminar antes de empezar, un turno admite **un solo** marcaje (`uq_staff_attendance_shift`), la salida no puede ser anterior a la entrada y la bitácora de marcajes es append-only idempotente por `request_id` (`uq_staff_attendance_events_request` + `request_sha256`). Hoy solo se escribe `source = "staff_app"`; `manual` y `access_reader` están declarados en el `CHECK` sin llamador.
- MFA, limitación de intentos, recuperación de contraseña, la interfaz de auto-marcaje del empleado y el cierre de nómina siguen pendientes; este corte no sustituye revisión de seguridad profesional.
