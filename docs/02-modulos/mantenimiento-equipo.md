# Módulo 8: Mantenimiento de equipo e instalaciones

## 1. Resumen y alcance

Este módulo gestiona todo lo relacionado con la disponibilidad física del gimnasio: máquinas, instalaciones, limpieza, mantenimientos preventivos y correctivos, y la comunicación de estado a socios y staff. El objetivo es mantener la operación confiable, evitar caídas de servicio y dar visibilidad clara a los usuarios del gimnasio.

### Incluye
- registro de equipos con modelo, serie, ubicación, vida útil y costo
- mantenimientos preventivos y correctivos
- tickets por falla reportada
- control de equipos fuera de servicio
- aviso en la app del socio cuando el equipo que necesita su plan vigente queda fuera de servicio
- checklist de limpieza y inspección por áreas
- historial técnico y costos asociados

### No incluye
- obra civil mayor o remodelaciones estructurales complejas
- gestión de mantenimiento de vehículos internos
- contratos de seguridad o administración de instalaciones de terceros

## 2. Actores y permisos

| Actor | Objetivo | Permisos clave |
|---|---|---|
| Mantenimiento | atender fallas, inspecciones y preventivos | crear tickets, cerrar tareas, registrar costos |
| Gerente | priorizar tareas y revisar costos | ver flota de equipos, estados críticos, presupuestos |
| Dueño | revisar inversión y estrategia de reemplazo | reports ejecutivos y compras |
| Recepción | avisar a clientes y evitar mal uso | marcar equipo fuera de servicio |
| Socio | conocer disponibilidad real del equipo | ver indicadores de servicio y avisos |

## 3. Flujos de usuario paso a paso

### Flujo principal: reporte de falla
1. Un socio, instructor o recepcionista detecta una falla o un riesgo de seguridad.
2. Se crea un ticket con foto, ubicación, descripción y severidad.
3. El sistema identifica el equipo, su estado y su historial.
4. Se asigna el ticket a mantenimiento o se prioriza por impacto en operación.
5. Se marca el equipo como “fuera de servicio” si aplica.
6. El personal ejecuta la reparación y luego valida la operación segura.

### Flujo de mantenimiento preventivo
1. Se genera una agenda por equipo, tipo de mantenimiento y fecha estimada.
2. El técnico revisa indicadores de desgaste, uso y vida útil.
3. Se ejecuta inspección, lubricación, ajuste o limpieza.
4. Se registra la actividad y fecha del siguiente mantenimiento.

### Flujo de reemplazo
1. El equipo supera el ciclo de vida o el costo de reparación es excesivo.
2. El gerente valida costos, proveedor y disponibilidad de reemplazo.
3. Se lanza la orden de compra y se registra la baja del equipo antiguo.
4. El equipo nuevo queda operativo con historial asociado.

### Flujo de avisos a socios
1. Un equipo queda fuera de servicio por mantenimiento o riesgo.
2. El sistema bloquea la reserva o la visualización de ese equipo en app y kiosco.
3. Se publica un aviso con impacto, horario estimado y alternativa disponible.

## 4. Pantallas / espacios

### 1. Inventario de equipos
- Objetivo: revisar todos los equipos por área, marca, modelo y estado
- Componentes: búsqueda, filtros, vida útil, costo de mantenimiento, ubicaciones
- Estados: operativo, en mantenimiento, fuera de servicio, en revisión

### 2. Dashboard de mantenimiento
- Objetivo: priorizar tareas urgentes y comparar indicadores
- Componentes: tickets abiertos, MTTR, equipos críticos, costo acumulado, próximos preventivos
- Estados: normal, crítico, vencido

### 3. Ticket de falla
- Objetivo: permitir reportar, asignar y resolver fallas
- Componentes: foto, descripción, prioridad, responsable, fecha estimada, costo
- Estados: abierto, asignado, en proceso, resuelto, cancelado

### 4. Checklist de limpieza e inspección
- Objetivo: asegurar estándares del gimnasio
- Componentes: listado de áreas, parámetros, responsables, resultad, observaciones
- Estados: pendiente, cumplido, con observación

### 5. Historial técnico 
- Objetivo: tener trazabilidad de cada equipo
- Componentes: mantenimientos, costos, piezas, fallas, garantía, vida útil
- Estados: completo, incompleto, vencida

### 6. Estados de servicio para clientes
- Objetivo: mostrar disponibilidad a socios y personal
- Componentes: aviso, horario de reparación, equipo alternativo, impacto por área
- Estados: disponible, parcial, cerrado, de baja temporal

## 5. Reglas de negocio y casos límite

### Reglas clave
- Cualquier equipo con riesgo de seguridad debe quedar bloqueado de uso inmediato.
- Los equipos fuera de servicio deben reflejarse en app, kiosco y panel de administración. Hoy la app lo hace por la bandeja de avisos del socio (`equipment_out_of_service`, ADR-018) y el panel por la advertencia del plan y el estado de la flota; el kiosco sigue pendiente.
- Todo mantenimiento debe quedar asociado a un responsable, fecha y costo si aplica.
- No se puede cerrar un ticket sin evidencias de revisión o resolución.
- Los equipos con mantenimiento vencido deben aparecer en dashboard prioritario.
- Las compras y reemplazos deben registrarse con proveedor, costo y justificación técnica.

### Casos límite
- Una máquina queda dañada en horario pico y afecta la operación.
- El equipo no tiene historial previo ni piezas de repuesto.
- Se reporta una falla de seguridad por parte del cliente que requiere bloqueo inmediato.
- El costo de reparación supera el valor útil esperado del equipo.
- Dos áreas reportan la misma falla con distinta prioridad.

## 6. Entidades de datos

- Equipo
- MarcaEquipo
- CategoriaEquipo
- UbicacionEquipo
- TicketMantenimiento
- HistorialMantenimiento
- ChecklistLimpieza
- Proveedor
- OrdenCompraEquipo
- CostoMantenimiento
- FallaEquipo
- UsuarioAsignado

### Campos clave
- Equipo: id, nombre, modelo, serial, marca_id, ubicacion_id, fecha_compra, vida_util, estado
- TicketMantenimiento: id, equipo_id, tipo, severidad, descripcion, reporte_por, estado, responsable_id
- HistorialMantenimiento: id, equipo_id, tipo, fecha, notas, costo, tecnico_id
- ChecklistLimpieza: id, ubicacion_id, fecha, responsable_id, inspeccion, observaciones

## 7. Integraciones con otros módulos

- Control de acceso: si un equipo está fuera de servicio en una zona, debe impactar la experiencia del usuario.
- Membresías: algunos equipos tienen acceso premium o restricción por plan.
- Punto de venta: consumibles y herramientas de mantenimiento pasan por inventario.
- Facturación y reportes: costos de mantenimiento y compras afectan reportes de gastos y análisis financiero.
- Clases y rutinas: las áreas con equipos críticos afectan disponibilidad de clases o entrenamiento.

## 8. Notificaciones y automatizaciones

- **aviso de ticket asignado al técnico** — implementado: al crear o editar un ticket con `assigned_to`, el módulo `notifications` escribe `maintenance_ticket_assigned` en la bandeja del panel de la cuenta vinculada a ese empleado, dentro de la misma transacción del ticket (ver `notificaciones-del-socio.md` y ADR-017)
- **aviso de equipo fuera de servicio a los socios** — implementado para la app: cuando un equipo pasa a `out_of_service` (por `set_equipment_status` o porque un ticket `critical` lo bloquea), se escribe `equipment_out_of_service` en la bandeja de **cada socio cuyo plan vigente usa un ejercicio vinculado a esa máquina** (ADR-018). Pendiente: kiosco y cartel de recepción.
- alerta de mantenimiento preventivo vencido
- recordatorio de inspección de limpieza por área
- ticket escalado por severidad o tiempo de respuesta
- recomendación de compra o reemplazo por antigüedad y costo

## 9. Consideraciones de rendimiento específicas del módulo

- filtros por área, estado, tipo de equipo y prioridad
- caché del inventario de equipos para app y recepción
- indices por `equipo_id`, `ubicacion_id`, `estado`, `fecha_programada`, `prioridad`
- render rápido de listas de equipos para pantallas táctiles y app móvil
- carga asíncrona de historial técnico cuando hay muchos movimientos

## 10. KPIs

- disponibilidad total del equipo (%)
- tiempo promedio de resolución (MTTR)
- tiempo medio entre fallas (MTBF)
- porcentaje de preventivos cumplidos
- costo por mantenimiento y por equipo
- equipos fuera de servicio por área

## 11. Preguntas abiertas

- ¿se manejará mantenimiento por equipo individual o por sesión de máquina general?
- ¿se incluirá limpieza y abuso de equipo como parte del mismo flujo?
- ¿el app debe mostrar solo “fuera de servicio” o también estimado de regreso?

## 12. Criterios de aceptación

- Cada equipo tiene estado visible, historial y responsable.
- Un equipo en riesgo se bloquea automáticamente y se informa a la operación.
- Todo ticket tiene flujo claro de asignación, ejecución y cierre.
- Los costos de mantenimiento y reemplazo quedan registrados y vinculados a gastos.
- La disponibilidad del equipo se refleja de forma consistente en app, kiosco y panel administrativo.

## 13. Implementación actual y límites

Primer incremento entregado (2026-10-17), **autocontenido**: no habla con proveedores ni genera órdenes de compra. En 2026-10-27 dejó de estar del todo aislado del socio: la caída de un equipo escribe un aviso en su bandeja (ADR-018) y la asignación de un ticket escribe uno en la campana del panel (ADR-017). Cubre la operación diaria desde el panel (flota, tickets, bitácora y rondas).

- **Entidades del borrador colapsadas**: las entidades sueltas de la sección 6 no se crearon como tablas. `MarcaEquipo`, `CategoriaEquipo` y `UbicacionEquipo` son las columnas `brand`, `category` y `location` de `equipment` (texto libre, con `categories`/`locations` devueltos como facetas del listado); `CostoMantenimiento` es `maintenance_records.cost_cents`; `FallaEquipo` es el propio ticket; `UsuarioAsignado` es `maintenance_tickets.assigned_to` / `maintenance_records.technician_id` (colaboradores de Personal y roles). `Proveedor` y `OrdenCompraEquipo` se difieren al módulo de compras (ver `docs/deuda-tecnica.md`).
- **Persistencia**: cuatro tablas nuevas —`equipment`, `maintenance_tickets`, `maintenance_records` y `maintenance_checklists`— creadas por la migración `20261017_0012_maintenance.py` con sus índices. La migración `20261017_0013_maintenance_permissions.py` amplía `maintenance.read` a recepción y entrenador y siembra el permiso nuevo `maintenance.report`. La migración `20261017_0014_exercises_equipment_link.py` agrega `exercises.equipment_id` (clave foránea con `ON DELETE SET NULL`) para vincular la biblioteca de ejercicios con la flota.
- **Estados**: equipo `operational` (operativo), `maintenance` (en mantenimiento), `out_of_service` (fuera de servicio), `inspection` (en revisión) y `retired` (baja). Ticket `open`, `assigned`, `in_progress`, `resolved` y `cancelled`, con `kind` `corrective`/`preventive` y `severity` `low`/`medium`/`high`/`critical`. Registro técnico `preventive`, `corrective`, `inspection`, `cleaning` y `calibration`. Ronda `ok`, `observation` y `pending`.
- **Regla de bloqueo**: un ticket de severidad **crítica** saca el equipo de servicio de inmediato (`out_of_service`) y guarda el estado previo en `tickets.previous_status`; al **iniciar** la reparación, un equipo operativo o en revisión pasa a `maintenance` (también recordando su estado previo). Resolver o cancelar un ticket **solo** devuelve el equipo a su estado previo si ese ticket lo estaba reteniendo (`blocked_equipment`), de modo que cerrar un ticket de baja severidad que nunca tocó la máquina no altera su estado.
- **Resolución obligatoria con evidencia**: `POST .../resolve` exige `resolution_notes` no vacío, marca el ticket como `resolved`, crea de forma **append-only** un `maintenance_record` de tipo correctivo (con costo y técnico) y libera el equipo. Cancelar exige motivo cuando el ticket tenía bloqueado el equipo.
- **Baja, nunca borrado**: `POST /admin/maintenance/equipment/{id}/retire` deja el equipo en `retired` (no se elimina) y rechaza la baja si aún tiene tickets abiertos. Un equipo retirado rechaza tickets nuevos, cambios de estado y registros.
- **Preventivos**: un registro de tipo `preventive` con `next_due_on` actualiza `equipment.next_preventive_due`; el resumen y el listado cuentan como **vencidos** los equipos operativos o en revisión cuya fecha ya pasó.
- **Rondas de limpieza/inspección**: `maintenance_checklists` guarda el área como texto (el borrador no definía una entidad de área), el resultado y las observaciones; un resultado `observation` exige `observations` no vacío.
- **Folio de ticket**: `MT-{YYYYMMDD}-{hex6}`, generado en el servicio; la fecha es el **día local del gimnasio** (`APP_TIMEZONE`), no el día UTC.
- **Asignación con aviso**: cuando `create_ticket` o `update_ticket` reciben `assigned_to`, se escribe `maintenance_ticket_assigned` en `staff_notifications` de la cuenta cuyo `AppUser.employee_id` coincide con el empleado, en la misma transacción. Si el empleado **no tiene cuenta activa** el aviso se omite y la asignación se guarda igual; el `dedupe_key` `maintenance_ticket_assigned:<ticket>:<empleado>` hace que re-guardar el mismo técnico no re-anuncie el ticket, aunque una reasignación A → B → A tampoco vuelve a avisar a A.
- **Permisos**: `maintenance.read` (consulta) lo tienen dueño, gerente, mantenimiento, recepción y entrenador; `maintenance.report` (crear ticket y fijar estado del equipo) lo tienen dueño, gerente, mantenimiento, recepción y entrenador; `maintenance.manage` (alta/edición/baja de equipos, gestión y cierre de tickets, registros y rondas) lo tienen dueño, gerente y mantenimiento; contabilidad no participa.
- **Vínculo ejercicio↔equipo**: `exercises.equipment_id` es opcional; los ejercicios y las líneas de rutina exponen `equipment_status` y el plan de la rutina muestra una **advertencia suave** (`Equipo en mantenimiento` / `Fuera de servicio`) cuando la máquina vinculada no está operativa. No bloquea el ejercicio: es aviso, no prohibición. Vincular un equipo inexistente o retirado responde `422`.
- **Caída del equipo con aviso al socio**: `_members_using_equipment` resuelve la audiencia uniendo `routine_assignments` → `routine_items` **por la versión congelada de la asignación** → `exercises.equipment_id` con `DISTINCT`, y `notify_equipment_out_of_service` escribe una fila por socio con `dedupe_key` `equipment_out_of_service:<equipo>:<socio>:<YYYYMMDD>` sobre el **día del club** (`club_date`), así que rebotar la máquina el mismo día no repite el aviso pero una caída en un día posterior sí. El mensaje nombra equipo y lugar y **no** incluye el título del ticket; no hay aviso cuando el equipo vuelve a `operational`. El import de `routines.models` es perezoso, como en `_linked_exercises`: mantenimiento no importa rutinas al cargar el módulo y el módulo de avisos sigue sin conocer esas tablas.
- **API**: 21 rutas bajo `/admin/maintenance/*` — resumen, directorio y opciones de equipos, alta/edición/estado/baja, registros por equipo y globales, tickets con asignación/inicio/resolución/cancelación, rondas y estado de servicio por área.
- **Panel web**: la vista Mantenimiento tiene cuatro pestañas. *Equipos* lista la flota con filtros (texto, estado, categoría, ubicación), resumen y estado de servicio por área, y abre la ficha con estado, datos, historial técnico y tickets, además de cambiar estado, registrar servicio, editar ficha y dar de baja. *Tickets* lista y filtra por estado y severidad, y abre el detalle para asignar, iniciar, resolver y cancelar. *Bitácora* lista los registros técnicos con costo acumulado. *Rondas* lista las limpiezas e inspecciones y permite registrar una nueva. Todo pasa por rutas BFF bajo `/api/admin/maintenance/*`.
- **Datos de ejemplo**: `backend/seed_maintenance.py` puebla la vista previa (12 equipos, 5 tickets —incluido uno crítico abierto y una falla resuelta—, registros preventivos y rondas) y vincula la biblioteca de ejercicios con la flota, incluida una banda de correr en mantenimiento para que el plan de rutina muestre la advertencia.

Pendiente (documentado en `docs/deuda-tecnica.md`): aviso de equipo fuera de servicio en **kiosco y recepción** (la app del socio ya lo recibe, ADR-018); proveedores y órdenes de compra; presupuesto y recomendación de reemplazo; adjuntos/fotos en tickets; métricas MTTR/MTBF; umbrales de escalado por tiempo; y definir si las rondas deben ligarse a una entidad de área propia.

## 14. Estado

Primer incremento implementado y probado (equipos con estado y baja, tickets con bloqueo y restauración, bitácora técnica append-only, rondas de limpieza e inspección, estado de servicio por área y vínculo ejercicio↔equipo) y conectado al panel; **la asignación de un ticket ya avisa al técnico en la campana del panel** (`maintenance_ticket_assigned`, tabla `staff_notifications`, ADR-017) y **la caída de un equipo ya avisa a los socios cuyo plan lo usa** (`equipment_out_of_service`, tabla `member_notifications`, ADR-018). El aviso al kiosco y a recepción, los proveedores y órdenes de compra, el presupuesto de reemplazo y los adjuntos en tickets quedan en diseño / validación funcional.

## 15. Historial de cambios

- 2026-10-27: la **caída del equipo avisa a los socios**. `set_equipment_status` y `_block_equipment` (alta y escalada de un ticket `critical`) emiten `equipment_out_of_service` en `member_notifications` para cada socio cuyo plan vigente —casando `routine_version` congelada con `exercises.equipment_id`— usa un ejercicio vinculado a esa máquina, con deduplicación por `(equipo, socio, día del club)`. Consulta nueva `_members_using_equipment` con import perezoso de `routines.models`; sin rutas, permisos ni estados nuevos. Documentado en ADR-018; el kiosco y recepción siguen pendientes.
- 2026-10-27: la asignación de un ticket (`create_ticket` / `update_ticket` con `assigned_to`) emite el aviso `maintenance_ticket_assigned` en la bandeja del panel del técnico, sobre la nueva tabla `staff_notifications` (migración `20261027_0036_staff_notifications.py`), con deduplicación por ticket y empleado y omisión silenciosa cuando el empleado no tiene cuenta activa. Sin cambios de rutas, permisos ni estados del ticket.
- 2026-10-18: el folio de ticket `MT-…` pasa a usar la fecha del **día local del gimnasio** (`APP_TIMEZONE`) en vez de UTC, para alinearse con las ventas, las devoluciones y los reportes; se agregó una prueba.
- 2026-10-17: primer incremento de implementación (equipos con estado y baja, tickets con bloqueo/restauración y folio, bitácora técnica append-only, rondas de limpieza e inspección, estado por área y vínculo ejercicio↔equipo) con las migraciones `20261017_0012`, `20261017_0013` y `20261017_0014`, API `/admin/maintenance/*`, panel web con la vista Mantenimiento, seeder de vista previa y pruebas de API.
- 2026-10-15: documento ampliado con flujos operativos, pantallas, reglas, KPI e integraciones.
