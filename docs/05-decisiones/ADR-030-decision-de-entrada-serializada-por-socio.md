# ADR-030: Decisión de entrada serializada por socio

- Fecha: 2026-10-29
- Estado: propuesta inicial

## Contexto

Con ADR-025 (límite diario del plan) y ADR-026 (antipassback del club) el kiosco dejó de decidir solo con la membresía: antes de autorizar cuenta las entradas autorizadas del día del socio y busca su última entrada. Esas dos lecturas y el `INSERT` del evento son pasos separados. Si dos kioscos atienden al mismo socio a la vez —la tablet de recepción y una segunda, o la tablet y un código emitido desde otro teléfono—, ambos pueden leer el mismo conteo viejo y la misma última entrada, y los dos autorizan: el plan con límite de una entrada deja pasar dos, y el antipassback deja de ver el duplicado.

La emisión de códigos tenía el mismo hueco en pequeño: dos peticiones simultáneas de `POST /member/access/code` pasaban el límite de 6 en 10 minutos con el mismo valor y dejaban **dos códigos vivos** para el mismo socio, uno por teléfono.

Hoy el despliegue es de un solo backend, pero los dos kioscos ya son un caso real de recepción y el club puede abrir una segunda entrada. El motor de acceso ya advierte en su documentación que la concurrencia depende del motor de base de datos.

## Decisión

- **Se bloquea la fila del socio antes de decidir.** `check_in_with_code` ejecuta `SELECT members.id ... FOR UPDATE` sobre el socio (`access.kiosk._lock_member_row`) antes de consumir el código y de leer el conteo del día y la última entrada. El bloqueo se sostiene hasta el `commit` que graba el evento dentro de `record_access_event`, así que la segunda transacción espera y, cuando entra, lee un estado que ya incluye la entrada anterior. Vale para dos kioscos y para dos peticiones concurrentes del mismo kiosco.
- **La emisión de códigos usa el mismo bloqueo.** `issue_member_access_code` bloquea al socio antes de contar las emisiones recientes y de invalidar el código anterior. Con eso, dos peticiones simultáneas se serializan: la segunda ve el límite actualizado, invalida el código que la primera acaba de crear y deja un solo código vivo por socio.
- **El código se consume después del bloqueo y con la caducidad en el mismo `UPDATE`.** El `UPDATE ... WHERE consumed_at IS NULL AND expires_at > :now` sigue siendo la garantía de un solo uso aunque el `SELECT` previo quedara viejo mientras se esperaba el bloqueo; si el código venció durante la espera, la fila no se toca y el kiosco responde «Código inválido o vencido.».
- **Orden de bloqueo fijo: socio y luego código.** Todos los caminos toman el bloqueo del socio primero, así que no hay dos transacciones esperándose en cruz.
- **La entrada manual de recepción queda fuera del bloqueo.** `record_manual_access` siempre autoriza (`manual_override`, ADR-025) y solo suma al conteo; bloquearla no cambiaría ninguna decisión y sí añadiría espera en el mostrador.
- **Sin migración ni permisos nuevos.** Es orden de ejecución, no esquema.

## Consecuencias y límites

- **La garantía es de PostgreSQL.** `FOR UPDATE` es efectivo en producción; el dialecto de SQLite lo descarta, y la vista previa y las pruebas corren sobre SQLite. Por eso la prueba cubre el orden de las llamadas y que la sentencia compile con `FOR UPDATE` para PostgreSQL, no una carrera real entre dos conexiones: con SQLite el bloqueo no existe y cualquier prueba de concurrencia sería ficticia. Replicarla de verdad exige PostgreSQL, como ya pasa con devoluciones, cupo de clases y crédito del socio.
- El bloqueo también vale contra la sincronización offline del outbox: cuando un evento offline llega al backend pasa por `record_access_event`, pero no por la decisión del kiosco, así que su orden respecto a un check-in en vivo no está serializado. Un evento offline del pasado cuenta en el día del club y un check-in concurrente podría no verlo todavía.
- El bloqueo se toma por socio; dos socios distintos siguen entrando en paralelo, y el kiosco no bloquea la tabla ni el club.
- Si la transacción que tiene el bloqueo muere sin `commit` (caída del proceso, timeout), PostgreSQL lo libera al cerrar la conexión; no queda el socio bloqueado.
- La validación de aforo se sumó después (ADR-032) y su conteo se lee dentro de la misma transacción bloqueada.

## Nota de actualización (2026-10-29)

La carrera se reprodujo contra PostgreSQL 16.4 portátil y quedó cubierta por `backend/tests/test_kiosk_access_postgres.py`, que corre con `TEST_POSTGRES_URL` sobre una base desechable y se omite en la suite normal. El segundo check-in esperó 1,28 s al bloqueo frente a 21 ms sin contención, y 20 rondas de dos check-ins simultáneos con límite diario 1 dejaron una sola entrada con el bloqueo y dos en las 20 sin él.

## Referencias

- `backend/src/app/modules/access/kiosk.py` (`_member_lock_statement`, `_lock_member_row`, `check_in_with_code`, `issue_member_access_code`)
- `backend/src/app/modules/access/service.py` (`record_access_event`, `count_member_entries_today`, `last_member_entry_at`)
- `backend/tests/test_kiosk_access_api.py` (`test_member_row_lock_precedes_the_limits_read`, `test_member_row_lock_is_for_update_on_postgresql`)
- `docs/05-decisiones/ADR-025-limite-diario-de-entradas-por-plan.md`, `docs/05-decisiones/ADR-026-control-de-duplicados-antipassback.md`
