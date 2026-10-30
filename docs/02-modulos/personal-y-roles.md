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
4. Si la marca quedó mal, el empleado **pide** la corrección o la anulación desde «Mi jornada» con una justificación; un supervisor con `attendance.manage` la aprueba —aplicando el cambio y dejando la bitácora del turno como si se hubiera hecho desde el panel, pero con el identificador de la solicitud en el evento— o la rechaza con una nota obligatoria. El colaborador recibe el aviso con la decisión.
5. El cierre del día provoca el resumen de asistencia y faltas.

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
- SolicitudCambioAsistencia
- EventoPoliticaAsistencia
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
- SolicitudCambioAsistencia: asistencia_id, empleado_id, marca, acción (corregir/anular), hora propuesta, justificación, estado, decidida_por, nota
- EventoPoliticaAsistencia: actor_id, valores anteriores, valores nuevos, fecha
- Nomina: periodo, subtotal, deducciones, neto, estado, usuario_cierre

## 7. Integraciones con otros módulos

- Membresías: comisiones por ventas y referencia de nuevos socios.
- Clases: el instructor se asocia a agenda, asistencia y comisiones por clase.
- Control de acceso: el personal también tiene asistencia por puerta/lector.
- Facturación: los recibos de nómina y pagos de honorarios se acompañan de CFDI.
- Comunicación: avisos de vacaciones, cambios de horario y fin de contrato. **Ninguno está implementado**; lo que sí existe es la bandeja del personal (`staff_notifications`, ADR-017), que hoy recibe avisos de otros módulos (entrenamientos del socio pendientes de revisión y tickets de mantenimiento asignados) y, desde ADR-044, los cinco del ciclo de asistencia: corrección, anulación, solicitud pendiente, solicitud aprobada y solicitud rechazada, más el aviso de solicitud vencida a la dirección desde ADR-045.

## 8. Notificaciones y automatizaciones

- Bandeja real del panel (campana con insignia de no leídos) alimentada por eventos del dominio: ver `docs/02-modulos/notificaciones-del-socio.md` y ADR-017. El destinatario se resuelve con `employee_id`, así que el aviso llega a la cuenta del colaborador y no al rol.
- Avisos del ciclo de asistencia (ADR-044): `attendance_corrected` y `attendance_voided` avisan al colaborador cuando un supervisor corrige o anula su marca, con la hora anterior y nueva, el motivo y quién lo hizo; `attendance_request_pending` avisa a los supervisores de una solicitud nueva —es cerrable desde la campana— y `attendance_request_approved`/`attendance_request_rejected` anuncian la decisión al colaborador con la nota del supervisor. No se avisa a quien actúa sobre su propia marca ni a un expediente sin cuenta.
- **Aviso de solicitud vencida (ADR-045).** Cuando una solicitud sigue pendiente después del plazo del club, `attendance_request_overdue` llega a las cuentas con rol `owner` —nunca a quien la pidió— con el colaborador, la marca, el día, cuándo se pidió y el plazo incumplido. Es cerrable desde la campana y se resuelve solo al decidir la solicitud. No hay planificador: el aviso se crea y se deduplica al leer la cola o la bandeja, con la clave `attendance_request_overdue:{request.id}:{user_id}`.
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

Roles, usuarios, directorio de personal, turnos y asistencia: implementación inicial. Nómina, contratos y expedición de recibos o CFDI: pendientes. Los avisos del panel ya existen (ADR-017), incluidos los del ciclo de asistencia (ADR-044), pero los del propio módulo Personal (faltas, certificaciones, vacaciones, nómina) no.

## 14. Historial de cambios

- 2026-10-15: documento ampliado con actores, permisos, flujos, pantallas, reglas, entidades, KPIs y criterios de aceptación.
- 2026-10-17: se conectó la consulta y programación de turnos y la lectura de asistencias desde la pestaña «Equipo y turnos».
- 2026-10-30: el colaborador marca su entrada y salida en la pestaña «Mi jornada» (ADR-041); la entrada abre 15 minutos antes y recepción registra marcas faltantes con motivo auditado.
- 2026-10-30: recepción corrige una marca **ya registrada** con motivo obligatorio (`POST /admin/staff/attendance/{id}/corrections`), la anterior queda en la bitácora del turno y el estado se recalcula (ADR-042).
- 2026-10-30: la gracia de entrada y la tolerancia de retardo se configuran en el club (`staffing_settings`), una marca se puede **anular** —salida sola o entrada completa— con motivo y la bitácora del turno se consulta desde el panel (ADR-043).
- 2026-10-30: el colaborador recibe aviso al corregirle o anularle una marca, **pide** el cambio con su justificación desde «Mi jornada», el supervisor decide con nota y todo queda con su aviso; la política de asistencia registra quién la cambió y con qué valores anteriores, y las anulaciones se reportan por operador (ADR-044).
- 2026-10-30: la política suma un **plazo para decidir** (24 h por defecto, 0 lo desactiva) que se congela en cada solicitud como `due_at`; al vencer, la solicitud sigue pendiente pero la dirección recibe un aviso de vencimiento y el panel la marca como «Vencida» (ADR-045).
- 2026-10-30: el evento de la bitácora guarda la **solicitud que lo originó** (`attendance_request_id`) cuando el cambio se aprobó, el reporte de anulaciones muestra su **origen** y la tarjeta «Anulaciones» descarga el periodo en **CSV** (ADR-046).
- 2026-10-30: las aprobaciones anteriores a la columna se **enlazan con su evento** por su propio motivo —misma asistencia, mismo actor, tipo de evento y texto exacto, solo en pares uno a uno—, sin cruzar instantes ni reescribir lo ya enlazado (ADR-047).

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
- La pestaña «Equipo y turnos» consulta los turnos del personal (`GET /admin/staff/shifts`), muestra cuántos están programados y cuántas asistencias hay registradas, la siguiente jornada de cada colaborador en la columna «Horario» y una tabla de turnos con su estado y marcaje de entrada/salida. El botón «Programar turno» (permiso `attendance.manage`) agenda un turno (`POST /admin/staff/{employee_id}/shifts`); el backend rechaza traslapes (`409`) y horarios inválidos o sin zona horaria (`422`). La columna «Asistencia» etiqueta las marcas registradas por un operador con «(manual)» y las corregidas con «(corregido)». «Registrar entrada/salida» solo aparece cuando falta esa marca: `POST /admin/staff/attendance` registra la marca ausente con motivo obligatorio y `source = "manual"` y nunca reescribe una existente (`409`). «Corregir» aparece cuando el turno está programado y tiene asistencia: el modal «Corregir marcas» prellena entrada y salida, exige un motivo de 3 a 500 caracteres y envía una petición por marca a `POST /admin/staff/attendance/{attendance_id}/corrections`; la asistencia queda con `check_in_source`/`check_out_source = "correction"` y la bitácora suma el evento `check_in_correction`/`check_out_correction` con el motivo y el actor sin borrar el original. El orden se valida en el servicio (la salida no precede a la entrada y la entrada no sigue a la salida) y el estado se recalcula contra `starts_at` (ADR-042). «Bitácora» abre el modal «Bitácora del turno», que lee `GET /admin/staff/attendance/{attendance_id}/events` (`attendance.read`) y lista del más viejo al más nuevo cada evento con su etiqueta legible, hora, correo y nombre de quien actuó, origen y motivo; cuando el cambio nació de una solicitud aprobada, el evento añade «Aplicado al aprobar la solicitud del colaborador · {id corto}» (ADR-046). «Anular» abre «Anular una marca»: deja elegir la entrada o la salida —la salida viene preseleccionada si existe— y envía `POST /admin/staff/attendance/{attendance_id}/voids` con el motivo; anular la salida la limpia y conserva la entrada, anular la entrada marca la asistencia completa como anulada y el turno vuelve a quedar libre para marcarse de nuevo (ADR-043).
- La tarjeta «Tolerancias del club» (solo con `attendance.manage`) edita la política de asistencia con dos campos de 0 a 240 minutos: la **apertura anticipada** (cuánto antes del inicio se habilita la entrada) y la **tolerancia de retardo** (cuántos minutos después del inicio siguen contando como presente). Lee `GET /admin/staff/settings`, guarda con `PATCH /admin/staff/settings` y avisa «Política de asistencia guardada.»; el botón queda deshabilitado mientras los valores coincidan con los guardados.
- La pestaña «Mi jornada» (permiso `attendance.self`) es el auto-marcaje del colaborador: reloj, turno vigente con su botón de entrada o salida y los turnos de los últimos y próximos 14 días con estado (`Programado`, `Presente`, `Tarde`, `Cancelado`) y marca. El panel llama a `GET /staff/attendance` y a `POST /staff/attendance/clock-in|clock-out`; la cuenta debe estar enlazada a un expediente y, si no lo está, la pestaña explica el `409`. La entrada abre los minutos configurados antes del inicio —15 por defecto— y cierra al terminar el turno; el tablero devuelve `settings` para que el pie anuncie «Puedes marcar desde 15 minutos antes del inicio» y la tolerancia vigente. La página Personal abre con `staff.read` **o** `attendance.self`, así que entrenadores, mantenimiento y contadores marcan sin ver el directorio (ADR-041).
- Las solicitudes de cambio (ADR-044) viven en `staff_attendance_requests`: el colaborador las crea con `POST /staff/attendance/{attendance_id}/requests` (`attendance.self`) —marca, `correct` con hora propuesta u `void` sin ella, y justificación de 3 a 500 caracteres— y las consulta con `GET /staff/attendance/requests`; el índice único parcial `uq_staff_attendance_requests_pending` impide dos abiertas para la misma marca y acción. La cola del supervisor es `GET /admin/staff/attendance/requests?status=` (`attendance.read`) y la decisión `POST /admin/staff/attendance/requests/{request_id}/decision` (`attendance.manage`): aprobar aplica la corrección o anulación por el camino normal con `commit=False`, así la bitácora del turno no distingue el origen, y rechazar exige nota; decidir la solicitud propia responde `403`. El ciclo escribe los cinco avisos nuevos en `staff_notifications`. La política deja rastro en `staffing_settings_events` —actor, valores anteriores y nuevos— que lee `GET /admin/staff/settings/events`, y `GET /admin/staff/attendance/annulments?days=&employee_id=&actor_id=` (`attendance.read`) reporta las anulaciones del periodo con desglose por operador. El panel suma «Solicitar cambio» y «Mis solicitudes» en «Mi jornada», «Solicitudes del equipo» con su modal de revisión, «Historial de cambios» en la tarjeta de política y «Anulaciones», que añade la columna «Origen» («Solicitud» o «Panel»), conserva el selector de 7/30/90 días y suma «Exportar CSV» para descargar el periodo elegido con las mismas filas del reporte (ADR-046). Las horas de la solicitud se entregan en UTC con zona explícita para que el panel las pinte en la zona del club. El **plazo** (ADR-045) se configura en la misma tarjeta (`attendance_request_sla_hours`, 24 por defecto, 0 sin plazo, máximo 720) y se congela al crear la solicitud como `due_at`; `attendance_request_is_overdue` decide con la hora del servidor y el payload expone `overdue`, que pinta el chip «Vencida · avisada la dirección» y el aviso `attendance_request_overdue` a los dueños. El escalado no tiene planificador: `escalate_overdue_attendance_requests` se dispara al leer la cola, la bandeja o el contador de no leídos y deduplica por solicitud y dueño. Cada evento de la bitácora guarda `attendance_request_id` cuando el cambio se aprobó, y `GET /admin/staff/attendance/annulments.csv` exporta el mismo reporte con su origen (ADR-046). Las aprobaciones hechas entre ADR-044 y ADR-046, que quedaron sin enlace, se recuperan con un relleno idempotente que no cruza instantes: mismo turno, mismo actor, el tipo de evento que produce la solicitud y el motivo exacto `Solicitud del colaborador: {justificación}` (con o sin la nota del supervisor), solo cuando el par es único en ambos lados; lo ejecuta `20261031_0064` en PostgreSQL y `preview_patch.py` en la vista previa (ADR-047).
- Las tres tablas del turno y del marcaje (`staff_shifts`, `staff_attendance`, `staff_attendance_events`) **existieron solo en los modelos hasta el 2026-10-27**: la vista previa las creaba `create_all`, por eso el panel funcionaba, pero ninguna migración las definía y una base PostgreSQL con `alembic upgrade head` no las tenía. La migración `20261027_0038_staffing_shifts_and_attendance.py` las agrega con la forma que los modelos publican; la detectó `alembic check`, que desde ese día corre en CI. Reglas que quedan en la base: un turno no puede terminar antes de empezar, un turno admite **un solo** marcaje vivo —índice único parcial `uq_staff_attendance_shift WHERE voided_at IS NULL` desde `20261030_0060`—, la salida no puede ser anterior a la entrada y la bitácora de marcajes es append-only idempotente por `request_id` (`uq_staff_attendance_events_request` + `request_sha256`). Se escriben `source = "staff_app"` desde «Mi jornada», `source = "manual"` desde el registro de una marca faltante, la corrección de una existente y la anulación con `attendance.manage` (con `event_type` `check_in_correction`/`check_out_correction` desde `20261030_0059` y `check_out_voided`/`attendance_voided` desde `20261030_0060`); `access_reader` sigue declarado en el `CHECK` sin llamador. La política —gracia de entrada, tolerancia de retardo y plazo para decidir solicitudes— vive en `staffing_settings`, una fila que la primera lectura del panel crea con 15 y 0 minutos y 24 horas y que `read_attendance_policy`/`read_attendance_request_sla_hours` leen sin escribir (ADR-043, ADR-045).
- MFA, limitación de intentos, recuperación de contraseña, el marcaje por lector físico o QR, el aviso por correo o push del ciclo de asistencia y el cierre de nómina siguen pendientes; este corte no sustituye revisión de seguridad profesional.
