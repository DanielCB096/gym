# Módulo 10: Fisioterapia

## 1. Resumen y alcance

Este módulo abre el consultorio de fisioterapia dentro del club: descargas musculares y atención de molestias o lesiones que no requieren diagnóstico médico. Recepción lleva la agenda, cobra en mostrador y marca la asistencia; el socio solo consulta su saldo y sus citas desde la app y recibe un aviso cuando se le agenda una.

La regla que ordena todo el módulo es **cobrar solo lo que se prestó**: una sesión se cobra o se descuenta del paquete únicamente cuando se marca como asistida. Una inasistencia —o una llegada a la que ya no se le puede dar la sesión— no genera cargo, no consume crédito y no deja deuda.

### Incluye
- catálogo de servicios de fisioterapia con duración y precio suelto
- paquete de dos sesiones mensuales pagado en una sola exhibición, con 20 % de descuento
- agenda por fisioterapeuta que administra recepción
- cita agendada, movida y cancelada desde el panel
- cobro de la sesión suelta al marcar la asistencia y consumo de un crédito del paquete
- consulta de solo lectura en la app: saldo del paquete, próxima cita e historial
- avisos en la bandeja del socio al agendar, mover o cancelar una cita, y recordatorio 24 horas antes
- extensión de la vigencia y anulación del paquete como corrección administrativa de gerencia
- catálogo de consultorios y especialidades, con el consultorio predeterminado de cada fisioterapeuta
- reporte del consultorio: citas, asistencia, ocupación, ingresos, ajustes y exportación CSV

### No incluye
- diagnóstico médico, prescripción, incapacidades ni rehabilitación de lesiones que requieren un médico; el club ofrece descarga muscular y atención básica
- planes alimenticios (el módulo 9 los mantiene diseñados de forma genérica, sin implementar)
- reserva o cancelación desde la app: la agenda la lleva recepción y el socio solo consulta
- expediente clínico: el sistema guarda la cita y su estado, no notas clínicas ni diagnósticos
- cobro en línea: se cobra en mostrador, como cualquier otro servicio del POS

## 2. Actores y permisos

| Actor | Objetivo | Permisos clave |
|---|---|---|
| Socio | saber cuántas sesiones le quedan y cuándo es su cita | consultar su saldo y sus citas en la app; sin acciones |
| Recepción | vender paquetes, agendar, cobrar y marcar asistencia | `physio.read`, `physio.manage`, `sales.manage` |
| Fisioterapeuta | ver su agenda del día | `physio.read`; `physio.manage` solo si el club decide que también marque |
| Gerente | definir catálogo, precios y descuento | `physio.read`, `physio.manage` |
| Dueño / administrador | controlar el negocio y el crecimiento del servicio | todos los anteriores |

Tres permisos nuevos, que llevan la matriz a 36: `physio.read` (consultar catálogo, agenda y saldos), `physio.manage` (administrar el catálogo, vender paquetes, agendar, mover, cancelar y marcar asistencia) y `physio.adjust` (extender la vigencia o anular un paquete). Por defecto `physio.read` va a dueño, gerente, recepción y entrenador; `physio.manage` a dueño, gerente y recepción; `physio.adjust` solo a dueño y gerente, para que recepción opere la agenda sin decidir sobre saldos ya cobrados. El cobro no estrena permiso: se apoya en `physio.manage` y exige un turno de caja abierto, igual que el cobro de una clase premium.

## 3. Flujos paso a paso

### Flujo principal: vender el paquete de dos sesiones
1. El socio pide en recepción el paquete de dos sesiones del mes.
2. Recepción elige el paquete en el catálogo, al socio y la forma de pago (efectivo, tarjeta declarada, transferencia o cuenta).
3. El sistema exige un turno de caja abierto, registra **una sola venta de servicio** con el precio del paquete (20 % menos que las dos sesiones sueltas) y crea el paquete con dos créditos y su vigencia.
4. El socio ve el saldo en la app; no recibe aviso por la compra.

### Flujo principal: agendar una cita
1. Recepción abre la agenda del día, elige socio, servicio, fisioterapeuta y horario.
2. El sistema calcula el fin con la duración del servicio, valida que el fisioterapeuta no tenga otra cita encimada y que el socio no esté inactivo.
3. Si el socio tiene un paquete con crédito y la cita cae dentro de su vigencia, la cita queda ligada a ese paquete; si no, queda como **sesión suelta por cobrar al asistir** y la agenda lo advierte.
4. Al guardar, el socio recibe en su bandeja el aviso de la cita con día, hora y fisioterapeuta (incremento 2).

### Flujo de asistencia
1. El socio llega; recepción abre la cita y pulsa «Asistió».
2. Si la cita trae paquete, el sistema descuenta **un crédito** y no cobra nada.
3. Si es sesión suelta, recepción elige la forma de pago y el sistema registra la venta de servicio con el precio del catálogo.
4. La cita queda `attended` con quién y cuándo la marcó; si es suelta y el turno de caja está cerrado, el sistema lo rechaza y la cita sigue pendiente (no se pierde ni se cobra dos veces).

### Flujo alterno: inasistencia
1. Pasa la hora y el socio no llegó, o llegó cuando ya no había tiempo de darle la sesión.
2. Recepción marca «No asistió» (o cierra el día en lote).
3. No hay cargo, no se descuenta crédito y el paquete conserva su saldo. La cita queda `no_show` como historial.

### Flujo alterno: mover o cancelar
1. El socio llama o pasa a recepción; no puede hacerlo desde la app.
2. Recepción mueve la cita a otro horario o la cancela antes de que empiece.
3. Mover valida de nuevo el traslape y la vigencia del paquete; cancelar libera el horario. En ambos casos el socio recibe el aviso correspondiente (incremento 2).

### Flujo de cierre del día
1. Al terminar la jornada, recepción pulsa «Cerrar el día».
2. Las citas que ya terminaron y nadie marcó se cierran como `no_show`.
3. El cierre no cobra ni descuenta nada; solo deja la agenda limpia y el historial completo.

### Flujo alterno: extender o anular un paquete (gerencia)
1. El socio pide más tiempo porque estuvo enfermo, o recepción vendió un paquete por error y gerencia debe corregirlo.
2. Dueño o gerente abre el paquete en la pestaña **Paquetes** y pulsa «Extender» o «Anular»; el motivo es obligatorio.
3. Extender suma días a la vigencia sin tocar créditos ni la venta; anular cancela los créditos restantes y las citas futuras cubiertas, con su aviso al socio.
4. El ajuste queda en la bitácora del paquete con su actor, motivo y fecha. No hay devolución de dinero en ninguna de las dos rutas.

## 4. Pantallas y espacios

### 1. Panel: «Fisioterapia»
- Objetivo: operar el consultorio desde recepción
- Pestañas: **Agenda**, **Paquetes**, **Catálogo** y **Reporte** (esta última solo para quien tiene `finance.read`, como el resto de los reportes)
- Banda superior: día y conteo de citas (agendadas, asistieron, inasistencias, con paquete), botón «Agendar cita» y «Cerrar día»
- Agenda: filtros por día, fisioterapeuta y estado, más un selector **«Cobro de sesión suelta»** con la forma de pago que se usará al marcar; tabla con paciente, servicio, terapeuta, horario y consultorio, cobertura (paquete con sesiones restantes o sesión suelta), cobro (por cobrar, cobrado, reembolsado) y estado; acciones «Asistió», «No asistió» —deshabilitadas antes del inicio—, «Mover» y «Cancelar», estas dos solo para citas `scheduled` futuras, con confirmación en línea
- El alta de cita elige el consultorio del catálogo o, si se deja vacío, el que tenga asignado el fisioterapeuta
- Paquetes: búsqueda de socio, tabla con sesiones usadas y restantes, vigencia, estado y precio, y «Vender paquete» con oferta y forma de pago. Cada paquete despliega sus ajustes —extensiones y anulación— con fecha, días, motivo y actor; «Extender» y «Anular» solo aparecen con `physio.adjust`
- Catálogo: servicios con duración y precio suelto, ofertas con sesiones, precio, ahorro y vigencia, consultorios y especialidades; además, la especialidad y el consultorio por defecto de cada fisioterapeuta. Alta y edición en modal, y activar o desactivar
- Reporte: filtro de periodo, tarjetas de citas, ocupación, ingresos y ajustes, tablas por fisioterapeuta, servicio y franja horaria, serie diaria y «Exportar CSV»

### 2. Panel: marca de asistencia y cobro
- Objetivo: cobrar la sesión suelta o consumir el crédito sin ambigüedad
- La marca se hace desde la fila de la agenda; la forma de pago del cobro suelto se elige en la barra de filtros y el aviso del resultado dice cuánto se cobró y con qué método, o cuántas sesiones quedan en el paquete
- Segunda confirmación para mover o cancelar una cita y para cerrar el día: aviso en línea con «Volver» y «Confirmar», sin diálogo nativo del navegador
- Estados: cubierta por paquete, por cobrar, paquete agotado (el backend busca otro paquete vigente del socio y, si no hay, cobra la sesión suelta con la forma de pago elegida)

### 3. App del socio: «Fisioterapia»
- Objetivo: consultar, no operar
- Componentes: tarjeta de la próxima cita, saldo de cada paquete («1 de 2 sesiones», «vence el 2 de diciembre») e historial de citas con su estado
- Pie fijo: «Para mover o cancelar tu cita, acude a recepción»
- Estados: sin paquete, sin citas, cita cancelada, inasistencia

### 4. Bandeja de avisos
- Los cuatro avisos de la cita —agendada, recordatorio, movida y cancelada— se etiquetan «Fisioterapia» y abren la pantalla de fisioterapia al tocarlos

## 5. Reglas de negocio y casos límite

- **Solo `attended` cobra o descuenta.** `no_show` y `cancelled` no tocan dinero ni saldo. No hay penalización, ventana de cancelación ni deuda por inasistencia.
- **La sesión suelta no se cobra al agendar**, solo al marcar la asistencia. El cargo es una venta de servicio de una línea, con SKU `FISIO`, ligada a la cita por `sales.physio_appointment_id`.
- **El paquete es un saldo prepagado, no una suscripción**: se paga completo en una exhibición, no se renueva solo y no admite parcialidades. Si se ofreciera en parcialidades, el descuento no aplicaría.
- **El 20 % vive en el catálogo, no en el código.** El paquete guarda su precio final y el precio de lista (`sessions × precio suelto` en el momento de crear la oferta); no se recalcula si el precio suelto cambia después. Ejemplo: sesión suelta de $500 → paquete de dos por $800, con $1,000 de lista.
- **Los créditos se consumen en orden de vencimiento.** Si el socio tiene dos paquetes, se descuenta el que vence primero.
- **Una cita debe caer dentro de la vigencia de su paquete**, al agendar y al mover. Si el paquete vence antes de la cita, recepción elige otra fecha o vende otro paquete.
- **La vigencia es de 31 días desde la compra** (configurable por paquete). Los créditos no usados vencen: no se devuelven, no se transfieren y no se acumulan. Como la inasistencia no consume, el único crédito que se pierde es el que nunca se agendó.
- **Si el paquete ligado se agota entre la reserva y la asistencia**, el sistema busca otro paquete vigente del socio; si tampoco hay, marcar «Asistió» pide la forma de pago y cobra la sesión suelta en el mismo paso. Nunca se cobra sin que el operador elija cómo.
- **Se marca asistencia desde el inicio de la cita hasta 24 horas después de su fin.** En esa misma ventana se corrige una marca equivocada: `attended → no_show` reembolsa el cobro y devuelve el crédito; `no_show → attended` cobra o descuenta. Fuera de la ventana, la marca es definitiva.
- **Cancelar y mover solo antes del inicio.** Después, la cita se cierra como asistencia o inasistencia.
- **El cobro exige turno de caja abierto** y la forma de pago; sin turno responde `409` y la cita queda pendiente. Vale igual para el paquete y para la sesión suelta.
- **Un socio inactivo no puede comprar ni agendar**; un socio con membresía vencida sí, porque la fisioterapia es un servicio aparte y no se condiciona a la membresía.
- **Una cita no puede encimarse con otra del mismo fisioterapeuta.** Se valida en el servicio y se protege con un índice único sobre el inicio exacto; el traslape parcial de dos recepcionistas simultáneas es una deuda conocida, igual que en el resto de la agenda.
- **La doble marca no duplica**: la cita se lee con `SELECT ... FOR UPDATE` y el paquete también. La garantía es de PostgreSQL —en SQLite, que usan la vista previa y las pruebas, el bloqueo es no-op—, así que la carrera se comprueba con una prueba opt-in contra `TEST_POSTGRES_URL`.
- **El consultorio tiene catálogo, pero no se reserva como recurso.** La cita puede apuntar a un consultorio del catálogo o usar el predeterminado del fisioterapeuta; el sistema no impide que dos citas compartan sala, porque el cuello de botella es el fisioterapeuta.
- **No hay reembolso del paquete.** El cobro de la sesión suelta sí se puede devolver por la ruta de servicios de caja (ADR-034), que se generaliza para aceptar el vínculo con la cita.
- **Extender el paquete solo mueve la vigencia.** Suma entre 1 y 366 días desde la fecha de vencimiento si aún no vence, o desde hoy si ya venció; no toca créditos ni la venta. Exige `physio.adjust` y un motivo obligatorio, y queda en `physio_pack_adjustments` con actor y fecha.
- **Anular el paquete retira los créditos restantes sin devolver dinero.** Es una corrección administrativa (venta equivocada o cortesía): las sesiones que quedaban se registran como anuladas, y toda cita futura cubierta por el paquete se cancela con su aviso al socio. Un paquete anulado no se extiende ni se anula dos veces; uno sin créditos restantes tampoco se anula.
- **El reporte del consultorio cuenta las citas por su hora de inicio en la zona del club** y el dinero por la fecha de cada hecho: paquetes por `purchased_at`, sesiones sueltas por `sold_at` y devoluciones por `returned_at`, con el descuento otorgado calculado contra el precio de lista congelado. La ocupación estima 8 horas de agenda por fisioterapeuta y día, así que es un indicador de carga, no una medición del consultorio.
- **Los cargos caen en el ledger de ventas existente**, así que aparecen en el turno de caja, el reporte de ingresos (categoría «Servicios») y el flujo de facturación sin cambios.

## 6. Entidades de datos

| Entidad | Campos clave | Notas |
|---|---|---|
| `physio_services` | `code`, `name`, `description`, `duration_minutes`, `price_cents`, `is_active` | catálogo; el precio es el suelto |
| `physio_offers` | `service_id`, `name`, `sessions`, `price_cents`, `list_price_cents`, `validity_days`, `payment_mode`, `is_active` | paquete; `payment_mode = "single"` |
| `physio_packs` | `member_id`, `offer_id`, `sale_id`, `sessions_total`, `sessions_used`, `price_cents`, `purchased_at`, `valid_until`, `voided_at`, `voided_by`, `void_reason`, `voided_sessions` | saldo; el estado se deriva de sesiones, vigencia y anulación |
| `physio_appointments` | `member_id`, `service_id`, `pack_id`, `therapist_employee_id`, `room_id`, `room`, `starts_at`, `ends_at`, `status`, `notes`, `booked_by`, `marked_at`, `marked_by`, `cancelled_at`, `cancelled_by` | `status` en `scheduled`/`attended`/`no_show`/`cancelled`; `pack_id` es el paquete que cubre la sesión y se reasigna si al asistir el ligado ya no tenía crédito; `room_id` apunta al catálogo y `room` guarda el nombre al momento de agendar |
| `physio_rooms` | `name`, `is_active` | consultorios; se pueden desactivar sin borrar el historial |
| `physio_specialties` | `name`, `is_active` | especialidades del fisioterapeuta |
| `physio_therapist_profiles` | `employee_id` único, `specialty_id`, `room_id` | especialidad y consultorio predeterminado; el empleado sigue en `employees` |
| `physio_pack_adjustments` | `pack_id`, `kind`, `days`, `reason`, `actor_id`, `created_at` | bitácora de extensiones (`extension`) y anulaciones (`void`), solo con `physio.adjust` |
| `sales.physio_appointment_id` | FK anulable con índice | liga el cobro suelto a su cita |

`physio_packs.sale_id` liga el paquete con su venta; no hay columna inversa en `sales` porque un paquete no se reembolsa. La migración `20261029_0055_physiotherapy.py` crea las cuatro tablas y la columna, `20261029_0056_physio_permissions.py` agrega los permisos iniciales y sus concesiones, `20261029_0057_physio_notifications.py` amplía el `CHECK` de tipos de aviso con los tres de la cita, y `20261030_0058_physio_control.py` agrega consultorios, especialidades, perfiles de fisioterapeuta, la bitácora de ajustes, las columnas de anulación del paquete, `room_id` en la cita, el permiso `physio.adjust` y el tipo `physio_reminder`. La vista previa crea las tablas con `create_all`, suma columnas con `preview_patch.py`, siembra los permisos en `PREVIEW_PERMISSIONS` y los servicios y consultorios de ejemplo en `seed_physio.py`; el parche de vista previa también actualiza el `CHECK` de tipos de aviso.

## 7. API

### Panel (`physio.read` para consultar, `physio.manage` para escribir; `physio.adjust` para ajustar paquetes y `finance.read` para el reporte)
- `GET /admin/physio/services` · `POST` · `PATCH /admin/physio/services/{id}`
- `GET /admin/physio/offers` · `POST` · `PATCH /admin/physio/offers/{id}`
- `GET /admin/physio/rooms` · `POST` · `PATCH /admin/physio/rooms/{id}`
- `GET /admin/physio/specialties` · `POST` · `PATCH /admin/physio/specialties/{id}`
- `GET /admin/physio/therapists` (colaboradores activos con su especialidad y consultorio) · `PATCH /admin/physio/therapists/{employee_id}` `{specialty_id?, room_id?}`
- `GET /admin/physio/appointments?date=&therapist_id=&status=`
- `POST /admin/physio/appointments` (agendar; valida traslape, vigencia y socio)
- `PATCH /admin/physio/appointments/{id}` (mover fecha, hora, fisioterapeuta o consultorio)
- `POST /admin/physio/appointments/{id}/attendance` `{attended, payment_method?}` (consumo o cobro; la corrección usa la misma ruta)
- `POST /admin/physio/appointments/{id}/cancel`
- `POST /admin/physio/appointments/close-day` `{date}` (cierra como `no_show` lo que terminó sin marca)
- `GET /admin/physio/packs?member_id=` · `POST /admin/physio/packs` `{member_id, offer_id, payment_method}` · `GET /admin/physio/packs/{id}` (detalle con ajustes y citas)
- `POST /admin/physio/packs/{id}/extend` `{days, reason}` · `POST /admin/physio/packs/{id}/void` `{reason}` (solo `physio.adjust`)
- `GET /admin/physio/report?date_from=&date_to=` · `GET /admin/physio/report/export` (CSV diario; ambos con `finance.read`)

### App del socio
- `GET /member/physio`: paquetes con saldo y vigencia, próxima cita e historial reciente; solo lectura

### BFF del panel
Veintiuna rutas bajo `web/src/app/api/admin/physio/**` —una por recurso y acción, reutilizada por sus verbos— con `proxyAuthenticatedGet`/`proxyAuthenticatedJson`, igual que el resto del panel.

## 8. Integraciones

- **Caja y ventas**: `register_service_sale` con SKU `FISIO`; la sesión suelta y el paquete son ventas de servicio en el ledger existente.
- **Personal**: `therapist_employee_id` apunta a `employees`; la especialidad y el consultorio predeterminado viven en `physio_therapist_profiles`, así que recepción sigue eligiendo a cualquier colaborador activo y el perfil es opcional.
- **Avisos**: bandeja del socio, escritos en la misma transacción de la cita.
- **Facturación**: la venta de servicio se puede facturar con el flujo actual, sin cambios.
- **Reportes**: los cobros entran en el reporte de ingresos y el consultorio tiene su propio reporte con ocupación, inasistencia y ajustes.
- **Kiosco y hardware**: sin participación; la fisioterapia no toca el control de acceso.

## 9. Notificaciones y automatizaciones

- `physio_appointment_scheduled`: al crear la cita desde recepción, con día, hora, fisioterapeuta y la indicación de llegar 10 minutos antes. `dedupe_key = physio_scheduled:<cita>:<socio>`.
- `physio_appointment_cancelled`: al cancelar; llega al socio aunque la cancelación sea del club.
- `physio_appointment_rescheduled`: solo si cambia el inicio o el fin, con la ventana anterior y la nueva; la clave lleva el instante del cambio.
- `physio_reminder`: recordatorio 24 horas antes de la cita, con día, hora, fisioterapeuta y consultorio. Se materializa al leer la bandeja —no hay programador de tareas— y `dedupe_key = physio_reminder:<cita>:24`, así que abrir la bandeja dos veces dentro de la ventana escribe un solo aviso; si la cita se cancela, deja de coincidir y el aviso queda como historial.
- Sin push ni correo: el socio se entera al abrir su bandeja, como el resto de los avisos.
- No se avisa de la compra del paquete ni de la asistencia; no son hechos que el socio deba atender. La anulación del paquete sí avisa, porque cancela citas futuras.

## 10. Consideraciones de rendimiento

- La agenda se consulta por día y por fisioterapeuta: índices por `starts_at` y `(therapist_employee_id, starts_at)`.
- El saldo del paquete se resuelve por socio con índice `(member_id, valid_until)`; el volumen esperado es de decenas de citas al día.
- El cálculo de vigencia y saldo se hace en la lectura, sin trabajos programados.
- El cierre del día opera sobre una fecha concreta y un máximo acotado de citas, sin barridos globales.
- El reporte se calcula en una pasada por las citas del periodo, con tres agrupaciones en memoria (fisioterapeuta, servicio, hora) y una consulta de ventas y devoluciones; no guarda agregados ni necesita migración.
- El recordatorio de la cita se escribe al leer la bandeja, con una consulta acotada a las citas del socio en las próximas 24 horas.

## 11. KPIs

Los cinco salen del reporte del consultorio:
- sesiones atendidas por semana y por fisioterapeuta
- tasa de inasistencia y de cancelación
- utilización de paquetes: créditos usados contra vendidos
- ingreso por sesión suelta frente a ingreso por paquete y descuento otorgado
- ocupación del consultorio por franja horaria, estimada sobre 8 horas de agenda por fisioterapeuta y día

## 12. Criterios de aceptación

- recepción vende un paquete de dos sesiones en una sola exhibición y el sistema muestra el 20 % de ahorro y los dos créditos
- agendar fuera de la vigencia del paquete o encima de otra cita se rechaza con un mensaje claro
- marcar «Asistió» en una cita con paquete descuenta exactamente un crédito y no crea venta
- marcar «Asistió» en una sesión suelta crea una venta de servicio en el turno abierto con la forma de pago elegida
- marcar «No asistió» no crea venta ni descuenta crédito
- repetir la marca no cobra ni descuenta dos veces, y la corrección dentro de la ventana revierte el movimiento
- cerrar el día deja las citas vencidas en `no_show` sin tocar saldos
- el socio ve su saldo y su próxima cita en la app, sin botones de reserva, y recibe el aviso de la cita y el recordatorio del día anterior
- recepción no ve las acciones de ajuste del paquete y el backend responde `403` si intenta extenderlo o anularlo; gerencia sí, y el ajuste queda con su motivo y su actor
- anular un paquete cancela sus citas futuras y avisa al socio sin mover dinero; extenderlo no altera créditos ni la venta
- el reporte del periodo cuadra con las ventas de servicio y sus devoluciones, y su CSV se descarga día por día
- los cobros aparecen en el turno, el reporte de ingresos y la facturación

## 13. Estado

**Incrementos 1 y 2 implementados el 2026-10-29.** Backend, migraciones, permisos, panel, app del socio y pruebas están en la rama principal. El incremento 1 trajo las cuatro tablas y la columna `sales.physio_appointment_id` (migración `20261029_0055_physiotherapy.py`), los permisos `physio.read` y `physio.manage` con sus concesiones (`20261029_0056_physio_permissions.py`), el módulo `app/modules/physio`, los quince endpoints del panel, las rutas BFF, la página «Fisioterapia» con sus tres pestañas, el seed de vista previa (`seed_physio.py`) y nueve pruebas (ocho de API y una opt-in de concurrencia contra PostgreSQL); el flujo completo se verificó en navegador: venta de paquete, cita ligada al paquete, asistencia que descuenta un crédito, corrección que lo devuelve, sesión suelta cobrada en efectivo con su venta `FISIO` en el turno y cierre del día. El incremento 2 agregó `GET /member/physio` con su modelo de lectura (`app/modules/portal/physio.py`), los tres avisos de la cita con su migración del `CHECK` de tipos (`20261029_0057_physio_notifications.py`), la pantalla de solo lectura en la app con su tarjeta en el inicio y el enlace desde la bandeja de avisos.

**Incremento 3 implementado el 2026-10-30.** La migración `20261030_0058_physio_control.py` agrega los consultorios y especialidades con el perfil del fisioterapeuta, la bitácora `physio_pack_adjustments` con las columnas de anulación del paquete, `room_id` en la cita, el permiso `physio.adjust` (dueño y gerente) y el tipo de aviso `physio_reminder`. El paquete se puede extender —días desde su vencimiento o desde hoy si ya venció— y anular —cancela los créditos restantes y las citas futuras con su aviso, sin devolver dinero—; ambas rutas exigen motivo y quedan auditadas. El modal de cita elige consultorio del catálogo y cae al predeterminado del fisioterapeuta. El reporte del consultorio (`app/modules/physio/reports.py`) entrega citas, asistencia, ocupación sobre 8 horas por fisioterapeuta y día, ingresos de paquetes y sueltas menos devoluciones, ajustes, tablas por fisioterapeuta, servicio y hora, serie diaria y exportación CSV, y se abre con `finance.read`. La app etiqueta el recordatorio y muestra un paquete anulado. Siete pruebas nuevas (cinco en `test_physio_control_api.py` y dos en `test_member_physio_api.py`) dejan la suite en 257 pruebas: 252 pasan y 5 de concurrencia se omiten sin `TEST_POSTGRES_URL`.

**Verificación en navegador del incremento 3 (2026-10-30).** Sobre la vista previa se recorrieron la asistencia que cobra la sesión suelta, la corrección a inasistencia que reembolsa, la nueva marcación que crea otra venta dejando la anterior reembolsada, la venta, extensión y anulación del paquete —esta última cancela la cita futura con su aviso y no devuelve dinero—, la pestaña Reporte con sus tarjetas y la exportación CSV, y la app del socio con los avisos de fisioterapia. Esa pasada destapó tres correcciones: la búsqueda de socios ahora separa el término por palabras —«Carla Mendez» encuentra aunque nombre y apellido estén en columnas distintas—, la tarjeta de ocupación formatea minutos en vez de redondear a horas, y `preview_patch.py` recupera el tramo de `CHECK` de 14 a 17 tipos que faltaba, con pruebas de regresión para la búsqueda y el script de vista previa. La suite queda en 259 pruebas (254 pasan y 5 se omiten).

Lo que sigue sin cubrirse: la devolución del paquete y la reserva desde la app siguen fuera de alcance, y el consultorio todavía no impide que dos citas compartan sala.

### Incrementos previstos

1. **Catálogo, paquetes y agenda sin app.** Tablas, columna en `sales`, permisos, servicio, API, página «Fisioterapia» con sus tres pestañas y pruebas. Al terminar, recepción puede vender un paquete, agendar, cobrar, marcar asistencia y cerrar el día.
2. **El socio se entera.** `GET /member/physio`, pantalla de solo lectura en la app con su tarjeta en el inicio, y los tres avisos de la cita con su migración del `CHECK` de tipos.
3. **Control del negocio.** Reporte de demanda, ocupación e inasistencia; recordatorio de 24 horas; política de devolución o extensión del paquete; catálogo de consultorios y especialidades del fisioterapeuta.

## 14. Historial de cambios

- 2026-10-30: incremento 3 implementado —consultorios y especialidades con el perfil del fisioterapeuta, extensión y anulación del paquete con `physio.adjust` y bitácora, `room_id` en la cita, recordatorio de 24 horas, reporte del consultorio con exportación CSV y migración `20261030_0058_physio_control.py`—; pantalla de reporte, acciones de ajuste y siete pruebas nuevas.
- 2026-10-29: incremento 2 implementado —`GET /member/physio`, pantalla «Fisioterapia» de la app con su tarjeta en el inicio, los tres avisos de la cita (`physio_appointment_scheduled`, `physio_appointment_cancelled`, `physio_appointment_rescheduled`), migración `20261029_0057_physio_notifications.py` que amplía el `CHECK` de tipos y prueba de extremo a extremo del portal.
- 2026-10-29: incremento 1 implementado —tablas, columna en `sales`, permisos, servicio, catorce endpoints, BFF, página «Fisioterapia» con Agenda, Paquetes y Catálogo, seed de vista previa y nueve pruebas—; el panel envía siempre la forma de pago al marcar para poder cobrar una cita cuyo paquete se agotó antes de la visita.
- 2026-10-29: documento inicial del módulo con las políticas de cobro, agenda y paquete (ADR-039).
