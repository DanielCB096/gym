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
| Socio | seguir su progreso | ver rutina, registrar entrenamientos y revisar metas |
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
1. El socio realiza entrenamiento y registra la sesión.
2. El sistema guarda ejercicio, series, peso, esfuerzo y observaciones.
3. El entrenador puede revisar el avance y ajustar la rutina si es necesario.
4. Se compara la progresión con las metas definidas por el socio.

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
- Componentes: curvas de peso, medidas, repeticiones, carga semanal y cumplimiento
- Estados: sin datos, en progreso, completada, rebasada

### 5. Chat o comunicación entrenador-socio
- Objetivo: coordinar dudas y ajustes
- Componentes: mensajes, seguimiento de observaciones, recordatorios del entrenador
- Estados: sin mensajes, nuevo, respondido

## 5. Reglas de negocio y casos límite

### Reglas clave
- Solo el entrenador asignado o un gerente autorizado puede editar la rutina de un socio.
- Cada ejercicio debe estar asociado a músculo, equipo o tipo de entrenamiento para búsquedas consistentes.
- Las medidas y fotos quedan como histórico; no se reemplaza el dato anterior salvo edición documental con auditoría.
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
- índices por `socio_id`, `entrenador_id`, `fecha`, `rutina_id`
- almacenamiento de fotos con compresión y optimización de tamaño

## 10. KPIs

- porcentaje de rutinas activas completadas
- avance promedio por meta
- asistencia real a sesiones programadas
- participación en seguimiento semanal
- tasa de retención en ejercicios asignados

## 11. Preguntas abiertas

- ¿las rutinas se gestionan por entrenador asignado o por general del gimnasio?
- ¿los progresos deben verse también como “entrenamiento personalizado” o solo como apoyo a la rutina base?
- ¿las fotos y medidas requieren consentimiento especial y exclusión de ciertos datos?

## 12. Criterios de aceptación

- El entrenador puede crear y asignar rutinas a un socio con historial de cambios.
- El socio puede registrar entrenamiento y visualizar su progreso.
- Las fotos, medidas y metas quedan con historial y no se pierden por una nueva edición.
- El sistema avisa cuando una rutina debe revisarse o cuando el progreso se estanca.
- La relación ejercicio-equipo se refleja al consultar disponibilidad del equipo.

## 13. Implementación actual y límites

Primer incremento entregado (2026-10-17), centrado en la operación de rutinas y el seguimiento desde el panel, sin app del socio, metas, fotos ni mensajería:

- **Persistencia**: siete tablas nuevas (`exercises`, `routines`, `routine_items`, `routine_revisions`, `routine_assignments`, `workout_logs`, `body_measurements`) creadas por la migración `20261017_0010_routines.py`. La migración `20261017_0011_routines_permissions.py` agrega los permisos `routines.read` / `routines.manage` y los otorga a dueño, gerente y entrenador; recepción, mantenimiento y contabilidad no los tienen (sección 2).
- **Biblioteca de ejercicios**: `POST/PATCH /admin/routines/exercises` administra nombre, grupo muscular, categoría, equipo, descripción, video e imagen. `GET /admin/routines/exercises` pagina y devuelve las facetas `muscle_groups` y `categories`; los ejercicios se desactivan (`is_active=false`) en vez de borrarse porque las rutinas los referencian.
- **Rutina como plantilla reutilizable**: a diferencia del borrador de la sección 6 (donde `Rutina` apuntaba a un `socio_id`), la rutina **no** pertenece a un socio. Es una plantilla del entrenador que se asigna a varios socios; el vínculo con el socio vive en `routine_assignments`. Así una misma rutina sirve de base para muchas personas sin duplicarse.
- **Versionado**: `routines.version` apunta al plan vivo. `PUT /admin/routines/{id}/items` publica la versión siguiente (`version+1`) con un juego nuevo de `routine_items`, conserva las líneas anteriores en la base y registra el motivo en `routine_revisions`. `GET /admin/routines/{id}?version=n` permite leer una versión histórica. **Ninguna asignación se modifica al publicar**: cada `routine_assignment` fija `routine_version` al crearse y el entrenamiento hereda esa versión fija, de modo que reescribir la plantilla nunca altera el historial del socio.
- **Asignaciones**: `POST /admin/routines/assignments` valida que la rutina exista, esté activa y tenga ejercicios, y que el socio exista y esté activo. Un índice único parcial (`uq_routine_assignments_active` sobre `(member_id, routine_id)` donde `status='active'`) impide dos asignaciones vivas de la misma rutina al mismo socio. Se cierran con `POST .../complete` o `POST .../cancel`; nunca se borran (retienen sus entrenamientos).
- **Archivado de rutinas**: `POST /admin/routines/{id}/archive` marca la rutina como `archived` y bloquea más ediciones, pero no cierra las asignaciones vivas: esas deben completarse o cancelarse por separado.
- **Entrenamientos**: `POST /admin/routines/assignments/{id}/workouts` solo acepta una asignación **activa**, con fecha no futura ni anterior a `start_date` del plan; guarda `performed_at`, duración, esfuerzo percibido (1–10) y notas. `POST /admin/routines/workouts/{id}/review` marca el entrenamiento como revisado por el entrenador.
- **Medidas corporales**: `POST /admin/routines/members/{id}/measurements` es **append-only**: nunca reemplaza una medida anterior, aunque se registre el mismo día (sección 5). Guarda peso, cintura, pecho y porcentaje de grasa como `Numeric` con conversión a `float` para la respuesta. `GET .../measurements` y `GET .../progress` exponen el histórico y el resumen del socio (asignaciones activas, entrenos totales, de los últimos 30 días, último entreno y última medida).
- **Números y fechas**: pesos y perímetros usan `Numeric(5,2)` / `Numeric(4,1)`; `start_date` / `end_date` / `performed_at` son fechas, y `measured_at` es un instante con zona horaria normalizado a UTC.
- **API**: 21 rutas bajo `/admin/routines/*` (resumen, ejercicios, rutinas con versiones, asignaciones, entrenamientos, medidas y progreso), todas protegidas por `routines.read` (consulta) o `routines.manage` (escritura).
- **Panel web**: la vista Rutinas tiene tres pestañas. *Seguimiento* lista asignaciones con filtros y abre un detalle con el plan asignado, los entrenamientos (registro y revisión), las mediciones (registro) y el resumen de progreso del socio. *Rutinas* lista plantillas con versión, ejercicios y asignaciones activas, permite crear una rutina con su plan, editar el plan publicando una versión nueva con motivo, y archivarla. *Ejercicios* administra la biblioteca con filtros por grupo y categoría. Todo pasa por rutas BFF bajo `/api/admin/routines/*`.
- **Datos de ejemplo**: `backend/seed_routines.py` puebla la base de vista previa (12 ejercicios, 4 rutinas —una con dos versiones—, asignaciones, entrenamientos y mediciones).

Pendiente (documentado en `docs/deuda-tecnica.md`): detalle por serie (series/peso/esfuerzo por ejercicio) en la app del socio, metas (`MetaSocio`), fotos de progreso (`FotoProgreso`), mensajería entrenador-socio, relación ejercicio-equipo que bloquee ejercicios con la máquina en mantenimiento, gráficas de evolución y notificaciones automáticas.

## 14. Estado

Primer incremento implementado y probado (biblioteca de ejercicios, rutinas con versionado y archivado, asignaciones con versión fija, registro y revisión de entrenamientos, medidas y resumen de progreso desde el panel); las metas, fotos, mensajería, gráficas y notificaciones, junto con la app del socio, quedan en diseño / validación funcional.

## 15. Historial de cambios

- 2026-10-17: primer incremento de implementación (biblioteca de ejercicios, rutinas como plantillas con versionado y archivado, asignaciones con versión fija, entrenamientos, medidas y progreso) con migraciones `20261017_0010` y `20261017_0011`, API `/admin/routines/*`, panel web con vista Rutinas, seeder de vista previa y pruebas de API.
- 2026-10-15: documento ampliado con flujos, entidades, pantallas, KPIs y criterios de aceptación.
