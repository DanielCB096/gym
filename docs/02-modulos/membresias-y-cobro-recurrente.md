# Módulo 1: Membresías y cobro recurrente

## 1. Resumen y alcance

Este módulo cubre la operación de alta de socios, venta de planes, pago inicial, renovación, congelamiento, cancelación, cambio de plan y cobro recurrente automático. Maneja además promociones, descuentos y recordatorios de vencimiento.

### Incluye
- alta de socio y consentimiento de privacidad
- planes: mensual, trimestral, anual, por visitas, estudiante, pareja/familiar, pase de día, cortesía, prueba
- pagos con tarjeta, SPEI, efectivo y cargo a cuenta del socio
- renovación automática con consentimiento y reintentos; sin periodo de gracia
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
3. En una renovación automática se reintenta 1, 3 y 5 días después del
   vencimiento.
4. No hay periodo de gracia: el acceso se suspende al vencer. Si el cobro se
   recupera, el periodo nuevo empieza en la fecha efectiva del pago.

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
- Historial de pagos de membresía de solo lectura (importe, plan, periodo, método y nota)
- Configuración de pago: aceptar o revocar la renovación automática con texto
  explícito sobre el primer cobro y los reintentos; en la fecha de vencimiento,
  abre la captura segura de tarjeta y confirma el cobro normal de renovación
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
- un cobro automático requiere consentimiento vigente y método tokenizado activo
- al aceptar la renovación para una membresía ya pagada no se cobra ni se
  tokeniza una tarjeta de inmediato; el socio completa la primera renovación en
  su fecha de vencimiento y los ciclos posteriores podrán cobrarse en automático
- la captura de tarjeta se habilita solo al vencer; guardar la tarjeta inicia
  el cobro normal de renovación, no un cargo de verificación, y la membresía
  solo se reactiva al confirmar Conekta por webhook

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

- recordatorio 7 días antes del vencimiento —implementado en la bandeja de avisos de la app del socio: al leerla se genera `membership_expiring` en las ventanas de 7, 3 y 1 día, una sola vez por ventana (ver `notificaciones-del-socio.md`); sigue sin push ni correo y exige abrir la app
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
- ningún cobro se inicia sin consentimiento vigente, método activo y clave
  idempotente por ciclo e intento
- un resultado desconocido no crea un nuevo cargo hasta conciliar el anterior
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

La primera parte de la integración de pagos en línea está implementada para sandbox. `POST /member/membership/checkout` (Bearer del socio, `plan_id` y encabezado `Idempotency-Key`) crea una orden alojada de Conekta para pago único con tarjeta, ligada a un intento interno; guarda la referencia de orden y la URL de checkout. La configuración requiere `CONEKTA_MODE=sandbox`, `CONEKTA_SANDBOX_API_KEY`, `CONEKTA_SUCCESS_URL` y `CONEKTA_FAILURE_URL`; la llave debe proceder del modo de pruebas del panel y no se permite producción. El importe y la moneda los fija el plan del servidor. Repetir la misma clave devuelve el checkout existente o reintenta la creación sin crear otro intento.

El endpoint `POST /webhooks/conekta/membership` procesa la confirmación solo tras verificar RSA-SHA256 sobre el cuerpo original, `livemode=false`, el ID de orden y la coincidencia de importe y moneda. `order.paid` y `charge.paid` crean un `Payment` y activan la membresía en una transacción idempotente; un rechazo no activa el acceso. Las discrepancias firmadas se conservan como evento fallido para revisión y responden `409`. Requiere `CONEKTA_WEBHOOK_PUBLIC_KEY` del webhook sandbox y no habilita producción. El checkout alojado, el retorno a la app y la respuesta HTTP de creación no son confirmación de pago. La prueba E2E con el sandbox de Conekta se completó el 2026-10-31 con un pago de $10 MXN. La captura del primer método y el cobro de renovación están implementados con respuestas simuladas; falta el E2E de ese nuevo flujo y la conciliación operativa. Los métodos guardados se cifran y solo pueden capturarse al vencimiento; el scheduler de ciclos posteriores, reintentos, métodos diferidos como SPEI, promociones/descuentos y prorrateo siguen pendientes. La facturación fiscal del cobro confirmado ya existe para pagos confirmados: un pago de membresía puede facturarse como CFDI 4.0 individual (`origin_type = "membership_payment"`) y acreditarse con nota de crédito desde el módulo de Facturación; el timbrado sigue siendo simulado hasta integrar el PAC real.

La **app del socio** consulta sus pagos de membresía desde `GET /member/payments` (Bearer, paginado, más recientes primero) con importe, moneda, método, fecha, periodo, plan y nota, sin cobrador ni turno de caja. Es de solo lectura: el cobro sigue siendo exclusivo del panel con `members.manage` y turno abierto. Ver ADR-012.

### Renovación automática (ADR-087, avance 2026-11-02)

La app ya permite al socio aceptar o revocar la renovación desde
`GET/POST /member/membership/auto-renewal`. El servidor conserva en
`member_consents` la versión, el hash del texto aceptado y la fecha de revocación, actualiza
`memberships.auto_renew` y registra el cambio en `membership_events`. Activar la
autorización no cobra ni captura la tarjeta. En la fecha de vencimiento, el
endpoint `POST /member/membership/payment-method/setup` genera un enlace de
10 minutos con un código aleatorio en el fragmento URL; la página lo borra antes
de comunicarse con el backend. El iframe de Conekta tokeniza la tarjeta fuera
del servidor; después de confirmar el importe normal del plan, se cifra la
referencia del cliente/método y se solicita el primer cargo. La nueva membresía
queda `pending_payment` hasta el webhook firmado. El panel administrativo ya no
puede otorgar consentimiento en nombre del socio. La integración exige llaves
`key_test_` y sigue sin una prueba E2E real; scheduler, reintentos y producción
permanecen pendientes/deshabilitados.

El plan ya guarda su **límite diario de entradas** (`plans.daily_entry_limit`, migración `20261028_0043`): `NULL` significa sin límite y el CHECK exige `>= 1`. Se fija o retira con `PATCH /admin/plans/{plan_id}` (`settings.manage`) desde la tarjeta «Límite diario de entradas» de la página «Kiosco» del panel; el kiosco lo aplica contando entradas autorizadas del día del club, incluidas las manuales. El alta y la edición completa de planes siguen pendientes: el panel solo expone este campo y `GET /admin/plans` lista los planes activos. Ver ADR-025.

## 14. Historial de cambios

- 2026-11-02: **renovación automática en sandbox** (ADR-087): el socio acepta/revoca desde la app; al vencer, un enlace de un solo uso abre el tokenizador de Conekta y envía el cobro normal de renovación. La referencia de cliente y tarjeta se cifra; la membresía solo se activa con webhook firmado. Scheduler, reintentos y validación E2E siguen pendientes; producción permanece deshabilitada.
- 2026-10-31: `GET /member/membership/plans` también recupera el checkout pendiente propio (plan, clave idempotente y URL) para reabrirlo o reintentarlo después de reiniciar la app.
- 2026-10-31: la app del socio obtiene los planes de primera inscripción desde `GET /member/membership/plans` y abre el checkout alojado de Conekta. La disponibilidad queda restringida a sandbox y a socios sin membresía no terminal; el retorno de la app no confirma el pago.
- 2026-10-28: **límite diario de entradas por plan** (`plans.daily_entry_limit`, migración `20261028_0043`, ADR-025). `PATCH /admin/plans/{plan_id}` con `settings.manage` fija o retira el límite; el kiosco lo aplica por día del club contando entradas autorizadas (también las manuales). No cambia el cobro, la vigencia ni las reglas de membresía.
- 2026-10-31: **webhook Conekta en sandbox**: `POST /webhooks/conekta/membership` valida `Digest`, `livemode`, orden, importe, moneda y eventos de pago; confirma el pago y activa la membresía de forma idempotente. Las discrepancias quedan auditadas como evento fallido. No habilita producción ni recurrencia.
- 2026-10-27: **consulta de pagos de membresía desde la app del socio** (`GET /member/payments`, solo lectura, paginada y acotada a la sesión), sin migración ni cambios en el cobro manual. El estado de cuenta de la tienda se expone por separado en `GET /member/account`.
- 2026-10-21: **cobro manual y renovación de membresía en mostrador** (migración `20261021_0023`). `POST /admin/members/{id}/membership/payments` registra un pago idempotente con efectivo, tarjeta declarada o transferencia, exige turno abierto, liga el pago al turno y crea/renueva la membresía. `payments` gana periodo, turno, cobrador y nota; `payment_attempts` acepta tarjeta declarada sin token. El panel agrega el cobro y el turno separa los cobros de membresía; la activación sin cobro queda como cortesía explícita.
- 2026-10-31: **decisión para el primer pago en línea** (ADR-066): checkout alojado de Conekta por orden e intento, pago único y activación solo por webhook verificado. Es una decisión para implementar y probar en sandbox; no existe aún integración productiva ni se habilitan cobros recurrentes.
- 2026-10-31: **creación de checkout alojado en sandbox** (migración `20261031_0075`): `POST /member/membership/checkout` crea una orden de tarjeta idempotente ligada al intento y guarda `provider_order_id`/`checkout_url`. Aún no procesa el webhook ni confirma pagos; producción y recurrencia siguen deshabilitadas.
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
