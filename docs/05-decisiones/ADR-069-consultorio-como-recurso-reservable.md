# ADR-069: El consultorio como recurso reservable

- Fecha: 2026-10-31
- Estado: propuesta inicial

## Contexto

El módulo de fisioterapia ya tiene catálogo de consultorios (`physio_rooms`) y cada cita puede apuntar a uno por `room_id`, con el consultorio predeterminado del fisioterapeuta cuando se deja vacío (ADR-039 y su incremento 3). Sin embargo, la agenda solo validaba al fisioterapeuta: dos citas con especialistas distintos podían reservar la misma sala a la misma hora, y el panel mostraba dos pacientes en el mismo consultorio. La deuda técnica lo listaba en dos puntos: «el consultorio es catálogo, pero no recurso reservable» y «el traslape solo se atrapa en el inicio exacto».

Al revisar el segundo punto se confirmó que estaba desactualizado: `_assert_slot_free` ya compara intervalos (`starts_at < fin AND ends_at > inicio`), no solo el inicio exacto, así que el traslape parcial del mismo fisioterapeuta se rechaza desde que se creó la agenda. El hueco real era la sala: el consultorio es el segundo recurso físico que se puede encimar, y con dos especialistas atendiendo en paralelo el club puede tener más citas que salas.

## Decisión

- **El consultorio del catálogo es un recurso reservable.** Al crear o mover una cita, el sistema rechaza con `409` («El consultorio ya tiene una cita que se encima con ese horario») si otra cita no cancelada del mismo consultorio se cruza en el intervalo. Aplica a cualquier fisioterapeuta: dos citas del mismo especialista ya se rechazaban por la agenda, y ahora tampoco pueden compartir sala dos especialistas distintos.
- **La validación se aplica al consultorio que se va a guardar, no al anterior.** Al mover, la cita resuelve primero dónde vivirá —la sala actual si no se cambia, la elegida si llega `room_id`, o ninguna si se quita— y valida ese destino antes de escribir. Mover una cita dentro de la misma sala y solo cambiar la hora se compara contra las demás citas, excluyéndose a sí misma (`exclude_id`).
- **Cancelar libera la sala.** La consulta ignora las citas `cancelled`, así que el mismo consultorio se puede volver a agendar en ese horario; `attended` y `no_show` siguen ocupando el intervalo porque representan una sesión que existió en esa sala.
- **La fila del consultorio se bloquea antes de validar.** `_assert_room_free` lee `physio_rooms` con `with_for_update()` y después busca el traslape. En PostgreSQL dos recepcionistas que agendan la misma sala al mismo tiempo se serializan; en SQLite —vista previa y pruebas— el bloqueo es no-op, como en el resto de la API, y la garantía de concurrencia depende del motor. No se agregó un índice único porque un intervalo no se puede expresar como columnas únicas.
- **Las salas de texto libre quedan fuera.** La columna histórica `room` (texto congelado) se conserva para citas viejas y para quien escriba una sala a mano; sin `room_id` no hay recurso del catálogo que validar y el sistema no compara nombres. El panel envía `room_id` cuando se elige un consultorio del catálogo, que es el camino normal.
- **Sin migración ni cambio de API.** La regla vive en el servicio de fisioterapia y reutiliza `PhysioSlotConflict`, que `main.py` ya traduce a `409`. El contrato de `POST`/`PATCH` de citas no cambia.

## Consecuencias y límites

- **No hay capacidad por consultorio.** Una sala admite una sola cita a la vez sin importar el servicio; no se puede declarar una sala con dos camillas ni compartirla entre dos sesiones cortas.
- **No hay horario propio de la sala.** El consultorio está disponible siempre que el club lo esté; no hay ventanas de apertura, bloqueos por limpieza ni días festivos por sala.
- **No hay serialización en SQLite.** La vista previa y las pruebas no reproducen la carrera de dos agendamientos simultáneos sobre la misma sala; igual que el bloqueo de la doble marca y el del cupo de clases, la garantía real es de PostgreSQL y la carrera de la sala se ejerce con la prueba opt-in `tests/test_physio_rooms_postgres.py`.
- **El consultorio no avisa nada.** Mover una cita a otra sala o liberar una no notifica a nadie más que al socio por el aviso de la cita; no hay panel de ocupación de salas ni alerta cuando una sala queda libre.
- **El reporte sigue estimando la ocupación** sobre 8 horas por fisioterapeuta y día (ADR-039), no sobre la sala; esta regla evita el doble uso, no mide utilización física.

## Referencias

- `backend/src/app/modules/physio/service.py` (`_assert_room_free`, `create_physio_appointment`, `move_physio_appointment`, `_assert_slot_free`)
- `backend/src/app/main.py` (`(PhysioSlotConflict, 409)`)
- `backend/tests/test_physio_api.py` (`test_rooms_cannot_double_book_the_same_hour`)
- `backend/tests/test_physio_rooms_postgres.py` (concurrencia opt-in de la sala con `TEST_POSTGRES_URL`)
- `docs/02-modulos/fisioterapia.md`
- `docs/05-decisiones/ADR-039-fisioterapia-cobro-por-asistencia.md`
