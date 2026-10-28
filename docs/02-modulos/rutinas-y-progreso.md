# Módulo 5: Rutinas y seguimiento de progreso

## 1. Resumen y alcance

Este módulo cubre la creación y asignación de rutinas por parte del entrenador, la administración de la biblioteca de ejercicios, y el seguimiento del progreso del socio mediante entrenamientos, medidas, fotos y metas. También permite relacionar los ejercicios con equipos del gimnasio y la disponibilidad de cada máquina.

### Incluye
- biblioteca de ejercicios con músculo, equipo, imagen o video
- creación y asignación de rutinas
- seguimiento del entrenamiento realizado
- medidas corporales, peso, fotos y metas
- comunicación entrenador-socio

### No incluye
- sesiones de entrenamiento individual pagadas como servicio extra
- nutrición o planes de rehabilitación médica especializados

## 2. Actores y permisos

| Actor | Objetivo | Permisos clave |
|---|---|---|
| Entrenador | crear, editar y asignar rutinas | gestionar biblioteca, rutinas y avances de su cliente |
| Socio | seguir su progreso | consultar en la app su rutina, entrenamientos, medidas, fotos y metas; registrar sus entrenamientos (pendientes de revisión) y medidas; crear y cancelar sus propias metas; capturar y eliminar sus fotos de progreso con consentimiento |
| Gerente | supervisar desempeño | consultar avances generales y asignaciones |
| Dueño / administrador | configuración global | activar plantillas y políticas de rutinas |

## 3. Flujos de usuario paso a paso

### Flujo principal: creación de una rutina
1. El entrenador entra a la biblioteca de ejercicios.
2. Selecciona ejercicios, series, repeticiones, descansos y objetivos.
3. Asigna la rutina a un socio o grupo de socios.
4. Define fecha de inicio, frecuencia y observaciones.
5. El sistema guarda la versión de la rutina y permite seguimiento posterior.

### Flujo alterno: seguimiento del progreso
1. El socio realiza el entrenamiento y lo registra desde la app (fecha, duración, esfuerzo y notas) o el entrenador lo captura en el panel.
2. El sistema guarda el resumen, marca el origen (`app`/`staff`) y deja el entrenamiento pendiente de revisión; si el origen es `app`, además escribe el aviso `workout_pending_review` en la bandeja del panel del entrenador de la asignación.
3. El entrenador revisa el entrenamiento y ajusta la rutina si es necesario.
4. El socio registra sus medidas desde la app; el sistema las conserva como histórico y actualiza las metas.
5. El socio sube fotos de progreso desde la app (frente, perfil, espalda u otra) tras autorizar su uso; el personal también puede capturarlas en recepción y el panel distingue el origen.
6. Se compara la progresión con las metas definidas.

### Flujo de cambio de rutina
1. El entrenador revisa el progreso semanal.
2. Detecta que una rutina quedó insuficiente o excesiva.
3. Modifica la versión y registra la razón del ajuste.
4. El sistema conserva el historial para no perder el contexto del cambio.

## 4. Pantallas / espacios

### 1. Biblioteca de ejercicios
- Objetivo: administrar material reutilizable y estándar
- Componentes: búsqueda por músculo, categoría, equipo, nombre del ejercicio
- Estados: vacío, cargando, éxito, error

### 2. Editor de rutinas
- Objetivo: preparar la planificación del entrenamiento
- Componentes: lista de ejercicios, series, repeticiones, descanso, orden, objetivos por sesión
- Estados: borrador, activa, finalizada, archivada

### 3. Seguimiento de progresos
- Objetivo: registrar entrenamiento y métricas del socio
- Componentes: historial de sesiones, peso, medidas, fotos, notas del entrenador
- Estados: registrado, pendiente de revisión, revisado

### 4. Metas y gráficas
- Objetivo: mostrar evolución con gráficos claros
- Componentes: metas por medida con línea base, valor actual, avance y fecha objetivo; curvas de evolución quedan pendientes
- Estados: activa, cumplida, cancelada; sin línea base mientras no exista una medición de esa medida

### 5. Chat o comunicación entrenador-socio
- Objetivo: coordinar dudas y ajustes
- Componentes: mensajes, seguimiento de observaciones, recordatorios del entrenador
- Estados: sin mensajes, nuevo, respondido

### 6. Rutinas y progreso en la app del socio
- Objetivo: consultar la rutina asignada, el avance y mantener al día el historial sin pasar por recepción
- Componentes: resumen de entrenamientos, metas con avance y alta/cancelación de metas propias, últimas medidas, tarjeta de alta de medidas, rutinas asignadas y detalle con el plan de la versión fija, historial y formulario de entrenamiento con editor de series por ejercicio; tarjeta «Fotos de progreso» que abre la galería del socio con consentimiento, carga desde cámara o galería, visor con metadatos y eliminación en dos pasos
- Estados: cargando, vacío (sin asignaciones, sin medidas o sin fotos), error, sesión expirada; el formulario de entrenamiento solo aparece en asignaciones activas; la casilla de consentimiento aparece solo mientras el socio no lo haya registrado; cada registro muestra su origen («Desde tu app»/«Desde recepción», «Creada desde tu app»/«Creada por el personal» o «Subida desde tu app»/«Subida en recepción») y los entrenamientos el estado «Por revisar»/«Revisado»

## 5. Reglas de negocio y casos límite

### Reglas clave
- Solo el entrenador asignado o un gerente autorizado puede editar la rutina de un socio.
- Cada ejercicio debe estar asociado a músculo, equipo o tipo de entrenamiento para búsquedas consistentes.
- Las medidas son append-only: una nueva medición nunca reemplaza a la anterior. Las fotos de progreso también se conservan como histórico y solo se eliminan con una acción explícita de corrección o privacidad (metadatos y archivo).
- Cada socio tiene como máximo una meta **activa** por medida (peso, cintura, pecho o grasa corporal); una meta cumplida o cancelada no bloquea crear otra de la misma medida.
- La línea base de una meta se congela al crearla con la última medición disponible, o con la primera medición posterior si aún no hay ninguna. El avance se calcula contra esa línea base y la meta pasa a `achieved` en cuanto una medición alcanza el objetivo; una meta cumplida no se reabre.
- El socio puede registrar sus propios entrenamientos (solo en una asignación activa y con fecha no futura), sus medidas y sus metas desde la app; los tres quedan con origen `app`. El entrenamiento permanece pendiente de revisión hasta que el personal lo valida —y el entrenador asignado recibe un aviso en la campana del panel— y la medida se conserva como histórico y actualiza las metas. El socio solo cancela las metas que él mismo creó: las del personal se administran en recepción. No edita ni borra registros: una corrección se hace en recepción o con una captura nueva.
- Las fotos de progreso exigen un **consentimiento explícito** del socio (`member_consents` con tipo `progress_photos` y versión `fotos-progreso-v1`) antes de la primera carga desde la app; el consentimiento se registra una sola vez y, si la imagen se rechaza, no queda guardado. El socio ve y descarga solo sus fotos, con enlaces firmados de 10 minutos, y puede eliminar cualquiera de las suyas —también las que subió el personal—; la eliminación es explícita e irreversible. Las fotos de otro socio se comportan como inexistentes (`404`). El panel distingue el origen (`staff`/`app`) en la galería y en el visor.
- La rutina debe poder revisarse en diferentes fechas sin perder el contexto de la evolución.

### Casos límite
- El entrenador asigna una rutina sin equipo disponible para ese día.
- El socio no registra entrenamiento durante varias semanas.
- Dos entrenadores intentan modificar la misma rutina simultáneamente.
- El socio cambia de meta o exige una nueva planificación.

## 6. Entidades de datos

- Ejercicio
- BibliotecaEjercicio
- Rutina
- DetalleRutina
- AsignacionRutina
- Entrenamiento
- DetalleEntrenamiento
- MedidaCorporal
- MetaSocio
- FotoProgreso
- MensajeEntrenadorSocio

### Campos clave
- Ejercicio: id, nombre, músculo, categoría, equipo, descripción, video_url, imagen_url
- Rutina: id, entrenador_id, socio_id, nombre, fecha_inicio, fecha_fin, objetivo
- Entrenamiento: id, rutina_id, socio_id, fecha, notas, completado
- MedidaCorporal: id, socio_id, peso, cintura, pecho, porcentaje grasa, fecha
- MetaSocio: id, socio_id, medida, dirección, objetivo, línea base, fecha objetivo, estado, valor alcanzado y fecha de cumplimiento
- FotoProgreso: id, socio_id, ángulo, fecha de captura, nota, tipo de contenido, tamaño en bytes, clave de almacenamiento, `origin` (`staff`/`app`), usuario que subió y fecha de alta; los bytes viven fuera de la base

## 7. Integraciones con otros módulos

- Clases y bookings: se puede relacionar la sesión con entrenamiento de grupo o instructor.
- Mantenimiento de equipo: un ejercicio puede marcar que requiere una máquina específica y quedar bloqueado si está fuera de servicio.
- Acceso y membresías: el sistema verifica que el socio tenga vigencia para seguir asignado a rutinas.
- Comunicación: recordatorios de cumplimiento y seguimiento del entrenador.

## 8. Notificaciones y automatizaciones

- Recordatorio semanal de progreso.
- Aviso de rutina nueva.
- Alerta de ausencia prolongada en entrenamiento.
- Sugerencia de ajuste de carga cuando el progreso se estanca.
- Notificación de cumplimiento de meta o incumplimiento.

## 9. Consideraciones de rendimiento específicas del módulo

- caché de ejercicios más usados y rutinas activas
- paginación por fecha para historial de entrenamientos
- carga diferida de fotos y videos para no bloquear la vista de progreso
- gráfica de evolución calculada en el navegador sobre las mediciones ya cargadas (máximo 36), sin agregación en el servidor
- índices por `socio_id`, `entrenador_id`, `fecha`, `rutina_id`
- almacenamiento local de fotos fuera de la base, con validación de tipo y tamaño; compresión, miniaturas y almacenamiento de objetos quedan pendientes

## 10. KPIs

- porcentaje de rutinas activas completadas
- avance promedio por meta
- asistencia real a sesiones programadas
- participación en seguimiento semanal
- tasa de retención en ejercicios asignados

## 11. Preguntas abiertas

- ¿las rutinas se gestionan por entrenador asignado o por general del gimnasio?
- ¿los progresos deben verse también como “entrenamiento personalizado” o solo como apoyo a la rutina base?
- ¿las medidas requieren un consentimiento especial como el que ya tienen las fotos de progreso, y qué retención aplica a cada dato?

## 12. Criterios de aceptación

- El entrenador puede crear y asignar rutinas a un socio con historial de cambios.
- El socio puede registrar entrenamiento y visualizar su progreso.
- Las medidas y metas quedan con historial y no se pierden por una nueva edición; las fotos se conservan y solo se eliminan con una acción explícita.
- El sistema avisa cuando una rutina debe revisarse o cuando el progreso se estanca.
- La relación ejercicio-equipo se refleja al consultar disponibilidad del equipo.

## 13. Implementación actual y límites

Noveno incremento entregado (2026-10-28) con las **fotos de progreso capturadas desde la app del socio**, sobre las metas desde la app del octavo; siguen fuera de alcance la edición de registros, la mensajería y las notificaciones:

- **Persistencia**: siete tablas del primer incremento (`exercises`, `routines`, `routine_items`, `routine_revisions`, `routine_assignments`, `workout_logs`, `body_measurements`) creadas por la migración `20261017_0010_routines.py`, más `member_goals` creada por `20261025_0029_member_goals.py`, `progress_photos` creada por `20261025_0030_progress_photos.py`, la columna `origin` (`staff`/`app`) en `workout_logs` y `body_measurements` agregada por `20261027_0032_member_activity_origin.py` la tabla `workout_sets` creada por `20261027_0033_workout_sets.py`, la columna `origin` (`staff`/`app`) en `member_goals` agregada por `20261027_0034_member_goal_origin.py` y la columna `origin` (`staff`/`app`) en `progress_photos` agregada por `20261028_0041_progress_photo_origin.py`. La migración `20261017_0011_routines_permissions.py` agrega los permisos `routines.read` / `routines.manage` y los otorga a dueño, gerente y entrenador; recepción, mantenimiento y contabilidad no los tienen (sección 2).
- **Biblioteca de ejercicios**: `POST/PATCH /admin/routines/exercises` administra nombre, grupo muscular, categoría, equipo, descripción, video e imagen. `GET /admin/routines/exercises` pagina y devuelve las facetas `muscle_groups` y `categories`; los ejercicios se desactivan (`is_active=false`) en vez de borrarse porque las rutinas los referencian.
- **Rutina como plantilla reutilizable**: a diferencia del borrador de la sección 6 (donde `Rutina` apuntaba a un `socio_id`), la rutina **no** pertenece a un socio. Es una plantilla del entrenador que se asigna a varios socios; el vínculo con el socio vive en `routine_assignments`. Así una misma rutina sirve de base para muchas personas sin duplicarse.
- **Versionado**: `routines.version` apunta al plan vivo. `PUT /admin/routines/{id}/items` publica la versión siguiente (`version+1`) con un juego nuevo de `routine_items`, conserva las líneas anteriores en la base y registra el motivo en `routine_revisions`. `GET /admin/routines/{id}?version=n` permite leer una versión histórica. **Ninguna asignación se modifica al publicar**: cada `routine_assignment` fija `routine_version` al crearse y el entrenamiento hereda esa versión fija, de modo que reescribir la plantilla nunca altera el historial del socio.
- **Asignaciones**: `POST /admin/routines/assignments` valida que la rutina exista, esté activa y tenga ejercicios, y que el socio exista y esté activo. Un índice único parcial (`uq_routine_assignments_active` sobre `(member_id, routine_id)` donde `status='active'`) impide dos asignaciones vivas de la misma rutina al mismo socio. Se cierran con `POST .../complete` o `POST .../cancel`; nunca se borran (retienen sus entrenamientos).
- **Archivado de rutinas**: `POST /admin/routines/{id}/archive` marca la rutina como `archived` y bloquea más ediciones, pero no cierra las asignaciones vivas: esas deben completarse o cancelarse por separado.
- **Entrenamientos**: `POST /admin/routines/assignments/{id}/workouts` solo acepta una asignación **activa**, con fecha no futura ni anterior a `start_date` del plan; guarda `performed_at`, duración, esfuerzo percibido (1–10) y notas. `POST /admin/routines/workouts/{id}/review` marca el entrenamiento como revisado por el entrenador.
- **Detalle por serie**: el alta del entrenamiento acepta `sets`, una lista opcional de series ejecutadas que se guardan en `workout_sets` con `exercise_id`, `set_number`, `reps` y `weight_kg` (nulo para peso corporal). Cada ejercicio debe pertenecer al plan de la **versión fijada** de la asignación; se rechazan con `422` un ejercicio fuera del plan, una serie duplicada, `set_number` fuera de 1–20, `reps` fuera de 1–100, peso fuera de 0–1000 kg y más de 60 series. El orden de lectura lo marca el plan (`routine_items.position`) y luego el número de serie, y la revisión del entrenador no altera las series. Las series no se editan ni se borran después del alta; un entrenamiento sin detalle sigue siendo válido y devuelve `sets: []`.
- **Medidas corporales**: `POST /admin/routines/members/{id}/measurements` es **append-only**: nunca reemplaza una medida anterior, aunque se registre el mismo día (sección 5). Guarda peso, cintura, pecho y porcentaje de grasa como `Numeric` con conversión a `float` para la respuesta. `GET .../measurements` y `GET .../progress` exponen el histórico y el resumen del socio (asignaciones activas, entrenos totales, de los últimos 30 días, último entreno y última medida).
- **Metas del socio**: `POST /admin/routines/members/{id}/goals` crea una meta de peso, cintura, pecho o grasa corporal con dirección `decrease`/`increase`, objetivo positivo y fecha objetivo opcional (no anterior a hoy). Si ya hay una meta activa de esa medida responde `409`; si el objetivo ya se cumple con la última medición responde `422`. La línea base se congela con la última medición disponible o con la primera posterior; `progress_percent` se calcula contra esa base y se acota a 0–100. `PATCH /admin/routines/goals/{id}` ajusta objetivo, fecha o nota mientras la meta esté activa; `POST .../cancel` la cierra como `cancelled`. Al registrar una medición que alcanza el objetivo, la meta pasa automáticamente a `achieved` con el valor y la fecha de cumplimiento, y ya no se edita ni se cancela. `GET /admin/routines/members/{id}/goals?status=` lista el histórico con activas, cumplidas y canceladas. La app agrega `POST /member/progress/goals` y `POST /member/progress/goals/{goal_id}/cancel`: crean y cancelan metas propias con `origin="app"` y las mismas validaciones de rango, objetivo ya cumplido y una sola meta activa por medida; una meta creada por el personal no se cancela desde la app (`409`) y una meta ajena responde `404`. Las metas del personal se siguen creando, editando y cancelando solo desde el panel con `routines.manage`.
- **Fotos de progreso**: `POST /admin/routines/members/{id}/photos` recibe una imagen multipart (`photo`), un ángulo (`front`/`side`/`back`/`other`), la fecha de captura opcional, que por defecto es el momento de la carga, y una nota de hasta 300 caracteres. Solo acepta JPEG, PNG o WebP verificados por **firma binaria** (no por nombre ni por el MIME declarado), con un máximo de **8 MB**; un tipo no admitido, un contenido que no coincide con lo declarado o una imagen vacía responde `422`, y un tamaño excedido `413`. Los bytes se guardan **fuera de la base** en `PROGRESS_PHOTOS_DIR` (por defecto `./uploads/progress_photos`, ignorado por Git) con un nombre aleatorio de 32 caracteres hexadecimales y extensión según el tipo, en un directorio `0700` y archivos `0600`; no se conserva el nombre original. La tabla `progress_photos` guarda solo metadatos y una clave de almacenamiento única que se valida con una expresión regular antes de tocar el disco, lo que impide rutas fuera del directorio. `GET .../photos` lista las fotos del socio más recientes primero (máximo 100) y `GET /admin/routines/photos/{id}/file` sirve la imagen en línea con `Cache-Control: private, no-store` y `X-Content-Type-Options: nosniff`, solo para usuarios autenticados con `routines.read`. `DELETE /admin/routines/photos/{id}` elimina la fila y, después de confirmar la transacción, el archivo; es una operación explícita e irreversible para corregir una carga o atender una solicitud de privacidad, no un reemplazo de la foto anterior. Si el archivo falta, la descarga responde `404` pero la fila todavía se puede eliminar; un archivo huérfano (fallo del disco posterior al commit) no se limpia automáticamente.
- **Números y fechas**: pesos y perímetros usan `Numeric(5,2)` / `Numeric(4,1)`; las metas usan `Numeric(6,2)`; `start_date` / `end_date` / `performed_at` son fechas, y `measured_at` / `baseline_measured_at` / `achieved_at` / `captured_at` son instantes con zona horaria normalizados a UTC. La fecha objetivo se valida contra el día local del gimnasio.
- **API**: 29 rutas bajo `/admin/routines/*` (resumen, ejercicios, rutinas con versiones, asignaciones, entrenamientos, medidas, metas, fotos y progreso), todas protegidas por `routines.read` (consulta y descarga de archivos) o `routines.manage` (escritura y eliminación).
- **Panel web**: la vista Rutinas tiene tres pestañas. *Seguimiento* lista asignaciones con filtros y abre un detalle con el plan asignado, los entrenamientos (registro y revisión), las mediciones (registro y gráfica de evolución), las fotos de progreso (carga con ángulo, fecha y nota; galería con miniaturas de carga diferida, visor ampliado con metadatos y eliminación con confirmación), las metas (alta, edición y cancelación con avance, estados y origen «Personal»/«App») y el resumen de progreso del socio. La gráfica de evolución se calcula en el navegador con las mediciones ya cargadas (máximo 36), permite alternar peso, cintura, pecho y grasa, dibuja la meta activa de esa medida como línea de referencia y resume el cambio desde la primera medición; con menos de dos mediciones muestra un aviso en lugar de la gráfica. *Rutinas* lista plantillas con versión, ejercicios y asignaciones activas, permite crear una rutina con su plan, editar el plan publicando una versión nueva con motivo, y archivarla. *Ejercicios* administra la biblioteca con filtros por grupo y categoría. Todo pasa por rutas BFF bajo `/api/admin/routines/*`, incluidas `/members/[memberId]/photos`, `/photos/[photoId]/file` y `/photos/[photoId]`; la descarga reenvía el tipo, el `Content-Disposition` y las cabeceras de seguridad.
- **Datos de ejemplo**: `backend/seed_routines.py` puebla la base de vista previa (12 ejercicios, 4 rutinas —una con dos versiones—, asignaciones, entrenamientos y mediciones) y agrega metas de demostración (una activa, una cancelada y una cumplida) incluso si la base ya tenía rutinas sembradas. También siembra cuatro fotos de demostración (tres ángulos del mismo socio y una de otro) como PNG generados con fecha local al mediodía, guardados en el directorio configurado; es idempotente y no vuelve a sembrar si ya existen fotos.
- **App del socio (lectura y registro propio)**: `backend/src/app/modules/portal/routines.py` expone quince rutas con Bearer de socio. `GET /member/routines` lista las asignaciones propias (máximo 100, activas primero) con nombre y versión de la rutina, entrenador, fechas, frecuencia, estado, notas, entrenamientos registrados y último entrenamiento, más el resumen por estado calculado en la propia capa. `GET /member/routines/{assignment_id}` devuelve el **plan de la versión fijada al asignar** (`routine_version`), el objetivo de la rutina, las notas de la asignación y los últimos 10 entrenamientos; una asignación ajena responde `404`. `GET /member/progress` devuelve entrenamientos totales y de los últimos 30 días, último entrenamiento, última medición, histórico de medidas (máximo 36) y metas con su avance. `POST /member/routines/{assignment_id}/workouts` y `POST /member/progress/measurements` permiten al socio **registrar su propio entrenamiento y sus medidas**: reutilizan `log_workout` y `record_measurement`, guardan `origin = "app"` y exigen una asignación propia y activa. El entrenamiento admite las **series** con las mismas validaciones contra el plan fijado que el panel. El entrenamiento queda `logged` (por revisar) hasta que el personal lo marca con `POST /admin/routines/workouts/{id}/review`, y ese marcado escribe el aviso `workout_reviewed` en la bandeja del socio; en cambio, **el origen `app` escribe `workout_pending_review` en la bandeja del panel del entrenador** de la asignación (`RoutineAssignment.trainer_id` → `AppUser.employee_id`), así que el pendiente llega a quien debe resolverlo sin abrir la pestaña. Un entrenamiento capturado por el personal no genera ese aviso y, si el entrenador no tiene cuenta activa, el aviso se omite mientras el entrenamiento se guarda igual. La medida, en cambio, se acepta directamente, es append-only y actualiza las metas en la misma transacción. Los límites de entrada son duración 0–600 min, esfuerzo 1–10, notas de 2000 caracteres en el entrenamiento y 300 en la medida, peso 0–500 kg, cintura y pecho 0–400 cm y grasa 0–100 %. `logged_by` y `measured_by` quedan vacíos en los registros de la app porque son FK al personal. `POST /member/progress/goals` y `POST /member/progress/goals/{goal_id}/cancel` permiten al socio **crear y cancelar metas propias** con `origin="app"`: la meta nace con la línea base de la última medición y solo se puede cancelar si la creó el socio. El `member_id` sale siempre de la sesión y ninguna ruta acepta un identificador de socio. **La escritura desde la app se limita a entrenamientos, medidas, metas propias y fotos propias**; el plan, las asignaciones y las metas del personal siguen exigiendo `routines.manage`. En la app, la pantalla «Rutinas y progreso» agrupa el resumen, las metas con su formulario de alta y cancelación, las últimas medidas con su tarjeta de alta, las rutinas asignadas y la tarjeta «Fotos de progreso», y el detalle muestra el plan numerado, el formulario de entrenamiento con su **editor de series por ejercicio** y el historial con el resumen de series, el origen y el estado.
- **Fotos desde la app**: `GET /member/progress/photos` devuelve las fotos propias (más recientes primero, máximo 100) junto con `consent_recorded`; `POST /member/progress/photos` recibe el multipart con `photo`, `angle`, `captured_at` opcional, `notes` y `consent`, guarda `origin="app"` y reutiliza las mismas validaciones de firma, tamaño y ángulo que el panel. El consentimiento (`member_consents` con tipo `progress_photos` y versión `fotos-progreso-v1`) es **precondición**: sin él la carga responde `422` y no escribe nada, se registra una sola vez con la primera foto aceptada y se revierte si la imagen se rechaza. `DELETE /member/progress/photos/{photo_id}` elimina una foto propia —también la que subió el personal— y una ajena responde `404`. La descarga no usa el Bearer: cada foto viaja con un **enlace firmado de 10 minutos** (`GET /member/progress/photos/{id}/file?exp=…&sig=…`, HMAC-SHA256 con `SECRET_KEY`, igual que las facturas del socio), responde `403` con firma alterada o vencida, `422` sin parámetros y entrega el archivo en línea con `Cache-Control: private, no-store` y `X-Content-Type-Options: nosniff`. La app añade `ProgressPhotosScreen` con la casilla de consentimiento (solo mientras no esté registrado), carga desde cámara o galería, chips de ángulo, fecha, nota de 300 caracteres, comprobación de 8 MB en el cliente, galería con visor, etiqueta de origen («Subida desde tu app»/«Subida en recepción») y eliminación en dos pasos.

Pendiente (documentado en `docs/deuda-tecnica.md`): series objetivo por sesión, series por tiempo o distancia, edición o corrección de una captura (incluidas sus series) desde la app, traza explícita del socio que capturó, edición de los metadatos de una foto, carga múltiple, revocación del consentimiento de fotos y política de retención, mensajería entrenador-socio, relación ejercicio-equipo que bloquee ejercicios con la máquina en mantenimiento y los avisos automáticos que aún no se emiten (recordatorio semanal, rutina recién asignada y ausencia prolongada). El aviso al entrenador de un entrenamiento pendiente **ya se emite** (`workout_pending_review`, campana del panel, ver `notificaciones-del-socio.md` y ADR-017); queda que ese aviso **no se cierra al revisar** y que se omite si el entrenador de la asignación no tiene cuenta activa.

## 14. Estado

Noveno incremento implementado y probado (biblioteca de ejercicios, rutinas con versionado y archivado, asignaciones con versión fija, registro y revisión de entrenamientos con detalle por serie, medidas, metas con cierre automático, fotos de progreso con almacenamiento local seguro, gráfica de evolución de medidas, resumen de progreso desde el panel, consulta de rutinas, entrenamientos, medidas y metas desde la app del socio, registro de entrenamientos con series —con revisión del entrenador— y medidas desde la app, alta y cancelación de metas propias desde la app, y **carga, consulta y eliminación de fotos de progreso desde la app con consentimiento y enlaces firmados**, además de los avisos que este módulo provoca en la bandeja del socio (`workout_reviewed`, `goal_updated_by_staff`, `goal_cancelled_by_staff` y `goal_achieved`) y en la del entrenador (`workout_pending_review`), ver `notificaciones-del-socio.md` y ADR-017; ver ADR-023 para las fotos desde la app); la edición de registros y la mensajería entrenador-socio quedan en diseño / validación funcional.

## 15. Historial de cambios

- 2026-10-28: noveno incremento (fotos desde la app): migración `20261028_0041_progress_photo_origin.py` con `origin` (`staff`/`app`) en `progress_photos`; rutas `GET/POST /member/progress/photos`, `GET /member/progress/photos/{id}/file` con enlace firmado de 10 minutos y `DELETE /member/progress/photos/{id}`; consentimiento `progress_photos`/`fotos-progreso-v1` como precondición idempotente y revertida si la imagen falla; `ProgressPhotosScreen` con casilla de consentimiento, cámara/galería, visor, etiqueta de origen y eliminación en dos pasos; etiqueta de origen en la galería y el visor del panel; prueba de API de ciclo completo y verificación en navegador (ADR-023).
- 2026-10-27: el alta de un entrenamiento con `origin = "app"` escribe `workout_pending_review` en la nueva bandeja del panel del entrenador de la asignación (migración `20261027_0036_staff_notifications.py`, tabla `staff_notifications`, ADR-017). Sin cambios en las reglas de registro, en las rutas ni en los permisos: el aviso se emite dentro de la misma transacción de `log_workout` y se omite si el entrenador no tiene cuenta activa.
- 2026-10-27: octavo incremento (metas desde la app): migración `20261027_0034_member_goal_origin.py` con `origin` (`staff`/`app`) en `member_goals`; rutas `POST /member/progress/goals` y `POST /member/progress/goals/{goal_id}/cancel` con las reglas del panel (rango, objetivo ya cumplido, una meta activa por medida, línea base congelada) y cancelación limitada a las metas creadas por el socio; `origin` en la respuesta y en el panel («Personal»/«App»); formulario de alta y cancelación en dos pasos en la app; pruebas de API y verificación en navegador en ambos canales.

- 2026-10-27: séptimo incremento (detalle por serie): migración `20261027_0033_workout_sets.py` con la tabla `workout_sets` (CASCADE desde el entrenamiento, RESTRICT al ejercicio, serie única por ejercicio y entrenamiento, rangos y máximo de 60 series); `WorkoutSetInput`/`WorkoutSetItem` en el servicio y validación contra el plan de la versión fijada; `sets` opcional en el alta del panel y de la app; editor de series y resumen en la app y en el panel; pruebas de API y verificación en navegador en ambos sentidos.

- 2026-10-27: sexto incremento (registro desde la app): migración `20261027_0032_member_activity_origin.py` con `origin` en `workout_logs` y `body_measurements`; rutas `POST /member/routines/{assignment_id}/workouts` (estado `logged`, pendiente de revisión) y `POST /member/progress/measurements` (append-only, actualiza metas), ambas con `origin="app"`; formularios de entrenamiento y medidas en la app; origen «Personal»/«App» y revisión en el panel; pruebas de API y verificación en navegador.

- 2026-10-27: quinto incremento (app del socio, solo lectura): capa `app.modules.portal.routines`, rutas `GET /member/routines`, `GET /member/routines/{assignment_id}` y `GET /member/progress`, con plan de la versión asignada, historial de entrenamientos, medidas y metas; pantallas `RoutinesScreen` y `RoutineDetailScreen` en la app Expo; sin migración ni cambios en las reglas del módulo.

- 2026-10-26: cuarto incremento (gráficas de evolución): gráfica SVG en el detalle de seguimiento con selector de peso, cintura, pecho y grasa, meta activa como línea de referencia, resumen del cambio desde la primera medición y estado vacío con menos de dos datos; sin migración ni cambios de API.
- 2026-10-26: tercer incremento (fotos de progreso): migración `20261025_0030_progress_photos.py`, almacenamiento local fuera de la base con validación por firma, límite de 8 MB y claves aleatorias, API de carga, listado, descarga autenticada y eliminación, BFF, galería con visor en el detalle de seguimiento, seed idempotente con PNG de demostración y prueba de ciclo de vida.
- 2026-10-25: segundo incremento (metas del socio): migración `20261025_0029_member_goals.py`, servicio con línea base congelada, progreso calculado y cierre automático, API `/admin/routines/members/{id}/goals` y `/admin/routines/goals/{id}`, BFF, panel de metas en el detalle de seguimiento, seed idempotente y prueba de ciclo de vida.
- 2026-10-17: primer incremento de implementación (biblioteca de ejercicios, rutinas como plantillas con versionado y archivado, asignaciones con versión fija, entrenamientos, medidas y progreso) con migraciones `20261017_0010` y `20261017_0011`, API `/admin/routines/*`, panel web con vista Rutinas, seeder de vista previa y pruebas de API.
- 2026-10-15: documento ampliado con flujos, entidades, pantallas, KPIs y criterios de aceptación.
