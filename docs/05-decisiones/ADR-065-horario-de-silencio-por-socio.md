# ADR-065: Horario de silencio por socio

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Cierra el límite de ADR-061 («el horario de silencio por socio queda abierto») y de ADR-059 («la preferencia es por tipo, no por horario»)

## Contexto

ADR-061 puso una ventana única para todo el club: dos variables de entorno en la hora local del gimnasio que frenan la pasada automática del push entre, por ejemplo, las 22:00 y las 07:00. Protege la noche de todos, pero el silencio que cada socio necesita no es el mismo: quien entra a las 05:00 quiere sonar a las 04:30 y callar a las 21:00; quien sale tarde prefiere que no le suene hasta las 09:00. La ventana del club tampoco puede multiplicarse por socio sin tocar el proceso, porque vive en la configuración y cambiarla exige reiniciar el backend.

ADR-059 dejó una puerta abierta a la decisión individual al imaginar «otra tabla» para el horario. Este corte la abre: el socio elige su propia franja desde la app, sin pedirle nada a recepción y sin aflojar la ventana del club, que sigue siendo el suelo de todos.

## Decisión

- **Una tabla nueva, una fila por socio.** `member_notification_settings` guarda `quiet_start`, `quiet_end` y `updated_at`, con FK `RESTRICT` a `members`, `uq_member_notification_settings_member` y el `CHECK` `ck_member_notification_settings_quiet_pair`: o las dos horas son nulas o las dos están y son distintas. **Un socio sin fila no tiene horario propio**, igual que una preferencia ausente significa encendida. La migración es `20261031_0074_member_notification_settings.py`.
- **Las horas van juntas y en el reloj del club.** El `PATCH` acepta `{"quiet_hours": {"start": "22:00", "end": "07:00"}}` o `{"quiet_hours": null}` para quitarlo; mandar una sola hora, la misma en las dos, un formato que no sea `HH:MM` o un socio inexistente responde `422` con el motivo. Se guardan como `TIME` y se interpretan en `APP_TIMEZONE`, como la ventana del club, así que ambos hablan del mismo «22:00»; la comparación soporta que la franja cruce medianoche (`start > end`).
- **La pasada filtra por fila, no salta filas.** `send_pending_member_push_deliveries` une la entrega con su socio y su ventana (`LEFT JOIN`) y descarta en SQL las entregas cuyo socio está dentro de su franja (`_outside_personal_window`). Un socio silenciado **no ocupa un lugar del lote** y no puede dejar esperando a los demás: la consulta sigue trayendo las primeras `limit` entregas enviables, no las primeras y luego las descarta. La ventana del club, en cambio, se consulta antes y difiere la pasada entera (`deferred: true`).
- **Silenciar es posponer, nunca cancelar.** No se borra ninguna entrega ni se anula `next_attempt_at`: las `pending` esperan y las `failed` conservan su reintento programado. Al terminar la franja, la siguiente pasada manda ambas. Es la misma regla que ADR-061 aplicó al club, ahora por destinatario.
- **La decisión humana no se pospone.** El envío manual desde la tarjeta «Push del socio» (`override_quiet_hours=True`) y el reintento manual de una entrega no consultan ninguna de las dos ventanas: si recepción decide avisar a las 23:00, su decisión manda. La vista previa (`PREVIEW_MODE=true`) tampoco las aplica, porque simular nunca suena.
- **La app explica el silencio y lo deja quitar.** `NotificationsScreen` suma la tarjeta «Tu horario de silencio» con dos campos («Desde»/«Hasta», `HH:MM`), el estado actual («Ahora mismo está en silencio: tu teléfono no sonará hasta las HH:MM.» / «En silencio de HH:MM a HH:MM.» / «Sin horario propio: tu teléfono suena a cualquier hora.»), la ventana del club como contexto y el botón «Quitar horario» cuando hay una. Un campo vacío en ambos quita el horario; un formato inválido o dos horas iguales se rechazan en la app antes de llamar al servidor, y el `422` del backend se muestra igual si llegara. La bandeja no cambia: los avisos siguen contándose y leyéndose.
- **El `GET` publica las dos ventanas.** `GET /member/notification-preferences` conserva las seis categorías y suma `quiet_hours` (`start`, `end`, `active`, `updated_at`) y `club_quiet_hours` (`start`, `end`, `active`); sin horario propio la primera llega `null`, y sin variables de club la segunda también. `active` se calcula con la hora del momento y la zona del club, así que la app puede decir si el teléfono está callado ahora. El `PATCH` sigue devolviendo la respuesta completa, y ahora exige **o categorías o horario, no ambos en la misma petición** (un cuerpo vacío responde `422`): cada acción se aplica y se confirma por su cuenta.

## Consecuencias y límites

- **Una sola franja por socio y ninguna por categoría.** Quien quiera silenciar solo las clases de madrugada y no una factura a las 23:00 tendría que apagar la categoría entera (ADR-059) o esperar a que el modelo admita ventanas por categoría. Tampoco hay ventana por dispositivo: el horario vale para todos los teléfonos del socio, igual que el interruptor de categoría.
- **El socio puede silenciar lo que el club considera urgente.** La ventana no distingue tipos: una cancelación de clase de última hora tampoco suena dentro de la franja. El aviso sigue en la bandeja, y la ventana del club no puede ser más permisiva que la individual; si el club necesita una excepción, hoy no existe.
- **La puntualidad depende de la pasada.** Sin programador, un push que espera el fin de la franja sale en la primera petición que dispare la pasada, como el resto del canal (ADR-061). El cron de ADR-063 consulta acuses y purga, no envía pushes, así que un club sin tráfico puede retrasar la salida unas horas.
- **La ventana no avisa a nadie y no deja historial.** No hay aviso al personal cuando un socio entra o sale de su franja, ni fila de auditoría: solo `updated_at`. Si el socio cambia la hora, la anterior se pierde. Para el procedimiento ARCO, la fila dice que ese socio eligió un horario, no cuándo ni desde qué dispositivo.
- **El panel no la muestra ni la edita.** La tarjeta «Push del socio» sigue enseñando la ventana del club (`quiet_window`) pero no la de cada socio; recepción no puede corregir un horario mal puesto salvo que el socio lo cambie desde la app. Agregar esa vista es trabajo de panel, no de este corte.
- **La hora es texto libre hasta el servidor.** La app sugiere `22:00`/`07:00` y valida `HH:MM`, y el backend vuelve a validarlo; no hay selector de hora nativo ni zonas horarias por socio: todas las franjas se leen en `APP_TIMEZONE`. Cambiar la zona del club mueve todas las ventanas, igual que la ventana de ADR-061.
- **Quitar el horario borra la fila.** No queda una fila con horas nulas ni un estado «apagado»; volver a poner un horario lo crea de nuevo. El borrado del socio sigue bloqueado por la FK `RESTRICT`.
- **La ventana no toca el correo del personal ni los avisos.** Solo gobierna el push real del socio; la campana, el correo y el contador de no leídos no se enteran. Tampoco cancela entregas: apagar una categoría sigue siendo la única acción que las retira.

## Referencias

- `backend/src/app/modules/notifications/models.py` (`MemberNotificationSetting`, `ck_member_notification_settings_quiet_pair`)
- `backend/src/app/modules/notifications/preferences.py` (`MemberQuietHours`, `PreferenceQuietHoursError`, `get_member_quiet_hours`, `update_member_quiet_hours`, `is_quiet_now`)
- `backend/src/app/modules/notifications/push.py` (`_outside_personal_window`, la consulta con `outerjoin` en `send_pending_member_push_deliveries`)
- `backend/src/app/main.py` (`GET`/`PATCH /member/notification-preferences`, `MemberNotificationQuietHoursResponse`, `MemberClubQuietHoursResponse`)
- `backend/alembic/versions/20261031_0074_member_notification_settings.py`
- `mobile/src/screens/NotificationsScreen.tsx` (tarjeta «Tu horario de silencio»), `mobile/src/api.ts` (`updateMemberNotificationQuietHours`), `mobile/src/types.ts`
- `backend/tests/test_member_notification_preferences.py` (21 pruebas: 13 de categorías y 8 del horario propio)
- `backend/tests/test_member_push_quiet_hours.py` (19 pruebas: 13 de la ventana del club y 6 del horario por socio)
- ADR-052 (push del socio), ADR-054 (reintento automático), ADR-059 (preferencias por tipo), ADR-061 (horario de silencio del club)
