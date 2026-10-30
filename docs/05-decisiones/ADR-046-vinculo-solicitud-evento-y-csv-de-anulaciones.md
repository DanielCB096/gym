# ADR-046: Vínculo explícito entre la solicitud aprobada y el evento, y CSV de anulaciones

- Fecha: 2026-10-30
- Estado: propuesta inicial

## Contexto

ADR-044 cerró el ciclo de solicitudes aplicando el cambio por el camino normal de corrección o anulación, y dejó anotadas dos limitaciones: la bitácora del turno no guardaba el identificador de la solicitud —el vínculo solo se podía reconstruir cruzando `staff_attendance_requests.decided_at` con el instante del evento, un cruce ambiguo cuando dos cambios caen en el mismo minuto o cuando el reloj de la base no coincide con el del servidor— y el reporte de anulaciones no se podía exportar. Para la supervisión, «¿esta anulación la pidió el colaborador o la hice yo desde el panel?» es una pregunta con consecuencias distintas: la primera tiene justificación y decisión registradas, la segunda no. Y un reporte que solo vive en pantalla no sirve para revisar el periodo fuera del panel ni para adjuntarlo a la revisión de nómina.

## Decisión

- **El vínculo vive en el evento, no en la solicitud.** `staff_attendance_events.attendance_request_id` es una FK nullable a `staff_attendance_requests.id` con `ON DELETE SET NULL`. Se eligió el evento porque es la fila que se lee en la bitácora y en el reporte de anulaciones: así la pregunta se responde en la misma consulta, sin cruzar instantes. Nullable porque la mayoría de los eventos no nacen de una solicitud —el marcaje del colaborador, la corrección del panel, el registro manual—, y `SET NULL` para que retirar una solicitud nunca borre la historia de la marca.
- **No se rellena el pasado en este corte** (cerrado por ADR-047). La migración no hace backfill: el cruce por `decided_at` es ambiguo por diseño (varias decisiones en el mismo minuto, correcciones posteriores) y escribir un vínculo inventado en la bitácora sería peor que dejarlo vacío. Los eventos anteriores al incremento quedan con `attendance_request_id` nulo; desde este corte, toda aprobación lo escribe. ADR-047 recupera después esas aprobaciones sin cruzar instantes: desde ADR-044 el motivo del evento lleva el prefijo `Solicitud del colaborador:` y basta con exigir asistencia, actor, tipo de evento y motivo exactos, y solo en pares uno a uno.
- **Quien aplica el cambio lo recibe por parámetro.** `correct_attendance` y `void_attendance_mark` suman `attendance_request_id: UUID | None = None` y lo copian al evento. `decide_attendance_request` pasa `request.id` en sus dos ramas (corregir y anular), de modo que un cambio pedido y aprobado se distingue de uno hecho desde el panel aunque el evento, el motivo y el efecto sean idénticos. El nombre no reutiliza `request_id`: esa columna es la clave de idempotencia del alta (`uq_staff_attendance_events_request`) y mezclarlas habría roto el reintento.
- **El reporte y su CSV comparten las mismas filas.** `AttendanceAnnulment` suma `attendance_request_id`, el endpoint JSON lo publica y `attendance_annulments_export` construye un `ExportTable` a partir del mismo `AttendanceAnnulmentReport` que pinta el panel. La exportación no vuelve a consultar ni a agregar: si la pantalla y el archivo discreparan, sería un defecto del mismo código, no de dos rutas paralelas. La columna «Origen» dice `Solicitud del colaborador` o `Panel`, y la columna «Solicitud» lleva el identificador completo cuando existe.
- **El CSV es una descarga autenticada, no un enlace público.** `GET /admin/staff/attendance/annulments.csv` (`attendance.read`) reutiliza los filtros `days`, `employee_id` y `actor_id` del reporte JSON, responde `text/csv; charset=utf-8` con `Content-Disposition: attachment` y el nombre fechado en la zona del club, y el BFF `proxyAuthenticatedDownload` lo reenvía leyendo bytes, sin decodificar. El panel lo abre como enlace con el periodo elegido y avisa con un toast mientras prepara la descarga.
- **El `ExportTable` se separa del constructor de reportes.** El nuevo `app/exports.py` guarda solo el contrato `title`/`headers`/`rows`; reportes y fisioterapia lo importan desde ahí y staffing lo usa sin arrastrar las consultas de reportes ni los modelos que tocan. Así el servicio de asistencia no depende del módulo de reportes y las pruebas de staffing no necesitan registrar tablas ajenas.

## Consecuencias y límites

- **La bitácora lo enseña sin ruido.** El modal del turno agrega bajo el evento la línea «Aplicado al aprobar la solicitud del colaborador · {id corto}», y el reporte de anulaciones gana la columna «Origen». Los eventos sin vínculo no muestran nada: el silencio significa «no consta», no «hecho por el panel» —esa lectura la da la columna «Origen» del reporte de anulaciones, que sí conoce el contexto.
- **Un cambio aplicado por una solicitud y luego corregido otra vez conserva el vínculo en el evento de la aprobación**, no en la corrección posterior del panel: cada evento responde por su propia causa. Es el comportamiento correcto para auditar, aunque quien lea solo la última fila vea un cambio sin solicitud.
- **El CSV no envía por correo ni se programa.** Es una descarga bajo demanda, como el resto de exportaciones del club; el desglose por operador sigue siendo una agregación de la pantalla y del JSON, y una hoja de cálculo puede pivotar las filas exportadas si hace falta.
- **El nombre del archivo usa la fecha del club, no UTC.** Un reporte descargado a las 23:30 en México lleva el día local correcto, coherente con el resto de fronteras de día del sistema.
- **La vista previa añade la columna y el índice.** `preview_patch.py` registra `staff_attendance_events.attendance_request_id` y `ix_staff_attendance_events_request_link`; en PostgreSQL lo hace `20261031_0063_attendance_request_event_link.py`, cuya reversión se niega mientras existan eventos enlazados.

## Referencias

- `backend/src/app/modules/staffing/models.py` (`AttendanceEvent.attendance_request_id`, `ix_staff_attendance_events_request_link`)
- `backend/src/app/modules/staffing/service.py` (`correct_attendance`, `void_attendance_mark`, `decide_attendance_request`, `AttendanceAnnulment`, `attendance_annulments_export`)
- `backend/src/app/exports.py` (`ExportTable`), `backend/src/app/modules/reports/service.py`, `backend/src/app/modules/physio/reports.py`
- `backend/src/app/main.py` (`GET /admin/staff/attendance/annulments.csv`, `attendance_request_id` en la bitácora y en el reporte)
- `backend/alembic/versions/20261031_0063_attendance_request_event_link.py`, `backend/preview_patch.py`
- `backend/tests/test_attendance_requests.py` (vínculo al aprobar una anulación y CSV con origen), `backend/tests/test_attendance_api.py` (`attendance_request_id` en la bitácora y el reporte, descarga CSV con comillas y filtros), `backend/tests/test_preview_patch.py` (columna e índice)
- `web/src/app/api/admin/staff/attendance/annulments/export/route.ts`, `web/src/app/page.tsx` (línea de la bitácora, columna «Origen», «Exportar CSV»), `web/src/app/globals.css` (`.staff-log-link`)
- `docs/05-decisiones/ADR-044-avisos-solicitudes-y-auditoria-de-politica.md`, `docs/02-modulos/personal-y-roles.md`, `docs/01-arquitectura/modelo-de-datos.md`, `docs/deuda-tecnica.md`, `docs/07-pruebas/plan-de-pruebas.md`
