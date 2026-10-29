# ADR-017: Bandeja de avisos del personal

- Fecha: 2026-10-27
- Estado: propuesta inicial

## Contexto

ADR-016 dejó la bandeja del socio cerrada pero pospuso deliberadamente la del personal, y la justificó con una premisa que resultó ser falsa: se documentó que «no existe un mapeo limpio de empleado → `app_users`» y que por eso no había forma de saber a quién avisar. Al revisar `app/modules/identity/models.py` y `register_user` el mismo 2026-10-27 se comprobó que **ese mapeo sí existe desde el módulo de RBAC**: `AppUser.employee_id` es una columna única con FK a `employees.id` (`RESTRICT`), la populatea `POST /admin/users` y la consume el alta de colaborador. La deuda real no era la ausencia del vínculo sino que **nadie lo usaba** para resolver una audiencia.

Mientras tanto el panel mostraba una campana con **datos de muestra** codificados en el propio `page.tsx` («7 membresías requieren seguimiento», «Todos los lectores están conectados»), es decir, una pantalla que finge funcionar. Dos eventos del dominio ya existían y hoy son invisibles para quien debe actuar:

- el socio registra un entrenamiento desde la app (`origin = "app"`, ADR-013) y queda **pendiente de revisión** del entrenador asignado; nadie se entera salvo que abra la pestaña de Rutinas;
- recepción asigna un ticket de mantenimiento a un técnico (`update_ticket` / `create_ticket` con `assigned_to`) y el técnico no recibe aviso alguno.

No se eligieron avisos que exigieran un programador (recordatorio semanal, ausencia prolongada) ni mensajería libre entrenador-socio: los dos anteriores son eventos ya implementados que producen trabajo asignable, y la infraestructura de ADR-016 (misma transacción, texto congelado, deduplicación en la base) sirve tal cual.

## Decisión

- **Se agrega `staff_notifications`** (migración `20261027_0036_staff_notifications.py`) con la misma forma que `member_notifications` pero dirigida a una **cuenta del panel**: `user_id` (FK `app_users.id`, `RESTRICT`), `kind`, `title`, `body`, `ref_id`, `dedupe_key`, `created_at`, `read_at`, y los índices `(user_id, created_at)`, `(user_id, read_at)` y el único parcial sobre `dedupe_key`. Razón de ser: el destinatario es quien inicia sesión en el panel, y ese sujeto es `app_users`, no `employees`.
- **Los dos `kind` son `workout_pending_review` y `maintenance_ticket_assigned`**, restringidos por `CHECK ck_staff_notifications_kind`. No se crearon tipos que dependan de un job inexistente.

> _Actualización 2026-10-29: el `CHECK` admite un tercer tipo, `kiosk_token_expiring`, que no lo emite un servicio de dominio sino la propia lectura de la bandeja (`warn_expiring_kiosk_tokens`) y se dirige a las cuentas con `settings.manage` en lugar de a un empleado. Ver ADR-028._
- **La audiencia se resuelve en un solo lugar**: `staff_user_for_employee(session, employee_id)` devuelve la cuenta **activa** vinculada al empleado o `None`. Los módulos de `routines` y `maintenance` solo pasan el `employee_id` que ya tienen en su modelo (`RoutineAssignment.trainer_id` y `MaintenanceTicket.assigned_to`, ambos FK a `employees.id`); nunca consultan `app_users` por su cuenta. La dirección de dependencia sigue siendo una sola —los módulos importan `notifications`, nunca al revés—, ahora con un tercer importador.
- **Un aviso sin destinatario se omite en silencio**, no falla. `notify_trainer_pending_workout` y `notify_technician_ticket_assigned` devuelven `None` si el empleado no tiene cuenta o está desactivada: el entrenamiento se registra y el ticket se asigna igual. Una cuenta mal dada no puede bloquear la operación.
- **Solo el origen `app` avisa al entrenador.** `log_workout` emite el aviso dentro de su transacción cuando `origin == "app"` y con el entrenador de la asignación; un entrenamiento que captura el personal ya está siendo mirado por él, así que avisarle sería ruido.
- **La asignación de ticket se avisa en el alta y en la edición**, con `dedupe_key = maintenance_ticket_assigned:<ticket_id>:<employee_id>`: volver a guardar el mismo técnico no re-anuncia nada, pero cambiar el responsable sí genera un aviso nuevo.
- **El texto se recorta, no se corta.** Los cuerpos se arman con `_clip(valor, límite)` porque nombre del socio, de la rutina, del equipo y título del ticket son editable por el usuario; sin recorte, un nombre largo haría fallar el `CHECK` de 500 caracteres y abortaría el alta del ticket o del entrenamiento.
- **El savepoint protege el cambio de dominio, no al revés.** El `begin_nested()` de la deduplicación se abre **después** de `session.flush()`: así, una colisión por `dedupe_key` repite solo la fila del aviso y deja intacta la inserción del ticket que estaba pendiente en la misma transacción (sin ese orden, perder el aviso habría borrado el ticket).
- **Cuatro rutas de auto-servicio bajo `/admin/notifications*`**: `GET` (paginado, `page_size` 1–50, `unread_total`), `GET /unread-count`, `POST /{id}/read` (idempotente, `404` si el aviso es de otra cuenta o no existe) y `POST /read-all` (`{"updated": n}`). **No se agregó ningún permiso**: la bandeja queda limitada a `principal.user_id`, de modo que un token de socio recibe `401` y un dueño no puede marcar leído el aviso de un entrenador.
- **La campana del panel se conecta a datos reales**: el popover deja de mostrar el texto de muestra, la insignia aparece solo con `unread > 0`, el `aria-label` pasa a «Notificaciones, N sin leer», y el encabezado alterna «N sin leer» / «Todo leído». El conteo se consulta al restaurar la sesión y tras iniciar sesión; la lista se carga al abrir el popover (`page_size=12`), no en segundo plano. Marcar uno es optimista sobre la respuesta; marcar todo usa el `updated` real para el mensaje.

## Consecuencias y límites

- El entrenador ve en el panel, sin abrir la pestaña de Rutinas, qué entrenamientos le quedaron pendientes; el técnico ve los tickets asignados. Los estados de muestra de la campana desaparecen.
- **Aviso omitido ≠ aviso perdido**: si el entrenador de las asignaciones no tiene cuenta activa, el entrenamiento se registra y nadie se entera. No hay advertencia en el alta del socio ni en la asignación; la verificación de que todo entrenador tiene cuenta sigue siendo un procedimiento manual.
- **No hay push ni correo**, solo la campana del panel, y su conteo se refresca al abrir la sesión o el popover. Un aviso nuevo generado mientras la pestaña está abierta no aparece hasta volver a abrirlo.
- `workout_pending_review` **no se cierra cuando el personal revisa el entrenamiento**: la bandeja es un historial de avisos, no un flujo de trabajo. El pendiente real se sigue viendo en Rutinas; el aviso no se marca «resuelto» ni desaparece.
- **La deduplicación del ticket es por (ticket, técnico)**, así que reasignar A→B→A **no vuelve a avisar** a A: el aviso original ya existe. Es deliberado para no spam, pero significa que una reasignación de vuelta puede pasar desapercibida.
- Los avisos **no caducan ni se purgan** y el texto es un snapshot que nombra socios y equipos, con lo que entra en el procedimiento ARCO igual que los del socio (sin FK en `ref_id`).
- Un fallo al redactar el aviso aborta la operación de dominio (misma transacción), y los textos están fijados en español dentro del servicio.
- La migración es PostgreSQL-only y la vista previa crea la tabla con `create_all`; el bloqueo de fila es no-op en SQLite aunque el índice único sí aplica.
- Antes de producción: decidir retención y política de privacidad de los avisos del personal, el transporte push/correo, qué hacer cuando el destinatario no tiene cuenta, y si el pendiente de revisión debe cerrarse al revisar.

## Referencias

- `backend/src/app/modules/notifications/models.py` (`StaffNotification`, `STAFF_NOTIFICATION_KINDS`, `ck_staff_notifications_kind`)
- `backend/src/app/modules/notifications/service.py` (`staff_user_for_employee`, `create_staff_notification`, `_append`, `notify_trainer_pending_workout`, `notify_technician_ticket_assigned`, `list_staff_notifications`, `mark_staff_notification_read`, `mark_all_staff_notifications_read`, `_paginate_inbox`)
- `backend/src/app/modules/identity/models.py` (`AppUser.employee_id`)
- `backend/src/app/modules/routines/service.py` (`log_workout`, rama `origin == "app"`)
- `backend/src/app/modules/maintenance/service.py` (`create_ticket`, `update_ticket`)
- `backend/src/app/main.py` (`staff_notifications`, `staff_notifications_unread`, `staff_notification_read`, `staff_notifications_read_all`)
- `backend/alembic/versions/20261027_0036_staff_notifications.py`
- `backend/tests/test_staff_notifications_api.py`
- `web/src/app/api/admin/notifications/**` (BFF) y `web/src/app/page.tsx` (campana)
- ADR-016 (bandeja del socio), ADR-008 (autenticación y RBAC), ADR-013 (registro desde la app)
- `backend/src/app/modules/identity/service.py` (`user_ids_with_permission`, añadido con ADR-028)
- `backend/src/app/modules/access/kiosk.py` (`warn_expiring_kiosk_tokens`, añadido con ADR-028)
