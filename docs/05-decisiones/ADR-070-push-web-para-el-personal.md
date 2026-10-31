# ADR-070: Push web para el personal del panel

- Fecha: 2026-10-31
- Estado: propuesta inicial

## Contexto

Los avisos del personal ya viven en la bandeja del panel (`staff_notifications`, ADR-017), salen por correo desde una cola con reintento manual (ADR-048 a ADR-051) y desde ADR-055 el personal recibe también los avisos que genera el push del socio agotado o con acuse fallido. Todo eso exige abrir la campana o el correo. El push del socio (ADR-052) no sirve para el personal: la app del socio no es su herramienta —quien opera el panel trabaja en el navegador— y el canal de Expo solo habla con dispositivos móviles registrados por socios.

La deuda técnica y el estado del proyecto venían anotando «los avisos push del personal» como pendiente. El caso de uso es operativo: una solicitud de cambio de marca, un ticket crítico asignado o un push del socio que se agota deben alcanzar a recepción sin que alguien refresque la página.

## Decisión

- **Canal Web Push, no Expo.** El navegador del panel registra una suscripción de Web Push (endpoint del servicio de notificaciones + claves `p256dh` y `auth`) contra el service worker `web/public/sw.js`; el backend firma con VAPID y cifra el mensaje (`aes128gcm`). No hay app de personal ni token de Expo.
- **Solo se guarda la clave privada.** `VAPID_PRIVATE_KEY` (32 bytes en base64url) y `VAPID_SUBJECT` (por defecto `mailto:avisos@centro-fit.local`, también acepta una URL `https:`) configuran el canal. La clave pública que necesita el navegador se **deriva** de la privada (`ec.derive_private_key` + punto X962 sin comprimir) en `GET /admin/staff/push/config`, así que el operador no puede publicar una clave y firmar con otra. Sin clave el canal se anuncia apagado; una clave mal formada también, con un `warning` en el log, en vez de romper cada petición. `backend/generate_vapid_keys.py` imprime un par nuevo.
- **La suscripción pertenece a la cuenta, no al navegador anónimo.** `staff_push_subscriptions` guarda `user_id`, el endpoint único, las dos claves, el `user_agent`, su estado y las fechas. Un endpoint solo puede pertenecer a una cuenta: registrarlo desde otra cuenta lo **transfiere** a quien inicia sesión después, porque es la persona frente al navegador la que decide recibir avisos ahí. Desactivar una suscripción la apaga sin borrar el historial de entregas.
- **Una entrega por aviso y navegador activo, escrita con el aviso.** `create_staff_notification` encola en `staff_push_deliveries` una fila `pending` por cada suscripción activa de la cuenta activa, en la misma transacción del aviso y con la dirección de destino congelada; un aviso deduplicado no encola dos veces y una cuenta deshabilitada no recibe push. `staff_push_deliveries` guarda el `notice_id`, la cuenta, la suscripción, el endpoint, el estado (`pending`/`sent`/`simulated`/`failed`), los intentos, el error y las marcas de tiempo. La audiencia es la que existía cuando ocurrió el evento: un navegador registrado después no recibe ese aviso.
- **La pasada reclama antes de hablar con el servicio de push.** Al terminar la respuesta, el mismo gancho del correo (`AttendanceEmailFlush`) lanza `send_pending_staff_push_deliveries` en su propia sesión: toma hasta 20 filas pendientes y las reclama con un `UPDATE … WHERE status = 'pending' AND attempts = :attempts` que suma el intento y se confirma antes de enviar, así dos pasadas concurrentes no mandan el mismo aviso dos veces. El mensaje lleva el título y el cuerpo del aviso, `tag` con el id del aviso para agrupar y `ttl` de una hora: un aviso de trabajo no sirve horas después. La vista previa marca la fila `simulated` y nunca contacta al servicio de push.
- **Sin reintento automático.** A diferencia del push del socio (ADR-054), una entrega `failed` no se reprograma sola: el canal roto alertaría a las mismas cuentas que operan el panel, y sus alertas fallarían también. Solo se reintenta a mano con `POST /admin/staff/push/deliveries/{id}/retry` (`attendance.manage`, `409` si la fila no está `failed`, `404` si no existe). El panel ofrece «Enviar pendientes» (`POST /admin/staff/push/deliveries/send`) para drenar la cola.
- **El servicio de push decide cuándo el navegador ya no existe.** Un `404` o `410` al enviar marca la entrega `failed` y **desactiva** la suscripción; los demás errores solo dejan la entrega `failed` con el detalle truncado a 500 caracteres. Una suscripción inactiva no se contacta: su entrega nace `failed` con la razón.
- **API y panel.** `GET /admin/staff/push/config` (cualquier cuenta autenticada), `GET`/`POST /admin/staff/push/subscriptions` y `DELETE /admin/staff/push/subscriptions/{id}` (la propia cuenta), `GET /admin/staff/push/deliveries` (`attendance.read`, filtro por estado y paginación de 20), el envío y el reintento (`attendance.manage`). El BFF de Next reexpone las seis rutas bajo `/api/admin/staff/push/*`. La pestaña Equipo estrena la tarjeta «Push del personal»: activa o desactiva **este** navegador (pide permiso, registra `sw.js` y se suscribe con la clave pública), lista «Mis navegadores» con el endpoint enmascarado y, para quien puede ver la operación, la cola con destinatario, aviso, dispositivo, estado, intentos, último intento, detalle y el reintento de las fallidas. El service worker enfoca una pestaña abierta del panel y navega a `/?avisos=1`, que abre la campana y la carga; sin pestaña, abre una nueva.
- **Migración propia anclada a la última revisión comprometida.** `20261031_0076_staff_push` crea las dos tablas con sus claves foráneas `RESTRICT`, el unicidad del endpoint, la unicidad `(aviso, suscripción)`, los `CHECK` de estado e intentos y los dos índices. Encadenó a la última revisión comprometida en su momento, `20261031_0074`. La `20261031_0075` del checkout con Conekta (ADR-066) se comprometió después y **se reencadenó sobre la 0076**, así que la cadena queda `0074 → 0076 → 0075`, con una sola cabeza lineal.

## Consecuencias y límites

- **No hay acuse como el de Expo.** El canal sabe que el servicio de push aceptó el mensaje, no que el navegador lo mostró; un navegador cerrado o con las notificaciones silenciadas por el sistema no se distingue de uno que las vio. La cola muestra «Sin acuse» como estado implícito.
- **Sin horario de silencio ni preferencias por tipo o por navegador.** Todos los avisos del personal suenan en cada navegador activo; apagar uno exige desactivar esa suscripción. Un socio silenciado no afecta al personal.
- **Rotar la clave VAPID invalida todos los navegadores registrados**: las suscripciones viejas fallan con error del servicio de push y hay que volver a activarlas desde cada navegador. No hay aviso previo de la rotación.
- **El navegador puede perder la suscripción** si el usuario borra los datos del sitio o el servicio de push la revoca; el panel no detecta la pérdida hasta el siguiente envío fallido.
- **El planificador llegó después (ADR-071)**: la pasada viaja con las peticiones que crean avisos o vacían la cola, y las entregas que un proceso caído dejó `pending` se drenan desde el cron con `backend/flush_staff_push.py`; las `failed` siguen esperando a una persona.
- **Los permisos son de la operación, no del canal**: cualquier cuenta autenticada puede activar su navegador, pero solo `attendance.read` ve la cola y solo `attendance.manage` envía o reintenta. Un entrenador sin esos permisos recibe los avisos que le corresponden y no ve la operación de los demás.

## Referencias

- `backend/src/app/modules/notifications/webpush.py` (`vapid_config`, `read_staff_push_config`, `register_staff_push_subscription`, `send_staff_web_push`, `send_pending_staff_push_deliveries`, `retry_staff_push_delivery`)
- `backend/src/app/modules/notifications/service.py` (`_enqueue_staff_notification_push`)
- `backend/src/app/main.py` (rutas `/admin/staff/push/*` y el gancho de la pasada)
- `backend/alembic/versions/20261031_0076_staff_push.py`
- `backend/generate_vapid_keys.py`
- `backend/tests/test_staff_push_api.py`
- `web/public/sw.js`, `web/src/app/api/admin/staff/push/**`, `web/src/app/page.tsx` (tarjeta «Push del personal»)
- `docs/02-modulos/personal-y-roles.md`
- `docs/05-decisiones/ADR-052-push-del-socio-desde-la-app.md`, `ADR-054-reintento-automatico-del-push-del-socio.md`
