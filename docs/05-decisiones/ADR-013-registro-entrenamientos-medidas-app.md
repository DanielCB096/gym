# ADR-013: Registro de entrenamientos y medidas desde la app del socio, con revisión del entrenador

- Fecha: 2026-10-27
- Estado: propuesta inicial

## Contexto

El módulo de rutinas ya permitía al personal registrar entrenamientos, medidas, metas y fotos, y el detalle de seguimiento del panel ya distinguía entrenamientos `logged` (por revisar) de `reviewed`. La app del socio, en cambio, nació **de solo lectura** (ADR-011): el socio podía ver su rutina, su plan y su historial, pero dependía de recepción o del entrenador para anotar cada sesión y cada medición.

Esa dependencia hace que el progreso real se pierda: el socio entrena fuera del horario del entrenador y las medidas caseras no se registran hasta la siguiente visita. Al mismo tiempo, el módulo no tenía forma de distinguir qué había capturado el personal y qué el socio, ni de que el entrenador validara lo que llega desde la app.

## Decisión

- Se agrega la columna **`origin`** (`'staff'` | `'app'`, CHECK) a `workout_logs` y `body_measurements` con la migración `20261027_0032_member_activity_origin.py`. Las filas existentes quedan como `staff` mediante `server_default`, así que la migración no reescribe historia.
- El portal gana **dos rutas de escritura**, siempre acotadas a la sesión del socio:
  - `POST /member/routines/{assignment_id}/workouts` (`201`): registra un entrenamiento propio con `origin = "app"` y estado inicial `logged`. Solo acepta una asignación **propia y activa**; una asignación ajena, inexistente o de otro socio responde `404`, una cerrada `409` y una fecha futura o anterior al inicio del plan `422`. Reutiliza `log_workout` del módulo de rutinas, que fija la `routine_version` de la asignación.
  - `POST /member/progress/measurements` (`201`): registra una medición propia con `origin = "app"`, **append-only** y con al menos una medida. Reutiliza `record_measurement`, de modo que las metas se actualizan en la misma transacción, igual que cuando mide el entrenador.
- **Los entrenamientos quedan pendientes de revisión**: el socio los crea como `logged` y el entrenador los valida con `POST /admin/routines/workouts/{id}/review` (`routines.manage`), que los pasa a `reviewed`. La app no puede revisar ni editar después del alta.
- **Las medidas se aceptan directamente**, sin estado de revisión: son un dato del socio sobre su propio cuerpo y el módulo ya las trata como histórico inmutable. Se descarta pasarlas por revisión para no retrasar el avance de las metas.
- El **panel** muestra el origen con las etiquetas «Personal» / «App» en la tabla de medidas y junto a cada entrenamiento, así que el entrenador identifica de inmediato lo que llega de la app. El **detalle de la app** muestra «Desde tu app» / «Desde recepción» y «Por revisar» / «Revisado».
- **`logged_by` / `measured_by` siguen vacíos** en las filas de origen `app`: ambas columnas son FK a `app_users` y el socio no es un usuario del personal. `origin` distingue el canal, no al actor; el vínculo con el socio ya existe por `member_id`. Antes de producción habrá que decidir si se añade una traza explícita del socio que capturó (como se hizo con las reservas en ADR-010).
- **Permisos**: el socio no usa la matriz RBAC. `get_current_member` autentica las rutas `/member/*`; el personal sigue necesitando `routines.manage` para registrar o revisar, y un token de personal recibe `401` en las rutas nuevas. La app no expone metas, fotos, cierre de asignaciones ni revisión.

## Consecuencias y límites

- El socio ya puede mantener su historial al día sin pasar por recepción, y el entrenador conserva la última palabra sobre los entrenamientos que revisa.
- **No hay edición ni borrado** desde la app: una captura equivocada se corrige en recepción o con una captura nueva (las medidas son append-only). El entrenador puede revisar un entrenamiento pero no corregir sus datos desde la app.
- Sigue sin existir **detalle por serie** (peso y repeticiones por ejercicio); el entrenamiento es un resumen de fecha, duración, esfuerzo y notas.
- No hay **notificación** al entrenador de un nuevo entrenamiento pendiente ni al socio cuando se revisa; el aviso es visual al abrir el detalle.
- El socio puede registrar un entrenamiento en una asignación activa aunque su membresía esté vencida (la regla actual del módulo no lo exige). Si el negocio quiere condicionarlo a la vigencia, se agrega en el servicio y se documenta.
- Las medidas capturadas desde la app **actualizan las metas al instante**, sin revisión; si el socio se equivoca, la meta puede cerrarse con un dato erróneo. La medición no se puede borrar, así que la corrección exige una nueva meta.
- No se suben fotos de progreso ni se editan metas desde la app; eso sigue en el panel.
- Antes de producción: definir notificaciones, traza del actor socio en los registros de origen `app`, validación de vigencia de membresía si aplica y política de retención/consentimiento para medidas capturadas por el socio.

## Referencias

- `backend/src/app/modules/portal/routines.py`
- `backend/src/app/modules/routines/service.py` (`log_workout`, `record_measurement`)
- `backend/src/app/modules/routines/models.py` (`WorkoutLog.origin`, `BodyMeasurement.origin`)
- `backend/alembic/versions/20261027_0032_member_activity_origin.py`
- `backend/src/app/main.py` (`POST /member/routines/{assignment_id}/workouts`, `POST /member/progress/measurements`)
- `backend/tests/test_member_activity_api.py`
- `mobile/src/screens/RoutineDetailScreen.tsx`, `mobile/src/screens/RoutinesScreen.tsx`
- `web/src/app/page.tsx` (origen «Personal»/«App» y revisión)
- ADR-009 (autenticación del socio)
- ADR-011 (rutinas y progreso de solo lectura)
