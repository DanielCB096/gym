# ADR-010: Reservas de clases desde la app del socio

- Fecha: 2026-10-27
- Estado: propuesta inicial

## Contexto

El módulo de clases ya resuelve el aforo, el bloqueo por fila, la lista de espera y la ventana de cancelación para recepción y panel. El socio ahora tiene sesión propia (ADR-009) y necesita apartar su lugar sin pasar por recepción, pero no debe poder usar la app para saltarse las reglas del club ni para tocar reservas ajenas.

## Decisión

- La app **reutiliza el módulo de clases** existente. No hay tablas nuevas ni migración: las reservas del socio viven en `class_reservations` con `origin = "app"`.
- `backend/src/app/modules/portal/classes.py` es una capa delgada y con alcance de socio sobre los servicios de clases. Las reglas de negocio (aforo, bloqueo, promoción de lista de espera, ventana de cancelación) siguen en `app.modules.classes`; la capa de portal solo decide **qué puede hacer un socio en su propio nombre**.
- Se exige **membresía activa** (socio activo y periodo vigente) tanto para listar como para reservar. Sin membresía la cartelera se muestra en modo consulta con `blocked_reason = membership_inactive`.
- Las **clases premium no se pueden reservar desde la app** mientras no exista el cobro del extra: aparecen con `blocked_reason = premium_class` y el intento de reserva responde `409`.
- No se puede reservar una clase **ya iniciada** ni duplicar una reserva activa. Ambos casos responden `409`.
- La cartelera (`GET /member/classes`) devuelve solo sesiones futuras programadas, con paginación (`days` 1–60, `page`, `page_size` hasta 50) y, por sesión, el cupo, la lista de espera y la reserva propia si existe.
- Cada sesión incluye `can_reserve` y `blocked_reason` (`already_reserved`, `membership_inactive`, `premium_class`, `started`, `full`) para que la app no tenga que replicar reglas.
- **Aislamiento**: una reserva ajena responde `404` igual que una inexistente. Los tokens de personal reciben `401` en `/member/classes*` y los de socio en `/admin/*`.
- La cancelación solo se permite **antes del inicio** de la clase. Se delega en `cancel_reservation` sin `actor_id`, porque `cancelled_by` es una FK a `app_users` (personal); el rastro del socio queda en `origin = "app"` y en la sesión autenticada.
- Cancelar antes de la ventana configurada (4 h por defecto) marca `late_cancellation` con la misma lógica que recepción y **promueve al primero de la lista de espera**.

## Consecuencias y límites

- El socio puede apartar y soltar su lugar, pero **no paga** una clase premium desde la app; hoy el aviso lo manda a recepción.
- No hay notificaciones (correo o push) de confirmación, promoción desde lista de espera ni recordatorio de clase, ni límite de reservas simultáneas por socio.
- La app pide la primera página (25 sesiones / 14 días) sin desplazamiento infinito; un socio con agenda muy amplia verá solo ese tramo.
- `cancelled_by` queda vacío en las cancelaciones hechas por el socio, así que los reportes del panel no pueden distinguir «canceló el socio» de «canceló el sistema» salvo por `origin`. Si se necesita esa traza habrá que agregar una columna o una tabla de auditoría de reservas.
- No hay lista de espera con vencimiento automático ni cobro de penalización por cancelación tardía: solo se registra la marca.
- Antes de producción: decidir el cobro del extra premium, política de reservas simultáneas y sanciones por inasistencia, notificaciones y una traza explícita del actor en la cancelación.

## Referencias

- `backend/src/app/modules/portal/classes.py`
- `backend/src/app/modules/classes/service.py`
- `backend/src/app/main.py` (`/member/classes*`)
- `backend/tests/test_member_classes_api.py`
- `mobile/src/screens/ClassesScreen.tsx`
- `docs/02-modulos/clases-y-reservaciones.md`
- ADR-009 (autenticación del socio)
