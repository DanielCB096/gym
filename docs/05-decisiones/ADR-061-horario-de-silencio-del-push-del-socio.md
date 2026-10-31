# ADR-061: Horario de silencio del push del socio

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Cierra la parte de club del límite de ADR-052 y ADR-059 («no hay horario de silencio»)

## Contexto

El push del socio sale en cuanto la pasada lo alcanza: una factura timbrada a las 23:00, un cambio de clase de madrugada o una meta ajustada de noche le hacen sonar el teléfono cuando el club está cerrado. La bandeja (ADR-016) y el aviso en sí son correctos —el club debe dejar constancia—; lo que sobra a las 23:00 es la interrupción.

ADR-059 apagó el ruido por tipo de aviso de forma individual; su límite explícito era de horario: «un horario de silencio (por ejemplo, no molestar de noche) es otra decisión». Esta es esa decisión, en su mitad de club: una ventana única para el club entero, que la operación configura y que protege la noche de todos los socios sin pedirles nada.

## Decisión

- **La ventana es de club, en hora local del gimnasio.** Dos variables `MEMBER_PUSH_QUIET_START` y `MEMBER_PUSH_QUIET_END` en formato `HH:MM` que se interpretan en `APP_TIMEZONE` (`America/Mexico_City` por defecto, UTC-6 todo el año, sin horario de verano). Puede cruzar medianoche (`22:00`–`07:00`) o no (`07:00`–`22:00`) y la comparación es la misma: la mitad [inicio, fin) del reloj, con la vuelta que haga falta.
- **Sin ventana en configuración incompleta o ambigua.** Nada de variables, dejar las dos vacías o poner el mismo valor en ambas son tres formas de «sin horario de silencio»; definir solo una es un error (`ValueError` con el nombre de la variable) y el arranque del backend llama a `validate_push_quiet_window()` junto a la comprobación de `APP_TIMEZONE`, así que una ventana mal escrita detiene el proceso en lugar de dejar la noche sin silenciar.
- **La pasada automática pospone; no descarta.** `send_pending_member_push_deliveries` revisa la ventana antes de tocar la cola: dentro de la ventana devuelve una pasada sin intentos (`deferred: true`), las filas quedan como están (`pending` sin tocar, `failed` con su `next_attempt_at`) y la primera pasada después de la ventana las manda, incluidos los reintentos que vencieron de madrugada, que siguen cubiertos porque su `next_attempt_at` quedó en el pasado. Nada se borra y no cambia ningún estado: el aviso contra las preferencias del socio (ADR-059) cancela, este solo espera.
- **La decisión humana del operador no la pospone la ventana.** El envío manual desde la tarjeta «Push del socio» (`POST /admin/notifications/push-deliveries/send`) manda `override_quiet_hours=True` y el reintento manual (`POST …/{id}/retry`) va por su propio camino sin pasar por la pasada: si recepción necesita avisar a las 22:30 que la clase de mañana se canceló, es su decisión consciente y la ventana no la bloquea.
- **La vista previa ignora la ventana.** `PREVIEW_MODE=true` simula el envío y nunca llega a un teléfono, así que una demo de noche sigue mostrando el flujo completo en la tarjeta; la ventana solo gobierna el envío real.
- **Sin tabla ni migración.** La ventana misma vive en la configuración del proceso; para cambiarla hay que reiniciar el backend, igual que `RECEIPT_MAX_AGE` (ADR-056) o la retención de acuses (ADR-058). No se toca el esquema.

## Consecuencias y límites

- **El horario de silencio por socio queda abierto.** ADR-059 imaginaba la decisión del socio como «otra tabla»; este corte es la política del club. Quien quiera su propio horario (por ejemplo, 21:00 en vez de 22:00) tendría `member_notification_quiet_hours` o una columna en `member_notification_preferences`, con su consulta en `_enqueue_member_push_deliveries` o en la pasada.
- **El panel anuncia el silencio.** `GET /admin/notifications/push-deliveries` publica `quiet_window` (`start`, `end`, `active`) y la tarjeta «Push del socio» muestra «En silencio hasta las HH:MM» mientras la pasada automática estaría esperando, o «Silencio de HH:MM a HH:MM» fuera de la ventana; sin variables la clave llega `null` y no aparece la insignia. El envío manual sigue llevando `deferred: false` porque anula la ventana, y el operador ya ve por qué la cola no baja de noche.
- **Sin planificador, la salida depende de la próxima petición.** Igual que el resto del proyecto sin worker: si nadie abre el panel ni toca el backend entre las 07:00 y el mediodía, los push esperan a la primera petición que dispare la pasada. La tecnología es la de siempre (ADR-052); el horario puede empujarla unas horas.
- **Las alertas de agotamiento no se silencian.** El aviso `member_push_failed` (ADR-055) es para el personal y viaja por correo y campana, no por push: la ventana no lo toca y una madrugada agitada puede dejar correos al amanecer, que es lo que se debe.
- **Un socio sin fila de preferencias es encendido; un club sin variables de ventana es sin silencio.** El valor por defecto de las dos decisiones es sonar, y el silencio siempre es una elección explícita.

## Referencias

- `backend/src/app/modules/notifications/push.py` (`parse_push_quiet_window`, `validate_push_quiet_window`, `_in_quiet_window`, `MemberPushPass.deferred`, la pasada y su `override_quiet_hours`)
- `backend/src/app/main.py` (`lifespan` llama a `validate_push_quiet_window`, `POST /admin/notifications/push-deliveries/send` con `deferred` y `override_quiet_hours=True`)
- `backend/src/app/timezone.py` (`to_club_timezone` para la hora local de la comparación)
- `.env.example` (`MEMBER_PUSH_QUIET_START` / `MEMBER_PUSH_QUIET_END`)
- `backend/tests/test_member_push_quiet_hours.py` (15 pruebas, dos de ellas del aviso del panel)
- ADR-052 (push del socio), ADR-054 (reintento automático), ADR-055 (aviso de agotamiento), ADR-059 (preferencias del socio)
