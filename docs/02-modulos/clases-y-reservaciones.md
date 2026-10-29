# Módulo 4: Clases y reservaciones

## 1. Resumen y alcance

Este módulo cubre la programación de clases, la reserva por parte de los socios, la lista de espera, la asistencia, la agenda del instructor y el cálculo de clases pagadas o inclusivas según la membresía. Está pensado para maximizar la ocupación del gimnasio sin crear fricción operativa.

### Incluye
- calendario semanal y mensual de clases
- cupos, salón, instructor y lista de espera
- reserva desde la app y desde recepción
- cancelación con políticas configurables
- asistencia por instructor o recepción
- clases incluidas vs. de pago extra

### No incluye
- venta de servicios extra de entrenamiento personalizado (se manejará en servicios extra)
- rutinas de entrenamiento individualizadas (módulo separado)

## 2. Actores y permisos

| Actor | Objetivo | Permisos clave |
|---|---|---|
| Socio | reservar y cancelar clases | consultar agenda, reservar, cancelar y ver asistencia |
| Instructor | gestionar clase e invitados | crear clase, marcar asistencia, ver lista y cambiar cupo |
| Recepcionista | apoyar operación | dar de alta clases, subir lista de espera, confirmar reservas |
| Gerente | definir programación y política | crear horarios, cambiar cupos y revisar ocupación |
| Dueño / administrador | controlar negocio general | ajustes globales de precios, políticas y seguridad |

## 3. Flujos de usuario paso a paso

### Flujo principal: reserva de una clase
1. El socio abre la app y entra a calendario.
2. Selecciona fecha, hora y clase disponible.
3. El sistema valida que la clase todavía tenga cupo y que el socio tenga acceso según su membresía.
4. Si todo es válido, crea la reserva y registra el cupo ocupado.
5. El socio recibe confirmación por app y notificación de recordatorio.

### Flujo alterno: reserva en lista de espera
1. Cuando la clase está llena, el socio entra a lista de espera.
2. El sistema le asigna prioridad por orden de llegada o por política del gimnasio.
3. Si alguien cancela, el siguiente en la lista es notificado automáticamente.
4. La lista se mantiene visible para la recepción y el instructor.

### Flujo de cancelación
1. El socio selecciona la clase reservada.
2. El sistema valida si está dentro de la ventana de cancelación.
3. Si aplica, se libera el cupo y se registra la cancelación.
4. Si la cancelación es fuera de ventana, se aplica penalización según la política del plan.

### Flujo de asistencia
1. El instructor o la recepción marca la asistencia.
2. El sistema valida que el socio tenga reserva activa.
3. Se actualiza el estado y se refleja en la app del socio.
4. Si el socio no asistió, la inasistencia queda registrada con política configurable.

## 4. Pantallas / espacios

### 1. Calendario de clases
- Objetivo: ver disponibilidad por día, salón e instructor
- Componentes: filtros por fecha, tipo de clase, salón, instructor, nivel y cupo
- Estados: disponible, lleno, lista de espera, cancelada

### 2. Detalle de clase
- Objetivo: ver información relevante antes de reservar
- Componentes: nombre, horario, instructor, salón, cupo disponible, requisitos, lista de asistentes
- Estados: activa, llena, cancelada, completa

### 3. App del socio
- Objetivo: reservar, confirmar y cancelar clases
- Componentes: calendario, botón de reserva, historial de clases y estado de asistencia
- Estados: reservada, cancelada, lista de espera, asistida, no asistida

### 4. Agenda del instructor
- Objetivo: gestionar clases, participantes y asistencia
- Componentes: agenda del día, lista de socios, lista de espera, nota de clase, faltas
- Estados: programada, en curso, finalizada, cancelada

### 5. Panel administrativo
- Objetivo: configurar clases y supervisar ocupación y incidencias
- Componentes: crear/editar clase, definir cupo y sala, revisar ocupación, alertas de cancelación
- Estados: activo, lleno, pausado, cancelado

## 5. Reglas de negocio y casos límite

### Reglas clave
- Una clase solo acepta reservas si hay cupo disponible.
- La lista de espera debe mantener orden de llegada y prioridad según política del gimnasio.
- El socio debe tener acceso a la clase según su membresía o paquete asociado.
- Las cancelaciones dentro de una ventana definida no sancionan; fuera de esa ventana sí aplican penalizaciones.
- Las clases gratuitas y de pago deben diferenciarse en la lógica de acceso.
- Si una clase se cancela, todos los socios reservados deben ser notificados y el cupo liberado.

### Casos límite
- Clase con 1 plaza libre y dos socios intentando reservar simultáneamente.
- Socio con reserva ya confirmada y lista de espera activa.
- Clase con cupo 0 y notificación automática a lista de espera.
- Inasistencia repetida por un socio con política de penalización por clase.
- Instructor no puede asistir y la clase debe reprogramarse.

## 6. Entidades de datos

- Clase
- Instructor
- Salón
- ReservaClase
- ListaEsperaClase
- AsistenciaClase
- PaqueteClase
- TipoClase
- PoliticaCancelacion
- HistorialClase

### Campos clave
- Clase: id, nombre, tipo, instructor_id, salón_id, fecha_hora_inicio, fecha_hora_fin, cupo_total, cupo_disponible, estado
- ReservaClase: id, socio_id, clase_id, estado, fecha_reserva, origen (app, recepción, web), cancelada_en
- ListaEsperaClase: id, socio_id, clase_id, posicion, estado, fecha_solicitud
- AsistenciaClase: id, reserva_id, socio_id, clase_id, estado (presente, ausente, no marcado), marcado_por

## 7. Integraciones con otros módulos

- Membresías: validan si una clase está incluida, limitada o disponible según plan.
- Control de acceso: si el socio ya tiene su entrada válida y marca asistencia, el flujo se integra con la puerta.
- Personal y roles: instructor y recepcionista tienen permisos específicos.
- Comunicación: recordatorios, listas de espera, cancelaciones y confirmaciones.
- Facturación: las clases de pago extra se cobran al marcar la asistencia como una venta de servicio ligada a la reserva, con su turno, forma de pago y reembolso (ADR-033).

## 8. Notificaciones y automatizaciones

- Recordatorio 24 h y 2 h antes de la clase, en la bandeja de avisos del socio. Es diferido —se escribe al leer la bandeja o la insignia, sin push— y se deduplica por reserva y ventana (ADR-035).
- Confirmación de reserva exitosa.
- Aviso a la lista de espera cuando alguien cancela, cuando sube el aforo o cuando se marca una inasistencia antes de la clase: en los tres casos se promueve a la cabeza y se avisa al promovido.
- Notificación de clase cancelada o reprogramada (pendiente).
- Alertas de inasistencia recurrente con política configurable.

## 9. Consideraciones de rendimiento específicas del módulo

- índices por `fecha_hora_inicio`, `instructor_id`, `salon_id`, `estado`
- caché de clases activas del día para la app del socio
- paginación y filtros por fecha para calendarios de alta concurrencia
- procesamiento de lista de espera y avisos mediante cola para evitar bloqueo de UX
- uso de transacciones para reservar una plaza y liberar cupo al cancelar

## 10. KPIs

- ocupación promedio por clase
- tasa de cancelación
- porcentaje de lista de espera convertida en reserva
- tasa de asistencia real
- número de clases activas por instructor
- tasa de no asistencias por plan o socio

## 11. Preguntas abiertas

- ¿las clases pagadas se venden como paquete o por reserva individual?
- ¿la penalización por inasistencia aplica a todas las clases o solo a clases premium?
- ¿la lista de espera se ordena por tiempo o por prioridad del socio?
- ¿las clases tienen cupo fijo o se ajusta por capacidad real del salón?

## 12. Criterios de aceptación

- El socio puede reservar una clase solo si hay cupo disponible y tiene acceso según su plan.
- Si la clase está llena, el socio puede entrar a lista de espera y ser notificado al liberarse un cupo.
- La cancelación fuera de la ventana genera penalización según la política del gimnasio.
- La asistencia se registra y refleja en la app del socio y en la agenda del instructor.
- Las clases canceladas liberan la plaza y notifican a los socios afectados.
- La lista de espera se respeta en orden y se actualiza en tiempo real.

## 13. Implementación actual y límites

Primer incremento entregado (2026-10-17), centrado en la operación de la agenda desde el panel, sin app del socio ni cobro de clases premium:

- **Persistencia**: cuatro tablas nuevas (`class_types`, `class_rooms`, `class_sessions`, `class_reservations`) creadas por la migración `20261017_0009_classes.py`. No se agregaron permisos: `classes.read` / `classes.manage` ya existían desde la migración de RBAC y están otorgados a dueño, gerente e instructor; recepción no los tiene (sección 2).
- **Modelo de la lista**: la asistencia y la lista de espera **no** son tablas aparte (a diferencia de los borradores `ListaEsperaClase` y `AsistenciaClase` de la sección 6). Viven como estados de `class_reservations`: `waitlist`, `reserved`, `attended`, `no_show` y `cancelled`. Así la asistencia queda 1:1 con la reserva y el orden de espera es `waitlist_position`.
- **Agenda**: `POST /admin/classes/sessions` valida ventana horaria, capacidad y existencia de tipo, salón e instructor; `PATCH /admin/classes/sessions/{id}` permite edición parcial (por ejemplo borrar salón o instructor pasando `null`), nunca baja la capacidad por debajo de las reservas confirmadas y rechaza editar una clase cancelada. `POST /admin/classes/sessions/{id}/cancel` cancela la clase y todas sus reservas vivas, liberando la plaza.
- **Cupo y lista de espera**: la reserva bloquea la fila de la clase (`SELECT ... FOR UPDATE`) y cuenta las plazas ocupadas (`reserved` + `attended`). Si hay cupo, crea `reserved`; si está llena y la clase admite lista de espera, crea `waitlist` con la siguiente posición; si no la admite, responde `409`. Un índice único parcial (`uq_class_reservations_active`) impide que un socio acumule dos reservas vivas en la misma clase.
- **Promoción y cancelación**: al cancelar una plaza confirmada, el primer socio en espera sube a `reserved` y la lista se renumera. Una cancelación fuera de `cancel_window_hours` (por defecto 4 h) se permite pero queda marcada con `late_cancellation` para aplicar la penalización cuando exista cobro.
- **Asistencia**: `POST /admin/classes/reservations/{id}/attendance` marca `attended` o `no_show` y solo se acepta desde una reserva confirmada (`reserved`) o ya marcada (`attended`, para corregir el marcado), con lo que se cierra el flujo de la sección 4.4.
- **Clases premium**: se guarda `access_type=premium` y `extra_price_cents`; el cobro se agregó después (tercer incremento, ADR-033).
- **Panel web**: la vista Clases tiene dos pestañas: *Agenda* (resumen, filtros por texto, estado y día; cupo ocupado, lista de espera, alta/edición/cancelación y roster con búsqueda de socio, marcado de asistencia y cancelación) y *Catálogo* (tipos de clase y salones). Todo pasa por rutas BFF bajo `/api/admin/classes/*`.

Segundo incremento (2026-10-27): **reserva y cancelación desde la app del socio**, sin migración ni tablas nuevas. La capa `app.modules.portal.classes` reutiliza el servicio de clases y añade solo las reglas del socio:

- `GET /member/classes` devuelve las sesiones futuras programadas (14 días por defecto, hasta 60) con cupo, lista de espera y la reserva propia; cada sesión trae `can_reserve` y `blocked_reason` (`already_reserved`, `membership_inactive`, `premium_class`, `started`, `full`).
- `POST /member/classes/sessions/{id}/reservations` exige membresía activa, clase programada y futura, no premium y sin reserva viva; si está llena respeta `waitlist_enabled` y asigna posición. `origin` queda en `app`.
- `POST /member/classes/reservations/{id}/cancel` solo permite reservas propias (las ajenas responden `404`) y solo antes del inicio de la clase; delega en la cancelación existente, que promueve al primero de la lista de espera y marca `late_cancellation` si aplica.
- `cancelled_by` queda vacío en las cancelaciones del socio porque la columna es una FK a `app_users`; el rastro disponible es `origin = "app"`.
- Las clases premium se muestran bloqueadas con el aviso de reservar en recepción hasta que exista el cobro del extra. La promoción desde la lista de espera ya avisa al socio promovido con `class_waitlist_promoted` (ver `notificaciones-del-socio.md`); la confirmación de la propia reserva y los recordatorios de la clase próxima siguen sin avisarse.

Tercer incremento (2026-10-29): **cobro de clases premium al marcar asistencia**, sobre el ledger de ventas existente (ADR-033):

- **Cargo**: `POST /admin/classes/reservations/{id}/attendance` acepta `payment_method` (`cash`, `card`, `transfer`, `account`) y, si la clase es `premium` con `extra_price_cents > 0` y el marcado es `attended`, crea una venta con una línea de servicio (`product_id=NULL`, `sku="CLASE"`, cantidad 1) ligada a la reserva con `sales.class_reservation_id`. La migración `20261029_0049` permite `product_id` nulo en líneas de venta y devolución. El cargo entra en el turno de caja, en el crédito de la cuenta del socio, en los reportes de ingresos (categoría «Servicios») y en la facturación como cualquier venta. Sin método de pago en una clase premium responde `409`; el cargo exige turno abierto como cualquier venta.
- **Sin doble cobro**: si la reserva ya tiene una venta `completed`, volver a marcarla como asistida devuelve la venta existente y no crea otra. Es la corrección de un marcado, no un segundo ingreso.
- **Reembolso**: marcar `no_show`, cancelar una reserva ya cobrada o cancelar la clase reembolsan la venta con una devolución de servicio (`product_id=NULL`, `disposition="write_off"`, sin movimientos de inventario) en la forma de la venta. Efectivo exige turno abierto; una venta a cuenta se abona a la cuenta. Un reembolso repetido no hace nada.
- **Lista de espera**: promover no cobra; el cobro queda pendiente hasta que se marque la asistencia. Cancelar antes de asistir no reembolsa nada porque nunca hubo venta.
- **API y panel**: cada reserva del roster expone `charge_sale_id`, `charge_cents`, `charge_payment_method`, `charge_folio` y `charge_status`. La lista muestra «cobro pendiente», «pagado $X» o «reembolsado $X», pide la forma de pago en las clases premium, confirma importe, método y folio del cobro, informa el reembolso y ofrece **«No asistió»** en una reserva ya marcada para corregirla y reembolsar.
- **Caja**: `_cash_session_totals` dejó de filtrar ventas `completed`: una venta reembolsada desaparecía como ingreso y su devolución seguía restando, dejando el efectivo esperado en negativo. Ahora suma todas las ventas del turno y resta las devoluciones.
- **Pruebas**: `backend/tests/test_class_premium_charge.py` (4 casos: efectivo con turno y reembolso, crédito de cuenta y reembolso de tarjeta al corregir la asistencia, promoción desde lista de espera con cobro pendiente, y reembolso en efectivo que exige turno abierto) más el caso de la devolución desde caja descrito abajo.
- La app del socio sigue bloqueando reservar clases premium: se reserva en recepción y se cobra al asistir.

Devolución de servicios desde la caja (2026-10-29, ADR-034): el cobro equivocado se corrige desde el historial de ventas del POS con `POST /admin/sales/{sale_id}/service-refund` y el permiso nuevo `sales.service_refund` (dueño y gerente, migración `20261029_0050`). Reembolsa el importe completo con motivo obligatorio, línea `write_off` y la forma de pago de la venta (efectivo exige turno abierto), y **no cambia el estado de la reserva**: quien asistió sigue `attended` y el roster muestra «Asistió · reembolsado». Una venta ya reembolsada responde `409`, una venta sin reserva de clase `422`. Como el roster solo ofrece «No asistió» en una reserva ya marcada, deshacer la asistencia después no vuelve a reembolsar y volver a marcarla crea un cargo nuevo. Cubierto por el quinto caso de `test_class_premium_charge.py` y por la prueba opt-in `backend/tests/test_service_refund_postgres.py` (dos reembolsos simultáneos pagan una sola vez; el reembolso cae en el turno que lo paga).

Cuarto incremento (2026-10-29): **recordatorio de la clase próxima y la lista de espera cuando el lugar se libera sin cancelación** (ADR-035).

- **Recordatorio**: `class_reminder` se materializa al leer la bandeja del socio o su contador de no leídos —no hay programador— para las reservas `reserved` de clases `scheduled` que empiezan dentro de las próximas 24 h. Cada lectura elige la ventana más estrecha ya alcanzada (24 h o 2 h) y deduplica por `class_reminder:<reservation_id>:<24|2>`, así que el socio recibe hasta dos avisos por clase y nunca dos iguales. La app lo etiqueta «Clase» y abre la pantalla Clases. Migración `20261029_0051_class_reminder_notification.py` y reconstrucción del `CHECK` en `preview_patch.py`.
- **Lugar liberado**: además de la cancelación, subir el aforo (`PATCH /admin/classes/sessions/{id}`) y marcar una inasistencia antes de la clase sientan a la cabeza de la fila con el aviso `class_waitlist_promoted` que ya existía. `_seat_waitlist_in_free_spots` promueve solo mientras haya sillas libres, así que un aforo que no cubre toda la fila deja al resto en orden.
- **Después del inicio no se promueve**: `_promote_next_waitlist` exige que la clase siga `scheduled` y que `starts_at` sea futuro. Una cancelación o inasistencia posterior deja la fila intacta y la silla sin usar, en lugar de avisar de una clase que ya ocurre.
- Pruebas: `backend/tests/test_class_notifications.py` (2 casos: ventanas y deduplicación del recordatorio, y promoción por aforo, inasistencia anticipada y bloqueo tras el inicio).

Pendiente (documentado en `docs/deuda-tecnica.md`): aviso de clase cancelada o reprogramada y confirmación de la propia reserva, reserva premium desde la app con pasarela, reserva automática desde control de acceso y penalizaciones efectivas por inasistencia (marcar `no_show` hoy reembolsa la clase premium).

## 14. Estado

Primer incremento implementado y probado (catálogo, agenda con cupo y lista de espera, asistencia e inasistencias desde el panel); segundo incremento entregado para reserva y cancelación desde la app del socio con lista de espera; la promoción a la cabeza de la fila ya deja su aviso en la bandeja del socio (`class_waitlist_promoted`, ver `notificaciones-del-socio.md`); tercer incremento entregado para cobrar la clase premium al marcar asistencia, con reembolso al deshacerla o cancelar (ADR-033) y, desde el mismo día, reembolso del importe desde la caja con permiso de gerencia sin tocar la reserva (ADR-034). Cuarto incremento entregado el 2026-10-29: recordatorio de la clase próxima en las ventanas de 24 h y 2 h y promoción de la lista de espera por aforo o inasistencia anticipada, con bloqueo de la promoción después del inicio (ADR-035). La confirmación de la propia reserva, el aviso de clase cancelada o reprogramada, la reserva premium desde la app y las penalizaciones por inasistencia quedan en diseño / validación funcional.

## 15. Historial de cambios

- 2026-10-29: cuarto incremento: recordatorio de la clase próxima y lista de espera sin cancelación (ADR-035). Nuevo tipo `class_reminder` (migración `20261029_0051`), `_ensure_class_reminders` materializado al leer la bandeja o la insignia con ventanas de 24 h y 2 h y dedupe por reserva/ventana; subir el aforo y marcar una inasistencia antes de la clase promueven a la cabeza con `class_waitlist_promoted`; la promoción exige que la clase no haya empezado; la app abre Clases desde los avisos de clase. Pruebas `test_class_notifications.py`; suite en 227 pruebas (2 omitidas sin PostgreSQL en ese momento, 4 en total).
- 2026-10-29: devolución de servicios desde la caja (ADR-034). `POST /admin/sales/{sale_id}/service-refund` con el permiso nuevo `sales.service_refund` (dueño y gerente, migración `20261029_0050`); reembolsa el importe de un cargo premium con motivo obligatorio sin cambiar el estado de la reserva (`attended` + `charge_status=refunded`), `409` si la venta ya está reembolsada; quinto caso en `test_class_premium_charge.py` y prueba opt-in `test_service_refund_postgres.py` (carrera de dos reembolsos y turno que paga), verificada contra PostgreSQL 16.4; suite en 225 pruebas (4 omitidas sin PostgreSQL).
- 2026-10-29: tercer incremento: cobro de clases premium al marcar asistencia (ADR-033). `sale_items.product_id` y `sale_return_items.product_id` nullable y `sales.class_reservation_id` (migración `20261029_0049`); `POST .../attendance` con `payment_method` crea una venta de servicio ligada a la reserva (sin doble cobro), y `no_show`, la cancelación de la reserva o de la clase la reembolsan; el roster expone `charge_*` y permite corregir una asistencia; `_cash_session_totals` suma todas las ventas del turno. Pruebas `test_class_premium_charge.py`; suite en 222 pruebas al cierre de ese incremento.
- 2026-10-27: corrección en la agenda del panel —`GET /admin/classes/sessions` con `search` inflaba `total` y el `summary` porque la condición lee `ClassType.name` y los dos agregados (`_session_summary` y el conteo de `list_class_sessions`) no unían `class_types`, así que cada sesión se contaba una vez por tipo (39 en lugar de 5 en la vista previa, con 5 tipos sembrados). Ahora ambos se construyen sobre `class_sessions` unido a `class_types`; el listado de elementos y el bloque de asistencia ya unían correctamente y no cambiaron, no hay migración ni ruta nueva, y sin `search` los números son idénticos. Cubierto por `test_summary_and_total_are_not_inflated_by_the_search_filter`, que falla sin el arreglo.
- 2026-10-27: segundo incremento (reserva y cancelación desde la app del socio sobre las mismas tablas, clases premium bloqueadas, `origin = "app"`), API `/member/classes*`, pantalla Clases en Expo y pruebas `test_member_classes_api.py`.
- 2026-10-17: primer incremento de implementación (catálogo de clases y salones, agenda con cupo y lista de espera, reservas, asistencia y cancelaciones) con migración `20261017_0009`, API `/admin/classes/*`, panel web con vista Clases y pruebas de API.
- 2026-10-15: documento ampliado con flujos, permiso, pantallas, reglas de negocio, entidades, KPIs y criterios de aceptación.
