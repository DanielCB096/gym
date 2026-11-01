# ADR-080: Cierre de los avisos de ticket al cerrar el ticket

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Cierra el límite de ADR-038 («solo el aviso de revisión se cierra solo») para el aviso de ticket

## Contexto

Desde ADR-038 la bandeja del personal distingue trabajo de lectura: `CLOSABLE_STAFF_KINDS` nombra los tipos que solo se descuentan cuando el servicio que completa el trabajo escribe `resolved_at`, y el resto se descuenta al marcarlos leídos. Solo `workout_pending_review` estaba en esa lista. El aviso de ticket asignado queda en el segundo grupo aunque el ciclo del ticket sí tenga un estado final: `resolve_ticket` y `cancel_ticket` son las dos únicas transiciones de cierre, y después de ellas `update_ticket` rechaza el ticket resuelto o cancelado. El resultado era una insignia que medía lecturas: el técnico podía marcar leído un ticket que seguía abierto y la campana lo daba por atendido, mientras un ticket terminado seguía contando hasta que alguien abriera el aviso.

La pieza ya existía: `resolve_staff_notifications(kind, ref_id)` cierra todas las filas de un tipo y una referencia dentro de la transacción del llamante, sin commit propio, y marca `read_at` si nadie había abierto el aviso. `resolve_ticket` y `cancel_ticket` tienen el ticket, su instante y un único `commit()` al final.

## Decisión

- **`maintenance_ticket_assigned` entra en `CLOSABLE_STAFF_KINDS`.** La insignia y `unread_total` lo cuentan mientras `resolved_at` sea nulo, se haya leído o no; leerlo deja de vaciarlo.
- **El cierre lo escriben las dos transiciones terminales del ticket.** `resolve_ticket` y `cancel_ticket` llaman a `resolve_staff_notifications(session, kind="maintenance_ticket_assigned", ref_id=ticket.id, now=occurred)` después de liberar el equipo y antes de su `session.commit()`. El cierre y el cambio de estado del ticket entran o revierten juntos; ninguna ruta de lectura cierra nada.
- **Cierra todas las cuentas que recibieron el aviso de ese ticket.** La búsqueda es por `(kind, ref_id)` sin filtrar `user_id`, igual que en ADR-038: si el ticket se reasignó, cada técnico que recibió el aviso ve el suyo atendido; las filas se conservan como historial con la etiqueta «Atendido» que el panel ya pinta.
- **Cerrar sin abrir deja el aviso leído.** `resolve_staff_notifications` sella `read_at` si era nulo, así que un ticket cerrado no aparece como «nuevo» en la lista ni suma al punto coral.
- **Un ticket sin destinatario cierra cero filas.** Si nunca se asignó a una cuenta activa no hay aviso que cerrar y la operación es inocua.
- **Sin migración, sin endpoint ni pantalla nueva.** La columna `resolved_at` existe desde ADR-038, el panel ya dibuja los avisos atendidos y la insignia ya lee `_staff_pending_condition`; el cambio es la lista de tipos y dos llamadas dentro de transacciones existentes.

## Consecuencias y límites

- **Reasignar un ticket no cierra el aviso del técnico anterior.** Solo el cierre del ticket lo hace: un ticket que pasa de A a B deja el aviso de A en su insignia hasta que el ticket se resuelva o se cancele, momento en que se cierran ambos. Cerrar al desasignar exigiría distinguir por destinatario y hoy la API de cierre trabaja por `(kind, ref_id)`.
- **Editar el ticket no cierra nada.** Cambiar título, severidad, costo o fecha no es cerrar; el aviso sigue pendiente hasta `resolve` o `cancel`.
- **El aviso del token del kiosco sigue sin cierre.** Rotar el token no es «atender el aviso» y su cierre quedó pospuesto; se descuenta al marcarlo leído, como antes.
- **Un ticket abierto para siempre deja su aviso para siempre.** La purga de ADR-075 nunca borra una tarea sin resolver; un ticket que nadie cierra conserva la fila aunque el técnico ya la haya leído. Es la misma regla que protege los pendientes de revisión.
- **La cola de correo y el push no cambian.** Una entrega ya enviada o `pending` sigue su curso; el cierre marca el aviso, no las entregas. Un aviso cerrado sin abrir puede haber salido por correo igualmente.
- **`resolve_staff_notifications` no abre savepoint propio**, como en ADR-038: si el `commit()` del ticket falla, el cierre se revierte con él.

## Referencias

- `backend/src/app/modules/notifications/service.py` (`CLOSABLE_STAFF_KINDS`, `resolve_staff_notifications`, `_staff_pending_condition`)
- `backend/src/app/modules/maintenance/service.py` (`resolve_ticket`, `cancel_ticket`)
- `backend/tests/test_maintenance_ticket_notice_closure.py`, `backend/tests/test_staff_notifications_api.py`, `backend/tests/test_inbox_retention.py`
- `docs/05-decisiones/ADR-038-cierre-del-aviso-de-revision.md`, `ADR-075-retencion-de-la-bandeja-y-entregas-del-personal.md`, `ADR-017-avisos-del-personal.md`
- `docs/02-modulos/notificaciones-del-socio.md`, `docs/02-modulos/mantenimiento-equipo.md`
