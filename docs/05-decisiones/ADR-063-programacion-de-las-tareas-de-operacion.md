# ADR-063: Programación de las tareas de operación

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Cierra el límite de ADR-058 y ADR-062 («la tarea depende de que alguien la programe a mano»)

## Contexto

El proyecto no tiene programador dentro de la aplicación: la purga de accesos (ADR-040), la de los acuses del correo (ADR-058) y la consulta de los acuses del push (ADR-062) son scripts que alguien debe lanzar desde el cron del servidor. La documentación de despliegue los mostraba como líneas sueltas que el operador copiaba a mano, con tres problemas previsibles:

- **Duplicados al reinstalar.** Cambiar la contraseña de la base o mover la carpeta obligaba a editar una línea de tres variables; copiar el bloque otra vez dejaba dos trabajos haciendo lo mismo, y no había forma de saber cuál sobraba.
- **Deriva entre entornos.** La hora de la purga, la frecuencia de los acuses y el `--limit` vivían en la cabeza de quien desplegaba y en un documento, no en un artefacto reproducible.
- **Un error de sintaxis solo se descubre al día siguiente.** Un `crontab` mal editado no avisa: la tarea sencillamente no corre, y la primera señal es un acuse vencido o una tabla que crece.

Las tres tareas comparten forma —un script de `backend/`, la misma `DATABASE_URL`, el mismo intérprete y una bitácora—, así que no hay razón para que el operador las escriba por separado.

## Decisión

- **Un instalador versionado.** `backend/ops_cron.py` renderiza las tres entradas como un solo bloque y las instala en el crontab del usuario actual. No es un programador: sigue siendo el cron del host (ADR-058, ADR-062), pero el texto que corre se genera desde el repositorio y no se copia a mano.
- **El bloque lleva marcas.** Empieza en `# BEGIN gimnasio-ops` y termina en `# END gimnasio-ops`. Instalar reemplaza exactamente ese tramo y conserva las demás líneas del crontab; volver a instalar el mismo bloque no cambia nada. Un bloque sin cierre descarta el resto del archivo: una mitad escrita no se distingue de las líneas del usuario y dejarla duplicaría trabajos.
- **Tres modos, uno por defecto.** `--print` imprime el bloque sin tocar nada y es el valor por defecto, para revisarlo antes; `--install` crea la carpeta de bitácoras y escribe el crontab con `crontab -`; `--uninstall` retira el bloque marcado y deja el resto intacto. Los tres son excluyentes.
- **La configuración se valida antes de escribir.** `--daily-at` exige `HH:MM` entre `00:00` y `23:59`; `--receipts-every` acepta de 5 a 59 minutos (se escribe `*/N`) o 60 (se escribe `0 * * * *`); `--limit` va de 1 a 1000, el tope de Expo; la `DATABASE_URL` no puede estar vacía ni contener saltos de línea. Una configuración inválida sale con código 2 y no modifica el crontab.
- **Los valores por defecto son los que ya documentaba la operación.** La purga de accesos corre a las `03:15` y la de los acuses del correo treinta minutos después, para no solaparse; los acuses del push se consultan cada 30 minutos (`--receipts-every`), dentro de la ventana de 24 horas que Expo conserva; `--limit` queda en 200 tickets por corrida. Las tres horas son **locales del servidor** —el cron del host no conoce `APP_TIMEZONE`—, así que el club debe fijar la zona del servidor o ajustar `--daily-at`.
- **La orden se arma con rutas y URL citadas.** Cada línea hace `cd <app-dir> && DATABASE_URL=<url> <python> <script> >> <log> 2>&1`: los scripts insertan `.\src` relativo al directorio de trabajo, y `shlex.quote` protege una URL con caracteres especiales o una carpeta con espacios. La carpeta de bitácoras se crea con `--install` (`<app-dir>/logs` por defecto) y cada tarea escribe la suya: `purge-access.log`, `purge-email.log` y `push-receipts.log`.
- **La URL de la base queda en el crontab del usuario.** Es el mismo secreto que ya usa el proceso y el modo `600` del archivo lo protege; por eso `--print` advierte que su salida no se pega en un ticket ni en un chat. El entorno del cron no hereda `DATABASE_URL`, así que la variable se escribe en cada línea en vez de depender de un perfil de shell.
- **Instalar exige que los tres scripts existan.** Antes de escribir, `--install` comprueba que `purge_access_data.py`, `purge_email_receipts.py` y `sync_push_receipts.py` estén en `--app-dir`; si falta alguno sale con código 2 y no toca el crontab. Así una carpeta equivocada se detecta al instalar y no a las tres de la mañana.
- **Sin cron no hay instalación silenciosa.** Si el comando `crontab` no existe (Windows, un contenedor mínimo), el instalador explica que hay que instalar cron o usar `--print` para copiar el bloque en el programador del servidor, y sale con código 1. La vista previa local no programa nada.
- **La pasada de acuses distingue su propio `--preview`.** El script acepta `--preview` y lo pasa a `sync_member_push_receipts(..., preview=...)`, que antes solo miraba `PREVIEW_MODE`; sin esa opción la corrida de vista previa decía «diferida» sin serlo. La variable de entorno sigue siendo el valor por defecto.
- **Actualización de ADR-071 (2026-10-31).** El bloque pasó a cuatro entradas: `flush_staff_push.py` drena la cola del push web del personal cada 15 minutos por defecto (`--staff-push-every`, de 5 a 59 o 60) y escribe `staff-push.log`; `--install` exige también ese script. Lo demás de esta decisión no cambia.
- **Actualización de ADR-073 (2026-10-31).** El bloque pasó a cinco entradas: `close_physio_day.py` cierra el día anterior de la agenda de fisioterapia a las `00:30` por defecto (`--physio-close-at`, `HH:MM`) y escribe `physio-close.log`; `--install` exige también ese script. Lo demás de esta decisión no cambia.
- **Actualización de ADR-074 (2026-10-31).** El bloque pasó a seis entradas: `purge_push_data.py` es la tercera purga diaria, treinta minutos después de la del correo (`--daily-at` más dos escalones de 30 min, `04:15` con los valores por defecto), escribe `purge-push.log` y `--install` exige también ese script. Lo demás de esta decisión no cambia.
- **Actualización de ADR-075 (2026-10-31).** El bloque pasó a siete entradas: `purge_inbox_data.py` es la cuarta purga diaria, noventa minutos después de la primera (`--daily-at` más tres escalones de 30 min, `04:45` con los valores por defecto), escribe `purge-inbox.log` y `--install` exige también ese script. Es la primera tarea que poda avisos y no solo datos operativos, con las reglas de ADR-075. Lo demás de esta decisión no cambia.
- **Actualización de ADR-076 (2026-10-31).** El bloque pasó a ocho entradas: `emit_deferred_notices.py` materializa por cron los recordatorios del socio y los avisos del personal que dependían de la lectura, cada 60 minutos por defecto (`0 * * * *`, `--notices-every` de 5 a 59 o 60), escribe `deferred-notices.log` y `--install` exige también ese script. Es la primera entrada que no purga ni cierra nada: solo escribe avisos. Lo demás de esta decisión no cambia.
- **Actualización de ADR-078 (2026-10-31).** El bloque sigue con ocho entradas y la misma hora para los avisos diferidos; lo que cambia es lo que hace esa entrada: además de escribir los recordatorios del socio, encola su push y drena la cola en la misma corrida. El comentario del bloque la rotula «avisos diferidos con su push» y el tope de envíos se ajusta en el script (`--push-limit`, 20 por defecto), no en el cron. Lo demás de esta decisión no cambia.
- **Cada tarea sigue siendo idempotente y sin estado compartido.** El cron no coordina nada: si una corrida tarda más que el intervalo, la siguiente corre igual. Las purgas borran lo que ya no aplica (una segunda pasada borra `0`) y la consulta de acuses no reescribe el estado de la entrega, así que una corrida solapada como mucho repite una consulta.

## Consecuencias y límites

- **Depende del cron del host.** No hay worker, cola ni planificador en la aplicación: en un contenedor sin cron, o en Windows, el bloque no se instala y hay que usar el programador del sistema. La vista previa nunca programa tareas reales.
- **No hay bloqueo de solapamiento.** Los acuses cada 30 minutos con 200 tickets y tres consultas externas caben de sobra, pero una corrida lenta no impide que la siguiente empiece; las operaciones son idempotentes, no exclusivas.
- **No hay rotación de bitácoras.** Los tres archivos crecen sin límite; `--log-dir` permite llevarlos a la carpeta que ya rote el servidor, pero el instalador no configura `logrotate` ni borra nada.
- **Un fallo solo se ve en la bitácora.** El instalador valida la forma y la existencia de los scripts, no la conectividad con la base ni con Expo; una credencial caducada aparece como una línea de error en el archivo correspondiente. No hay alerta ni correo por una tarea fallida.
- **La hora es la del servidor.** El cron no interpreta `APP_TIMEZONE`; si el servidor está en UTC, la purga de las `03:15` cae a otra hora local. Conviene fijar la zona del host o ajustar `--daily-at` al desplegar.
- **La URL de la base se duplica en el crontab.** Cambiarla exige reinstalar el bloque para que las tres líneas la tomen; el `--install` es idempotente y reemplaza el anterior, pero no hay sincronización con el `.env` del proceso.
- **No se instala un temporizador de sistema.** Se eligió el crontab del usuario por ser el mecanismo que ya describían los ADR y el más portable en un VPS; un `systemd` timer o una tarea de Windows quedan fuera de este incremento.
- **La instalación es local al usuario.** El bloque vive en el crontab de quien ejecuta el instalador; si la aplicación corre con otro usuario, hay que instalarlo con ese usuario o mover el crontab.

## Referencias

- `backend/ops_cron.py` (`build_block`, `replace_block`, `remove_block`, `--print`, `--install`, `--uninstall`)
- `backend/purge_access_data.py`, `backend/purge_email_receipts.py`, `backend/sync_push_receipts.py`, `backend/flush_staff_push.py` (ADR-071), `backend/emit_deferred_notices.py` (ADR-076)
- `backend/src/app/modules/notifications/push_receipts.py` (`sync_member_push_receipts(..., preview=...)`)
- `backend/tests/test_ops_cron.py` (35 pruebas)
- `backend/tests/test_member_push_receipts.py` (12 pruebas, incluida la del `preview` explícito)
- `docs/06-operacion/despliegue.md` (mantenimiento programado)
- ADR-040 (retención del kiosco), ADR-058 (retención de los acuses del correo), ADR-062 (acuses de entrega del push)
