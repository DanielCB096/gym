# ADR-035: Recordatorios de la clase próxima y lista de espera sin promoción

- Fecha: 2026-10-29
- Estado: aceptada

## Contexto

El módulo de clases promete dos avisos que nunca existieron (sección 8 de `docs/02-modulos/clases-y-reservaciones.md`): recordar la clase próxima y avisar a la lista de espera cuando un lugar se libera. Hasta ahora el socio solo descubría ambos abriendo la pantalla de Clases.

El aviso de lista de espera sí existía, pero **solo en un camino**: cancelar una reserva confirmada promueve a la cabeza de la fila y emite `class_waitlist_promoted`. Hay dos maneras más de liberar un lugar y ninguna promovía:

- **subir el aforo** en `PATCH /admin/classes/sessions/{id}` deja sillas vacías con la fila intacta;
- **marcar una inasistencia** (`attended=false`) libera la reserva, y nadie ocupa el lugar.

El recordatorio planteado en la sección 8 era «30 minutos antes de la clase». Este proyecto no tiene programador: los avisos diferidos se materializan al leer la bandeja (ADR-016 y el recordatorio de membresía). Una ventana de 30 minutos solo se escribiría si el socio abre la app en esos 30 minutos, así que en la práctica no recordaría nada.

## Decisión

- **Un tipo nuevo, `class_reminder`.** Se suma al `CHECK` de `member_notifications` con la migración `20261029_0051_class_reminder_notification.py` y la reconstrucción encadenada de `preview_patch.py`. El `ref_id` apunta a la reserva y la app abre la pantalla **Clases** al tocar el aviso, igual que los de factura abren Facturas.
- **Dos ventanas: 24 h y 2 h antes.** Son las que un socio puede encontrar abriendo la app un día antes y otra vez poco antes de la clase. Sustituyen a los 30 minutos del borrador por la misma razón que el recordatorio de membresía usa días: sin job, la ventana debe ser lo bastante ancha para que la lectura ocurra dentro. Cada lectura elige **la ventana más estrecha** en la que la clase ya entró, así que abrir la bandeja dos veces en el mismo tramo escribe un solo aviso.
- **Diferido y deduplicado.** `_ensure_class_reminders` se ejecuta al leer `GET /member/notifications` y también `GET /member/notifications/unread-count`: la insignia es lo que invita a abrir la bandeja, así que un recordatorio que solo apareciera después de abrirla nunca se anunciaría. La clave `class_reminder:<reservation>:<24|2>` y su índice único parcial impiden duplicados entre peticiones concurrentes. Solo aplica a reservas `reserved` de clases `scheduled` que **todavía no empezaron**; una reserva cancelada, asistida o de una clase pasada no recibe recordatorio, y el que ya recibió se queda como historial.
- **El lugar liberado se ofrece promoviendo, no avisando a toda la fila.** La lista es ordenada: avisar a todos «hay lugar» rompería el turno de llegada y podría dejar la silla vacía si nadie responde. Por eso los dos caminos que no promovían ahora **promueven a la cabeza de la fila**, con el aviso `class_waitlist_promoted` que ya existía: `_seat_waitlist_in_free_spots` sienta a tantos socios como sillas haya libres tras subir el aforo, y marcar una inasistencia antes de la clase hace lo mismo.
- **Después de empezar la clase no se promueve.** `_promote_next_waitlist` comprueba `starts_at > ahora` y `status = scheduled` antes de mover a nadie: sentar a un socio en una clase que ya ocurre solo produce un aviso inútil. Una cancelación o inasistencia posterior deja la fila intacta y la silla sin usar. Antes de este ADR la cancelación promovía sin mirar la hora.
- **Sin tipo nuevo para el lugar liberado.** El aviso que recibe el socio es el de siempre (`class_waitlist_promoted`), porque la promoción es el hecho: el panel no necesita una columna nueva y la app ya lo etiqueta como «Clase».

## Consecuencias y límites

- **Sigue sin haber push ni correo.** El recordatorio se ve al abrir la app o al refrescar la insignia, y una clase que empieza sin que el socio abra la app no recibe aviso. Es el mismo límite que ya tiene la membresía por vencer.
- **La 24 h no garantiza 24 h de antelación.** Si el socio reserva cuando falta una hora, recibe el aviso de 2 h; el de 24 h no se escribe hacia atrás. El recordatorio anuncia «menos de N horas», no una cuenta exacta.
- **El recordatorio es un congelado.** Si el club mueve la hora de la clase después del aviso, el mensaje conserva la hora original; un cambio de horario no reenvía ni corrige el aviso (programar la clase y su aviso sigue siendo tema del programador pendiente).
- **Cancelar o liberar no borra el recordatorio recibido.** La bandeja es un historial: el socio puede ver «tu clase empieza en menos de 2 horas» de una clase que luego canceló. El estado real se ve en Clases, a donde lleva el aviso.
- **Promover en la subida de aforo puede sorprender.** Quien esperaba un lugar recibe el aviso sin que nadie haya cancelado; es el resultado buscado, pero la recepción debe saber que editar el cupo mueve la fila. La promoción se detiene en el aforo: si el nuevo cupo no alcanza para toda la fila, el resto conserva su posición.
- **La clase cancelada sigue sin avisar a nadie.** `cancel_class_session` cancela las reservas vivas (incluidas las de la fila) y no escribe avisos; queda documentado como pendiente. Tampoco se avisa del cambio de horario ni de la confirmación de la reserva propia.
- **El recordatorio no se cobra ni reserva nada.** Una clase premium promovida o recordada sigue cobrándose al marcar la asistencia (ADR-033); el aviso no crea venta.

## Referencias

- `backend/src/app/modules/notifications/models.py` (`class_reminder` en `NOTIFICATION_KINDS` y en el `CHECK`)
- `backend/src/app/modules/notifications/service.py` (`CLASS_REMINDER_WINDOWS_HOURS`, `_materialise_deferred`, `_ensure_class_reminders`)
- `backend/src/app/modules/classes/service.py` (`_promote_next_waitlist`, `_seat_waitlist_in_free_spots`, `update_class_session`, `mark_attendance`, `cancel_reservation`)
- `backend/alembic/versions/20261029_0051_class_reminder_notification.py`, `backend/preview_patch.py`
- `backend/tests/test_class_notifications.py`, `backend/tests/test_member_notifications_api.py`
- `mobile/src/format.ts`, `mobile/src/screens/NotificationsScreen.tsx`, `mobile/App.tsx`
- `docs/02-modulos/notificaciones-del-socio.md`, `docs/02-modulos/clases-y-reservaciones.md`
- ADR-016, ADR-033
