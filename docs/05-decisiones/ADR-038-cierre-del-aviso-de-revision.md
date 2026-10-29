# ADR-038: Cierre del aviso de revisión cuando el entrenador revisa

- Fecha: 2026-10-29
- Estado: aceptada

## Contexto

El aviso `workout_pending_review` nació en ADR-017 para que el entrenador supiera que un socio había registrado un entrenamiento desde la app. Anunciaba trabajo pendiente, pero la bandeja no tenía forma de enterarse de que ese trabajo ya estaba hecho: al revisar el entrenamiento en la pestaña de Rutinas, el aviso seguía en la lista y en el contador de no leídos hasta que alguien lo marcaba leído a mano. Marcar leído, además, no distinguía «lo vi» de «lo atendí» —la bandeja solo tenía `read_at`—, así que la insignia de la campana podía seguir marcando un pendiente que el panel ya había resuelto, o quedarse en cero con trabajo real sin hacer.

La bandeja del socio no tiene este problema porque casi todos sus avisos informan de un hecho consumado (la revisión, la meta, la clase), no piden una acción. El único lado con trabajo accionable es el personal, y el único de sus tres tipos con un estado final claro y alcanzable por el sistema es el de revisión: el ticket asignado no tiene cierre único —puede reabrirse— y el token del kiosco se arregla rotándolo.

La primera verificación en vivo (2026-10-29) dejó ver el segundo filo del problema: «Marcar todo leído» bajaba la insignia a cero con tres entrenamientos todavía sin revisar, porque el filtro solo miraba `read_at`. Leer un pendiente de revisión no es atenderlo, así que la regla de conteo se corrigió en el mismo incremento.

## Decisión

- **Una columna `resolved_at` en `staff_notifications`.** La migración `20261029_0054_staff_notification_resolved.py` agrega la columna anulable y `preview_patch.py` la añade a la vista previa; la bandeja del socio **no** la recibe, porque sus avisos no son tareas. Es distinta de `read_at` a propósito: un aviso puede estar leído y seguir pendiente, o resolverse sin que nadie lo abriera.
- **La resolución la escribe el servicio que completa el trabajo, no el lector.** `review_workout` llama a `resolve_staff_notifications(kind="workout_pending_review", ref_id=<entrenamiento>)` antes de su `commit()`. La función no hace commit ni abre savepoint: el cierre y el cambio de estado del entrenamiento entran o revierten juntos. El lector sigue sin poder resolver nada por API; marcar leído no toca `resolved_at`.
- **El cierre no se limita a una cuenta.** La búsqueda es por `(kind, ref_id)` sin filtrar `user_id`: si la asignación cambió de entrenador o quien revisó fue recepción, el aviso se cierra donde viva. Es la misma idea que ya usa la emisión para resolver la audiencia —el destinatario se decide al emitir, el cierre va al aviso, no a la persona—, y evita que un pendiente quede huérfano porque su dueño ya no es el responsable.
- **Cerrar también da por leído.** Si la fila no tenía `read_at`, se sella con el mismo instante. Sin eso, el panel mostraría un punto de «nuevo» junto a la etiqueta «Atendido», y el `read-all` contaría un aviso que ya no debe nada. El sello es parte del mismo `UPDATE` lógico dentro de la transacción.
- **Lo pendiente no es lo no leído.** `unread_total` de `GET /admin/notifications` y `GET /admin/notifications/unread-count` cuentan trabajo por hacer: filas con `resolved_at IS NULL` que todavía deben algo. Para los tipos con cierre —`CLOSABLE_STAFF_KINDS`, hoy solo `workout_pending_review`— basta con no estar resueltos, aunque ya se hayan leído; para los tipos sin camino de cierre (`maintenance_ticket_assigned`, `kiosk_token_expiring`) se conserva la regla de no leído hasta que su servicio sepa cerrarlos. Marcar leído un pendiente de revisión no lo saca de la insignia; revisarlo, sí. La fila sigue en la lista con su `resolved_at`, para que el entrenador pueda comprobar que el pendiente que vio anoche se atendió. El envío al socio de `workout_reviewed` no cambia.
- **`_paginate_inbox` acepta la condición de conteo.** Es la única pieza compartida con la bandeja del socio, así que el conteo del personal pasa su condición (`unread_condition`) en vez de duplicar la consulta; la bandeja del socio conserva la suya, «no leído».
- **El panel lo cuenta como trabajo, no como lectura.** La insignia y el encabezado del popover pasan a «N por atender» / «Todo atendido», el aviso resuelto se ve atenuado con la etiqueta «Atendido», y el punto coral sigue al `resolved_at`, no al `read_at`: un pendiente ya leído sigue marcado en coral. Tras marcar leído, el panel vuelve a preguntar el contador al servidor en lugar de restarlo por su cuenta, y la vista de Rutinas avisa al encabezado tras revisar para que el conteo se actualice sin recargar. La etiqueta «Revisar» del entrenamiento ya desaparecía al revisarlo; ahora la campana coincide con esa pantalla.

## Consecuencias y límites

- **El cierre es definitivo**: revisar un entrenamiento responde `409` la segunda vez y ninguna ruta reabre ni el entrenamiento ni su aviso. Corregir una revisión exigiría decidir antes cómo reabrir ambos; hoy no existe.
- **Solo el aviso de revisión se cierra solo.** `maintenance_ticket_assigned` y `kiosk_token_expiring` siguen contando como pendientes hasta que alguien los lea, aunque el ticket se cierre o el token se rote: cerrar el ticket no es un paso único —puede reabrirse— y rotar el token no es «atender el aviso». Queda como pendiente decidir un cierre por estado para el ticket; el día que exista, su tipo se suma a `CLOSABLE_STAFF_KINDS` y la insignia lo contará hasta el cierre como el de revisión.
- **No queda registro de quién lo atendió en la bandeja.** El entrenamiento guarda `reviewed_by` y `reviewed_at`, pero el aviso solo conoce el instante del cierre. Para saber quién revisó hay que abrir la asignación.
- **Un aviso cerrado sin abrir no se lee.** El sello de `read_at` al cerrar significa que el entrenador puede no haber visto nunca el mensaje de un trabajo que ya está hecho; es el comportamiento buscado —la insignia mide trabajo, no lecturas—, pero perderá el detalle de que el socio registró el entrenamiento desde la app.
- **Un pendiente de revisión ya leído sigue en la insignia hasta que se revise.** Es lo buscado, pero cambia lo que significaba «Marcar todo leído» para ese tipo: deja de ser una forma de vaciar la campana y pasa a ser solo el registro de que el aviso se vio. Para los tipos sin cierre el botón conserva su efecto anterior.
- **La deduplicación no cambia**: el aviso de revisión sigue sin `dedupe_key`, porque cada entrenamiento es un hecho nuevo. Lo que cambia es su estado final.
- **El cierre no retira el aviso del socio** ni el historial del entrenamiento: el socio recibe su `workout_reviewed` y la fila atendida se conserva. La bandeja sigue creciendo sin retención.

## Referencias

- `backend/src/app/modules/notifications/models.py` (`StaffNotification.resolved_at`)
- `backend/src/app/modules/notifications/service.py` (`resolve_staff_notifications`, `_paginate_inbox`, `_staff_pending_condition`, `CLOSABLE_STAFF_KINDS`)
- `backend/src/app/modules/routines/service.py` (`review_workout`)
- `backend/alembic/versions/20261029_0054_staff_notification_resolved.py`, `backend/preview_patch.py`
- `backend/tests/test_staff_notifications_api.py`
- `web/src/app/page.tsx` (campana del panel, `AssignmentDetailModal`), `web/src/app/globals.css`
- ADR-017, ADR-028, ADR-037
