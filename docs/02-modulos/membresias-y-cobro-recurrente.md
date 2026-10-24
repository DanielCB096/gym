# Módulo 1: Membresías y cobro recurrente

## 1. Resumen y alcance

Este módulo cubre la operación de alta de socios, venta de planes, pago inicial, renovación, congelamiento, cancelación, cambio de plan y cobro recurrente automático. Maneja además promociones, descuentos y recordatorios de vencimiento.

### Incluye
- alta de socio y consentimiento de privacidad
- planes: mensual, trimestral, anual, por visitas, estudiante, pareja/familiar, pase de día, cortesía, prueba
- pagos con tarjeta, SPEI, efectivo y cargo a cuenta del socio
- reintentos automáticos y período de gracia
- actualización de método de pago y cancelación simple
- historial y auditoría completa

### No incluye
- nómina, clases o inventario (son módulos separados)
- servicios extra no activados aún

## 2. Actores y permisos

| Rol | Acciones |
|---|---|
| Socio | ver plan, pagar, actualizar método de pago, solicitar congelamiento |
| Recepcionista | alta, cobro inicial, renovación, cambios de plan |
| Gerente | aprobar promociones y cambios de régimen |
| Dueño | configuraciones y políticas, descuentos, contratos |
| Contador | ver cuota, efectivo y conciliación |

## 3. Flujos de usuario paso a paso

### Flujo principal: alta de socio con primer pago
1. El socio ingresa datos básicos, foto, teléfono y contacto de emergencia.
2. Completa cuestionario PAR-Q y acepta aviso de privacidad.
3. Firma digitalmente la responsiva y el consentimiento de datos sensibles si aplica.
4. El recepcionista selecciona plan y promocional que aplique.
5. El sistema calcula precio final con descuentos, impuestos y promoción.
6. Se confirma método de pago y se genera token desde la pasarela.
7. El backend crea la membresía y emite comprobante si aplica.
8. El socio recibe confirmación por WhatsApp, push y correo.

### Flujo alterno: pago fallido
1. La pasarela devuelve error o rechazo.
2. El sistema marca el pago como fallido.
3. Se disparan reintentos en días 1, 3 y 5 según política.
4. Si sigue fallando, se emite aviso y se bloquea acceso con un periodo de gracia configurable.

### Flujo de error
- si el método de pago no está disponible, el sistema muestra error claro y no duplica cobro
- si la foto o consentimiento no llega, la alta queda en estado pendiente
- si el socio no firma la responsiva, la membresía se marca invalidada

## 4. Pantallas

### Web administrativa
- Dashboard de membresías: total activos, vencimientos, morosidad, cobros del día
- Alta de socio: formulario de datos, contacto, PAR-Q, consentimiento y firma
- Gestión de planes: precio, vigencia, horario, cupos y beneficio
- Cobros del día: lista de cargos, estatus, reintentos, alertas
- Historial del socio: pagos, cambios, congelamientos y observaciones

### Móvil
- Mi membresía: vigencia, plan, fecha de pago y acceso
- Configuración de pago: agregar tarjeta, cambiar método, visualizar historial
- Recordatorios y alertas: vencimiento, cobros fallidos, cambios de plan

### Kiosco
- Buscar socio por nombre o QR
- Presentación rápida de datos de membresía
- Confirmación de alta o renovación asistida por recepción

### Estados de pantalla
- vacío: no hay socios o no hay pagos pendientes
- cargando: consulta de listas, cargando detalle
- error: fallo de pasarela o sincronización
- éxito: alta, pago, reactivación o cambio de plan confirmado

## 5. Reglas de negocio y casos límite

- la membresía solo es activa si está vigente y no tiene adeudo bloqueante
- el congelamiento no elimina el compromiso, solo pausa la vigencia
- la renovación calcula prorrateo según la fecha real de vencimiento
- los cupones y descuentos se validan solo si cumplen condiciones de vigencia
- una cancelación requiere motivo, confirmación y cronología de cobros
- el socio con baja deuda no puede acceder si la seguridad lo requiere

### Casos límite
- tarjeta vencida o bloqueada
- pago SPEI pendiente por validación
- un socio cambia de plan a mitad de ciclo
- un cobro recurrente se duplica por reintento o doble clic
- una promoción aplica solo a nuevos socios o a un rango de fechas

## 6. Entidades de datos

- Socio
- Contacto de emergencia
- MembreíaSocio
- Plan
- DescuentoPromoción
- Cupón
- Pago
- ReintentoCobro
- ConsentimientoPrivacidad
- ArchivoFirmado
- MétodoPago
- HistorialSocio

### Campos clave
- socio: nombre, RFC, teléfono, email, foto, fecha nacimiento, género, dirección
- membresía: plan, estado, fecha inicio, fecha fin, auto-renovación
- pago: monto, moneda, método, token, id externa, estado, referencia, intento

## 7. Integraciones con otros módulos

- Acceso: un socio con adeudo bloqueante no puede entrar
- Facturación: la membresía activa y la venta de producto generan CFDI cuando aplica
- Comunicación: avisos de vencimiento, pago fallido y renovación
- Inventario: no le aplica directamente, pero sí la caja y ventas de productos

## 8. Notificaciones y automatizaciones

- recordatorio 7 días antes del vencimiento
- recordatorio 24 h antes del cobro recurrente
- notificación de cobro fallido y tarjeta por vencer
- aviso de suspensión por falta de pago
- confirmación de reactivación y de cambio de plan

## 9. Consideraciones de rendimiento

- lista de socios paginada y filtrable por nombre, status, plan y morosidad
- caché de planes y promociones activas
- reintentos en worker y no en la request del usuario
- índices sobre `socio_id`, `estado`, `membresia_id`, `fecha_vencimiento`, `metodo_pago_id`

## 10. KPIs

- tasa de retención mensual
- MRR por plan
- churn por mes
- tasa de cobro exitoso
- tiempo promedio entre vencimiento y renovación
- tasa de morosidad

## 11. Preguntas abiertas

- ¿se permiten promociones combinadas o exclusivas?
- ¿todas las membresías tienen prueba o solo algunos planes?
- ¿qué tipo de congelamiento se acepta: por fecha o por días específicos?
- ¿la baja por cancelación requiere tiempo de prueba o penalización?

## 12. Criterios de aceptación

- el alta de socio se completa con toda la documentación requerida
- la membresía queda activa solo con validación de plan y consentimiento
- los pagos recurrentes se guardan con token y no con datos de tarjeta
- el sistema reintenta cobros según política
- el acceso se bloquea para adeudos configurados
- el historial del socio es trazable desde el primer pago

## 13. Estado

Implementación inicial: ya funcionan el alta de socio con consentimiento de privacidad desde el panel (`POST /admin/members`, permiso `members.manage`), el listado de socios con su membresía y plan, la edición de los datos del socio (`PATCH /admin/members/{id}`) y el ciclo de vida de la membresía desde la ficha del socio: asignar o cambiar plan (`POST /admin/members/{id}/membership`), congelar, reanudar y cancelar con motivo. Asignar o cambiar el plan **sin cobro** sigue disponible como cortesía auditada y deja la membresía `active` con el evento `manual_activation`/`plan_changed` marcado `no_charge: true`.

El **cobro manual de membresía** ya está implementado (2026-10-21) con la migración `20261021_0023_membership_manual_payments.py`:

- **API**: `POST /admin/members/{member_id}/membership/payments` (permiso `members.manage`) recibe `plan_id` opcional, `payment_method` (`cash`/`card`/`transfer`), `idempotency_key` obligatoria, `note` opcional y `auto_renew` opcional. Para un socio sin membresía exige `plan_id`; para una membresía `active` (también vencida) usa el plan actual si se omite y permite cambiarlo con el nuevo periodo.
- **Efecto**: registra un `PaymentAttempt` exitoso sin proveedor, un `Payment` confirmado y un evento de membresía (`payment_confirmed` o `renewed`). La activación o renovación y el pago se confirman en una sola transacción. El socio `pending` pasa a `active`; una renovación extiende desde `max(ahora, ends_at)` para no perder días pagados.
- **Turno de caja**: todo cobro manual exige un turno abierto (`409`) y queda ligado a él con `cash_session_id`. Solo el efectivo suma al efectivo esperado; tarjeta y transferencia se registran como declaradas por el operador y quedan en los totales de membresías del turno. La nota y el usuario que cobró se guardan en el pago.
- **Idempotencia**: la clave es única y una huella de la solicitud impide reutilizarla con otros datos. Repetir el mismo cobro devuelve el pago original con `idempotent_replay: true`; usar la misma clave con otro socio, plan, método o nota responde `409`.
- **Restricciones**: no se cobra una membresía `frozen`, `suspended` o `pending_payment` (primero hay que reanudar/cancelar o resolver la pasarela); un plan inexistente o sin precio responde `404`; un método inválido o una clave incompleta responde `422`.
- **Panel**: la ficha del socio muestra el plan actual, la forma de pago, el importe y los botones **Cobrar y activar/Cobrar renovación** y **Activar/Cambiar plan sin cobro** (este último pide confirmación). El resumen del turno de caja agrega los cobros de membresía y su parte en efectivo.
- **Reportes**: al ser `Payment` confirmados, los cobros manuales entran a los reportes de ingresos y de socios por `paid_at` y por método, sin cambiar el cálculo del MRR esperado.

La pasarela real, el cobro recurrente automático, las promociones/descuentos, el prorrateo por cambio de plan a mitad de ciclo y la facturación fiscal del cobro siguen en diseño.

## 14. Historial de cambios

- 2026-10-21: **cobro manual y renovación de membresía en mostrador** (migración `20261021_0023`). `POST /admin/members/{id}/membership/payments` registra un pago idempotente con efectivo, tarjeta declarada o transferencia, exige turno abierto, liga el pago al turno y crea/renueva la membresía. `payments` gana periodo, turno, cobrador y nota; `payment_attempts` acepta tarjeta declarada sin token. El panel agrega el cobro y el turno separa los cobros de membresía; la activación sin cobro queda como cortesía explícita.
- 2026-10-15: documento inicial con alcance, flujos, entidades y criterios de aceptación
- 2026-10-16: el alta de socio desde el panel ya registra al socio y su consentimiento de privacidad (`POST /admin/members`).
- 2026-10-16: se añadió la edición de datos del socio y el ciclo de vida de la membresía desde la ficha (asignar/cambiar plan, congelar, reanudar y cancelar con motivo). Asignar o cambiar plan activa la membresía sin cobro (evento `manual_activation`/`plan_changed` con `no_charge: true`); el primer cobro real queda pendiente de la pasarela.

## 15. Persistencia de la primera versión

- `members` mantiene el estado del perfil; `memberships` mantiene por separado el estado y vigencia del plan.
- Una membresía nueva inicia en `pending_payment`; solo se activa cuando el pago queda confirmado y la transacción registra el pago y el evento de cambio de estado.
- La base impide que un socio tenga más de una membresía no terminal al mismo tiempo.
- Cada intento, incluido un rechazo o un resultado incierto, se conserva en `payment_attempts`; `payments` contiene exclusivamente cobros confirmados.
- La clave idempotente es única y queda ligada a una huella de los datos de la solicitud; reutilizarla con datos diferentes se rechaza. Webhooks repetidos se deduplican por proveedor e identificador de evento.
- Los replays en estado `processing` o `unknown` devuelven el estado guardado sin reenviar el cobro; se resuelven mediante webhook verificado o reconciliación explícita.
- `payment_methods` conserva únicamente la referencia tokenizada cifrada del proveedor; no almacena número de tarjeta ni CVV.
- Los consentimientos y cambios de estado son históricos y no se borran. Los textos firmados y secretos del proveedor no se guardan dentro de los metadatos de eventos.
- Un cobro fallido o incierto no activa una membresía ni crea un pago confirmado; los estados se registran como eventos auditables.
- El alta desde el panel crea al socio en estado `pending` y registra su consentimiento de privacidad (versión `privacidad-v1`); no crea membresía ni cargo hasta que se asigne un plan.
- Asignar o cambiar el plan **sin cobro** activa la membresía directamente (`active`) sin crear `payment_attempts` ni `payments`; el evento de membresía lleva `no_charge: true` para no presentar un cobro que no ocurrió. Es una cortesía auditada, no el camino normal de alta.
- El cobro manual crea un `PaymentAttempt` exitoso con `provider = NULL` (tarjeta declarada sin token), un `Payment` con periodo (`period_starts_at`/`period_ends_at`), turno de caja, cobrador y nota, y un evento `payment_confirmed`/`renewed`. La clave idempotente y su huella viven en el intento, igual que en la pasarela. Una renovación conserva `starts_at` y extiende `ends_at` desde el vencimiento actual o desde hoy si ya venció.
- Congelar y reanudar cambian solo el estado de la membresía (`active`↔`frozen`); la cancelación exige motivo y deja la membresía en `cancelled`, liberando al socio para una nueva alta. Cada transición registra su evento de membresía con el actor responsable.
