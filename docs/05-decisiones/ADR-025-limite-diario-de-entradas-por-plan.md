# ADR-025: Límite diario de entradas por plan

- Fecha: 2026-10-28
- Estado: propuesta inicial

## Contexto

El motor de acceso ya sabía negar por límite diario: `AccessSnapshot.daily_entry_limit` y `entries_today` existen desde el primer incremento, `evaluate_access` responde `daily_limit` y el mensaje del kiosco («Ya usaste tus entradas de hoy.») ya estaba redactado. Lo que faltaba era la política: el plan no tenía dónde guardar el límite, el kiosco lo enviaba siempre como `None` con `entries_today = 0`, y no había forma de configurarlo desde el panel. La lista de pendientes de acceso lo arrastraba junto con el antipassback.

El club necesita que un plan de una entrada al día no pueda usarse para entrar varias veces, y que la regla se pueda cambiar sin tocar código. El kiosco es el único canal con una decisión automática en producción; el acceso manual de recepción es una excepción deliberada.

## Decisión

- **La política vive en el plan.** `plans.daily_entry_limit` es un entero opcional con `CHECK (daily_entry_limit IS NULL OR daily_entry_limit >= 1)`. `NULL` significa «sin límite» y es el valor de todas las filas existentes, así que la migración `20261028_0043_plan_daily_entry_limit.py` no rellena nada. La vista previa recibe la columna con `preview_patch.ADDED_COLUMNS["plans"]`.
- **Se configura con un PATCH acotado.** `PATCH /admin/plans/{plan_id}` recibe `{"daily_entry_limit": 2}` o `{"daily_entry_limit": null}` (campo obligatorio: no se puede omitir por accidente) y responde el plan completo. Exige `settings.manage`, igual que la administración de kioscos, porque es una política del club y no una tarea de recepción. `GET /admin/plans` expone `daily_entry_limit` junto a los datos que ya usaba el selector de membresías. El panel lo edita en la página «Kiosco», con una fila por plan y campo vacío = sin límite.
- **El kiosco lee el plan de la membresía más reciente.** En `_decide`, `access.kiosk` obtiene `membership.plan_id`, carga el plan y pasa `daily_entry_limit` al snapshot. Un plan sin límite no ejecuta la consulta de conteo. La regla sigue viviendo en `evaluate_access`: el kiosco solo alimenta el snapshot.
- **El conteo es del día del club, no de las últimas 24 horas.** `count_member_entries_today` usa la medianoche local de `APP_TIMEZONE` (la misma convención de `access_today_summary` y los reportes) y cuenta eventos `authorized=true`, `direction=entry` del socio, sin importar si vienen del kiosco (`source="reader"`) o de recepción (`source="manual"`). Una denegación y una salida no cuentan. El instante de referencia es el `occurred_at` de la decisión, no el reloj del servidor.
- **La entrada manual siempre se permite y sí suma.** Recepción puede dejar entrar a un socio aunque haya agotado su límite, porque el override manual es una excepción con bitácora; pero esa entrada cuenta para el siguiente intento del kiosco. El límite no se aplica al acceso manual para no convertir una cortesía o una incidencia en un bloqueo del mostrador.
- **La emisión del código no se bloquea.** El socio con el límite agotado puede pedir un código; el kiosco lo consume y responde `200` con `authorized=false`, `reason="daily_limit"` y el mensaje existente. Bloquear la emisión exigiría duplicar la regla en el portal y dejaría al socio sin explicación en la tablet.
- **El límite es del plan vigente en el momento de la decisión.** Cambiar de plan o editar el límite aplica de inmediato, sin recálculo ni caché. El conteo del día no se reinicia al cambiar de plan: las entradas ya registradas siguen contando.

## Consecuencias y límites

- Un plan de «una entrada al día» ya no se puede usar dos veces por el kiosco, y la regla se ve y se cambia desde el panel con una cuenta con `settings.manage`.
- **Solo el kiosco aplica la regla.** Los lectores físicos no existen todavía y el acceso manual la omite por diseño; cuando se conecten hardware y accesos por QR/tarjeta, el lector deberá alimentar el mismo snapshot o la política quedará a medias.
- **No hay validación atómica entre el conteo y la inserción.** Dos kioscos que consuman códigos del mismo socio en el mismo instante podrían contar el mismo estado y ambos conceder. Hoy el club tiene una sola tablet y el código es de un solo uso, así que el riesgo es teórico; si se abren varios kioscos, habrá que bloquear la fila del socio o contar dentro de la transacción del evento.
- **El día del club no se reinicia con un job.** Se recalcula en cada decisión con la zona horaria configurada; un cambio de `APP_TIMEZONE` a mitad del día mueve la frontera y puede repetir o alargar el cupo. La zona se valida al arrancar (ADR y `validate_club_timezone`), pero no se audita el cambio.
- **El panel no administra planes completos.** Solo edita este campo; no hay alta, baja, precio ni duración desde la interfaz, ni historial de quién cambió el límite y cuándo. Queda como deuda junto con el resto del CRUD de planes.
- **No se avisa al socio.** La bandeja no gana un aviso de «límite alcanzado»: la tablet muestra el mensaje y la bitácora guarda la denegación, pero no hay push ni correo. El socio se entera al intentar entrar.
- **Cupo y horarios siguen fuera.** El snapshot del kiosco mantiene ocupación 0, adeudo `false` y horario `null`; este incremento solo conecta el límite diario, no el resto de la política de acceso.
- Un plan con límite `0` no existe: se usa `NULL` para «sin límite». La API valida `ge=1` y el servicio repite la guarda para cualquier llamada interna.

## Referencias

- `backend/src/app/modules/memberships/models.py` (`Plan.daily_entry_limit`, `ck_plans_daily_entry_limit`)
- `backend/alembic/versions/20261028_0043_plan_daily_entry_limit.py`, `backend/preview_patch.py` (`ADDED_COLUMNS["plans"]`)
- `backend/src/app/modules/memberships/service.py` (`update_plan_daily_entry_limit`)
- `backend/src/app/main.py` (`PlanResponse`, `PlanDailyEntryLimitRequest`, `PATCH /admin/plans/{plan_id}`)
- `backend/src/app/modules/access/service.py` (`count_member_entries_today`, `evaluate_access`)
- `backend/src/app/modules/access/kiosk.py` (`_decide`)
- `backend/tests/test_kiosk_access_api.py` (2 pruebas del límite)
- `web/src/app/page.tsx` (`KioskView`), `web/src/app/api/admin/plans/[planId]/route.ts`
