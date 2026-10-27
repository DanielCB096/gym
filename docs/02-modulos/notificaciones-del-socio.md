# Módulo transversal: avisos y notificaciones del socio

## 1. Resumen y alcance

Este módulo concentra **los avisos que el gimnasio genera sobre un socio** cuando algo relevante pasa en otro módulo: una revisión, un cambio en sus metas, un cupo que se libera o una membresía que está por vencer. Vive en `backend/src/app/modules/notifications` y se materializa en la **bandeja de entrada de la app del socio**.

No es un servicio de mensajería ni un canal de salida: hoy **no envía correo ni push**. Guarda el aviso y espera a que el socio abra la app.

### Incluye
- tabla `member_notifications` con tipo, título, cuerpo, referencia opcional, clave de deduplicación y fecha de lectura
- emisión de avisos desde los eventos del dominio (rutinas, clases) y un aviso diferido por vencimiento de membresía
- bandeja paginada con contador de no leídos y marcado individual o masivo desde la app
- insignia de avisos sin leer en la pantalla de inicio

### No incluye
- notificación push, correo o SMS como canal de entrega
- campana de notificaciones del panel web (sigue mostrando datos de muestra)
- avisos al entrenador (por ejemplo, un entrenamiento pendiente de revisión)
- mensajería libre entrenador-socio ni respuestas del socio a un aviso
- programación de envíos (jobs, Celery, cron)

## 2. Actores y permisos

| Actor | Objetivo | Autorización |
|---|---|---|
| Socio | ver y marcar como leídos **sus propios avisos** | sesión de la app (`get_current_member`); no usa la matriz RBAC |
| Entrenador / recepción / gerente | provocar avisos sin saberlo: revisan un entrenamiento, editan o cancelan una meta | sus permisos de siempre (`routines.manage`) |
| Instructor / recepción | provocar el aviso de lista de espera al confirmar una reserva | `classes.manage` |

**No se agregó ningún permiso nuevo.** Las cuatro rutas son de auto-servicio y derivan el `member_id` de la sesión; un token de personal recibe `401` en `/member/notifications*` y uno de socio recibe `401` en `/admin/*`.

## 3. Tipos de aviso

| `kind` | Quién lo provoca | Texto que ve el socio |
|---|---|---|
| `workout_reviewed` | el entrenador marca un entrenamiento como revisado | «Entrenamiento revisado» + rutina y fecha |
| `goal_achieved` | una medición alcanza el objetivo de una meta | «¡Alcanzaste tu meta!» + valor actual y objetivo |
| `goal_updated_by_staff` | el personal cambia el objetivo o la fecha de una meta | «El personal ajustó tu meta» + nuevo objetivo |
| `goal_cancelled_by_staff` | el personal cancela una meta | «El personal canceló tu meta» + medida |
| `class_waitlist_promoted` | se libera un cupo y su reserva en espera queda confirmada | «Tienes lugar en la clase» + clase, día y hora |
| `membership_expiring` | la membresía activa entra en la ventana de 7, 3 o 1 días | «Tu membresía está por vencer» + fecha y días restantes |

El `kind` es una cadena con `CHECK` en la base (`ck_member_notifications_kind`), igual que los estados de otros módulos: agregar un tipo nuevo exige migración y etiqueta en la app.

## 4. Cómo se producen los avisos

- **En la misma transacción que el evento.** No hay cola ni worker: el servicio de rutinas o de clases llama al emisor (`notify_*`) antes de su `commit()`. Un aviso no puede existir sin el cambio que anuncia, y si la redacción falla, el cambio revierte.
- **El texto es un congelado del momento.** El cuerpo se arma con los datos disponibles al producirse el evento (nombre de la rutina, valor y objetivo de la meta, título y hora de la clase). `ref_id` guarda el identificador de origen **sin FK**, solo como pista de navegación; borrar o editar el origen no deja un aviso roto.
- **El vencimiento se calcula al leer.** `_ensure_membership_expiring` revisa, solo cuando el socio consulta su bandeja, la membresía `active` que termina primero: si faltan ≤ 7, ≤ 3 o ≤ 1 días crea el aviso con `dedupe_key = membership_expiring:<membership_id>:<7|3|1>`. La fórmula elige **una sola ventana** por lectura, así que no se repite un aviso por día.
- **La deduplicación la impone la base de datos.** Un índice único parcial sobre `dedupe_key` (donde no es nulo) garantiza que no haya dos avisos iguales aunque dos peticiones concurrentes intenten crearlos. `create_notification` escribe dentro de un savepoint y, si pierde la carrera, devuelve la fila existente.
- **Nadie se avisa a sí mismo.** La cancelación de una meta desde la app no pasa `actor_id`, así que no genera aviso; el aviso de meta ajustada o cancelada solo se emite cuando lo hizo el personal.

## 5. API del socio

- `GET /member/notifications?page=1&page_size=20` (Bearer) — bandeja del más reciente al más antiguo, con `total`, `pages`, `unread_total` y por aviso su `kind`, `title`, `body`, `ref_id`, `created_at` y `read_at`. Tamaño de página entre 1 y 50.
- `GET /member/notifications/unread-count` — `{"unread": n}` para la insignia.
- `POST /member/notifications/{notification_id}/read` — marca uno como leído; es **idempotente** (repetirlo no cambia `read_at` ni el conteo). Un aviso inexistente o de otro socio responde `404`.
- `POST /member/notifications/read-all` — marca todos los pendientes en un solo `UPDATE` y devuelve `{"updated": n}` (`0` si ya estaba todo leído).

No hay creación, edición ni borrado de avisos por API: el socio solo puede leerlos y marcarlos como leídos.

## 6. App del socio

- La pantalla de inicio muestra la tarjeta **«Avisos del gimnasio»** con una insignia con el número de no leídos (tope visible `99+`) entre la tarjeta de acceso y la de clases.
- `NotificationsScreen` lista los avisos con etiqueta de tipo, fecha y hora; los no leídos se distinguen con un borde y un punto de color, los leídos se atenúan. Tocar un aviso lo marca como leído; «Marcar todas como leídas» aparece solo cuando hay pendientes y confirma cuántos se marcaron.
- Estados: «Tienes N avisos sin leer.», «Estás al día.», aviso tras marcar todas («Marcaste N avisos como leídos.»), vacío («Todavía no hay avisos. Aquí verás lo que el gimnasio registre sobre ti.»), recorte cuando hay más avisos que la página («Mostrando los últimos 30 de 42 avisos.»), errores en español y actualización con deslizamiento. Cualquier `401` cierra la sesión y devuelve al acceso.
- El contador se refresca al restaurar la sesión, al iniciar sesión, al actualizar el perfil y al salir de la bandeja; un fallo al consultarlo se ignora en silencio porque la bandeja muestra el conteo real al abrirla.

## 7. Reglas de integridad

- `member_id` es FK `RESTRICT` con `members`: un socio con avisos no se puede borrar (el borrado de socios sigue siendo lógico).
- `title` entre 1 y 140 caracteres y `body` entre 1 y 500, validados en el servicio y en la base; `dedupe_key` hasta 120.
- Índices: `(member_id, created_at)` para la bandeja, `(member_id, read_at)` para el conteo de no leídos y el único parcial `dedupe_key`.
- `read_at` es la única columna que cambia después del alta: **un aviso nunca se edita ni se borra**, la bandeja es un historial.

## 8. Límites conocidos

- Sin programador, el aviso de vencimiento **no llega si el socio no abre la app**; y solo se genera para la membresía activa que termina primero.
- No hay retención: la bandeja crece indefinidamente por socio.
- Los cuerpos están fijados en español dentro del servicio; no hay catálogo de textos ni preferencia de idioma.
- El aviso se escribe en la transacción del evento: un error al redactarlo aborta la operación de dominio.
- El panel no tiene bandeja real y el entrenador no recibe avisos (bloqueado por la misma falta de traza empleado → `app_users` que arrastran `logged_by`/`created_by`).

## 9. Consideraciones de rendimiento

- La bandeja está paginada (por defecto 20, máximo 50 por página); el conteo de no leídos es una consulta agregada por socio apoyada en el índice `(member_id, read_at)`.
- `read-all` es un único `UPDATE` filtrado por socio y `read_at IS NULL`, no un recorrido fila por fila.
- `_ensure_membership_expiring` hace como máximo una lectura de membresías y un insert por consulta de bandeja; el `dedupe_key` evita reescribir el aviso en cada apertura.

## 10. Estado de implementación

Implementado y probado (2026-10-27) para el socio: tabla `member_notifications` (`20261027_0035_member_notifications.py`), seis tipos de aviso, cuatro rutas de auto-servicio y bandeja con insignia en la app Expo. En diseño/validación funcional: push y correo como canal, campana real del panel, avisos al entrenador, retención de avisos y un programador que genere el recordatorio de vencimiento sin depender de abrir la app.

## 11. Bitácora

- 2026-10-27: primer incremento. Módulo `app.modules.notifications` con `member_notifications`, emisores desde `review_workout`, `_apply_goal_updates`, `cancel_member_goal`, `update_member_goal` (que estrena `actor_id`) y `_promote_next_waitlist`, aviso diferido de vencimiento con `dedupe_key` e índice único parcial, rutas `/member/notifications*` sin permisos nuevos, `NotificationsScreen` y tarjeta «Avisos del gimnasio» con insignia en la app. Documentado en ADR-016.
