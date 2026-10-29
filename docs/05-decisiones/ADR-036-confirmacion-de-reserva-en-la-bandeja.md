# ADR-036: Confirmación de la reserva de clase en la bandeja del socio

- Fecha: 2026-10-29
- Estado: aceptada

## Contexto

La bandeja del socio ya tenía dos avisos de clase: la promoción desde la lista de espera (`class_waitlist_promoted`, ADR-016 y ADR-035) y el recordatorio de la clase próxima (`class_reminder`, ADR-035). Lo que faltaba era el más básico: **el socio nunca recibe la confirmación de su propia reserva**. Lo dice la documentación del módulo desde el segundo incremento («la confirmación de la propia reserva y los recordatorios de la clase próxima siguen sin avisarse») y quedó como pendiente al cerrar ADR-035.

El hueco se nota en dos caminos. En la **app**, el socio reserva y ve la confirmación en pantalla, pero esa pantalla no es un registro: si cierra la app, la única prueba del lugar es la propia lista de clases, y el primer aviso llega recién a las 24 horas con `class_reminder`. En **recepción**, el personal reserva por teléfono o en mostrador y el socio no se entera por ningún canal hasta que abre la pantalla de Clases; el aviso de promoción solo cubre el caso de la lista de espera, no el de una plaza sentada.

## Decisión

- **Tipo nuevo `class_reserved`**: `member_notifications.kind` admite un tipo más con la migración `20261029_0052_class_reserved_notification.py`, que suelta y recrea `ck_member_notifications_kind` con el mismo nombre (el `downgrade` se niega si quedan filas del tipo). `preview_patch.py` encadena un cuarto reemplazo del `CHECK` en la vista previa.
- **Se escribe al sentar el lugar, en la misma transacción.** `notify_class_reserved` se llama desde `reserve_seat` justo después del `flush()` de la reserva y antes del `commit`, así que el aviso y la reserva comparten transacción: no puede existir una sin la otra. Una reserva que cae en **lista de espera no confirma nada**; el socio ve su posición en la app y la promoción tiene su propio aviso cuando el lugar se abre.
- **También avisa la reserva que el socio hace en la app.** Es una excepción consciente a la regla de «nadie se avisa a sí mismo» que se aplica a las metas: la confirmación en pantalla es efímera y la bandeja es el único comprobante que queda, porque el proyecto no envía correo ni push. El cuerpo cambia según quién reservó: «Ya tienes tu lugar reservado en …» cuando el origen es la app y «Recepción reservó tu lugar en …» cuando lo hizo el personal (`origin = "reception"`), para que el socio no se sorprenda con una reserva que no hizo.
- **Una reserva, un aviso.** `ref_id` apunta a la reserva y no lleva `dedupe_key`: la reserva tiene identificador propio y el índice único parcial (`uq_class_reservations_active`) impide crearla dos veces, así que no hay nada que deduplicar. Cancelar y volver a reservar crea otra reserva y, por tanto, otra confirmación; la anterior queda en la bandeja como historial de la primera vez.
- **El seed no avisa.** `seed_classes.py` reconstruye la agenda en cada corrida y crearía cientos de confirmaciones de clases que ya no existen; sus dos llamadas pasan `notify_member=False`. Es la única excepción a la regla: las rutas reales (app y panel) avisan siempre.
- **La app la etiqueta y la enlaza.** `class_reserved` se pinta con la etiqueta «Clase», abre la pantalla Clases al tocarla y entra en el mismo grupo que el recordatorio y la promoción, sin cambios de API.

## Consecuencias y límites

- **Sin push ni correo**: el aviso se ve cuando el socio abre la bandeja; si no la abre, la confirmación existe pero no la lee. No sustituye a un correo de confirmación.
- **El texto es un congelado del momento**: título, fecha y hora de la clase al reservar. Si el club reprograma o renombra la clase, el aviso no se corrige; corregirlo exigiría un aviso de cambio, que sigue pendiente.
- **Cancelar no borra el aviso**: el socio conserva la confirmación de un lugar que ya no tiene. Se documenta como historial y no se intenta compensar con un aviso de cancelación, que tampoco existe.
- **Más ruido en la bandeja**: un socio que reserva cinco clases recibe cinco confirmaciones además de los recordatorios. El club puede preferir silencio para las reservas hechas en la app; hoy no hay preferencia por tipo ni forma de silenciarlas, y la alternativa sería limitar el aviso a recepción.
- **La lista de espera sigue sin aviso al entrar**: quien se apunta desde la app o lo apunta recepción no recibe nada hasta ser promovido; la posición solo se ve en la pantalla de Clases.
- **La reserva premium no anticipa el cobro**: la confirmación no menciona el precio extra porque se cobra al marcar la asistencia (ADR-033); un socio que reserva por teléfono una clase premium se entera del cargo en recepción, no en el aviso.
- **El aviso no se escribe si la reserva falla**: una reserva duplicada, una clase cancelada o un socio inactivo siguen respondiendo `409`/`404` sin dejar un aviso huérfano, porque el `flush()` de la reserva ocurre antes de redactar y todo revierte junto.

## Referencias

- `backend/src/app/main.py` (`POST /admin/classes/sessions/{id}/reservations`)
- `backend/src/app/modules/classes/service.py` (`reserve_seat`, `notify_member`)
- `backend/src/app/modules/portal/classes.py` (`reserve_member_class`)
- `backend/src/app/modules/notifications/service.py` (`notify_class_reserved`)
- `backend/src/app/modules/notifications/models.py` (`class_reserved`)
- `backend/alembic/versions/20261029_0052_class_reserved_notification.py`, `backend/preview_patch.py`
- `backend/tests/test_class_notifications.py`, `backend/tests/test_member_notifications_api.py`
- `backend/seed_classes.py`
- `mobile/src/screens/NotificationsScreen.tsx`, `mobile/src/format.ts`
- ADR-035, ADR-033
