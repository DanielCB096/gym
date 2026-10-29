# ADR-032: Aforo estimado del club con ventana de estancia configurable

- Fecha: 2026-10-29
- Estado: propuesta inicial

## Contexto

El motor de accesos siempre tuvo la regla de ocupación: `evaluate_access` deniega con `reason="occupancy_full"` y «El club está lleno en este momento.» cuando `current_occupancy >= max_occupancy`. Nunca hubo datos. El kiosco enviaba `current_occupancy=0` y `max_occupancy=1`, valores fijos que jamás se cruzaban, y no existía un aforo configurable en ningún lado del backend. La única «capacidad» del sistema era la de los salones de clases.

Contar ocupación real exige saber cuánta gente está dentro, y eso pide restar salidas a las entradas. El sistema solo registra entradas: el kiosco graba siempre `direction="entry"` y no hay ningún punto que grabe una salida. Contar solo entradas haría que el número creciera todo el día y el club se autobloqueara al mediodía.

El club todavía no define su aforo ni cuánto dura una visita. Por eso el incremento no decide la política: deja el aforo **configurable y apagado por defecto**, con una **estimación** de la ocupación basada en el tiempo de estancia (dos horas por defecto). Configurar un número es lo que cambia el comportamiento.

## Decisión

- **Dos ajustes nuevos en la fila única de `access_settings`.** `max_occupancy` (`NULL` = sin límite) y `occupancy_window_seconds` (5 minutos a 24 horas, `7200` por defecto). La migración `20261029_0048` agrega las columnas con `CHECK` de rango y deja el aforo en `NULL`, así que ningún club cambia de comportamiento al migrar.
- **La ocupación se estima con la ventana de estancia.** `count_current_occupancy` cuenta socios distintos con una entrada **autorizada** —del kiosco o de recepción— cuyo `occurred_at` cae entre `ahora - ventana` y `ahora`. Una entrada nueva del mismo socio refresca su visita en vez de sumar a otra persona, y una denegación o una salida nunca suman.
- **Se documenta como estimación, no como sensor.** El kiosco no registra salidas, así que quien se queda más tiempo que la ventana se cuenta como que ya salió. Es el error conocido y aceptado: con dos horas, un socio que se queda cuatro ocupa lugar solo dos. Si algún día hay torniquete o salida escaneada, la consulta se cambia por salidas reales sin tocar la regla del motor.
- **`max_occupancy=0` significa «sin límite».** El motor antes trataba `<= 0` como club lleno; ahora solo deniega con un tope positivo. Es la misma convención de `antipassback_seconds = 0` y permite que el kiosco traduzca `NULL` a `0` sin un camino especial. El endpoint de vista previa sigue exigiendo `max_occupancy >= 1`, así que el contrato del motor no cambia para quien sí manda un aforo.
- **El kiosco manda los valores reales.** `_decide` lee el aforo y la ventana, cuenta la ocupación **solo si hay tope configurado** (una consulta indexada por `occurred_at` en cada check-in) y pasa ambos números al motor. La regla se evalúa después del horario, del límite diario y del antipassback; la denegación queda en la bitácora con `reason="occupancy_full"`.
- **Se configura donde ya se configura el resto de la política.** `GET`/`PATCH /admin/access/settings` (`settings.manage`) suman `max_occupancy` y `occupancy_window_seconds` a `antipassback_seconds`; el `PATCH` reemplaza la política completa en una sola transacción. El panel estrena la sección **«Aforo del club»** en «Kiosco», debajo de «Control de duplicados», con el aforo (vacío = sin límite), el tiempo de estancia en minutos y un chip que dice `Off` o «N socios». Valida en el cliente los rangos y muestra el error del backend si lo hay.

## Consecuencias y límites

- **Mientras el aforo quede vacío, nada cambia.** El kiosco sigue sin limitar la ocupación, igual que ayer; la migración no siembra un tope. Configurarlo es decisión del club.
- **Es una estimación, no un conteo de personas.** Quien se queda más de la ventana deja de contar y el aforo puede permitir unas personas de más; con una ventana muy larga el contador tarda en bajar. La ventana se elige con el club.
- **Solo cuentan las entradas autorizadas.** La entrada manual de recepción suma (el socio entró), pero un intento denegado no. Un evento offline sincronizado después cambia la ocupación retroactivamente, igual que la «última entrada» del antipassback.
- **No hay ocupación por zona, por plan ni por área**, ni cierre por festivo; tampoco se muestra al socio ni en la app ni en la tablet («El club está lleno en este momento.» solo aparece al capturar el código).
- **No sustituye a las salidas.** El kiosco sigue sin registrar `direction="exit"` y el motor nunca consulta la salida; con hardware de acceso o una salida escaneada, esta estimación debe revisarse.
- **La consulta extra solo corre con aforo configurado**, y el conteo no viaja en el snapshot: un check-in offline no podría evaluarlo.

## Referencias

- `backend/src/app/modules/access/models.py` (`AccessSettings.max_occupancy`, `occupancy_window_seconds`)
- `backend/src/app/modules/access/service.py` (`count_current_occupancy`, `read_occupancy_policy`, `update_access_settings`, `evaluate_access`)
- `backend/src/app/modules/access/kiosk.py` (`_decide`)
- `backend/src/app/main.py` (`AccessSettingsResponse`, `AccessSettingsRequest`, `PATCH /admin/access/settings`)
- `backend/alembic/versions/20261029_0048_club_occupancy.py`
- `backend/tests/test_kiosk_access_api.py` (`test_occupancy_estimate_counts_entries_inside_the_window`, `test_kiosk_denies_entries_when_the_club_is_at_capacity`), `backend/tests/test_access_offline.py` (`test_zero_occupancy_cap_means_the_club_has_no_limit`)
- `web/src/app/page.tsx` (`KioskView`, sección «Aforo del club»)
- `docs/05-decisiones/ADR-025-limite-diario-de-entradas-por-plan.md`, `docs/05-decisiones/ADR-026-control-de-duplicados-antipassback.md`, `docs/05-decisiones/ADR-031-horario-de-acceso-por-plan.md`
