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
- avisos en la bandeja del socio al agendar, mover o cancelar una cita

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

Dos permisos nuevos, que se suman a la matriz de 31: `physio.read` (consultar catálogo, agenda y saldos) y `physio.manage` (administrar el catálogo, vender paquetes, agendar, mover, cancelar y marcar asistencia). Por defecto `physio.read` va a dueño, gerente, recepción y entrenador; `physio.manage` a dueño, gerente y recepción. El cobro no estrena permiso: se apoya en `physio.manage` y exige un turno de caja abierto, igual que el cobro de una clase premium.

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

## 4. Pantallas y espacios

### 1. Panel: «Fisioterapia»
- Objetivo: operar el consultorio desde recepción
- Pestañas: **Agenda**, **Paquetes**, **Catálogo**
- Agenda: vista por día y por fisioterapeuta, con el estado de cada cita; acciones «Asistió», «No asistió», «Mover» y «Cancelar»; botón «Agendar cita» y «Cerrar el día»
- Paquetes: búsqueda por socio, sesiones usadas y restantes, vigencia y venta de un paquete nuevo
- Catálogo: servicios con duración y precio suelto, paquetes con su precio y ahorro frente al suelto, activar o desactivar

### 2. Panel: modal de asistencia
- Objetivo: cobrar la sesión suelta o consumir el crédito sin ambigüedad
- Componentes: nombre del socio, servicio, hora, saldo del paquete tras el movimiento y, cuando toca cobrar, la forma de pago
- Estados: cubierta por paquete, por cobrar, paquete agotado (busca otro paquete del socio y, si no hay, pide la forma de pago para cobrar la sesión suelta)

### 3. App del socio: «Fisioterapia»
- Objetivo: consultar, no operar
- Componentes: tarjeta de la próxima cita, saldo de cada paquete («1 de 2 sesiones», «vence el 2 de diciembre») e historial de citas con su estado
- Pie fijo: «Para mover o cancelar tu cita, acude a recepción»
- Estados: sin paquete, sin citas, cita cancelada, inasistencia

### 4. Bandeja de avisos
- Los tres avisos de la cita se etiquetan «Fisioterapia» y abren la pantalla de fisioterapia al tocarlos

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
- **El consultorio es texto libre** en la fase 1 (una sola sala en la práctica): no se valida que dos citas no compartan sala.
- **No hay reembolso del paquete** en la fase 1. El cobro de la sesión suelta sí se puede devolver por la ruta de servicios de caja (ADR-034), que se generaliza para aceptar el vínculo con la cita.
- **Los cargos caen en el ledger de ventas existente**, así que aparecen en el turno de caja, el reporte de ingresos (categoría «Servicios») y el flujo de facturación sin cambios.

## 6. Entidades de datos

| Entidad | Campos clave | Notas |
|---|---|---|
| `physio_services` | `code`, `name`, `description`, `duration_minutes`, `price_cents`, `is_active` | catálogo; el precio es el suelto |
| `physio_offers` | `service_id`, `name`, `sessions`, `price_cents`, `list_price_cents`, `validity_days`, `payment_mode`, `is_active` | paquete; `payment_mode = "single"` |
| `physio_packs` | `member_id`, `offer_id`, `sale_id`, `sessions_total`, `sessions_used`, `price_cents`, `purchased_at`, `valid_until` | saldo; sin estado persistido, se deriva de sesiones y vigencia |
| `physio_appointments` | `member_id`, `service_id`, `pack_id`, `therapist_employee_id`, `room`, `starts_at`, `ends_at`, `status`, `notes`, `booked_by`, `marked_at`, `marked_by`, `cancelled_at`, `cancelled_by` | `status` en `scheduled`/`attended`/`no_show`/`cancelled`; `pack_id` es el paquete que cubre la sesión y se reasigna si al asistir el ligado ya no tenía crédito |
| `sales.physio_appointment_id` | FK anulable con índice | liga el cobro suelto a su cita |

`physio_packs.sale_id` liga el paquete con su venta; no hay columna inversa en `sales` porque un paquete no se reembolsa en la fase 1. La migración `20261029_0055_physiotherapy.py` crea las cuatro tablas y la columna, y `20261029_0056_physio_permissions.py` agrega los dos permisos y sus concesiones. La vista previa crea las tablas con `create_all`, suma la columna con `preview_patch.py`, siembra los permisos en `PREVIEW_PERMISSIONS` y los servicios de ejemplo en `seed_physio.py`.

## 7. API

### Panel (permiso `physio.read` para consultar, `physio.manage` para escribir)
- `GET /admin/physio/services` · `POST` · `PATCH /admin/physio/services/{id}`
- `GET /admin/physio/offers` · `POST` · `PATCH /admin/physio/offers/{id}`
- `GET /admin/physio/appointments?date=&therapist_id=&status=`
- `POST /admin/physio/appointments` (agendar; valida traslape, vigencia y socio)
- `PATCH /admin/physio/appointments/{id}` (mover fecha, hora o fisioterapeuta)
- `POST /admin/physio/appointments/{id}/attendance` `{attended, payment_method?}` (consumo o cobro; la corrección usa la misma ruta)
- `POST /admin/physio/appointments/{id}/cancel`
- `POST /admin/physio/appointments/close-day` `{date}` (cierra como `no_show` lo que terminó sin marca)
- `GET /admin/physio/packs?member_id=` · `POST /admin/physio/packs` `{member_id, offer_id, payment_method}`

### App del socio (incremento 2)
- `GET /member/physio`: paquetes con saldo y vigencia, próxima cita e historial reciente; solo lectura

### BFF del panel
Una ruta por endpoint bajo `web/src/app/api/admin/physio/**`, con `proxyAuthenticatedGet`/`proxyAuthenticatedJson`, igual que el resto del panel.

## 8. Integraciones

- **Caja y ventas**: `register_service_sale` con SKU `FISIO`; la sesión suelta y el paquete son ventas de servicio en el ledger existente.
- **Personal**: `therapist_employee_id` apunta a `employees`; el sistema todavía no modela especialidades, así que recepción elige a cualquier colaborador activo.
- **Avisos**: bandeja del socio, escritos en la misma transacción de la cita (incremento 2).
- **Facturación**: la venta de servicio se puede facturar con el flujo actual, sin cambios.
- **Reportes**: los cobros ya entran en el reporte de ingresos; el reporte propio del consultorio se planea para el incremento 3.
- **Kiosco y hardware**: sin participación; la fisioterapia no toca el control de acceso.

## 9. Notificaciones y automatizaciones

- `physio_appointment_scheduled`: al crear la cita desde recepción, con día, hora, fisioterapeuta y la indicación de llegar 10 minutos antes. `dedupe_key = physio_scheduled:<cita>:<socio>`.
- `physio_appointment_cancelled`: al cancelar; llega al socio aunque la cancelación sea del club.
- `physio_appointment_rescheduled`: solo si cambia el inicio o el fin, con la ventana anterior y la nueva; la clave lleva el instante del cambio.
- Sin push ni correo: el socio se entera al abrir su bandeja, como el resto de los avisos.
- El recordatorio de 24 horas queda para el incremento 3, con el mismo mecanismo diferido de `class_reminder`.
- No se avisa de la compra del paquete ni de la asistencia; no son hechos que el socio deba atender.

## 10. Consideraciones de rendimiento

- La agenda se consulta por día y por fisioterapeuta: índices por `starts_at` y `(therapist_employee_id, starts_at)`.
- El saldo del paquete se resuelve por socio con índice `(member_id, valid_until)`; el volumen esperado es de decenas de citas al día.
- El cálculo de vigencia y saldo se hace en la lectura, sin trabajos programados.
- El cierre del día opera sobre una fecha concreta y un máximo acotado de citas, sin barridos globales.

## 11. KPIs

- sesiones atendidas por semana y por fisioterapeuta
- tasa de inasistencia y de cancelación
- utilización de paquetes: créditos usados contra vendidos
- ingreso por sesión suelta frente a ingreso por paquete y descuento otorgado
- ocupación del consultorio por franja horaria

## 12. Criterios de aceptación

- recepción vende un paquete de dos sesiones en una sola exhibición y el sistema muestra el 20 % de ahorro y los dos créditos
- agendar fuera de la vigencia del paquete o encima de otra cita se rechaza con un mensaje claro
- marcar «Asistió» en una cita con paquete descuenta exactamente un crédito y no crea venta
- marcar «Asistió» en una sesión suelta crea una venta de servicio en el turno abierto con la forma de pago elegida
- marcar «No asistió» no crea venta ni descuenta crédito
- repetir la marca no cobra ni descuenta dos veces, y la corrección dentro de la ventana revierte el movimiento
- cerrar el día deja las citas vencidas en `no_show` sin tocar saldos
- el socio ve su saldo y su próxima cita en la app, sin botones de reserva, y recibe el aviso de la cita
- los cobros aparecen en el turno, el reporte de ingresos y la facturación

## 13. Estado

En diseño. Documento inicial del 2026-10-29 con las tres políticas decididas: cobro solo por asistencia, agenda de recepción con consulta en la app y paquete mensual de dos sesiones al 80 % en una sola exhibición (ADR-039).

### Incrementos previstos

1. **Catálogo, paquetes y agenda sin app.** Tablas, columna en `sales`, permisos, servicio, API, página «Fisioterapia» con sus tres pestañas y pruebas. Al terminar, recepción puede vender un paquete, agendar, cobrar, marcar asistencia y cerrar el día.
2. **El socio se entera.** `GET /member/physio`, pantalla de solo lectura en la app con su tarjeta en el inicio, y los tres avisos de la cita con su migración del `CHECK` de tipos.
3. **Control del negocio.** Reporte de demanda, ocupación e inasistencia; recordatorio de 24 horas; política de devolución o extensión del paquete; catálogo de consultorios y especialidades del fisioterapeuta.

## 14. Historial de cambios

- 2026-10-29: documento inicial del módulo con las políticas de cobro, agenda y paquete (ADR-039).
