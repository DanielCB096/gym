# ADR-015: Metas creadas y canceladas por el socio desde la app

- Fecha: 2026-10-27
- Estado: propuesta inicial

## Contexto

Las metas del socio existían desde el segundo incremento del módulo (`20261025_0029_member_goals.py`, ADR de rutinas): una medida, una dirección, un objetivo, línea base congelada, avance y cierre automático. Pero **solo el personal podía escribirlas**, y la app del socio las mostraba con el aviso «Tu entrenador puede crearlas en recepción».

El roadmap pedía ampliar la app del socio (pago en línea, facturas, **metas** y notificaciones). A partir del sexto y séptimo incremento el socio ya registraba entrenamientos con sus series y medidas con `origin = "app"` (ADR-013 y ADR-014), así que tenía contexto suficiente para fijarse él mismo un objetivo sin pasar por recepción.

La restricción del modelo era que no había forma de saber **quién** había creado una meta: `created_by` es una FK a `app_users` del personal y queda vacía cuando escribe el socio, igual que `logged_by`/`measured_by` en los entrenamientos y medidas. Sin esa información no se podía permitir cancelar sin abrir un agujero (el socio cancelaría metas del entrenador) ni informar al panel de qué venía de la app.

## Decisión

- Se agrega la columna **`origin`** a `member_goals` con la migración `20261027_0034_member_goal_origin.py`: `'staff'` | `'app'`, `nullable=False`, `server_default='staff'` y CHECK `ck_member_goals_origin`. Es el mismo patrón que `workout_logs.origin` y `body_measurements.origin` (ADR-013): **el origen distingue el canal, no al actor**; las metas del socio siguen con `created_by = NULL`.
- **El socio crea metas con `POST /member/progress/goals`** (`201`) y las cancela con `POST /member/progress/goals/{goal_id}/cancel` (`200`). Ambas viven en `app.modules.portal.routines` como `create_member_goal_from_app` y `cancel_member_goal_from_app`, que **delegan en el servicio existente** (`create_member_goal`, `cancel_member_goal`) y solo añaden el alcance de sesión: ninguna ruta acepta un `member_id`.
- **Una sola regla de negocio**: la app no duplica validaciones. `create_member_goal` recibe el parámetro `origin` (`"staff"` por defecto) y conserva todas las reglas del panel — medida y dirección válidas, objetivo > 0, grasa ≤ 100, objetivo ≤ 1000, nota de hasta 300 caracteres, fecha objetivo no anterior a hoy, socio activo, **una sola meta activa por medida** (`409`) y rechazo del objetivo ya cumplido por la última medición (`422`). La línea base se congela igual que antes con la última medición disponible.
- **La cancelación es la única operación con restricción de propiedad**: `cancel_member_goal_from_app` comprueba `goal.member_id == member_id` (una meta ajena o inexistente responde `404`, sin revelar si existe) y `goal.origin == "app"` (una meta del personal responde `409` con «La meta la creó el personal; cancélala en recepción»). No hay edición de metas desde la app: mover un objetivo o su fecha sigue siendo `PATCH /admin/routines/goals/{id}` con `routines.manage`.
- **El panel distingue el origen**: `MemberGoalResponse` expone `origin` y el detalle de seguimiento lo muestra como «· Personal» / «· App» en cada meta, junto al estado. El personal puede cancelar y editar las metas del socio sin cambio de permisos: no se agrega ningún permiso nuevo, la escritura del socio sigue apoyada en la sesión de la app.
- **La app reemplaza el aviso** «Tu entrenador puede crearlas en recepción» por un formulario de alta (medida y dirección como chips, objetivo, fecha objetivo opcional y nota) y una cancelación **en dos pasos** («Cancelar meta» → «Sí, cancelar meta» / «Conservar meta») que solo aparece en las metas activas creadas desde la app. Cada meta rota su autoría («Creada desde tu app» / «Creada por el personal»).

## Consecuencias y límites

- El socio fija sus propios objetivos y el entrenador ve de dónde salió cada meta sin abrir el historial de auditoría.
- La app **no** avisa si la medida ya tiene una meta activa antes de enviar: el `409` llega del backend y se muestra en español («Ya hay una meta activa de cintura»). La validación local solo cubre formato, rango y fecha.
- Las metas del socio se aceptan **sin revisión** del entrenador, igual que las medidas: ninguna persona valida que el objetivo sea razonable. El entrenador puede corregirlo después cancelando o editando la meta desde el panel.
- Crear una meta **no exige membresía vigente**: sigue la regla del servicio (solo rechaza al socio `inactive`), igual que el registro de entrenamientos y medidas.
- `origin` no reemplaza la **traza del actor**: si el negocio necesita saber qué socio creó una meta en un momento dado, falta una columna de autoría del socio o una bitácora; hoy solo se sabe el canal.
- Una meta `achieved` o `cancelled` no se reabre ni se cancela de nuevo (`409`), y no bloquea crear otra de la misma medida, que toma como línea base la última medición.
- Antes de producción: decidir si el entrenador debe **aprobar** las metas del socio (estado `pending`), notificar al socio cuando el personal cancela o edita una meta suya, y definir la retención de metas y notas como dato personal.

## Referencias

- `backend/src/app/modules/routines/models.py` (`MemberGoal.origin`, `ck_member_goals_origin`)
- `backend/src/app/modules/routines/service.py` (`create_member_goal(..., origin=...)`, `cancel_member_goal`, `_validate_goal_target`)
- `backend/src/app/modules/portal/routines.py` (`create_member_goal_from_app`, `cancel_member_goal_from_app`)
- `backend/src/app/main.py` (`CreateMemberGoalRequest`, `MemberGoalResponse.origin`, `member_create_goal`, `member_cancel_goal`)
- `backend/alembic/versions/20261027_0034_member_goal_origin.py`
- `backend/tests/test_member_goals_api.py`
- `mobile/src/screens/RoutinesScreen.tsx` (formulario de alta y cancelación en dos pasos)
- `mobile/src/api.ts` (`createMemberGoal`, `cancelMemberGoal`), `mobile/src/format.ts` (`goalDirectionLabel`, `goalMetricUnit`)
- `web/src/app/page.tsx` (`BackendGoal.origin` y la etiqueta de origen en el detalle)
- ADR-013 (registro de entrenamientos y medidas desde la app) y ADR-014 (detalle por serie)
