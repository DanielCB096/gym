# ADR-041: Auto-marcaje del personal y corrección de marcas faltantes

- Fecha: 2026-10-30
- Estado: propuesta inicial

## Contexto

El módulo de turnos nació con la API de auto-servicio ya escrita —`GET /staff/attendance`, `POST /staff/attendance/clock-in` y `clock-out` con el permiso `attendance.self`— y sus pruebas, pero **ninguna interfaz la llamaba**: el panel decía que la asistencia se marcaba «desde la app del colaborador», que no existe (la app Expo es solo del socio). En la práctica, un colaborador no tenía forma de marcar su entrada y recepción no tenía forma de registrar una marca que se hubiera olvidado.

Al abrir el marcaje aparecieron tres decisiones que la API no resolvía sola:

1. **Dónde se marca.** Crear una app de personal es un incremento entero por sí mismo. El club ya entrega cuentas del panel a todo el equipo —los seis roles base traen `attendance.self`—, así que el panel es el lugar natural.
2. **Cuándo se puede marcar.** El servicio exigía `starts_at <= ahora <= ends_at`. Llegar diez minutos antes es lo normal, no un error, y el sistema lo rechazaba; a la vez, quien recordaba su entrada al terminar el turno tampoco tenía salida.
3. **Qué pasa con una marca olvidada.** El modelo guarda un solo marcaje por turno (`uq_staff_attendance_shift`) y el servicio ya rechazaba un segundo check-in (`AttendanceAlreadyRecorded`). No existía, en cambio, un permiso ni una ruta para que recepción llenara el hueco.

## Decisión

- **El auto-marcaje vive en el panel, en la pestaña «Mi jornada».** La cuenta del colaborador —enlazada a su expediente por `app_users.employee_id`— ve su reloj, su turno vigente con el botón de entrada o salida y sus turnos de los últimos y próximos 14 días con estado (`Programado`, `Presente`, `Tarde`, `Cancelado`) y marca. La pestaña aparece con `attendance.self`; quien no tiene expediente enlazado recibe el `409` del backend convertido en un aviso claro, no en un error.
- **La pestaña Personal no exige `staff.read`.** Antes el ítem de navegación se filtraba solo por `staff.read`, así que entrenadores, mantenimiento y contadores —que tienen `attendance.self` pero no acceso al directorio— no podían llegar al marcaje. Ahora la página abre si la cuenta tiene `staff.read` **o** `attendance.self`, y la pestaña «Equipo» —directorio y turnos del club— sigue exigiendo `staff.read`. Sin ese permiso el panel no llama a `/admin/staff` y arranca directamente en «Mi jornada».
- **La ventana de entrada abre 15 minutos antes del inicio.** `CHECK_IN_EARLY_GRACE = 15 min`: marcar dentro de esa franja se acepta y conserva la regla de retardo (entrada después de `starts_at` queda `late`). Quince minutos antes es un margen fijo, no configurable, porque todavía no hay política de tolerancia acordada con el club y un número en la base sin respaldo operativo solo agrega superficie. La salida no tiene gracia: puede marcarse en cualquier momento después de la entrada.
- **La corrección solo llena marcas faltantes.** `POST /admin/staff/attendance` con `attendance.manage` registra una entrada o una salida **ausente**. Si el turno ya tiene esa marca, el servicio compartido lanza `AttendanceAlreadyRecorded` y la API responde `409`: nunca se reescribe un marcaje existente, ni siquiera con el permiso de administración. Corregir una marca equivocada —que hoy no tiene camino— queda explícitamente fuera de este incremento.
- **El operador puede registrar fuera de la ventana y debe justificar.** Quien olvidó la entrada la registra después de que el turno terminó, así que la ruta manual no aplica la ventana (`enforce_window=False`); lo que sí exige es un **motivo de 3 a 500 caracteres**, guardado en `staff_attendance_events.reason` junto con `source = "manual"` y el actor responsable. La UI muestra `(manual)` en la marca y el motivo queda en la bitácora del turno; sin motivo la ruta responde `422` (`ManualAttendanceReasonRequired`).
- **El marcaje sigue siendo idempotente.** La app envía `request_id` (UUID generado en el cliente y recordado por turno y tipo de marca mientras la petición viaja), la bitácora conserva `request_sha256` y un reintento devuelve la misma asistencia. El registro manual genera un `request_id` nuevo por envío, porque cada corrección es un hecho distinto y el `409` por marca ya existente cubre el doble clic.

## Consecuencias y límites

- **Sigue sin lector físico ni app de personal.** `access_reader` continúa en el `CHECK` sin llamador y la asistencia se marca a mano, desde el panel, en un navegador. No hay QR, RFID, geolocalización ni selfie: el registro dice *quién marcó con qué cuenta*, no *quién estaba físicamente en el club*.
- **No hay tolerancia configurable ni justificación del empleado.** El retardo se calcula contra `starts_at` con los 15 minutos de gracia fijos. Un colaborador no puede justificar su propia llegada tarde, y recepción tampoco puede marcar un retardo como justificado: la clasificación es binaria.
- **La corrección no modifica lo marcado.** Si alguien marcó la entrada a la hora equivocada, la única salida sigue siendo la base de datos; el incremento deliberadamente no expone una edición. Una marca manual después de una automática también se rechaza, aunque la automática sea errónea.
- **Las marcas manuales se ven igual en los reportes de asistencia.** `check_in_source`/`check_out_source` distinguen `staff_app` de `manual`, pero el estado del turno (`present`/`late`) no cambia y la tabla de turnos solo añade el sufijo «(manual)». No hay reporte propio de correcciones ni conteo por operador más allá de la bitácora.
- **La ventana de consulta es de 14 días en la app y 21 en el panel.** Un turno fuera de esa franja no aparece en «Mi jornada» aunque siga en el backend; el turno vigente se elige entre los que tienen una acción posible, así que un turno futuro muestra «Abre 15 min antes» sin botón.
- **El registro manual no valida contra el turno del empleado.** La ruta recibe `shift_id` y usa el empleado del turno; no verifica que quien registra sea su supervisor ni que la hora caiga en la jornada. La ventana y la razón quedan documentadas en la bitácora, no impuestas contra el calendario del club.

## Referencias

- `backend/src/app/modules/staffing/service.py` (`CHECK_IN_EARLY_GRACE`, `clock_in`, `clock_out`, `record_manual_attendance`, `ManualAttendanceReasonRequired`, `_record_attendance_event`)
- `backend/src/app/main.py` (`POST /admin/staff/attendance`, `ManualAttendanceRequest`, `GET /staff/attendance`, `POST /staff/attendance/clock-in|clock-out`)
- `backend/tests/test_staffing_shifts.py` (ventana de 15 minutos, registro manual que solo llena huecos), `backend/tests/test_attendance_api.py` (403 del rol Entrenador, `409` duplicado, `422` sin zona horaria)
- `web/src/app/page.tsx` (`StaffView`, «Mi jornada», `selfMarkFor`, `attendanceLabel`, `ManualAttendanceModal`), `web/src/app/api/admin/staff/attendance/route.ts`
- `docs/02-modulos/personal-y-roles.md` (estado e historial), `docs/deuda-tecnica.md`, `docs/07-pruebas/plan-de-pruebas.md`
