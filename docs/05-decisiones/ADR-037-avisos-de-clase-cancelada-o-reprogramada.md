# ADR-037: Avisos de clase cancelada o reprogramada

- Fecha: 2026-10-29
- Estado: aceptada

## Contexto

La bandeja del socio ya avisa del lugar confirmado, de la promoción desde la lista de espera y del inicio próximo de la clase (ADR-035 y ADR-036). Quedaba el caso inverso: **la clase se cae o se mueve y nadie se lo dice**. `cancel_class_session` cancelaba todas las reservas vivas —sentadas y en espera, con su reembolso premium— y no escribía un solo aviso; el socio lo descubría al abrir Clases. `update_class_session` movía el horario con las reservas intactas y tampoco avisaba, así que el recordatorio congelado seguía anunciando la hora vieja (ADR-035 lo documenta como límite). Las dos cosas figuraban como pendientes en el módulo de clases, en el de avisos y en la deuda técnica.

El hueco castiga justo al socio que hizo lo correcto: reservó, recibió su recordatorio y se presenta a una clase cancelada, o llega a la hora vieja de una clase que el club movió.

## Decisión

- **Dos tipos nuevos**, `class_cancelled` y `class_rescheduled`. La migración `20261029_0053_class_change_notifications.py` suelta y recrea `ck_member_notifications_kind` con el mismo nombre y catorce tipos (el `downgrade` se niega si quedan filas de los nuevos); `preview_patch.py` encadena el reemplazo del `CHECK` en la vista previa.
- **La audiencia es toda reserva viva**, `reserved` y `waitlist`. No solo el que tiene lugar: quien está en la fila también espera esa clase y, si no se le avisa, sigue esperando un lugar que ya no existe o que ahora es a otra hora. La consulta compartida es `_live_reservations(session, session_id)`.
- **La cancelación avisa a cada reserva antes de `commit()`**, después de cancelarla y de devolver su cobro premium si lo tenía. Todo comparte transacción: si la cancelación o el reembolso fallan, el aviso revierte con ellas y no queda un mensaje de una cancelación que no ocurrió. `dedupe_key = class_cancelled:<clase>:<socio>` impide un segundo aviso si dos cancelaciones concurrentes llegan a la misma fila, aunque la segunda ya responde `InvalidSessionState`.
- **La reprogramación solo se anuncia cuando cambia el horario.** `update_class_session` guarda `starts_at` y `ends_at` antes de tocarlos y compara al final: editar aforo, título, salón, instructor o notas no escribe nada. Si el inicio o el fin cambian, cada reserva viva recibe el aviso con **las dos ventanas** —«era el … de … a … y ahora es el … de … a …»— en el calendario del club, y el recordatorio anterior queda como historial con la hora vieja. `dedupe_key` incluye el instante del cambio, así que mover una clase dos veces deja dos avisos, y moverla de vuelta también.
- **El aviso de cancelación no habla de dinero.** Una reserva viva normalmente no tiene cobro —el premium se cobra al marcar asistencia (ADR-033)—; el reembolso es la red de seguridad para una asistencia ya cobrada y el socio lo ve en su estado de cuenta. Mencionarlo en el aviso sugeriría una devolución que casi nunca existe.
- **Si la capacidad sube en el mismo cambio, el promovido también se entera.** `_seat_waitlist_in_free_spots` corre antes de redactar, así que quien deja la fila por el nuevo aforo recibe su `class_waitlist_promoted` y, si además se movió la hora, el de reprogramación: dos hechos distintos, dos avisos.
- **La app las etiqueta y las enlaza.** `class_cancelled` se pinta como «Clase cancelada» y `class_rescheduled` como «Clase movida»; ambas abren la pantalla Clases al tocarlas y entran en el mismo grupo que el resto de avisos de clase, sin cambios de API.

## Consecuencias y límites

- **Sin push ni correo**: si el socio no abre la bandeja ni la app, se entera al llegar al gimnasio. El aviso no sustituye a una llamada de recepción para una clase que empieza en una hora.
- **El recordatorio viejo no se retira**: la bandeja puede mostrar «tu clase empieza pronto» con la hora anterior junto al aviso de reprogramación. Se conserva como historial, igual que la confirmación de una reserva cancelada.
- **Cancelar la clase deja una cancelación por socio**: una clase con treinta reservas escribe treinta filas en la misma petición. Es lineal y ocurre una vez, pero no hay tope ni trabajo diferido.
- **La cancelación de una reserva suelta no avisa**: `cancel_reservation` sigue en silencio, porque lo provocó el propio socio o recepción con el socio delante. Solo la cancelación de la clase —que nadie pidió desde la bandeja— escribe.
- **Reprogramar avisa aunque la clase ya empezó** si el personal edita el horario de una clase pasada; la validación de estado permite editar mientras siga `scheduled`. El texto dice la verdad (el horario cambió), aunque el aviso llegue tarde para ser útil.
- **No hay aviso de cambio de salón, instructor ni cupo**: solo el horario mueve el aviso, porque es lo único que cambia cuándo hay que presentarse. El resto se ve en la pantalla de Clases.

## Referencias

- `backend/src/app/modules/classes/service.py` (`cancel_class_session`, `update_class_session`, `_live_reservations`)
- `backend/src/app/modules/notifications/service.py` (`notify_class_cancelled`, `notify_class_rescheduled`)
- `backend/src/app/modules/notifications/models.py` (`class_cancelled`, `class_rescheduled`)
- `backend/alembic/versions/20261029_0053_class_change_notifications.py`, `backend/preview_patch.py`
- `backend/tests/test_class_notifications.py`
- `mobile/src/screens/NotificationsScreen.tsx`, `mobile/src/format.ts`
- ADR-035, ADR-036, ADR-033
