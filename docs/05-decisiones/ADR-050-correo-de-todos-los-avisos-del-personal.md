# ADR-050: El correo de la cola cubre todos los avisos del personal

- Fecha: 2026-10-30
- Estado: propuesta inicial
- Sustituye el límite de ADR-049 («los demás avisos del personal siguen en la campana»)

## Contexto

ADR-048 y ADR-049 dejaron una cola de correo completa —entrega escrita con el aviso, pasada fuera de la transacción, reclamo compare-and-set, reintento manual y tarjeta de entregas— pero solo para los seis tipos del ciclo de asistencia. Los otros tres avisos del personal seguían llegando únicamente a la campana: la revisión de un entrenamiento (`workout_pending_review`), el ticket de mantenimiento asignado (`maintenance_ticket_assigned`) y el vencimiento del token del kiosco (`kiosk_token_expiring`). El entrenador y el técnico no suelen tener el panel abierto cuando el socio registra su entrenamiento o cuando el ticket se les asigna, así que el aviso dependía de que alguien mirara la campana.

La infraestructura ya resuelve los problemas difíciles —no hay worker, el envío no puede vivir dentro de la transacción del evento y la fila se reclama antes de tocar el SMTP—, así que extender el canal es una decisión de qué sale por correo y con qué texto, no un cambio de mecanismo.

## Decisión

- **Los nueve tipos del personal salen por correo.** `STAFF_NOTIFICATION_EMAIL_KINDS` deja de listar solo el ciclo de asistencia y toma la misma tupla de `STAFF_NOTIFICATION_KINDS`. Se conserva la tupla explícita —en vez de eliminar el filtro— para que un tipo futuro tenga que optar por el correo en lugar de salir por defecto.
- **El prefijo y la línea final cambian con el tipo, no el mecanismo.** Cada aviso sale con el prefijo del área que lo posee —`[Asistencia] `, `[Rutinas] `, `[Mantenimiento] `, `[Kiosco] `— y una línea que dice dónde revisarlo («pestaña Personal», «pestaña Rutinas», «pestaña Mantenimiento» o «página Kiosco»). El cuerpo sigue siendo el texto congelado del aviso más la firma del club; nada se recalcula desde el dominio.
- **La pasada se dispara también desde los emisores nuevos.** `AttendanceEmailFlush` se cuelga de `POST /member/routines/{assignment_id}/workouts` (el socio registra y el entrenador recibe), `POST /admin/maintenance/tickets` (el ticket nace asignado) y `PATCH /admin/maintenance/tickets/{ticket_id}` (la reasignación avisa al técnico nuevo). El aviso del token del kiosco ya se materializa al leer la campana, y esas dos lecturas ya llevan la pasada, así que no necesita un disparador propio.
- **El interruptor sigue siendo uno solo.** `staffing_settings.attendance_email_enabled` —y su nombre interno— se conserva: ahora decide el canal de correo de todo el personal, no solo del ciclo de asistencia. Se documenta como tal en el panel y en la documentación; renombrar la columna exigiría una migración sin cambiar el comportamiento.
- **La tarjeta se generaliza.** En «Personal → Equipo» la tarjeta pasa a «Correos del personal», el interruptor a «Enviar por correo los avisos del personal», la columna de tipo muestra su etiqueta («Rutinas · revisión pendiente», «Mantenimiento · ticket asignado», «Kiosco · vencimiento del token», etc.) y los textos de error del transporte hablan del correo del personal. Las rutas, los estados, el lote de 20, el compare-and-set y el reintento manual no cambian.

## Consecuencias y límites

- **No hay interruptor por tipo.** Apagar el correo detiene asistencia, rutinas, mantenimiento y kiosco a la vez. Separarlo exigiría columnas o una tabla de preferencias y no lo pidió el club.
- **La tarjeta sigue bajo `attendance.read`/`attendance.manage`.** Un técnico de mantenimiento o un entrenador sin permisos de asistencia recibe su correo, pero no puede ver la cola ni reintentar una entrega fallida; el permiso se decidirá cuando exista una pantalla de notificaciones propia del personal.
- **El aviso del token solo existe si alguien abre la campana.** Es la misma mecánica de ADR-028: quien no abre el panel no genera el aviso y, por tanto, tampoco su correo. El aviso de rutinas y el del ticket sí nacen con el evento.
- **No hay relleno.** Los avisos escritos mientras el canal estaba apagado —o antes de este corte— no se encolan al encenderlo; solo los avisos nuevos.
- **La ventana at-least-once y la falta de acuse siguen igual.** `sent` es que el servidor SMTP aceptó el mensaje, y el intento se confirma antes de enviar, así que un corte entre la aceptación y el `commit` puede repetir el correo. Ver la deuda técnica.
- **El destinatario sigue congelado al emitir.** Si la cuenta del técnico o del entrenador cambia de correo después, la entrega conserva la dirección anterior; una cuenta deshabilitada o sin correo deja el aviso solo en la campana.

## Referencias

- `backend/src/app/modules/notifications/models.py` (`STAFF_NOTIFICATION_KINDS`, `STAFF_NOTIFICATION_EMAIL_KINDS`)
- `backend/src/app/modules/notifications/delivery.py` (`SUBJECT_PREFIXES`, `NOTICE_LOCATIONS`, `email_message_for_notice`)
- `backend/src/app/main.py` (`member_log_workout`, `create_ticket_endpoint`, `update_ticket_endpoint`, `AttendanceEmailFlush`)
- `backend/src/app/modules/access/kiosk.py` (`warn_expiring_kiosk_tokens`)
- `backend/tests/test_attendance_email_delivery.py`, `backend/tests/test_staff_notifications_api.py`
- `web/src/app/page.tsx` (tarjeta «Correos del personal», etiquetas por tipo, interruptor de la política)
- `docs/05-decisiones/ADR-049-envio-y-reintento-de-la-cola-de-correos-de-asistencia.md`
