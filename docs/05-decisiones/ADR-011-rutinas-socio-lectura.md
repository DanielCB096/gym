# ADR-011: Rutinas y progreso de solo lectura en la app del socio

- Fecha: 2026-10-27
- Estado: propuesta inicial

## Contexto

El módulo de Rutinas ya resuelve la autoría de rutinas, el versionado y archivado, las asignaciones con versión fija, el registro de entrenamientos, las medidas corporales, las metas con cierre automático y las fotos de progreso para el panel. El socio ya tiene sesión propia (ADR-009) y app móvil con perfil y reservas de clases (ADR-010). Le falta ver qué rutina le asignaron, qué plan tiene y cómo va su progreso sin pedirle a recepción que se lo imprima.

El módulo no distingue «miembro» de «personal»: todos sus endpoints viven bajo `/admin/routines/*` y usan la matriz RBAC del personal. Exponerlos tal cual a la app daría al socio acceso a datos de otros socios y a operaciones de escritura que hoy son responsabilidad del entrenador.

## Decisión

- La app **reutiliza el módulo de rutinas**. No hay tablas, columnas ni migración nuevas: las asignaciones, versiones, entrenamientos, medidas y metas ya existen.
- `backend/src/app/modules/portal/routines.py` es una capa delgada **de solo lectura** con alcance de socio. Las reglas de negocio (versión fija de la asignación, cálculo de progreso, estado de metas) siguen en `app.modules.routines`; la capa de portal solo decide **qué ve un socio en su propio nombre**.
- Tres rutas, todas con Bearer de socio:
  - `GET /member/routines`: asignaciones propias (activas primero, luego por alta descendente) con nombre de rutina, versión, entrenador, fechas, frecuencia, estado, entrenamientos registrados y último entrenamiento; el resumen `total`/`active`/`completed`/`cancelled` se calcula en la propia capa para no reutilizar el resumen administrativo.
  - `GET /member/routines/{assignment_id}`: detalle de una asignación propia con el **plan de la versión fijada al asignar** (`routine_version`), el objetivo de la rutina y los últimos 10 entrenamientos. Recargar o editar la plantilla no altera lo que ve el socio ni su historial.
  - `GET /member/progress`: entrenamientos totales y de los últimos 30 días, último entrenamiento, la última medición, el histórico de medidas (máximo 36) y las metas del socio con su avance ya calculado.
- **Aislamiento**: el `member_id` sale siempre de la sesión autenticada; ninguna ruta acepta un identificador de socio por parámetro. Una asignación ajena responde `404` igual que una inexistente, de modo que la ruta no sirve para enumerar rutinas de otros. Un token de personal recibe `401` en `/member/*` y uno de socio en `/admin/*`.
- **Sin escritura**: registrar entrenamientos, medidas, metas y fotos de progreso sigue siendo exclusivo del panel con `routines.manage`. La app no crea, edita ni borra nada; la pantalla de detalle lo explica al pie.
- La app muestra un aviso cuando la sesión expira y vuelve al acceso, igual que el resto del portal.

## Consecuencias y límites

- El socio consulta su plan y su avance, pero **no registra** entrenamientos ni medidas desde la app; tiene que pedirlo en recepción o con su entrenador. Es deliberado mientras no exista una revisión o validación del lado del personal.
- No hay detalle por serie (series, peso, esfuerzo por ejercicio) en el historial: el entrenamiento se muestra con fecha, duración, esfuerzo y notas.
- El listado devuelve hasta 100 asignaciones y el detalle hasta 10 entrenamientos, sin paginación en la app.
- No se muestran fotos de progreso desde la app (la descarga administrativa exige `routines.read`); si se exponen habrá que decidir consentimiento, almacenamiento y auditoría de acceso.
- No hay notificaciones de rutina nueva, meta cumplida ni recordatorio de entrenamiento.
- Antes de producción: decidir si el socio podrá registrar sus propios entrenamientos y medidas con revisión posterior, exponer fotos con consentimiento explícito y agregar paginación o carga incremental.

## Referencias

- `backend/src/app/modules/portal/routines.py`
- `backend/src/app/modules/routines/service.py`
- `backend/src/app/main.py` (`/member/routines`, `/member/progress`)
- `backend/tests/test_member_routines_api.py`
- `mobile/src/screens/RoutinesScreen.tsx`
- `mobile/src/screens/RoutineDetailScreen.tsx`
- `docs/02-modulos/rutinas-y-progreso.md`
- ADR-009 (autenticación del socio)
- ADR-010 (reservas de clases desde la app)
