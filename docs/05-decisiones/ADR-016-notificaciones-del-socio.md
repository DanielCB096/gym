# ADR-016: Bandeja de avisos del socio alimentada por eventos del dominio

- Fecha: 2026-10-27
- Estado: propuesta inicial

## Contexto

Desde los incrementos anteriores el socio ya registraba entrenamientos, medidas y metas desde la app (ADR-013, ADR-014 y ADR-015), pero **todo lo que el personal resolvía sobre él quedaba invisible**: cuando el entrenador revisaba su entrenamiento, cuando recepción ajustaba o cancelaba una meta suya, cuando se liberaba un cupo y su lugar en la lista de espera quedaba confirmado, o cuando su membresía estaba por vencer. El roadmap pedía cerrar el ciclo con notificaciones y varias deudas técnicas del módulo de rutinas y de clases apuntaban exactamente a ese aviso.

El documento de arquitectura ya dibujaba las notificaciones como un **worker** alimentado por jobs (`H[Worker Jobs] --> I[Notificaciones]`), pero el backend no tiene Celery ni Redis desplegados: las tareas de fondo que existen hoy (envío de estados de cuenta, recordatorios de cobranza) se ejecutan de forma síncrona dentro de la petición. Introducir una cola solo para avisar al socio era infraestructura nueva sin beneficio demostrable, y un cron que escanee socios para «avisar» obliga a definir dónde vive, con qué idempotencia y qué pasa si se ejecuta dos veces.

Tampoco había un lugar dónde guardar el aviso: no existe ninguna tabla de notificaciones, y el panel web muestra una campana con **datos de muestra** que no provienen del backend.

## Decisión

- **Se crea el módulo `app.modules.notifications`** con la tabla `member_notifications` (migración `20261027_0035_member_notifications.py`): `member_id` (FK `RESTRICT`), `kind`, `title`, `body`, `ref_id` opcional, `dedupe_key` opcional, `created_at` y `read_at`. Un aviso es un **mensaje congelado**, no una referencia a datos vivos: el texto se redacta al producirse el evento, de modo que borrar o editar el origen no deja un aviso incomprensible.
- **Los avisos los emiten los propios eventos del dominio, en la misma transacción**, no un worker: `notify_workout_reviewed` desde `review_workout`, `notify_goal_achieved` desde `_apply_goal_updates`, `notify_goal_cancelled_by_staff` y `notify_goal_updated_by_staff` desde `cancel_member_goal`/`update_member_goal`, y `notify_waitlist_promoted` desde `_promote_next_waitlist`. Así un aviso no puede existir sin el cambio que anuncia ni faltar después de un commit. La dirección de dependencia es **una sola**: `routines` y `classes` importan `notifications`; `notifications` no importa a ninguno de los dos, así que no hay ciclos.
- **El aviso de membresía por vencer se genera de forma diferida** (`_ensure_membership_expiring`), calculado al leer la bandeja: si la membresía `active` más próxima a vencer termina en ≤ 7, ≤ 3 o ≤ 1 días, se crea el aviso con `dedupe_key = membership_expiring:<membership_id>:<7|3|1>`. Es la única forma de cubrir el vencimiento sin programador: **un solo recordatorio por ventana**, no uno por día, y ninguna ventana se reabre aunque el socio vuelva a entrar.
- **La deduplicación la garantiza la base de datos**, no una lectura previa: un **índice único parcial** sobre `dedupe_key` (solo donde `dedupe_key IS NOT NULL`) impide dos avisos iguales. `create_notification` escribe dentro de un `begin_nested()` y, si pierde la carrera contra una inserción idéntica de otra conexión, devuelve la fila ganadora en vez de propagar `IntegrityError`: el savepoint mantiene útil la transacción del llamante. En SQLite el bloqueo de fila es no-op, pero el índice único sí aplica.
- **La bandeja es de solo lectura para el socio y no se puede borrar**: `GET /member/notifications` (paginado, `page_size` 1–50, con `unread_total`), `GET /member/notifications/unread-count`, `POST /member/notifications/{id}/read` (idempotente) y `POST /member/notifications/read-all` (devuelve `updated`). El `member_id` sale siempre de la sesión y un aviso ajeno o inexistente responde `404` sin revelar si existe. **No se agregan permisos**: son rutas de auto-servicio bajo `get_current_member`, igual que el resto de `/member/*`.
- **`update_member_goal` recibe `actor_id`** para distinguir quién movió la meta: el endpoint administrativo lo pasa (`principal.user_id`, con `routines.manage`) y solo entonces se notifica al socio, y únicamente si cambió el objetivo o la fecha. La cancelación desde la app no pasa actor, así que el socio no se auto-notifica algo que acaba de hacer.
- **La app muestra la bandeja, no el push**: nueva `NotificationsScreen` con contador de no leídos, botón «Marcar todas como leídas», toque individual para marcar leído y etiqueta de tipo (`Membresía`, `Clase`, `Meta cumplida`, …). El inicio suma la tarjeta «Avisos del gimnasio» con una insignia de no leídos (tope visible 99+). El badge se refresca al abrir la sesión, al actualizar el perfil y al volver de la bandeja.
- **El destinatario de este incremento es solo el socio.** La campana del panel siguió mostrando datos de muestra y el aviso al entrenador de un entrenamiento pendiente quedó fuera. Se justificó como bloqueado «porque no hay un mapeo limpio de empleado → `app_users`», **una premisa que resultó ser falsa**: `AppUser.employee_id` ya existe (único, FK `RESTRICT` a `employees.id`) y lo puebla `POST /admin/users`. Lo que faltaba no era el vínculo sino un consumidor, y ese trabajo se hizo en el incremento siguiente (**ADR-017**).

## Consecuencias y límites

- El socio se entera en la app de las revisiones, los cambios de meta, la promoción de lista de espera y el vencimiento próximo, sin infraestructura nueva ni jobs.
- **No hay notificación push ni correo**: el aviso espera a que el socio abra la app. El `unread-count` se consulta al iniciar sesión y al actualizar el perfil, no en segundo plano.
- El aviso de vencimiento **depende de que el socio abra la bandeja**: si nunca entra, no se genera. Es un compromiso consciente frente a un programador que hoy no existe; si se despliega un job, `_ensure_membership_expiring` se puede invocar desde ahí sin cambiar el modelo (el `dedupe_key` ya evita duplicados).
- Los avisos **no caducan ni se borran**: la bandeja crece indefinidamente por socio y no hay política de retención definida, aunque el texto es un snapshot que puede contener nombre de rutina, medidas o importe.
- `ref_id` es una referencia **sin FK** (puede apuntar a varias tablas según el `kind`): no garantiza que el origen siga existiendo, que es justo lo que se buscaba al congelar el texto.
- Un fallo al redactar el aviso aborta la operación de dominio que lo acompaña (misma transacción). Es deliberado: se prefirió coherencia a tolerar un cambio sin su aviso.
- La traducción está fija en español dentro del servicio; no hay catálogo de textos ni preferencia de idioma del socio.
- Antes de producción: decidir la retención y la política de privacidad de los avisos y el push/correo como transporte. La campana real del panel y el aviso al entrenador **ya se resolvieron en ADR-017**, no con esta deuda.

## Referencias

- `backend/src/app/modules/notifications/models.py` (`MemberNotification`, `NOTIFICATION_KINDS`, `ck_member_notifications_kind`)
- `backend/src/app/modules/notifications/service.py` (`create_notification`, `_ensure_membership_expiring`, los `notify_*`, `list_member_notifications`, `mark_notification_read`, `mark_all_notifications_read`)
- `backend/src/app/modules/routines/service.py` (`review_workout`, `_apply_goal_updates`, `cancel_member_goal`, `update_member_goal(..., actor_id=...)`)
- `backend/src/app/modules/classes/service.py` (`_promote_next_waitlist`)
- `backend/src/app/main.py` (`MemberNotificationResponse`, `member_notifications`, `member_notification_unread_count`, `member_notification_read`, `member_notifications_read_all`)
- `backend/alembic/versions/20261027_0035_member_notifications.py`
- `backend/tests/test_member_notifications_api.py`
- `mobile/src/screens/NotificationsScreen.tsx`, `mobile/src/screens/HomeScreen.tsx` (insignia), `mobile/src/api.ts`
- ADR-010 (reservas de clases), ADR-015 (metas desde la app) y ADR-009 (autenticación del socio)
- ADR-017 (bandeja de avisos del personal), que corrige la premisa sobre el mapeo empleado → `app_users`

## Corrección posterior

- 2026-10-27 (ADR-017): la afirmación de que no existía un mapeo limpio empleado → `app_users` era falsa. La columna `AppUser.employee_id` vive en el módulo de identidad desde el RBAC (ADR-008) —única, FK `RESTRICT` a `employees.id`— y la escriben `POST /admin/users` y el alta de colaborador. Lo que faltaba no era el vínculo sino un consumidor que lo usara para resolver la audiencia de un aviso.
