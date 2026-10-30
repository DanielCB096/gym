# ADR-047: Relleno del vínculo solicitud→evento en la bitácora anterior

- Fecha: 2026-10-30
- Estado: propuesta inicial

## Contexto

ADR-046 dejó el vínculo `staff_attendance_events.attendance_request_id` a partir de su despliegue y decidió **no** rellenar el pasado porque el cruce por `decided_at` era ambiguo. Al revisar el histórico de la vista previa apareció que el cruce por instantes no hacía falta: desde ADR-044 la aprobación ya escribe el motivo del evento como `Solicitud del colaborador: {justificación}` —y añade ` · Nota del supervisor: {nota}` cuando la hay—, así que el evento se identifica por su propio texto y por quién lo escribió. Quedaban sin vínculo las aprobaciones hechas entre ADR-044 y ADR-046, es decir, la única etapa en que existieron solicitudes sin enlace: la solicitud aprobada el 2026-10-30 a las 20:27 y su corrección seguían sueltas aunque la bitácora dijera de dónde venían.

## Decisión

- **Se rellena con una regla explícita, no con proximidad de tiempo.** Un evento se enlaza con una solicitud aprobada cuando coinciden la asistencia, el actor del evento con `decided_by`, el tipo de evento que produce su `mark`/`action` (`check_in_correction`/`check_out_correction` para corregir; `attendance_voided` para anular la entrada, `check_out_voided` para la salida), `source = 'manual'` y el motivo exacto que la aprobación escribió —las dos formas, con y sin nota—. El instante no participa: en una corrección `occurred_at` es la hora propuesta y no la de la decisión, así que usarlo habría introducido justo la ambigüedad que ADR-046 quiso evitar.
- **Emparejamiento uno a uno o nada.** Si una solicitud encaja con más de un evento, o un evento con más de una solicitud, no se enlaza ninguno. Se prefiere dejar el hueco a escribir un par inventado; el caso aparece cuando la misma persona pide dos veces lo mismo sobre la misma marca con la misma justificación.
- **No se reescribe lo que ya tiene vínculo.** El `UPDATE` solo mira filas con `attendance_request_id IS NULL`, así que ejecutarlo dos veces no cambia nada; la migración y el parche de la vista previa son idempotentes por construcción.
- **Una sola consulta, portable.** La regla es un `WITH ... UPDATE` con funciones de ventana (`COUNT(*) OVER (PARTITION BY ...)`) que PostgreSQL y SQLite aceptan igual. En PostgreSQL lo ejecuta `20261031_0064_attendance_request_link_backfill.py`; en la vista previa, `preview_patch.backfill_attendance_request_links`, que además reporta cuántos eventos enlazó.
- **La reversión es un no-op.** Un vínculo rellenado es indistinguible de uno escrito en vivo por ADR-046, así que deshacerlo exigiría adivinar cuáles se rellenaron; la migración deja la columna como está y `20261031_0063` ya se niega a quitarla mientras haya eventos enlazados.
- **No hay API ni cambio de panel.** La línea «Aplicado al aprobar la solicitud del colaborador» de la bitácora y la columna «Origen» del reporte ya leen la columna; con el relleno, los eventos antiguos la muestran sin tocar la interfaz.

## Consecuencias y límites

- **El histórico queda completo para los casos reconocibles.** Las aprobaciones registradas desde ADR-044 se enlazan; quedan nulos los eventos sin el prefijo en el motivo, los pares ambiguos y las aprobaciones cuyo evento se haya borrado, que en la práctica son ninguno o casi ninguno.
- **El motivo manda.** Un cambio hecho desde el panel con un motivo que empiece literalmente por `Solicitud del colaborador: ` y coincida con la justificación de una solicitud aprobada del mismo actor podría enlazarse; el filtro uno a uno lo descarta cuando hay más de un candidato, y el texto de ese prefijo no es algo que un operador escriba por casualidad.
- **La búsqueda por nota usa `LIKE`.** Una justificación con `%` o `_` amplía el patrón; el filtro uno a uno vuelve a descartar el emparejamiento cuando aparecen varios candidatos, y el caso normal compara cadenas exactas.
- **El relleno es de una sola vez.** No hay planificador ni trabajo periódico: la migración corre al desplegar y `preview_patch.py` al preparar la vista previa. Las aprobaciones nuevas ya nacen enlazadas.

## Referencias

- `backend/alembic/versions/20261031_0064_attendance_request_link_backfill.py`
- `backend/preview_patch.py` (`BACKFILL_ATTENDANCE_REQUEST_LINKS`, `backfill_attendance_request_links`)
- `backend/tests/test_preview_patch.py` (`test_preview_backfills_the_request_link_on_older_events`)
- `backend/src/app/modules/staffing/service.py` (`decide_attendance_request`, `correct_attendance`, `void_attendance_mark`)
- `docs/05-decisiones/ADR-044-avisos-solicitudes-y-auditoria-de-politica.md`, `docs/05-decisiones/ADR-046-vinculo-solicitud-evento-y-csv-de-anulaciones.md`
