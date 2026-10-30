# ADR-040: Retención de los datos operativos del kiosco

- Fecha: 2026-10-29
- Estado: propuesta inicial

## Contexto

El canal de entrada con código rotativo (ADR-024) escribe dos tablas operativas que no forman parte del registro de negocio: `member_access_codes` guarda el HMAC de códigos que viven cinco minutos y se consumen una sola vez, y `kiosk_attempts` guarda un renglón por intento para el límite de 10 por minuto del dispositivo. Ninguna de las dos se limpiaba: los códigos vencidos se acumulaban para siempre y los intentos se conservaban indefinidamente, aunque solo el último minuto tiene efecto en la regla.

Ese crecimiento no aporta nada a la operación y deja datos personales en disco más tiempo del necesario: un código vencido sigue ligado a un socio aunque ya no sirva, y un intento conserva el vínculo socio-dispositivo. La bitácora `access_events` es distinta: es el registro de negocio que sostiene reportes, auditoría y disputas, y no debe borrarse por una tarea de limpieza.

## Decisión

- **Solo se purgan las dos tablas operativas.** `member_access_codes` y `kiosk_attempts` se borran; `access_events` no se toca. La retención de la bitácora queda como decisión pendiente con el club, porque depende de sus obligaciones de conservación y no de una regla técnica.
- **Un código se borra por su vencimiento, no por su consumo.** El corte se aplica sobre `expires_at < ahora − retención`: así se eliminan los códigos vencidos que nadie usó y los consumidos hace días —que vencieron cinco minutos después de emitirse—, pero **nunca** uno que todavía puede usarse. Un código consumido ayer y uno activo se conservan hasta que su propia fecha cruce el corte.
- **Un intento se borra por su fecha.** `kiosk_attempts.occurred_at < ahora − retención`. La regla de límite solo mira el último minuto, así que conservar más es una decisión de diagnóstico, no de funcionamiento.
- **Dos retenciones, configurables por entorno.** `KIOSK_CODE_RETENTION_DAYS` con 7 días por defecto y `KIOSK_ATTEMPT_RETENTION_DAYS` con 30. Se separan porque el código es más sensible y su vida útil es de minutos, mientras el intento sirve para investigar un patrón de rechazos. Ambas aceptan enteros de **1 a 3650**; un valor inválido se rechaza con un mensaje y la corrida no toca la base. No hay configuración por club: el volumen esperado no lo justifica y una política única es más fácil de auditar.
- **La purga es una tarea externa, no un programador interno.** La lógica vive en `access.retention.purge_expired_access_data` y el punto de entrada operativo es `backend/purge_access_data.py`, que se programa por cron o el planificador del hosting. La aplicación no gana un hilo ni una tabla de trabajos: el despliegue ya tiene un lugar para tareas periódicas y así la purga se puede correr a mano, en seco y con respaldo previo.
- **La corrida es idempotente y explícita.** `--dry-run` cuenta lo que se borraría sin modificar nada; `--preview` apunta a `gym_preview.db`; `DATABASE_URL` o `--database-url` apuntan a otra base; `--codes-days` y `--attempts-days` mueven el corte solo en esa corrida. El script imprime los cortes y cuántas filas borró, y sale con código 2 ante una configuración inválida para que el cron lo marque como fallo.
- **La primera corrida es una simulación.** La guía de despliegue pide `--dry-run` antes de programar la tarea, y la de respaldos la coloca después del respaldo diario. La purga no sustituye al respaldo: si alguien necesita un código o un intento viejo, tiene que estar en la copia de seguridad.

## Consecuencias y límites

- **La bitácora sigue creciendo.** `access_events` es el registro de negocio y no entra en esta purga; su retención debe acordarse con el club y, cuando se decida, tendrá su propio procedimiento y probablemente un archivo histórico antes del borrado.
- **El estado del código más reciente puede volver a `none`.** `GET /member/access/code` informa el estado del código más nuevo del socio; si ese código ya se purgó, la app recibe `none` en vez de `expired`. A los 7 días no hay pantalla que lo esté consultando, así que el cambio es invisible en la práctica.
- **No hay índice por fecha de purga.** Los códigos tienen índice por socio/fecha de creación y hash, y los intentos por dispositivo/fecha; el borrado filtra por `expires_at` y `occurred_at` globales, así que con volúmenes altos puede recorrer la tabla. Con la operación esperada —decenas de códigos y cientos de intentos al día— es aceptable; conviene revisar el índice con volúmenes reales.
- **No hay auditoría de la purga más allá del log.** El script no escribe una fila de auditoría: el cron deja su salida en el archivo de log y el conteo de filas. Tampoco queda registrado quién la programó o cambió la retención; el valor vive en el entorno del servicio.
- **No hay límite por club ni por dispositivo.** La retención es global. Un club que quiera conservar más o menos tiempo cambia la variable y reinicia la tarea, no la configura desde el panel.
- **La ventana de la tarea es diaria.** Entre dos corridas los datos existen hasta un día más de lo configurado; no hay purga en caliente al consumir un código. Es irrelevante para la regla del kiosco, que solo mira el último minuto.
- **La vista previa se purga a mano.** El script reconoce `--preview` y crea las tablas si faltan, pero no se ejecuta solo al arrancar; los datos de prueba pueden quedarse hasta que alguien lo corra.

## Referencias

- `backend/src/app/modules/access/retention.py` (`purge_expired_access_data`, `retention_policy_from_env`, `RetentionPolicy`, `PurgeResult`, límites 1–3650)
- `backend/purge_access_data.py` (`--dry-run`, `--preview`, `--database-url`, `--codes-days`, `--attempts-days`)
- `backend/tests/test_access_retention.py` (9 pruebas)
- `backend/src/app/modules/access/models.py` (`MemberAccessCode`, `KioskAttempt`)
- `docs/06-operacion/despliegue.md` (tarea programada), `docs/06-operacion/respaldos-y-recuperacion.md`
- `docs/deuda-tecnica.md` (límites que quedan), `docs/02-modulos/control-de-acceso.md`
