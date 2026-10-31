# ADR-072: El fisioterapeuta se bloquea al agendar

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Cierra el límite (5) de la ficha de Fisioterapia (ADR-039) y complementa ADR-069

## Contexto

El traslape del fisioterapeuta se comprueba por intervalos completos: `_assert_slot_free` compara inicio y fin, así que una cita que se encima parcialmente ya se rechaza en el camino normal, y el índice único parcial `uq_physio_appointments_therapist_start` protege el inicio idéntico. La comprobación, sin embargo, no era atómica: dos recepcionistas que agendaban a la vez horas parcialmente encimadas para el mismo especialista —sin consultorio del catálogo— leían la agenda libre antes de que la otra confirmara y ambas insertaban, porque el índice único no ve intervalos.

Con consultorio del catálogo la fila de la sala ya serializaba las dos transacciones (ADR-069), pero el camino sin sala quedaba a merced de las transacciones, como quedó anotado en la deuda técnica.

## Decisión

- **`_assert_slot_free` bloquea la fila del empleado antes de comparar.** Lee `employees` con `SELECT ... FOR UPDATE` y después busca el traslape. En PostgreSQL la segunda transacción espera a que la primera confirme y vuelve a leer la agenda con la cita nueva; en SQLite el bloqueo es no-op, como en el resto de la API.
- **Cubre el alta y el movimiento.** Ambas rutas llaman a la misma comprobación, así que mover una cita a un horario parcialmente ocupado del mismo fisioterapeuta también se serializa.
- **Orden de bloqueo estable.** El empleado se bloquea antes que el consultorio, igual en el alta que en el movimiento, para no introducir ciclos entre citas, empleados y salas.
- **Sin migración ni cambio de contrato.** La garantía vive en `physio.service`; `PhysioSlotConflict` ya se traduce a `409` con el mensaje del fisioterapeuta.

## Consecuencias y límites

- **Serializa solo al mismo fisioterapeuta.** Dos especialistas distintos siguen agendando en paralelo; la agenda no se vuelve un bloqueo global.
- **El bloqueo es breve.** Retiene la fila del empleado durante la transacción de agendamiento; una edición simultánea de Personal sobre ese colaborador puede esperar, y al revés.
- **No sustituye al índice único.** El índice sigue atrapando el inicio idéntico aunque el bloqueo no exista (SQLite o una ruta futura que no pase por la comprobación).
- **No cubre la sala de texto libre.** Sin `room_id` no hay recurso del catálogo que bloquear; la regla de ADR-069 sigue limitada a las salas del catálogo.
- **La vista previa sigue sin reproducir la carrera.** La prueba es opt-in con `TEST_POSTGRES_URL`: dos altas simultáneas a las 10:00 y 10:10 del mismo especialista dejan una sola cita.

## Referencias

- `backend/src/app/modules/physio/service.py` (`_assert_slot_free`)
- `backend/tests/test_physio_therapist_postgres.py`
- `docs/05-decisiones/ADR-039-fisioterapia-cobro-por-asistencia.md`
- `docs/05-decisiones/ADR-069-consultorio-como-recurso-reservable.md`
- `docs/02-modulos/fisioterapia.md`
