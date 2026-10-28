# Módulo transversal: avisos y notificaciones (socio y personal)

## 1. Resumen y alcance

Este módulo concentra **los avisos que el gimnasio genera sobre alguien** cuando algo relevante pasa en otro módulo. Sobre el socio: una revisión, un cambio en sus metas, un cupo que se libera, una membresía que está por vencer, el equipo que su rutina necesita y acaba de quedar fuera de servicio, o el estado de la factura que pidió. Sobre el personal: un entrenamiento que le quedó pendiente de revisar o un ticket de mantenimiento asignado. Vive en `backend/src/app/modules/notifications` y se materializa en dos bandejas distintas: la **app del socio** y la **campana del panel web**.

No es un servicio de mensajería ni un canal de salida: hoy **no envía correo ni push**. Guarda el aviso y espera a que el destinatario abra su bandeja.

### Incluye
- tabla `member_notifications` (socio) y tabla `staff_notifications` (cuenta del panel), ambas con tipo, título, cuerpo, referencia opcional, clave de deduplicación y fecha de lectura
- emisión de avisos desde los eventos del dominio (rutinas, clases, mantenimiento y facturación) y un aviso diferido por vencimiento de membresía
- búsqueda de audiencia en otro módulo cuando el evento no la trae en la mano (los socios cuyo plan usa un equipo descompuesto)
- resolución de audiencia del personal a partir del vínculo `AppUser.employee_id`
- bandeja paginada con contador de no leídos y marcado individual o masivo desde la app y desde el panel
- insignia de avisos sin leer en la pantalla de inicio de la app y en la campana del panel

### No incluye
- notificación push, correo o SMS como canal de entrega
- mensajería libre entrenador-socio ni respuestas del socio a un aviso
- programación de envíos (jobs, Celery, cron)
- flujo de trabajo sobre el aviso: marcarlo leído no cierra ni resuelve lo que anuncia

## 2. Actores y permisos

| Actor | Objetivo | Autorización |
|---|---|---|
| Socio | ver y marcar como leídos **sus propios avisos** | sesión de la app (`get_current_member`); no usa la matriz RBAC |
| Cuenta del panel (entrenador, técnico) | ver y marcar como leídos **sus propios avisos** | sesión del panel (`get_current_principal`), acotada a su `user_id`; no usa la matriz RBAC |
| Entrenador / recepción / gerente | provocar avisos sin saberlo: revisan un entrenamiento, editan o cancelan una meta | sus permisos de siempre (`routines.manage`) |
| Instructor / recepción | provocar el aviso de lista de espera al confirmar una reserva | `classes.manage` |
| Gerente / técnico / dueño | provocar el aviso de ticket asignado al asignar un `assigned_to` | `maintenance.manage` |
| Mantenimiento / recepción | provocar el aviso de equipo al marcar `out_of_service` o al abrir o escalar un ticket `critical` | `maintenance.report`, el mismo que ya usa el alta de ticket y el cambio de estado |

**No se agregó ningún permiso nuevo.** Las ocho rutas son de auto-servicio y derivan el destinatario de la sesión (`member_id` o `user_id`); un token de personal recibe `401` en `/member/notifications*` y uno de socio recibe `401` en `/admin/notifications*`. Nadie lee ni marca la bandeja de otro: un aviso ajeno responde `404`, igual que uno inexistente.

## 3. Tipos de aviso

### Bandeja del socio (`member_notifications`)

| `kind` | Quién lo provoca | Texto que ve el socio |
|---|---|---|
| `workout_reviewed` | el entrenador marca un entrenamiento como revisado | «Entrenamiento revisado» + rutina y fecha |
| `goal_achieved` | una medición alcanza el objetivo de una meta | «¡Alcanzaste tu meta!» + valor actual y objetivo |
| `goal_updated_by_staff` | el personal cambia el objetivo o la fecha de una meta | «El personal ajustó tu meta» + nuevo objetivo |
| `goal_cancelled_by_staff` | el personal cancela una meta | «El personal canceló tu meta» + medida |
| `class_waitlist_promoted` | se libera un cupo y su reserva en espera queda confirmada | «Tienes lugar en la clase» + clase, día y hora |
| `membership_expiring` | la membresía activa entra en la ventana de 7, 3 o 1 días | «Tu membresía está por vencer» + fecha y días restantes |
| `equipment_out_of_service` | el personal marca un equipo como `out_of_service`, o un ticket `critical` lo saca de servicio | «Un equipo está fuera de servicio» + nombre y lugar del equipo y fecha del día del club |
| `invoice_stamped` | el personal timbra la factura del socio | «Factura timbrada» + folio, importe y, si es simulada, aviso de que no tiene validez fiscal |
| `invoice_failed` | el PAC rechaza el timbrado, o una nota de crédito no se puede timbrar | «No pudimos timbrar tu factura» + folio, importe e invitación a revisar los datos fiscales en Facturas o acudir a recepción |
| `invoice_cancelled` | el personal cancela una factura timbrada | «Factura cancelada» + folio e importe |

### Bandeja del personal (`staff_notifications`)

| `kind` | Quién lo provoca | Destinatario | Texto que ve el destinatario |
|---|---|---|---|
| `workout_pending_review` | el socio registra un entrenamiento desde la app (`origin = "app"`) | la cuenta vinculada al entrenador de la asignación (`RoutineAssignment.trainer_id`) | «Entrenamiento pendiente de revisión» + socio, rutina y fecha |
| `maintenance_ticket_assigned` | recepción asigna un ticket (`create_ticket` o `update_ticket` con `assigned_to`) | la cuenta vinculada al técnico (`MaintenanceTicket.assigned_to`) | «Se te asignó un ticket» + folio, equipo y título |

El `kind` es una cadena con `CHECK` en la base (`ck_member_notifications_kind` y `ck_staff_notifications_kind`), igual que los estados de otros módulos: agregar un tipo nuevo exige migración y etiqueta en la app o el panel.

## 4. Cómo se producen los avisos

- **En la misma transacción que el evento.** No hay cola ni worker: el servicio de rutinas, de clases o de mantenimiento llama al emisor (`notify_*`) antes de su `commit()`. Un aviso no puede existir sin el cambio que anuncia, y si la redacción falla, el cambio revierte.
- **La audiencia del personal se resuelve por el vínculo de identidad.** `staff_user_for_employee(session, employee_id)` devuelve la cuenta **activa** cuya `AppUser.employee_id` coincide, o `None`. Los módulos solo pasan el `employee_id` que ya tienen en su modelo; nunca consultan `app_users`. **Si el empleado no tiene cuenta, o la tiene desactivada, el aviso se omite en silencio**: la operación de dominio (el entrenamiento, la asignación del ticket) se completa igual.
- **La única audiencia que hay que buscar es la del equipo caído.** Cuando un socio pierde la máquina de su plan, nadie tiene esa lista en la mano: `maintenance._members_using_equipment` une `routine_assignments` → `routine_items` **por la versión congelada de la asignación** → `exercises.equipment_id` y pasa los `member_id` ya resueltos a `notify_equipment_out_of_service`. El módulo de avisos sigue sin conocer tablas de rutinas; el import perezoso de `routines.models` vive en mantenimiento, donde `_linked_exercises` ya lo usaba. Si nadie usa ese equipo, no se consulta ni se escribe nada.
- **El texto es un congelado del momento.** El cuerpo se arma con los datos disponibles al producirse el evento (nombre de la rutina, valor y objetivo de la meta, título y hora de la clase, folio y equipo del ticket). `ref_id` guarda el identificador de origen **sin FK**, solo como pista de navegación; borrar o editar el origen no deja un aviso roto.
- **Facturación avisa los estados que el socio no provoca.** `billing._notify_invoice_status` se llama antes del `commit()` del timbrado y de la cancelación y escribe `invoice_stamped`, `invoice_failed` o `invoice_cancelled` solo si `invoice.member_id` existe; la factura global y las ventas de público en general no tienen destinatario. La solicitud (`requested`) no avisa porque la acaba de hacer el socio. El `dedupe_key` es `invoice_<estado>:<invoice_id>`, así que un fallo y una recuperación dejan dos avisos, mientras repetir el mismo estado no duplica. El `ref_id` apunta a la factura y la app abre Facturas al tocar el aviso.
- **Los datos libres se recortan, no invalidan.** Los emisores del personal pasan nombre de socio, de rutina, de equipo y el título del ticket por `_clip(valor, límite)`, porque cualquiera de esos campos lo edita el usuario y un texto largo habría roto el `CHECK` de 500 caracteres y abortado la operación.
- **El vencimiento se calcula al leer.** `_ensure_membership_expiring` revisa, solo cuando el socio consulta su bandeja, la membresía `active` que termina primero: si faltan ≤ 7, ≤ 3 o ≤ 1 días crea el aviso con `dedupe_key = membership_expiring:<membership_id>:<7|3|1>`. La fórmula elige **una sola ventana** por lectura, así que no se repite un aviso por día.
- **La deduplicación la impone la base de datos.** Un índice único parcial sobre `dedupe_key` (donde no es nulo) garantiza que no haya dos avisos iguales aunque dos peticiones concurrentes intenten crearlos. `_append` primero `flush()` los cambios pendientes del llamante y **después** abre el savepoint, de modo que una colisión repite solo la fila del aviso y deja intacta la inserción del ticket; si pierde la carrera, devuelve la fila existente. Hoy la usan tres productores: `membership_expiring:<membership_id>:<7|3|1>`, `maintenance_ticket_assigned:<ticket_id>:<employee_id>` y `equipment_out_of_service:<equipo>:<socio>:<YYYYMMDD>`; los avisos de un solo hecho (revisión, meta cumplida) dejan la clave nula y nunca se comparan entre sí.
- **La ventana del aviso de equipo es el día del club.** `occurred_on` sale de `club_date(occurred)`, no de la fecha UTC, así que rebotar la máquina (`operational` → `out_of_service`) dentro del mismo día del club no repite el mensaje, mientras que una caída en un día posterior vuelve a avisar a los mismos socios.
- **Nadie se avisa a sí mismo.** La cancelación de una meta desde la app no pasa `actor_id`, así que no genera aviso; el aviso de meta ajustada o cancelada solo se emite cuando lo hizo el personal. Del mismo modo, un entrenamiento **capturado por el personal** no genera `workout_pending_review`: quien lo registró ya lo está viendo.

## 5. API del socio

- `GET /member/notifications?page=1&page_size=20` (Bearer) — bandeja del más reciente al más antiguo, con `total`, `pages`, `unread_total` y por aviso su `kind`, `title`, `body`, `ref_id`, `created_at` y `read_at`. Tamaño de página entre 1 y 50.
- `GET /member/notifications/unread-count` — `{"unread": n}` para la insignia.
- `POST /member/notifications/{notification_id}/read` — marca uno como leído; es **idempotente** (repetirlo no cambia `read_at` ni el conteo). Un aviso inexistente o de otro socio responde `404`.
- `POST /member/notifications/read-all` — marca todos los pendientes en un solo `UPDATE` y devuelve `{"updated": n}` (`0` si ya estaba todo leído).

No hay creación, edición ni borrado de avisos por API: el socio solo puede leerlos y marcarlos como leídos.

## 6. API del personal

Son el espejo exacto de las del socio, pero la audiencia sale de la sesión del panel (`principal.user_id`) y se sirven bajo `/admin/*` **sin permiso RBAC**:

- `GET /admin/notifications?page=1&page_size=20` — bandeja del más reciente al más antiguo, con `total`, `pages`, `unread_total` y por aviso su `kind`, `title`, `body`, `ref_id`, `created_at` y `read_at`. Tamaño de página entre 1 y 50.
- `GET /admin/notifications/unread-count` — `{"unread": n}` para la insignia de la campana.
- `POST /admin/notifications/{notification_id}/read` — **idempotente**; un aviso inexistente o de otra cuenta responde `404`.
- `POST /admin/notifications/read-all` — un solo `UPDATE` sobre los pendientes de esa cuenta, devuelve `{"updated": n}`.

El panel las consume a través del BFF (`web/src/app/api/admin/notifications/**`), que reenvía la cookie `gym_session` al backend; ninguna llamada del navegador va directa a `GYM_API_URL`.

## 7. App del socio

- La pantalla de inicio muestra la tarjeta **«Avisos del gimnasio»** con una insignia con el número de no leídos (tope visible `99+`) entre la tarjeta de acceso y la de clases.
- `NotificationsScreen` lista los avisos con etiqueta de tipo, fecha y hora; los no leídos se distinguen con un borde y un punto de color, los leídos se atenúan. Tocar un aviso lo marca como leído; si es de factura (`invoice_stamped`, `invoice_failed` o `invoice_cancelled`), además abre la pantalla **Facturas**, donde el socio ve el comprobante y sus enlaces de descarga. El `accessibilityLabel` del aviso lo anuncia como «Abrir facturas: …». «Marcar todas como leídas» aparece solo cuando hay pendientes y confirma cuántos se marcaron.
- Estados: «Tienes N avisos sin leer.», «Estás al día.», aviso tras marcar todas («Marcaste N avisos como leídos.»), vacío («Todavía no hay avisos. Aquí verás lo que el gimnasio registre sobre ti.»), recorte cuando hay más avisos que la página («Mostrando los últimos 30 de 42 avisos.»), errores en español y actualización con deslizamiento. Cualquier `401` cierra la sesión y devuelve al acceso.
- El contador se refresca al restaurar la sesión, al iniciar sesión, al actualizar el perfil y al salir de la bandeja; un fallo al consultarlo se ignora en silencio porque la bandeja muestra el conteo real al abrirla.

## 8. Panel web

La campana del encabezado **deja de ser dato de muestra** y muestra la bandeja real de la cuenta que inició sesión:

- La insignia roja aparece **solo** cuando hay no leídos, y el `aria-label` del botón pasa a «Notificaciones, N sin leer».
- El encabezado del popover alterna «N sin leer» y «Todo leído»; debajo, los avisos con punto de color (coral si no leído, verde si leído), título, cuerpo y fecha/hora en el calendario del gimnasio (`27-oct, 05:01 p.m.`).
- Estados: carga («Cargando avisos…»), error en español con reintento, y vacío («Sin avisos por ahora.»). «Marcar todo leído» se deshabilita cuando no hay pendientes y confirma cuántos se marcaron con el `updated` que devolvió el servidor; tocar un aviso lo marca individual de forma optimista.
- El conteo se consulta al restaurar la sesión y al iniciar sesión; la lista se pide al **abrir** el popover (`page_size=12`), con una sola llamada por apertura. Cualquier `401` cierra la sesión y devuelve al acceso.
- No hay sondeo en segundo plano: un aviso generado mientras la pestaña está abierta aparece al volver a abrir el popover.

## 9. Reglas de integridad

- `member_id` es FK `RESTRICT` con `members`: un socio con avisos no se puede borrar (el borrado de socios sigue siendo lógico). `user_id` es FK `RESTRICT` con `app_users`: una cuenta con avisos no se puede eliminar del directorio de acceso.
- `title` entre 1 y 140 caracteres y `body` entre 1 y 500, validados en el servicio y en la base; `dedupe_key` hasta 120.
- Índices por bandeja: `(owner, created_at)` para la lista, `(owner, read_at)` para el conteo de no leídos y el único parcial `dedupe_key`, donde `owner` es `member_id` o `user_id` según la tabla.
- `read_at` es la única columna que cambia después del alta: **un aviso nunca se edita ni se borra**, ambas bandejas son historiales.
- Las dos tablas comparten los mismos límites y la misma política de texto congelado; lo único que cambia es el sujeto de la audiencia.

## 10. Límites conocidos

- Sin programador, el aviso de vencimiento **no llega si el socio no abre la app**; y solo se genera para la membresía activa que termina primero.
- No hay retención: ambas bandejas crecen indefinidamente por destinatario.
- Los cuerpos están fijados en español dentro del servicio; no hay catálogo de textos ni preferencia de idioma.
- El aviso se escribe en la transacción del evento: un error al redactarlo aborta la operación de dominio.
- **Aviso omitido ≠ aviso perdido**: si el entrenador de una asignación o el técnico de un ticket no tiene cuenta activa en `app_users`, el aviso no se crea y no hay ninguna señal de ello. Verificar que todo entrenador y todo técnico tenga cuenta sigue siendo un procedimiento manual.
- `workout_pending_review` **no se cierra al revisar el entrenamiento**: la bandeja no es un flujo de trabajo, marcarla leído no resuelve el pendiente. El estado real sigue viéndose en la pestaña de Rutinas.
- La deduplicación del ticket es por `(ticket, técnico)`, así que reasignar A → B → **A** no vuelve a avisar a A: su aviso original ya existe y puede pasar desapercibido.
- El pendiente de revisión depende de `RoutineAssignment.trainer_id`: una asignación sin entrenador no produce aviso.
- El aviso de equipo **no avisa del regreso**: cuando la máquina vuelve a `operational` no se escribe nada, así que la bandeja puede mostrar «fuera de servicio» de hace dos días sobre un equipo que ya funciona. Tampoco lleva fecha estimada de regreso porque el módulo no la garantiza (`tickets.scheduled_for` es opcional).
- **Un socio con la membresía suspendida recibe su aviso de equipo igual que cualquier otro.** No se filtra por estado de la membresía: la bandeja no molesta a nadie, y quien reactiva y abre la app ve lo que pasó mientras no venía.
- La audiencia del aviso de equipo **no tiene tope**: un equipo usado por muchos socios escribe una fila por socio dentro de la misma petición que cambia el estado. Sin programador ni trabajo diferido, el costo es lineal al uso real del equipo.
- El aviso de equipo **no enlaza con nada**: `ref_id` apunta al equipo pero la app no tiene pantalla de equipos, y el detalle de la rutina no renderiza `equipment_status`, así que el socio lee el aviso sin ver marcado el ejercicio afectado.

## 11. Consideraciones de rendimiento

- Ambas bandejas están paginadas (por defecto 20, máximo 50 por página) sobre `_paginate_inbox`, que hace una lectura de la página, un `COUNT` y un conteo de no leídos apoyado en el índice `(owner, read_at)`.
- `read-all` es un único `UPDATE` filtrado por destinatario y `read_at IS NULL`, no un recorrido fila por fila.
- `_ensure_membership_expiring` hace como máximo una lectura de membresías y un insert por consulta de bandeja; el `dedupe_key` evita reescribir el aviso en cada apertura.
- `staff_user_for_employee` es una lectura de `app_users` por aviso emitido, dentro de la transacción del evento.
- `_members_using_equipment` es una sola lectura con `DISTINCT` apoyada en `ix_exercises_equipment` y en el índice propio de `routine_items`, y **solo corre cuando hay transición real** a `out_of_service`; si devuelve vacío no se escribe ninguna fila. El insert del aviso pasa por `_append`, que agrega un `flush()` y, con `dedupe_key`, un savepoint por destinatario.

## 12. Estado de implementación

Implementado y probado (2026-10-27) en **ambas direcciones**: para el socio, la tabla `member_notifications` (`20261027_0035_member_notifications.py`) con seis tipos, cuatro rutas y bandeja con insignia en la app Expo (ADR-016); para el personal, la tabla `staff_notifications` (`20261027_0036_staff_notifications.py`) con dos tipos, resolución de audiencia por `AppUser.employee_id`, cuatro rutas `/admin/notifications*` y campana real en el panel (ADR-017). El mismo 2026-10-27 se añadió el séptimo tipo del socio, `equipment_out_of_service`, con su CHECK ensanchado por `20261027_0037_equipment_out_of_service_notice.py`, la audiencia buscada desde mantenimiento y la etiqueta «Equipo» en la app (ADR-018). El 2026-10-28 se sumaron los tres tipos de estado de factura (`invoice_stamped`, `invoice_failed`, `invoice_cancelled`) con la migración `20261028_0039_invoice_status_notifications.py`, emisión desde el servicio de facturación y navegación directa a Facturas (ADR-021). En diseño/validación funcional: push y correo como canal, retención de avisos, cerrar el pendiente cuando el entrenador revisa, avisar cuando un destinatario no tiene cuenta, anunciar el regreso del equipo y un programador que genere el recordatorio de vencimiento sin depender de abrir la app.

## 13. Bitácora

- 2026-10-27: primer incremento. Módulo `app.modules.notifications` con `member_notifications`, emisores desde `review_workout`, `_apply_goal_updates`, `cancel_member_goal`, `update_member_goal` (que estrena `actor_id`) y `_promote_next_waitlist`, aviso diferido de vencimiento con `dedupe_key` e índice único parcial, rutas `/member/notifications*` sin permisos nuevos, `NotificationsScreen` y tarjeta «Avisos del gimnasio» con insignia en la app. Documentado en ADR-016.
- 2026-10-27: segundo incremento, bandeja del personal. Tabla `staff_notifications`, `staff_user_for_employee` sobre el vínculo `AppUser.employee_id` (que desmonta la premisa de ADR-016), emisores `notify_trainer_pending_workout` desde `log_workout` con `origin = "app"` y `notify_technician_ticket_assigned` desde `create_ticket`/`update_ticket`, `_append` con `flush()` previo al savepoint, `_clip` en los textos, rutas `/admin/notifications*` y campana del panel conectada a datos reales en lugar de muestras. Documentado en ADR-017.
- 2026-10-27: tercer incremento, el socio se entera de que su máquina se descompuso. `equipment_out_of_service` en el `CHECK` de `member_notifications` (migración 0037 y reconstrucción en la vista previa), `notify_equipment_out_of_service` con una fila por socio deduplicada por `(equipo, socio, día del club)`, `maintenance._members_using_equipment` que casa la **versión congelada** de la asignación con `exercises.equipment_id`, emisión desde `set_equipment_status` y desde `_block_equipment` (alta y escalada de un ticket `critical`), etiqueta «Equipo» en la app y dos pruebas nuevas (`test_equipment_out_of_service_notice.py`, 164 en total). Documentado en ADR-018; el kiosco y el cartel de recepción del pendiente original siguen abiertos.
- 2026-10-28: cuarto incremento, el socio sabe qué pasó con su factura. Los tipos `invoice_stamped`, `invoice_failed` e `invoice_cancelled` ensanchan el `CHECK` por la migración `20261028_0039_invoice_status_notifications.py` (y la reconstrucción encadenada en `preview_patch.py`), `notify_invoice_stamped`/`notify_invoice_failed`/`notify_invoice_cancelled` redactan el texto con folio e importe y deduplican por `(factura, estado)`, y `billing._notify_invoice_status` los emite **dentro de la misma transacción** que cambia la factura: timbrado con aviso de simulación, rechazo del PAC, nota de crédito relacionada sin timbrar, saldo a favor excedido y cancelación. La app etiqueta los tres como «Factura» y tocar el aviso lo marca leído y abre la pantalla de Facturas. Dos pruebas nuevas (`test_invoice_notifications.py`, 170 en total) y verificación en navegador con `A-000003`. Documentado en ADR-021; el envío de la factura por correo y el motivo de cancelación siguen fuera de alcance.
