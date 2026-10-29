# ADR-018: Aviso al socio cuando un equipo de su rutina queda fuera de servicio

- Fecha: 2026-10-27
- Estado: propuesta inicial

## Contexto

`deuda-tecnica.md` arrastraba, dentro de Mantenimiento, «avisos automáticos a socios/kiosco/app cuando un equipo queda fuera de servicio». El vínculo que lo hace posible existe desde `20261017_0014_exercises_equipment_link.py`: `exercises.equipment_id` (FK a `equipment.id`, `ON DELETE SET NULL`, índice `ix_exercises_equipment`) y su propio comentario dice que está ahí «so a plan can be flagged when the machine it needs is out of service».

Hoy ese flag lo ve **solo el personal**: la vista del plan en el panel pinta «Equipo fuera de servicio» / «Equipo en mantenimiento» (`web/src/app/page.tsx:6966`), y la lectura de rutinas ya entrega `equipment_status` por línea. El socio, en cambio, tiene el dato en su tipo (`mobile/src/types.ts:114`) y **no lo renderiza en ninguna pantalla**: si la máquina de su plan se descompone, la app sigue mostrando el ejercicio como si nada, y enterarse depende de que alguien se lo diga en recepción.

Mientras tanto ADR-016 y ADR-017 dejaron montada la infraestructura que este aviso necesita: bandeja por destinatario, emisión dentro de la transacción del evento, texto congelado, `ref_id` sin FK y deduplicación impuesta por la base. No había que abrir un canal nuevo, solo conectar un evento de mantenimiento a una audiencia de socios.

Se eligió **solo la mitad del socio** del pendiente: el kiosco y el cartel de recepción siguieron esperando en ese incremento, porque requerían pantalla y flujo propios, no una fila más en una bandeja.

_Actualización 2026-10-28: el kiosco de recepción y el cartel de recepción (`kiosk/cartel.html`) ya muestran la flota no disponible con `GET /kiosk/equipment`._

## Decisión

- **Nuevo `kind` en `member_notifications`: `equipment_out_of_service`**, añadido a `NOTIFICATION_KINDS` y al `CHECK ck_member_notifications_kind`. PostgreSQL guarda un `CHECK` como una sola expresión, así que ensanchar la lista exige soltar y volver a crear la restricción con el mismo nombre (`20261027_0037_equipment_out_of_service_notice.py`); la vista previa reconstruye la tabla con la misma pareja de textos en `preview_patch.CHECK_UPGRADES`. El revertido cuenta los avisos del tipo nuevo y **se niega** si existen, en lugar de borrarlos a traición.
- **La audiencia es el plan vigente, no la plantilla.** `_members_using_equipment(session, equipment_id)` devuelve los `member_id` de las asignaciones `active` cuya **versión congelada** (`RoutineAssignment.routine_version`) contiene un ejercicio vinculado al equipo, con `DISTINCT`. Casar la versión es la parte que importa: reescribir la plantilla no decide quién se entera, y una asignación cancelada deja de recibir avisos de la máquina que ya no usa.
- **El emisor vive en `notifications` y recibe la audiencia ya resuelta.** `notify_equipment_out_of_service(..., member_ids=..., occurred_on=...)` solo redacta e inserta; quien sabe encontrar a los socios afectados es `maintenance`, que ya hace la consulta con el import perezoso de `routines.models` documentado en `_linked_exercises`. Así el módulo de avisos sigue sin conocer tablas de rutinas y la dirección de dependencia no se invierte.
- **Se avisa solo en la transición real a `out_of_service`.** Los dos caminos que sacan una máquina de servicio announce, y ninguno más: `set_equipment_status` (que sale antes si el estado no cambia) y `_block_equipment`, invocado tanto al **crear** un ticket `critical` como al **escalar** la severidad de uno abierto a `critical` (y que sale antes si la máquina ya estaba fuera de servicio o retirada). Poner `maintenance`, `inspection` o devolverla a `operational` no genera aviso.
- **Una fila por socio, deduplicada por `(equipo, socio, día del club)`.** `dedupe_key = equipment_out_of_service:<equipo>:<socio>:<YYYYMMDD>` con `occurred_on` calculado con `club_date(occurred)`, no con la fecha UTC: la ventana sigue el calendario del gimnasio. Rebotar la máquina el mismo día (operativa → fuera de servicio otra vez) no repite el mensaje; una caída en un día del club posterior sí vuelve a avisar.
- **El texto nombra la máquina y su lugar, nunca el ticket.** «Un equipo está fuera de servicio» + «El equipo {nombre} de {lugar} quedó fuera de servicio el dd/mm/aaaa. Si tu rutina usa un ejercicio con este equipo, pídele a tu entrenador que lo sustituya.» El nombre y el lugar pasan por `_clip(..., 80)` y `_clip(..., 40)` porque son campos que el personal edita libremente. El cuerpo **no** incluye el título del ticket: puede traer datos internos o de terceros, y el aviso es para el socio.
- **Sin aviso de regreso, sin filtro de membresía, audiencia sin tope.** Tres omisiones deliberadas: `operational` no anuncia (la bandeja es un historial de cosas que pasaron, no un estado), un socio con la membresía suspendida recibe igual su fila (es una bandeja, no un push: nadie está molestando a nadie) y no hay máximo de destinatarios por caída (una máquina muy usada escribe N inserciones en la misma petición).
- **La app solo gana una etiqueta.** `equipment_out_of_service: "Equipo"` en `NOTIFICATION_KIND_LABELS` (`mobile/src/format.ts:95`); la bandeja ya renderizaba título, cuerpo y fecha, y un `kind` desconocido cae en «Aviso», así que el cambio es cosmético y hacia atrás. `ref_id` apunta al equipo **sin deep link**: la app no tiene pantalla de equipos.
- **Actualización 2026-10-28 — el kiosco recibe la misma información como estado vivo, no como bandeja.** `GET /kiosk/equipment` (autenticado con el token del dispositivo) devuelve la flota en `maintenance`/`out_of_service` y la PWA la pinta bajo el teclado con nombre, ubicación y estado. No hay un aviso por equipo ni push: la tablet refresca cada minuto, así que un cambio se ve sin reiniciar. La consulta reutiliza `list_unavailable_equipment` de `maintenance` con import perezoso desde `access.kiosk`, y la app además marca `equipment_status` en el detalle de la rutina. El **cartel de recepción** (`kiosk/cartel.html`) reutiliza el mismo endpoint como pantalla pasiva para una TV, con tarjetas grandes de nombre, ubicación y estado, estado vacío «Todos los equipos están operativos», reloj y fecha, y un token de **dispositivo propio** guardado en `localStorage` (`centrofit.sign.config.v1`) para poder revocarlo sin detener el kiosco. Refresca cada minuto, al recuperar la red y al volver a la pestaña; conserva la última lista si falla, muestra error si nunca pudo consultar y un `401` lo devuelve a configuración. No valida códigos ni escribe en la bitácora.

## Consecuencias y límites

- El socio que pierde una máquina de su plan lo ve en su bandeja sin preguntar en recepción; el panel ya lo venía mostrando, así que personal y socio tienen la misma noticia.
- **Sigue sin haber push ni correo** (ADR-016): el aviso se ve cuando el socio abre la app. Sin programador, una caída a las 6 a.m. puede esperar al anochecer para ser leída.
- **No hay fecha estimada de regreso** porque el módulo no la tiene: `scheduled_for` es opcional y no se garantiza que exista. El mensaje dice qué pasó y qué hacer, no cuándo vuelve.
- Rebotar la máquina **el mismo día del club** queda sin segundo aviso aunque la segunda caída sea real; el día siguiente sí vuelve a avisar. Es el precio de la deduplicación anti-spam.
- Una máquina vinculada a un plan de **muchos** socios produce una inserción por socio dentro de la misma llamada que cambia el estado; con la lista de `DISTINCT` y el índice `ix_exercises_equipment` el costo es lineal y acotado al uso real del equipo, pero no hay tope ni trabajo diferido.
- **El aviso puede tumbar la operación**: se emite dentro de la transacción de `set_equipment_status`, `create_ticket` y `update_ticket`, así que un error al redactarlo revierte el estado del equipo y el ticket. Mitigado con `_clip` y con los límites ya validados en el servicio.
- El aviso **no se cierra cuando el equipo vuelve**: la bandeja no es un flujo de trabajo (misma límite que `workout_pending_review` en ADR-017).
- Un ejercicio vinculado a una máquina que luego se **retira** pierde el vínculo (`ON DELETE SET NULL`), así que el historial de avisos no queda enlazado a un equipo existente: es la política de `ref_id` sin FK de siempre.
- **El cartel de recepción comparte los límites del kiosco** (`deuda-tecnica.md`): sin push (refresco de un minuto), sin fecha de regreso ni equipo alternativo porque el modelo no los expone, y con un token bearer que conviene emitir para un dispositivo aparte (desde ADR-027 caduca a los 90 días y se puede rotar desde el panel). Lo mismo que el bloqueo duro de un ejercicio cuya máquina está fuera de servicio, que sigue siendo un aviso suave.
- Antes de producción: decidir si el regreso se anuncia y si debe existir un tope de audiencia o un job. La app ya renderiza `equipment_status` en el detalle de la rutina (2026-10-28), así que el plan y la bandeja ya no son dos verdades distintas.

## Referencias

- `backend/src/app/modules/notifications/models.py` (`NOTIFICATION_KINDS`, `ck_member_notifications_kind`)
- `backend/src/app/modules/notifications/service.py` (`notify_equipment_out_of_service`, `create_notification`, `_append`, `_clip`)
- `backend/src/app/modules/maintenance/service.py` (`_members_using_equipment`, `_announce_equipment_outage`, `set_equipment_status`, `_block_equipment`)
- `backend/src/app/modules/routines/models.py` (`Exercise.equipment_id`, `RoutineAssignment.routine_version`, `RoutineItem`)
- `backend/alembic/versions/20261027_0037_equipment_out_of_service_notice.py`
- `backend/preview_patch.py` (`CHECK_UPGRADES["member_notifications"]`)
- `backend/tests/test_equipment_out_of_service_notice.py`
- `mobile/src/format.ts` (`NOTIFICATION_KIND_LABELS`)
- ADR-016 (bandeja del socio), ADR-017 (bandeja del personal), ADR-011 (rutinas del socio en lectura)
