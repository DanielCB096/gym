# ADR-054: Reintento automático del push del socio

- Fecha: 2026-10-30
- Estado: propuesta inicial
- Extiende ADR-052 y ADR-053 (push del socio y su cola en el panel)

## Contexto

ADR-052 dejó la pasada de push corriendo después de la respuesta, pero solo tomaba filas `pending`: un fallo de transporte —un 503 de Expo, un corte de red— se quedaba `failed` para siempre. ADR-053 añadió el botón «Reintentar», que depende de que una persona abra la tarjeta y lo pulse. La mayoría de los fallos de un servicio externo son pasajeros, así que el club terminaba perdiendo avisos que se habrían entregado solos segundos después.

## Decisión

- **Un reintento programado por fila.** `member_push_deliveries` gana `next_attempt_at` (nullable, `DateTime(timezone=True)`) y el índice `(status, next_attempt_at)`. La fila guarda cuándo toca el próximo intento automático; `NULL` significa que no hay nada programado, sea porque el push salió o porque ya no habrá más intentos.
- **Hasta tres intentos en total: el original y dos reintentos.** `MAX_PUSH_ATTEMPTS = 3`. Las esperas crecen según el intento que acaba de fallar: un minuto tras el primero y cinco después del segundo (`PUSH_RETRY_BACKOFF`). La espera se elige por número de intento, no por hora del reloj, así que una pasada retrasada no acorta la siguiente.
- **La pasada toma lo pendiente y lo que ya toca reintentar.** La consulta selecciona `status = 'pending'` o `status = 'failed'` con `attempts < MAX_PUSH_ATTEMPTS`, `next_attempt_at` no nulo y `next_attempt_at <= now`. Una fila que aún no vence se salta sin consumir el lote. El reclamo compare-and-set sobre `attempts` sigue igual y ahora se hace con el estado leído (`pending` o `failed`), así que un reintento manual y una pasada concurrente se excluyen entre sí.
- **El resultado se registra igual que en el primer intento.** Un error de transporte (`PushDeliveryFailed` o cualquier excepción inesperada) deja la fila `failed`, conserva el error truncado y programa el siguiente intento; al llegar a `MAX_PUSH_ATTEMPTS` el `next_attempt_at` vuelve a `NULL` y la fila queda final. Un éxito limpia `next_attempt_at` y fija `sent_at`.
- **Un dispositivo desinstalado nunca se reintenta.** `DeviceNotRegistered` retira el token y deja `next_attempt_at = NULL`: volver a intentarlo contra un teléfono sin la app no arregla nada. Lo mismo aplica a la notificación ausente, que no puede volver.
- **El reintento manual sigue mandando.** `POST …/{id}/retry` acepta cualquier fila `failed`, esté o no programada para el próximo lote, y cuenta como un intento más: si vuelve a fallar, la fila se reprograma o se agota según `attempts`. El botón no espera al backoff.
- **La API y el panel exponen el estado del reintento.** Cada entrega publica `next_attempt_at`; la página añade `max_attempts` y la pasada añade `retried` (cuántas de las filas tomadas eran reintentos automáticos). El panel muestra «Reintento HH:MM» bajo el error y «Sin reintentos» cuando la fila ya agotó sus intentos, y el aviso del envío resume los reintentos del lote.
- **Sin trabajador ni planificador.** Se mantiene el diseño de ADR-052: la pasada corre como tarea de fondo después de una respuesta que pudo encolar un push y bajo demanda desde el panel. Una fila programada espera a la siguiente pasada; en la operación real eso llegará con cualquier aviso nuevo o con «Enviar pendientes», no con un reloj propio.

## Consecuencias y límites

- **La espera es de la pasada, no del reloj.** Sin un planificador, un reintento programado para dentro de un minuto puede salir minutos u horas después si nadie provoca una pasada. La reprogramación evita perder el aviso, no garantiza la puntualidad.
- **Nadie se entera cuando se agotan los intentos.** La fila queda `failed` y «Sin reintentos», pero no hay campana ni correo al personal; eso es el siguiente corte (ADR-055).
- **El reintento puede duplicar.** La ventana at-least-once de ADR-052 sigue vigente: si el intento llegó al teléfono pero el registro quedó `failed`, el reintento automático lo repite.
- **Sigue sin haber acuse de Expo.** `sent` es que Expo aceptó el mensaje; no se consultan los recibos.
- **Tres intentos es una política fija.** No se configura por club ni por aviso; si la operación real pide otra espera o más intentos, se cambian las constantes de `push.py`.

## Referencias

- `backend/src/app/modules/notifications/push.py` (`MAX_PUSH_ATTEMPTS`, `PUSH_RETRY_BACKOFF`, `_schedule_retry`, `_retry_due`, `send_pending_member_push_deliveries`)
- `backend/src/app/modules/notifications/models.py` (`MemberPushDelivery.next_attempt_at`)
- `backend/alembic/versions/20261031_0068_member_push_retries.py`
- `backend/preview_patch.py` (columna e índice de la vista previa)
- `backend/tests/test_member_push.py`, `backend/tests/test_member_push_admin.py`, `backend/tests/test_preview_patch.py`
- `web/src/app/page.tsx`
- `docs/05-decisiones/ADR-052-push-del-socio-desde-la-app.md`, `ADR-053-cola-de-push-del-socio-en-el-panel.md`
