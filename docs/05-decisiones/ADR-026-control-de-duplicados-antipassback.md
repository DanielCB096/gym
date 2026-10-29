# ADR-026: Control de duplicados (antipassback) del club

- Fecha: 2026-10-28
- Estado: propuesta inicial

## Contexto

El motor de acceso ya sabía detectar una entrada duplicada: `AccessSnapshot.antipassback_seconds` y el parámetro `last_successful_entry_at` de `evaluate_access` existen desde el primer incremento, el motor responde `reason="antipassback"` y el mensaje del kiosco («Entrada duplicada. Espera un momento.») ya estaba redactado. Faltaba la política: no había dónde guardar la ventana, el kiosco evaluaba siempre con la ventana en cero y nadie pasaba la última entrada del socio.

El caso real es sencillo: el código del socio es de un solo uso, pero el socio puede pedir otro y volver a entrar en segundos —o recepción puede haberlo dejado pasar a mano— y el club quiere que el kiosco detecte el duplicado y lo registre, sin bloquear el mostrador. La regla tiene que ser del club, no de un plan, porque el umbral depende del flujo de la puerta y no de la tarifa.

## Decisión

- **La política vive en una fila única del club.** La tabla `access_settings` tiene una sola fila (`id = 1`) con `antipassback_seconds` entre `0` y `3600` y un `CHECK` de rango. `0` significa «desactivado» y es el valor con el que la migración `20261028_0044_access_antipassback_settings.py` siembra la fila, así que la regla queda apagada hasta que el club la encienda. No se guarda por plan ni por área.
- **Se configura con GET/PATCH acotados.** `GET /admin/access/settings` y `PATCH /admin/access/settings` (`{"antipassback_seconds": 60}`) exigen `settings.manage` y devuelven la ventana con su `updated_at`. El servicio `update_antipassback_seconds` repite la validación del rango por si la llamada viene de otro lado. El panel lo edita en la página «Kiosco», en la tarjeta «Control de duplicados», con `0` para desactivarlo.
- **El kiosco lee la ventana en cada check-in.** `access.kiosk._decide` consulta `read_antipassback_seconds` y, si es mayor que cero, busca la última entrada autorizada del socio con `last_member_entry_at(..., before=occurred_at)` y alimenta el snapshot y `last_successful_entry_at`. La decisión sigue en `evaluate_access`: el kiosco solo reúne los datos. Con la ventana en cero no se hace la consulta.
- **Cuenta la última entrada autorizada, también la manual.** La consulta filtra `authorized=true` y `direction=entry`, sin importar el origen (`reader` o `manual`), así que un socio que ya entró por recepción no puede saltarse la ventana con un código inmediatamente después. La búsqueda se acota con `occurred_at < occurred_at` de la decisión para no comparar el evento consigo mismo.
- **La entrada manual nunca se bloquea, pero sí cuenta.** `record_manual_access` sigue autorizando con `manual_override` sin mirar la ventana: una cortesía o una incidencia en el mostrador no puede quedar bloqueada. Esa entrada, en cambio, sí alimenta el siguiente intento del kiosco.
- **La emisión del código no se bloquea.** El socio puede pedir un código dentro de la ventana; el kiosco lo consume y responde `200` con `authorized=false`, `reason="antipassback"` y el mensaje existente. Bloquear la emisión exigiría duplicar la regla en el portal y dejaría al socio sin explicación.
- **La ventana se aplica al instante.** Cambiar el valor en el panel afecta el siguiente check-in, sin caché ni job de reinicio; no hay ventana «por día» ni reinicio a medianoche, porque el cálculo es una resta entre dos instantes.

## Consecuencias y límites

- Un segundo código del mismo socio dentro de la ventana queda denegado y registrado en la bitácora con el motivo «antipassback», y el club puede ajustar el umbral sin tocar código. Con `0` el comportamiento es idéntico al anterior.
- **Solo el kiosco aplica la regla.** El acceso manual la omite por diseño y los lectores físicos no existen todavía; cuando se conecten, deberán alimentar el mismo snapshot.
- **No hay validación atómica entre la lectura y la inserción.** Dos kioscos que consuman códigos del mismo socio en el mismo instante podrían leer el mismo estado y ambos conceder. Hoy el club tiene una tablet y el código es de un solo uso; si se abren varios kioscos habrá que bloquear la fila del socio o contar dentro de la transacción del evento.
- **No hay auditoría del cambio de política.** Se guarda `updated_at`, pero no quién cambió la ventana ni el valor anterior; el panel no muestra historial. Queda como deuda junto con el resto de la configuración del club.
- **La ventana es global.** No se puede fijar por plan, por área o por horario; un club con dos puertas o con un flujo especial necesitará una tabla por área o por lector.
- **La salida no reinicia la ventana.** Solo cuentan las entradas: un socio que entra, sale y vuelve a entrar en menos de la ventana queda denegado. Es el comportamiento esperado del antipassback simple, pero conviene documentarlo para no confundirlo con un fallo.
- **Una entrada retroactiva puede descolocar la ventana.** Si se corrige o importa una entrada con fecha anterior, la «última entrada» cambia con ella; no hay reloj monotónico por socio.
- **No se avisa al socio.** La tablet muestra el mensaje y la bitácora guarda la denegación, pero no hay push ni correo.

## Referencias

- `backend/src/app/modules/access/models.py` (`AccessSettings`, `ck_access_settings_antipassback_range`)
- `backend/alembic/versions/20261028_0044_access_antipassback_settings.py`
- `backend/src/app/modules/access/service.py` (`read_antipassback_seconds`, `get_access_settings`, `update_antipassback_seconds`, `last_member_entry_at`, `evaluate_access`)
- `backend/src/app/modules/access/kiosk.py` (`_decide`)
- `backend/src/app/main.py` (`AccessSettingsResponse`, `AccessSettingsRequest`, `GET`/`PATCH /admin/access/settings`)
- `backend/tests/test_kiosk_access_api.py` (2 pruebas del control de duplicados)
- `web/src/app/page.tsx` (`KioskView`), `web/src/app/api/admin/access/settings/route.ts`
- `kiosk/app.js` (muestra el `message` que devuelve el backend; el texto vive en `access.kiosk`)
