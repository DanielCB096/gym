# ADR-042: Corrección de una marca ya registrada

- Fecha: 2026-10-30
- Estado: propuesta inicial

## Contexto

ADR-041 dejó el auto-marcaje en la pestaña «Mi jornada» y reservó la ruta manual (`POST /admin/staff/attendance`) para **llenar marcas faltantes**. Una marca ya existente, aunque estuviera mal, no tenía camino: el servicio compartido rechazaba un segundo check-in y la documentación lo declaraba fuera de alcance. En la operación real eso deja a recepción frente a una entrada marcada a las 11:10 cuando la persona llegó a las 11:00, o una salida sin cerrar hasta el día siguiente, sin más salida que la base de datos.

Corregir una marca no es lo mismo que llenar un hueco: hay que decidir **quién puede reescribir**, **qué se conserva de la marca anterior** y **cómo se evita que una edición silencie la historia**.

## Decisión

- **Solo `attendance.manage` corrige.** El auto-servicio (`attendance.self`) no expone edición: el colaborador sigue marcando su entrada y salida, pero no puede reescribir una marca. La corrección vive en la tabla «Turnos programados» con un botón «Corregir» sobre los turnos que ya tienen asistencia.
- **La corrección reescribe la marca y conserva el original.** `POST /admin/staff/attendance/{attendance_id}/corrections` acepta `event_type` (`check_in`/`check_out`), `occurred_at`, `reason` y `request_id`. El registro de asistencia toma el valor nuevo (`check_in_at`/`check_out_at`, actor y `source = "correction"`) y la bitácora **no se sobrescribe**: el evento original sigue ahí y se añade un evento `check_in_correction` o `check_out_correction` con `source = "manual"`, el motivo y el operador. La tabla muestra «(corregido)» en la marca.
- **Solo se corrige una marca que existe.** Si falta la salida, la ruta responde `409` (`AttendanceMarkMissing`) y el operador usa el registro manual de ADR-041. Así cada camino conserva su significado: el manual crea, la corrección reescribe.
- **El estado del turno se recalcula al corregir la entrada.** Igual que en el marcaje original, `check_in_at > starts_at` deja el turno en `late`; corregirlo a una hora anterior al inicio lo devuelve a `present`. Corregir la salida no cambia el estado.
- **El orden de las marcas se mantiene.** Una entrada posterior a la salida existente y una salida anterior a la entrada responden `422` (`InvalidAttendanceTime`). La ventana del turno **no** se vuelve a aplicar: igual que el registro manual, una corrección suele ocurrir cuando el turno ya terminó.
- **Cada corrección exige motivo y es idempotente.** El motivo va de 3 a 500 caracteres y queda en la bitácora; sin él la ruta responde `422`. El `request_id` es único: un reintento con los mismos valores devuelve la asistencia ya corregida y reutilizarlo con otros valores responde `409`. La huella (`request_sha256`) incluye esta vez el instante corregido además de la asistencia, el actor y el tipo, para que un mismo `request_id` no pueda representar dos correcciones distintas.
- **El panel manda una corrección por marca.** Si el operador cambia entrada y salida en el mismo formulario, el panel envía dos peticiones, ordenadas por la que todavía encaja con el valor almacenado para que el backend nunca reciba una combinación intermedia inválida; si la segunda falla, avisa que una marca sí quedó corregida y refresca la tabla. El formulario valida antes el orden y exige el motivo.

## Consecuencias y límites

- **No se borra ni se vacía una marca.** La corrección cambia el instante; no existe «deshacer» ni dejar el turno sin asistencia. Una marca cargada por error se corrige a otro valor, no se elimina.
- **La bitácora no tiene visor en el panel.** El historial completo (marca original, corrección, motivo y actor) se guarda en `staff_attendance_events`, pero la interfaz solo muestra «(corregido)»; no hay una pantalla de bitácora del turno ni un reporte de correcciones por operador.
- **No hay justificación del empleado ni validación de supervisor.** La corrección la hace quien tiene `attendance.manage`; el colaborador no puede pedirla ni aprobarla desde el panel, y el sistema no exige un segundo visto bueno.
- **Los turnos cancelados no se corrigen.** La ruta exige que el turno siga `scheduled`, igual que el registro manual; hoy no existe una ruta para cancelar un turno, así que el límite solo importa si aparece más adelante.
- **El «(corregido)» reemplaza al «(manual)».** Una marca registrada por un operador y corregida después se muestra como «(corregido)»; el evento original conserva que fue manual. La etiqueta de la tabla no distingue ambos matices.
- **La migración ensancha `event_type`.** `20261030_0059_attendance_corrections.py` amplía la columna a `VARCHAR(32)` —los tipos nuevos miden 19 y 20 caracteres— y reemplaza `ck_staff_attendance_events_type`; el revertido se niega a ejecutarse si existen correcciones. En la vista previa, `preview_patch.CHECK_UPGRADES["staff_attendance_events"]` reconstruye la tabla con el `CHECK` nuevo.

## Referencias

- `backend/src/app/modules/staffing/models.py` (`AttendanceEvent.event_type`, `ck_staff_attendance_events_type`)
- `backend/src/app/modules/staffing/service.py` (`correct_attendance`, `AttendanceNotFound`, `AttendanceMarkMissing`, `_fingerprint`)
- `backend/src/app/main.py` (`POST /admin/staff/attendance/{attendance_id}/corrections`, `AttendanceCorrectionRequest`)
- `backend/alembic/versions/20261030_0059_attendance_corrections.py`, `backend/preview_patch.py`
- `backend/tests/test_staffing_shifts.py` (recalculo de estado, orden, marca faltante, replay y conflicto), `backend/tests/test_attendance_api.py` (403 del rol Entrenador, `404`, `409` y `422`), `backend/tests/test_preview_patch.py` (el `CHECK` de vista previa acepta correcciones)
- `web/src/app/page.tsx` (`attendanceLabel`, `AttendanceCorrectionModal`, botón «Corregir»), `web/src/app/api/admin/staff/attendance/[attendanceId]/corrections/route.ts`
- `docs/02-modulos/personal-y-roles.md`, `docs/01-arquitectura/modelo-de-datos.md`, `docs/deuda-tecnica.md`, `docs/07-pruebas/plan-de-pruebas.md`
