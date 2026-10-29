# ADR-031: Horario de acceso por plan con ventanas configurables

- Fecha: 2026-10-29
- Estado: propuesta inicial

## Contexto

El motor de accesos siempre supo validar un horario: `evaluate_access` compara la hora local del club con `AccessSnapshot.allowed_windows` y deniega con `reason="outside_allowed_hours"` y «Estás fuera del horario permitido.». Nunca hubo datos: ningún camino del backend llenaba esa lista, así que el kiosco enviaba `allowed_windows=None` y la regla era código muerto. Un socio con membresía vigente, sin adeudo bloqueante y dentro de su límite diario entraba a cualquier hora.

El club todavía no define sus ventanas (si cierra al mediodía, si abre domingos, si un plan es matutino). Por eso el incremento no decide la política: deja el horario **preparado y configurable por plan**, con la regla de que un plan sin ventanas sigue abierto todo el día. Configurar es lo que cambia el comportamiento; mientras nadie configure nada, la operación es idéntica a la de ayer.

## Decisión

- **Las ventanas son del plan, en una tabla propia.** `plan_access_windows` guarda `plan_id` (FK con `ON DELETE CASCADE`), `weekday` (0 = lunes, como `datetime.weekday()`), `starts_at` y `ends_at` (`TIME`), con un índice por plan. Se modela como filas y no como columnas del plan porque un plan puede tener varias ventanas por día y ninguna en otros. `CHECK` limita `weekday` a `0..6` y prohíbe `starts_at = ends_at`; una restricción única evita el mismo tramo repetido. La migración `20261029_0047` crea la tabla **sin relleno**: ningún plan nace con horario.
- **Un plan sin ventanas está abierto todo el día.** `plan_access_windows` devuelve una tupla vacía y el kiosco la traduce a `allowed_windows=None`, el único caso en que el motor no consulta el horario. La distinción importa: una lista vacía habría cerrado el club entero, así que el traductor vive en el kiosco y está comentado en el código.
- **Las ventanas se reemplazan completas desde el panel.** `PUT /admin/plans/{plan_id}/access-windows` recibe `{"windows": [...]}` con `settings.manage` y sustituye el conjunto en una sola transacción: borra las filas del plan e inserta las nuevas. No hay `POST` ni `DELETE` por ventana, así que el kiosco nunca lee media semana guardada y dos administradores no dejan estados mezclados. Una lista vacía retira el horario y devuelve el plan a «abierto todo el día». `GET /admin/plans` y el propio `PUT` devuelven `access_windows` dentro de `PlanResponse`, así que el panel no necesita otra consulta para pintar el resumen.
- **La validación vive en el servicio, no solo en el esquema.** `_validated_windows` rechaza más de 28 ventanas por plan, un día fuera de `0..6`, inicio igual al fin (mensaje que remite a dejar el plan sin ventanas), el tramo duplicado y dos ventanas que se traslapan el mismo día. Los traslapes se comprueban en segundos del día y **una ventana nocturna se parte en dos tramos** —desde su inicio hasta la medianoche y desde las 00:00 del día siguiente hasta su fin—, para que el cruce con una ventana matutina del día siguiente también se detecte. El `CHECK` y el índice único son la última red; los mensajes en español salen del servicio.
- **El kiosco aplica el horario del plan de la membresía vigente.** `_decide` ya resuelve el plan; ahora también lee sus ventanas y las pasa al motor con `allowed_windows`. La hora se interpreta en el huso del club (`APP_TIMEZONE`), el mismo que usa el conteo diario, y se evalúa **antes** del límite diario y del antipassback. Una ventana cuyo fin es menor que su inicio cruza la medianoche: el motor permite desde el inicio hasta las 23:59 de ese día y desde las 00:00 del día siguiente hasta el fin, exclusive. Una ventana aplica al día en que empieza, no al día en que termina.
- **El panel estrena una sección «Horario de acceso» en «Kiosco».** Una tabla por plan muestra «Abierto todo el día» o el resumen compacto (`Lun 06:00–22:00 · Dom 08:00–14:00`) y cuántas ventanas tiene; «Editar horario» abre un modal con una fila por ventana (día, inicio, fin), «Agregar ventana», «Quitar todas» y «Guardar horario». El panel valida en línea que cada fila tenga horas y que no sean iguales, y muestra tal cual el mensaje de traslape o de duplicado que responde el backend. El chip de la sección cuenta los planes con horario configurado.
- **Sin permiso nuevo, sin cambio en la entrada manual y sin cambio en las salidas.** Configurar usa `settings.manage`, el mismo permiso que el límite diario y el antipassback, y el acceso manual de recepción sigue autorizándose como `manual_override` fuera de horario —el caso que ya documenta el módulo—. Una salida se autoriza sin consultar horario.

## Consecuencias y límites

- **Mientras nadie configure ventanas, nada cambia.** El comportamiento de hoy —entrar a cualquier hora— es exactamente el de un plan sin filas, y la migración no siembra ninguna. Configurar un horario es una decisión del club, no un efecto de este incremento.
- **El socio no ve su horario en la app.** Se entera en la tablet con «Estás fuera del horario permitido.» y la denegación queda en la bitácora con `reason="outside_allowed_hours"`. Mostrarlo en `GET /member/access/code` o junto al plan es un incremento aparte.
- **Las ventanas son horas de pared del club, sin zona propia.** Si el club cambia `APP_TIMEZONE`, el mismo horario significa otra cosa; no hay conversión ni zona por ventana. Tampoco hay excepciones: ni días festivos, ni horarios especiales, ni ventanas por área o por lector, ni distinción entre entrada y salida.
- **La lista se lee en cada check-in, no se cachea en el snapshot.** Evita incoherencias entre kioscos, pero cuesta una consulta por intento (indexada por plan) y deja el horario fuera del alcance de una futura validación offline: hoy no existe check-in sin red.
- **El tope de 28 ventanas** (cuatro por día en promedio) es un límite de producto, no técnico: alcanza para abrir y cerrar al mediodía cada día de la semana. Un club que necesite más tendría que replantear el modelo, no subir el número.
- **El horario no bloquea la emisión de códigos**: el socio puede generar su código a cualquier hora y el rechazo ocurre en la tablet, igual que con el límite diario (ADR-025).
- La fila del socio sigue bloqueada durante la decisión (ADR-030), así que dos kioscos no pueden decidir con horarios distintos a la vez; la lectura del plan y sus ventanas entra en la misma transacción.

## Referencias

- `backend/src/app/modules/access/models.py` (`PlanAccessWindow`)
- `backend/src/app/modules/access/service.py` (`plan_access_windows`, `replace_plan_access_windows`, `_validated_windows`, `_reject_overlaps`, `_is_within_schedule`)
- `backend/src/app/modules/access/kiosk.py` (`_decide`)
- `backend/src/app/main.py` (`PlanAccessWindowResponse`, `PlanAccessWindowsRequest`, `PUT /admin/plans/{plan_id}/access-windows`, `_plan_response`)
- `backend/alembic/versions/20261029_0047_plan_access_windows.py`
- `backend/tests/test_kiosk_access_api.py` (`test_plan_schedule_windows_are_configured_from_the_panel`, `test_kiosk_denies_outside_the_plan_schedule`)
- `web/src/app/page.tsx` (`KioskView`, resumen y modal «Horario de acceso»), `web/src/app/api/admin/plans/[planId]/access-windows/route.ts`
- `docs/05-decisiones/ADR-025-limite-diario-de-entradas-por-plan.md`, `docs/05-decisiones/ADR-026-control-de-duplicados-antipassback.md`, `docs/05-decisiones/ADR-030-decision-de-entrada-serializada-por-socio.md`
