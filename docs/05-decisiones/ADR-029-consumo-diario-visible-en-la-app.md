# ADR-029: Consumo diario de entradas visible al socio

- Fecha: 2026-10-29
- Estado: propuesta inicial

## Contexto

ADR-025 hizo que el kiosco contara las entradas autorizadas del día del club y negara con «Ya usaste tus entradas de hoy.» cuando el plan tiene límite. El socio no tenía forma de saberlo antes de caminar a recepción: generaba un código, la tablet lo consumía y solo entonces descubría que ya no le quedaban entradas. La app mostraba el código como «usado» sin explicar por qué.

El dato ya existía en el backend —`count_member_entries_today` y `plans.daily_entry_limit`—, pero no salía por ninguna ruta del socio.

## Decisión

- **Se extiende `GET /member/access/code`, no se crea una ruta nueva.** La pantalla que necesita el dato ya consulta esa ruta cada 4 segundos mientras el código está vigente; agregar `entries_today` y `daily_entry_limit` a esa respuesta evita duplicar peticiones y garantiza que el número y el estado del código se lean del mismo instante. Una ruta aparte (`/member/access/consumption`) habría costado otro sondeo para un dato que siempre se muestra junto al código, y meterlo en `/member/me` lo habría congelado en el último refresco del inicio.
- **El conteo es el mismo del kiosco.** Se reutiliza `count_member_entries_today`: entradas **autorizadas** de la dirección `entry` dentro del día local del club (`APP_TIMEZONE`), incluidas las manuales de recepción. La app y la tablet no pueden discrepar porque ejecutan la misma consulta; una entrada denegada no suma.
- **El límite sale del plan de la membresía más reciente**, el mismo par que usa `_decide` (`_latest_membership` + `Plan`). `null` significa «sin límite» y se informa tal cual.
- **El conteo se calcula siempre, aunque el plan no tenga límite.** Es una sola consulta indexada y el socio gana saber cuántas veces entró hoy; condicionarla al límite haría que la tarjeta apareciera y desapareciera al cambiar de plan.
- **La tarjeta es aparte del código y habla en español llano.** «N de M» cuando hay límite y «1» cuando no; debajo, «Te queda 1 entrada hoy.», «Te quedan N entradas hoy.», «Ya usaste tus entradas de hoy: la tablet no registrará otra hasta mañana.» o «Tu plan no tiene límite diario de entradas.». El aviso de agotado es el mismo hecho que el kiosco rechazará, dicho antes del viaje a recepción.
- **El primer refresco es inmediato.** El sondeo ejecuta su comprobación una vez al entrar al efecto y después cada 4 segundos, así que la tarjeta no queda vacía durante el primer intervalo.
- **Sin permiso nuevo, sin migración y sin columna.** Son datos derivados de tablas que ya existían.

## Consecuencias y límites

- El número **solo se refresca mientras hay un código en pantalla**. Al consumirse o vencer, el sondeo se detiene y la tarjeta queda con el último valor leído; no es un contador en vivo ni hay push.
- Una entrada registrada después del último sondeo aparece hasta que se genere el siguiente código.
- **La pantalla no distingue una entrada denegada de una concedida**: el kiosco consume el código en el intento, así que ambas terminan en «Código usado», y el conteo no sube en la denegada. El motivo lo dice la tablet. Cambiarlo exigiría que el estado del código consultara el resultado del check-in.
- Si el día del club cambia con la pantalla abierta, el conteo vuelve a cero en el siguiente sondeo, porque se calcula con el día local de la petición.
- La tarjeta informa, no bloquea: emitir un código nunca se impide por haber agotado las entradas (ADR-025). El rechazo sigue ocurriendo en la tablet.

## Referencias

- `backend/src/app/modules/access/kiosk.py` (`AccessCodeStatus.entries_today`, `AccessCodeStatus.daily_entry_limit`, `latest_member_access_code_status`)
- `backend/src/app/modules/access/service.py` (`count_member_entries_today`)
- `backend/src/app/main.py` (`MemberAccessCodeStatusResponse`, `GET /member/access/code`)
- `backend/tests/test_kiosk_access_api.py` (`test_member_access_code_status_reports_daily_consumption`)
- `mobile/src/screens/AccessCodeScreen.tsx`, `mobile/src/types.ts`, `mobile/src/api.ts`
