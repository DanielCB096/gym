# ADR-014: Detalle por serie en los entrenamientos del socio

- Fecha: 2026-10-27
- Estado: propuesta inicial

## Contexto

Hasta este incremento, un entrenamiento era un **resumen**: fecha, duración, esfuerzo percibido y notas (ADR-013). El plan de la rutina sí define series y repeticiones por ejercicio, pero el registro no guardaba qué se hizo realmente en cada serie, así que el entrenador no podía comparar lo planificado con lo ejecutado ni ver la progresión de carga de un ejercicio concreto.

La app del socio ya escribía entrenamientos (`POST /member/routines/{assignment_id}/workouts`, `origin="app"`) y el panel los registraba con `routines.manage`. Faltaba un modelo de datos que guardara las series y que validara que cada ejercicio pertenece a la **versión congelada** de la rutina asignada.

## Decisión

- Se agrega la tabla **`workout_sets`** con la migración `20261027_0033_workout_sets.py`: una fila por serie ejecutada, con `workout_id`, `exercise_id`, `set_number`, `reps`, `weight_kg` opcional y `created_at`.
- **Integridad**: `workout_id` referencia a `workout_logs` con `ON DELETE CASCADE` y `exercise_id` a `exercises` con `ON DELETE RESTRICT` (los entrenamientos nunca se borran; los ejercicios se desactivan). Un índice único `uq_workout_sets_line` sobre `(workout_id, exercise_id, set_number)` impide dos veces la misma serie, y `ix_workout_sets_workout` acelera la lectura del historial.
- **Rangos**: `set_number` 1–20, `reps` 1–100 y `weight_kg` entre 0 y 1000 (o `NULL` para peso corporal); un entrenamiento admite como máximo **60 series**. Los CHECK de base de datos replican los límites del servicio.
- **El ejercicio debe pertenecer al plan de la versión asignada**: la validación compara cada `exercise_id` con las líneas de `routine_items` de la `routine_version` que fijó la asignación. Un ejercicio de otra rutina o de otra versión responde `422`, igual que un número de serie repetido, un rango inválido o más de 60 series.
- **Las series son opcionales**: `sets` llega como lista vacía por defecto, así que un entrenamiento sin detalle sigue siendo válido y los registros anteriores no cambian. La respuesta de `WorkoutResponse` siempre incluye `sets` (vacía si no hay detalle).
- **El orden de lectura lo pone el plan**: las series se devuelven por `RoutineItem.position` y luego por `set_number`, no por el orden de inserción, para que el panel y la app muestren el mismo orden que la rutina.
- **Una sola escritura**: las series se guardan en la misma transacción que el entrenamiento, con `created_at` igual al `performed_at` del entrenamiento. No hay rutas propias para series: se envían dentro del alta del entrenamiento (`POST /admin/routines/assignments/{id}/workouts` y `POST /member/routines/{assignment_id}/workouts`) y viajan con él en las respuestas.
- **La revisión no altera las series**: `POST /admin/routines/workouts/{id}/review` solo cambia el estado del entrenamiento; las series quedan como se capturaron. Tampoco hay edición ni borrado de series desde la app: una corrección se hace en recepción, igual que el resto del entrenamiento.
- **Permisos**: no se agregan permisos nuevos. Escribir series exige `routines.manage` en el panel y una sesión de socio en `/member/*`; leerlas usa las mismas rutas y permisos que el entrenamiento.

## Consecuencias y límites

- El entrenador ya ve qué series y con qué carga se ejecutaron, y el socio conserva ese detalle en su historial.
- El detalle por serie **no sustituye** la revisión: el entrenador sigue siendo quien valida el entrenamiento completo.
- No hay **plantilla de series objetivo** por sesión: el plan sigue expresando series y repeticiones, y la comparación planificado/ejecutado es visual, no una regla que bloquee el registro.
- Una serie con peso corporal se guarda con `weight_kg = NULL`; no se distingue de una serie sin peso registrado.
- No hay **series por tiempo** (planchas, cardio) ni unidades distintas de kg y repeticiones; el campo `reps` es siempre un entero.
- No se pueden **editar ni borrar** series después del alta, ni desde el panel ni desde la app. Corregir exige registrar un entrenamiento nuevo.
- El historial de entrenamientos sigue sin paginación (máximo 10 en la app) y el panel carga hasta 50 por asignación.
- Antes de producción: decidir si se agregan series objetivo por sesión, series por tiempo/distancia, edición con auditoría y métricas de volumen y carga acumulada por ejercicio.

## Referencias

- `backend/src/app/modules/routines/models.py` (`WorkoutSet`, `MAX_WORKOUT_SETS`)
- `backend/src/app/modules/routines/service.py` (`WorkoutSetInput`, `_validate_workout_sets`, `log_workout`)
- `backend/alembic/versions/20261027_0033_workout_sets.py`
- `backend/src/app/main.py` (`WorkoutSetRequest`, `WorkoutSetResponse`, `LogWorkoutRequest.sets`)
- `backend/tests/test_workout_sets_api.py`
- `mobile/src/screens/RoutineDetailScreen.tsx` (editor de series e historial)
- `web/src/app/page.tsx` (editor de series y resumen en el historial)
- ADR-013 (registro de entrenamientos y medidas desde la app)
