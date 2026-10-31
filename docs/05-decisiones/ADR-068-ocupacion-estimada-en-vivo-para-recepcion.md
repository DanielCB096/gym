# ADR-068: Ocupación estimada en vivo para recepción

- Fecha: 2026-10-31
- Estado: propuesta inicial

## Contexto

El kiosco ya aplica el aforo del club desde ADR-032: `count_current_occupancy` estima cuántos socios están dentro y `evaluate_access` deniega con «El club está lleno en este momento.» al llegar al tope. El número existía y se recalculaba en cada check-in, pero solo lo veía el kiosco al denegar.

El panel, mientras tanto, mostraba un aforo de muestra: el Resumen pintaba «82 / 120» con tres zonas inventadas («Zona de fuerza», «Cardio», «Salones») y la página de Accesos decía «Sin sensores de aforo conectados». Recepción no tenía forma de saber cuánta gente había dentro ni de anticipar el rechazo del kiosco; el único dato real era el chip `Off`/«N socios» de la página «Kiosco», que muestra el **tope configurado**, no la ocupación, y exige `settings.manage`.

La estimación es la misma que ya se usa para denegar, así que exponerla no agrega una regla nueva: es lectura del mismo cálculo.

## Decisión

- **Un endpoint de lectura con el permiso de la bitácora.** `GET /admin/access/occupancy` (`access.read`, el permiso que ya tienen recepción, gerencia y dueño) devuelve `inside`, `max_occupancy`, `occupancy_window_seconds` y `sampled_at`. No permite cambiar la política: eso sigue en `PATCH /admin/access/settings` (`settings.manage`).
- **Se reutiliza el cálculo del kiosco.** `read_current_occupancy` en `access.service` lee la política con `read_occupancy_policy` y cuenta con `count_current_occupancy` usando la misma ventana de estancia que aplicará el siguiente check-in, así que el número del panel y el que decide el kiosco no pueden divergir por configuración. No crea la fila de ajustes si no existe: sin fila, el aforo es «sin límite» y la ventana es la de dos horas por defecto.
- **El panel pinta el dato real y retira el de muestra.** El Resumen estrena la tarjeta «Ocupación estimada» con `N / tope` y porcentaje cuando hay aforo, `N` y «Sin aforo máximo configurado» cuando no, la hora de la muestra y una nota que recuerda que es una estimación por entradas. La página «Accesos» reemplaza «Sin sensores de aforo conectados» por el mismo resumen en «Aforo general · Ahora mismo». Se eliminan la cifra fija y las zonas de muestra.
- **Sondeo mientras la página está abierta.** Con `access.read`, el panel consulta el endpoint al entrar a «Resumen» o «Accesos», al refrescar y cada 30 segundos; al cambiar de página o cerrar sesión el intervalo se detiene. Un `401` cierra la sesión como el resto de las consultas. Si una consulta falla, el panel conserva la última muestra y su hora, en vez de vaciar la tarjeta.
- **Sin permiso no se consulta.** Los perfiles sin `access.read` (por ejemplo entrenador o mantenimiento) no disparan la petición y ven «Tu perfil no tiene permiso para consultar la ocupación.» en el Resumen.

## Consecuencias y límites

- **Sigue siendo una estimación.** No hay registro de salidas: un socio cuenta como dentro mientras su última entrada autorizada cae dentro de la ventana (dos horas por defecto). Quien se queda más tiempo deja de contar y el club puede permitir unas personas de más; el número nunca corresponde a personas físicas.
- **Entradas manuales y denegaciones.** La entrada manual de recepción suma a la ocupación (el socio entró); un intento denegado o una salida no suman. Un evento offline sincronizado después mueve la ocupación retroactivamente, igual que en el kiosco.
- **No es push.** El panel refresca cada 30 segundos mientras la página está abierta; un check-in recién grabado puede tardar hasta medio minuto en reflejarse y, si la consulta falla, la tarjeta conserva la última muestra (la hora de la muestra lo delata). No hay aviso automático al acercarse al tope ni al llenarse.
- **Es del club completo.** No hay aforo por zona, plan, área ni por día festivo. El bloque de zonas del Resumen era de muestra y se retiró; si el club define un aforo por área, se necesitará otro cálculo y otro contrato.
- **La hora de muestra se pinta en el huso del navegador**, no en `APP_TIMEZONE`: en la recepción del club coinciden, pero una sesión abierta desde otra zona verá otra hora. El conteo en sí no depende del huso.
- **Solo lectura y solo kiosco aplica la regla.** Cambiar el aforo o la ventana sigue siendo una decisión de `settings.manage` en «Kiosco»; la recepción ve la ocupación, pero no la configura. La entrada manual de recepción se sigue autorizando con el club lleno como `manual_override`.

## Referencias

- `backend/src/app/modules/access/service.py` (`read_current_occupancy`, `count_current_occupancy`, `read_occupancy_policy`)
- `backend/src/app/main.py` (`AccessOccupancyResponse`, `GET /admin/access/occupancy`)
- `web/src/app/page.tsx` (`OccupancyEstimate`, `DashboardView`, `AccessView`)
- `web/src/app/api/admin/access/occupancy/route.ts`
- `backend/tests/test_kiosk_access_api.py` (`test_admin_occupancy_endpoint_reads_the_kiosk_estimate`)
- `docs/05-decisiones/ADR-032-aforo-estimado-del-club.md`
