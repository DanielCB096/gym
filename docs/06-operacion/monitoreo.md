# Monitoreo

## Objetivo

Definir qué señales existen hoy para saber si el sistema sigue operando y cómo revisarlas sin inventar una plataforma que el repositorio todavía no tiene.

Este documento describe **monitoreo manual**. No hay métricas, alertas automáticas ni tablero de disponibilidad instalados. Las brechas que deben cerrarse antes de producción están al final.

## Señales disponibles

### 1. Salud del backend

El backend expone un único endpoint de salud:

```bash
curl -fsS https://<host-del-backend>/health
```

Respuesta esperada:

```json
{"status": "ok", "preview_mode": false}
```

- Un `200` solo demuestra que el proceso responde. **No comprueba la base de datos, Redis, SMTP, Conekta ni el estado de las migraciones.**
- En producción `preview_mode` debe ser `false`. Si es `true`, los cobros y correos se simulan; trátalo como una configuración peligrosa, no como una vista previa inofensiva.
- El endpoint está definido en `backend/src/app/main.py` y no requiere autenticación.
- El Compose de staging lo consulta cada 10 segundos como healthcheck del contenedor `api`. En producción depende del mecanismo de despliegue elegido; el repositorio no incluye esa configuración.

No hay un healthcheck equivalente para el panel web ni para el kiosco. Para el panel, comprueba que la página de login carga y que el BFF puede autenticar. Para el kiosco, comprueba que la tablet muestra la pantalla de captura y que un código válido se acepta.

### 2. Cron de operación

Las tareas programadas no viven dentro de la aplicación: dependen del cron del servidor y se instalan con `backend/ops_cron.py` (ver [despliegue.md](despliegue.md)). Son **doce** entradas.

Comprobaciones básicas:

```bash
crontab -l
cd /srv/gimnasio/backend
ls -l --time-style=full-iso logs
```

- `crontab -l` debe mostrar el bloque entre `# BEGIN gimnasio-ops` y `# END gimnasio-ops`. Si falta, el cron no está instalado para ese usuario.
- Cada corrida agrega su salida a un archivo de `logs/`. Si el archivo no cambia dentro del intervalo esperado, la tarea está detenida o fallando antes de escribir.
- Las líneas **no llevan fecha ni hora**. La fecha de modificación del archivo y el orden de las líneas son la única referencia temporal.
- El bloque no configura `MAILTO` ni alertas: un error solo queda en el archivo, salvo que el crontab del host tenga un `MAILTO` global.

| Tarea | Frecuencia por defecto | Bitácora | Línea de una corrida sana |
| --- | --- | --- | --- |
| Cierre del día de fisioterapia | diaria a las `00:30` | `logs/physio-close.log` | `Día de fisioterapia cerrado: …` |
| Purga de accesos | diaria a las `03:15` | `logs/purge-access.log` | `Purga aplicada — retención de …` |
| Purga de acuses del correo | diaria a las `03:45` | `logs/purge-email.log` | `Purga aplicada — retención de …` |
| Purga de acuses y entregas del push | diaria a las `04:15` | `logs/purge-push.log` | `Purga aplicada — acuses de …` |
| Purga de la bandeja y entregas del personal | diaria a las `04:45` | `logs/purge-inbox.log` | `Purga aplicada — avisos de …` |
| Acuses del push del socio | cada 30 minutos | `logs/push-receipts.log` | `Acuses consultados: …` |
| Push web del personal | cada 15 minutos | `logs/staff-push.log` | `Cola del push web del personal: …` |
| Correo del personal | cada 15 minutos | `logs/staff-email.log` | `Cola de correo del personal: …` |
| Correo de socios | cada 15 minutos | `logs/member-email.log` | `Cola de correo de socios: …` |
| Avisos diferidos y su push | cada 60 minutos | `logs/deferred-notices.log` | `Revisados … socios con recordatorios en ventana.` |
| Reportes financieros | diaria a las `06:00` | `logs/income-reports.log` | `Reportes financieros: …` |
| Renovaciones de membresía | cada 15 minutos | `logs/membership-renewals.log` | `Pasada de renovaciones completada: …` |

Las horas del cron son **locales del servidor**, no `APP_TIMEZONE`. Si el host está en otra zona, ajusta la zona del host o las banderas `--daily-at`, `--physio-close-at` y `--income-reports-at`.

Qué mirar en cada grupo:

- **Purgas:** la línea `Purga aplicada` y los conteos. Un `Simulación (no se borró nada)` significa que alguien ejecutó con `--dry-run`; no es una purga real. Un error de configuración o de base termina con código distinto de cero, pero el cron no lo usa para avisar.
- **Cierre de fisioterapia:** debe imprimir el día cerrado, incluso con `0 citas`. Si se perdió una corrida, hay que recuperar cada día con `--date AAAA-MM-DD`; no hay barrido automático de varios días.
- **Acuses del push:** revisa `con error`, `vencidos` y `Entregas enviadas que siguen sin acuse`. Un error distinto de `DeviceNotRegistered` genera un aviso al personal; `DeviceNotRegistered` retira el dispositivo. Expo puede tardar hasta 24 horas y el ticket vence a las 24 horas.
- **Colas de push y correo:** revisa `pendientes que quedan`. Un número que no baja entre corridas indica un cuello de botella. Las entregas `failed` no se reintentan solas: esperan a que una persona las reintente desde el panel (el push web del personal y el correo del personal) o al reintento limitado del correo de socios (máximo cinco intentos).
- **Correo del personal apagado:** si el interruptor del club está apagado, la corrida imprime `El correo del personal está apagado en la política del club; las entregas siguen pendientes.` No es un fallo, pero la cola crecerá.
- **Avisos diferidos:** revisa cuántos avisos se escribieron y cuántos push quedaron pendientes. La ventana de silencio del club o del socio puede retener los push; saldrán en la pasada siguiente.
- **Reportes financieros:** revisa `intento(s)`, `enviado(s)`, `fallido(s)` y `omitido(s)`. El script termina con código 1 si hubo fallos, aunque la línea de resumen se haya escrito.
- **Renovaciones:** revisa vencidas, cobros iniciales, reintentos y conciliaciones. Mientras producción siga deshabilitada, la corrida puede fallar con código 2 al validar que solo se opera en sandbox; es esperado, pero confirma que la renovación automática no está procesando cobros reales.

### 3. Colas y estado de negocio en el panel

Además de los logs, el panel expone el estado de las colas. Úsalas para confirmar que un problema es de negocio y no solo de un archivo:

- **Push del socio:** `GET /admin/notifications/push-deliveries` lista las entregas; `POST /admin/notifications/push-deliveries/receipts` consulta los acuses de Expo. Revisa pendientes, fallidas y el próximo reintento.
- **Correo del personal:** `GET /admin/staff/notifications/deliveries` lista las entregas. Las fallidas se reintentan a mano desde el panel.
- **Push web del personal:** `GET /admin/staff/push/deliveries` lista las entregas por navegador. Rotar `VAPID_PRIVATE_KEY` invalida todos los navegadores registrados.
- **Kiosco:** `GET /admin/kiosk/devices` muestra los dispositivos y su caducidad. El token vive 90 días y el panel avisa cuando faltan 15 días o menos.
- **Accesos:** `GET /admin/access-events` permite revisar entradas, denegaciones y accesos manuales. Un aumento de denegaciones puede ser un problema de membresías, de código o de configuración del kiosco, no de disponibilidad.
- **Reportes y renovaciones:** no hay una pantalla de historial de entregas de reportes ni de conciliación de renovaciones; usa el resumen de `income-reports.log` y `membership-renewals.log` y, para renovaciones, `run_membership_renewals.py --dry-run`.

### 4. Base de datos, disco y respaldos

El endpoint `/health` no consulta la base. Para comprobar la conexión y el esquema, desde el servidor:

```bash
cd /srv/gimnasio/backend
DATABASE_URL="postgresql+psycopg://..." PYTHONPATH=src .venv/bin/python - <<'PY'
import os
from sqlalchemy import create_engine, text

with create_engine(os.environ["DATABASE_URL"]).connect() as connection:
    print(connection.execute(text("select 1")).scalar_one())
PY

DATABASE_URL="postgresql+psycopg://..." .venv/bin/python -m alembic current
```

No pegues la URL real en un ticket, un chat o una captura. El prefijo `+psycopg` es de SQLAlchemy; si usas `psql` directamente, quita ese sufijo.

Tamaño y crecimiento:

```bash
df -h /srv/gimnasio
du -sh /srv/gimnasio/backend/logs
du -sh "$PROGRESS_PHOTOS_DIR"
```

```sql
SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS total
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 20;
```

Los respaldos no los hace el cron. El estado real y los procedimientos están en [respaldos-y-recuperacion.md](respaldos-y-recuperacion.md). Mientras no exista un respaldo automático verificado, el RPO de 15 minutos y el RTO de 4 horas siguen sin demostrarse.

### 5. Registros de la aplicación

La aplicación no configura un archivo de log propio: el backend escribe en `stdout`/`stderr` y el destino depende del despliegue (contenedor, servicio o proceso). Revisa esos registros para errores HTTP, trazas de Python y fallos de proveedores.

`LOG_LEVEL` y `SENTRY_DSN` aparecen en `.env.example`, pero ningún módulo del repositorio los lee: no cambian el nivel de log ni envían errores a Sentry. No los consideres una capacidad instalada.

## Rutina recomendada

### Diaria, al abrir o antes de la jornada

1. Consulta `/health` y confirma `preview_mode: false`.
2. Revisa que el panel de login y el kiosco respondan.
3. Comprueba `crontab -l` y que las bitácoras diarias tengan una corrida reciente.
4. Revisa las colas del panel: push pendiente/fallido, correo pendiente/fallido, token del kiosco por caducar.
5. Revisa el espacio libre y el tamaño de `logs/`.
6. Confirma que el respaldo contratado reportó éxito dentro de la ventana acordada.

### Semanal

1. Revisa el historial de denegaciones de acceso y los accesos manuales.
2. Revisa entregas fallidas que nadie haya reintentado.
3. Ejecuta `run_membership_renewals.py --dry-run` para ver vencimientos e intentos sin conciliar, sin cobrar.
4. Revisa el crecimiento de las tablas grandes y de las fotos de progreso.
5. Verifica que la rotación externa de logs esté funcionando.

### Mensual

1. Prueba una restauración aislada según [respaldos-y-recuperacion.md](respaldos-y-recuperacion.md).
2. Revisa retenciones, accesos y cuentas activas.
3. Revisa los umbrales de este documento y ajústalos si cambió la operación.

## Umbrales sugeridos

No están automatizados. Son valores de trabajo para decidir cuándo investigar; ajústalos con el club.

| Señal | Umbral | Acción |
| --- | --- | --- |
| `/health` | Dos comprobaciones seguidas fallidas | Abrir el manual de incidentes por indisponibilidad. |
| `preview_mode` | `true` en producción | Tratarlo como configuración peligrosa: los cobros y correos se simulan. |
| Bitácora cada 15 o 30 minutos | Sin cambio en 60 minutos | Revisar cron y ejecutar la tarea a mano. |
| Bitácora cada 60 minutos | Sin cambio en 2 horas | Revisar cron y ejecutar la tarea a mano. |
| Bitácora diaria | Sin cambio en 26 horas | Revisar cron y recuperar la corrida. |
| Cola pendiente | Crece en dos corridas seguidas | Revisar proveedor, credenciales y límite por corrida. |
| Entregas fallidas | Cualquier aumento | Revisar el motivo; recordar que `failed` no se reintenta solo en las colas del personal. |
| Token del kiosco | 15 días o menos | Rotarlo desde el panel antes de que caduque. |
| Espacio libre | Menos del 15 % | Liberar de forma controlada; no borrar datos ni archivos de base. |
| Respaldo | Sin éxito dentro de la ventana RPO | Escalar; el RPO no está cubierto. |

## Brechas antes de producción

- **Sin alertas automáticas:** un cron detenido no avisa. Hay que conectar un vigilante externo (por ejemplo, un dead-man's switch o una alerta sobre la fecha de modificación de cada bitácora) o revisar manualmente. No está implementado.
- **Sin rotación de bitácoras:** `ops_cron.py` no rota ni comprime; los archivos crecen sin límite. Usa `--log-dir` hacia una carpeta que ya rote el servidor o configura `logrotate` fuera del repositorio.
- **Sin bloqueo de solapamiento:** una corrida lenta puede coincidir con la siguiente. Las operaciones son idempotentes en lo que permite cada integración, pero no ejecutes a mano una pasada larga mientras el cron está activo.
- **Sin marcas de tiempo:** las líneas de los scripts no incluyen fecha ni hora. Para auditoría, envuélvelas con un timestamp o usa la fecha del archivo.
- **Health parcial:** `/health` no consulta base, Redis, SMTP ni Conekta. Un `200` no prueba que se pueda cobrar, enviar correo o autenticar.
- **Sin métricas ni APM:** no hay `/metrics`, Prometheus, trazas ni Sentry. `SENTRY_DSN` y `LOG_LEVEL` están declaradas pero no se usan.
- **Entorno del cron incompleto:** `ops_cron.py` solo inyecta `DATABASE_URL`. Las credenciales de SMTP, VAPID y Conekta deben estar en el entorno del usuario del cron, no en el bloque. Además, diez de los doce scripts insertan `.\src`, una ruta de Windows; en Linux necesitan `PYTHONPATH=src` o fallan con `ModuleNotFoundError`. Verifícalo con una corrida manual antes de confiar en el cron.
- **Zona horaria:** las horas del cron son del servidor, no `APP_TIMEZONE`. Un host en UTC desplaza el cierre y las purgas.
- **Respaldo no monitorizado:** el cron no respalda ni verifica copias. RPO/RTO siguen pendientes de demostración.
- **Renovaciones deshabilitadas en producción:** el cron puede salir con código 2 por diseño. No lo interpretes como una caída, pero tampoco como una renovación funcionando.
- **Colas con intervención manual:** las entregas `failed` de correo y push del personal no se reintentan solas.
- **Acuses del correo:** no hay proveedor real conectado al webhook de acuses; `sent` significa que el SMTP aceptó el mensaje, no que el socio lo recibió.
