# Manual de incidentes

## Objetivo

Guiar la respuesta ante una caída, un error de datos, una tarea programada detenida o una cola de notificaciones atascada, sin improvisar pasos que puedan agravar la pérdida.

Este manual cubre la operación técnica del sistema. Un incidente de seguridad o de datos personales se trata además con los procedimientos de seguridad, privacidad y derechos ARCO; una restauración de base se rige por [respaldos-y-recuperacion.md](respaldos-y-recuperacion.md).

## Roles y contactos

| Rol | Responsabilidad | Contacto |
| --- | --- | --- |
| Responsable técnico | Diagnostica, ejecuta la recuperación y deja evidencia | Completar antes de producción |
| Gerencia o dueño | Autoriza parar el servicio, restaurar y reabrir | Completar antes de producción |
| Responsable del módulo | Valida caja, acceso, membresías y datos restaurados | Completar antes de producción |
| Proveedores | Hosting, PostgreSQL, SMTP, Conekta o Expo, según contrato | Completar antes de producción |

Una sola persona puede cubrir varios roles en un club pequeño, pero una restauración de producción necesita autorización explícita y registro de quién la autorizó, quién la ejecutó y quién la validó.

## Severidad

Los tiempos son objetivos de trabajo, no un compromiso contractual. Si hay duda entre dos niveles, empieza por el más grave.

| Nivel | Ejemplos | Objetivo inicial |
| --- | --- | --- |
| **S1 — Crítico** | Backend o base caídos; no se puede cobrar ni registrar acceso; pérdida o corrupción de datos; sospecha de acceso no autorizado; cobros duplicados o inciertos | Atención inmediata; recuperar dentro del RTO de 4 horas y preservar datos |
| **S2 — Alto** | Panel operativo pero una función clave falla; correo o push acumulados; cron detenido; reportes sin enviar; kiosco sin token | Mismo día |
| **S3 — Medio** | Una tarea programada falla sin impacto directo; una cola fallida requiere reintento manual; un reporte aislado no llegó | Siguiente día hábil |
| **S4 — Bajo** | Error visual, texto incorrecto o documentación desactualizada | Según prioridad |

## Primeros 15 minutos

1. Registra hora de detección, quién reporta, síntomas, módulos afectados y cambios recientes (despliegue, migración, rotación de secretos, cambio de configuración).
2. **No reinicies en cascada, no ejecutes migraciones y no restaures** hasta entender el alcance. Si hay pérdida de datos o sospecha de seguridad, preserva logs, base y evidencia antes de tocar nada.
3. Comprueba `/health` y el valor de `preview_mode`. Un `200` no descarta una base caída.
4. Comprueba la base con una consulta simple y revisa el espacio libre.
5. Revisa `crontab -l` y la fecha de modificación de las bitácoras.
6. Clasifica la severidad y avisa a gerencia y al responsable técnico.
7. Comunica el estado y la próxima hora de actualización. No prometas una recuperación que aún no está confirmada.

## Diagnóstico rápido

| Síntoma | Primera comprobación | Sección |
| --- | --- | --- |
| El panel o la API no cargan | `/health`, proceso y puerto | [A](#a-el-backend-no-responde) |
| `/health` responde pero una operación falla | Base, configuración y `preview_mode` | [B](#b-el-backend-responde-pero-la-operación-falla) |
| Errores de base, lentitud o datos incoherentes | Conexión, disco y bloqueos | [C](#c-base-de-datos-inalcanzable-lenta-o-llena) |
| Las tareas programadas no corren | `crontab -l`, bitácoras y ejecución manual | [D](#d-cron-detenido-o-tarea-que-falla) |
| El correo no sale o se acumula | SMTP, consentimiento e interruptor del club | [E](#e-correo-atascado-o-sin-entregar) |
| El push no suena o se acumula | VAPID, tokens y acuses de Expo | [F](#f-push-atascado-o-sin-entregar) |
| Renovaciones o cobros fallan | `--dry-run`, configuración de Conekta y conciliación | [G](#g-renovaciones-y-cobros) |
| El kiosco rechaza o no valida | Token, motivo de denegación y red | [H](#h-acceso-y-kiosco) |
| Los reportes no llegan | Bitácora, destinatarios y allowlist | [I](#i-reportes-financieros) |
| El disco se llena o los logs crecen | `df`, `du` y tamaño de tablas | [J](#j-disco-y-bitácoras) |
| Sospecha de acceso o secreto expuesto | Preservar evidencia y avisar | [K](#k-incidente-de-seguridad) |

## A. El backend no responde

1. Distingue el tipo de fallo:

   ```bash
   curl -v https://<host-del-backend>/health
   ```

   - Conexión rechazada: el proceso no escucha o el puerto no está publicado.
   - Tiempo de espera: red, proxy, firewall o proceso colgado.
   - `500` o error de arranque: revisa `stdout`/`stderr` del proceso.

2. Si el despliegue es el staging local:

   ```bash
   docker compose --env-file .env.staging.local -f compose.staging.local.yml ps
   docker compose --env-file .env.staging.local -f compose.staging.local.yml logs --tail=200 api
   ```

   En producción usa el mecanismo con el que se desplegó. El repositorio no incluye una unidad `systemd` ni un script de arranque de producción.

3. Revisa el puerto y el proxy inverso, y confirma si hubo un despliegue o cambio de configuración reciente.
4. Si el proceso arranca y muere, lee el error de arranque antes de reintentar. Una `APP_TIMEZONE` inválida detiene el arranque; si falta `DATABASE_URL`, la API puede quedar sin base y las rutas que la usan responden `503`. No lo soluciones reiniciando a ciegas.
5. Reinicia una sola vez después de capturar los logs. Si vuelve a fallar, no entres en un ciclo de reinicios: pasa a la sección B o C.

## B. El backend responde pero la operación falla

1. Confirma `preview_mode`:

   ```bash
   curl -fsS https://<host-del-backend>/health
   ```

   Si es `true` en producción, los cobros y correos se están simulando. Trátalo como un incidente de configuración, no como una vista previa válida.

2. Comprueba la base con la consulta de la sección C.
3. Revisa las variables del proceso que atiende la petición:
   - `SECRET_KEY` con valor de ejemplo: el portal del socio responde `503` al emitir códigos.
   - `SMTP_HOST` ausente: el correo falla o queda en cola con error de configuración.
   - `VAPID_PRIVATE_KEY` ausente: el push web del personal aparece apagado.
   - `CONEKTA_SANDBOX_API_KEY`, `CONEKTA_SANDBOX_PUBLIC_KEY` o `MEMBERSHIP_PAYMENT_ENCRYPTION_KEY` ausentes: checkout y renovaciones fallan.
4. Distingue un `403` de permisos de una caída: si solo falla una cuenta, revisa roles y sesiones antes de tocar el servicio.
5. Si la base responde y la configuración está completa, revisa el log del proceso para la traza exacta y escala con ese mensaje.

## C. Base de datos inalcanzable, lenta o llena

1. Comprueba la conexión y el esquema:

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

   Si usas `psql` directamente, quita el sufijo `+psycopg` de la URL. No pegues la URL real en un ticket ni en un chat.

2. Revisa disco, conexiones y consultas lentas:

   ```bash
   df -h /srv/gimnasio
   ```

   ```sql
   SELECT count(*) AS conexiones FROM pg_stat_activity;
   SELECT pid, state, wait_event_type, query_start, left(query, 120) AS query
   FROM pg_stat_activity
   WHERE state <> 'idle'
   ORDER BY query_start;
   ```

3. Si el disco está lleno, evita escrituras nuevas y escala. **No borres archivos de PostgreSQL, WAL ni fotos de progreso para liberar espacio.** La liberación de logs se trata en la sección J.
4. Si hay bloqueos, identifica la consulta que bloquea antes de cancelar nada. No cierres sesiones de otros procesos sin confirmar qué están haciendo.
5. Si hay corrupción, pérdida de datos o un borrado accidental, pasa a [respaldos-y-recuperacion.md](respaldos-y-recuperacion.md). No restaures sin autorización, no sobrescribas la base sin conservar una copia del estado previo y no rehagas pagos, accesos o facturas a ciegas.
6. Después de una restauración, valida primero la base y el backend; deja el cron detenido hasta que los datos estén comprobados.

## D. Cron detenido o tarea que falla

1. Confirma que el bloque está instalado y con el usuario correcto:

   ```bash
   crontab -l
   ```

   Debe aparecer entre `# BEGIN gimnasio-ops` y `# END gimnasio-ops`. Si la aplicación corre con otra cuenta, el bloque debe estar en el crontab de esa cuenta.

2. Confirma que el servicio de cron está activo. En Debian/Ubuntu suele ser `systemctl status cron`; en RHEL, `crond`. Usa el nombre que corresponda al host.
3. Compara la fecha de modificación de cada bitácora con su frecuencia. Si una tarea de 15 minutos no escribe en una hora, o una diaria no escribe en 26 horas, trátala como detenida.
4. Lee el final de la bitácora:

   ```bash
   cd /srv/gimnasio/backend
   tail -n 100 logs/membership-renewals.log
   ```

5. Ejecuta la tarea a mano con el mismo entorno del cron:

   ```bash
   cd /srv/gimnasio/backend
   DATABASE_URL="postgresql+psycopg://..." PYTHONPATH=src .venv/bin/python sync_push_receipts.py
   ```

   - `ModuleNotFoundError: No module named 'app'`: falta `PYTHONPATH=src`. Diez de los doce scripts insertan `.\src`, una ruta de Windows; en Linux no basta.
   - Error de configuración: falta una variable del entorno (SMTP, VAPID o Conekta).
   - Error de base: vuelve a la sección C.
   - `--preview` usa `gym_preview.db` y simula; no sirve para diagnosticar la base real. Para las purgas usa `--dry-run` si solo quieres contar.

6. Códigos de salida: `0` terminó, `1` error de ejecución (base inalcanzable, fallo de proveedor o reportes fallidos) y `2` configuración inválida en la mayoría de los scripts. El cron **no** usa el código para avisar; el diagnóstico está en la bitácora.
7. Si el bloque falta o cambió la contraseña de la base, reinstala:

   ```bash
   cd /srv/gimnasio/backend
   DATABASE_URL="postgresql+psycopg://..." PYTHONPATH=src .venv/bin/python ops_cron.py --print
   DATABASE_URL="postgresql+psycopg://..." PYTHONPATH=src .venv/bin/python ops_cron.py --install
   ```

   Revisa la salida de `--print` antes de instalar. No la pegues con una URL real en un ticket o un chat.

8. No ejecutes a mano una pasada larga mientras el cron está activo: no hay bloqueo de solapamiento. Si hay acumulación, usa `--limit` y espera a que termine.

Recuperación por tarea:

| Tarea | Acción segura |
| --- | --- |
| Cierre de fisioterapia | Ejecutar con `--date AAAA-MM-DD` por cada día perdido; no hay barrido automático. |
| Purgas | Volver a ejecutar; usar `--dry-run` primero. Nunca borrar `access_events` a mano. |
| Acuses del push | Volver a ejecutar; un fallo de Expo se reintenta en la siguiente pasada. El ticket vence a las 24 horas. |
| Push web y correo del personal | Volver a ejecutar; las `failed` se reintentan desde el panel, no solas. |
| Correo de socios | Volver a ejecutar; máximo cinco intentos por entrega. Revisa SMTP y consentimiento. |
| Avisos diferidos | Volver a ejecutar; los push pueden quedar retenidos por la ventana de silencio. |
| Reportes financieros | Usar `--today AAAA-MM-DD` para recuperar una pasada y `--retry-exhausted` para reintentar agotados; revisa destinatarios. |
| Renovaciones | Usar `--dry-run` para ver vencimientos e intentos sin conciliar; no recrear un cobro incierto. |

## E. Correo atascado o sin entregar

1. Comprueba `SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_TLS` o `SMTP_USE_SSL`, `SMTP_USER`, `SMTP_PASSWORD` y `SMTP_FROM` en el proceso **que ejecuta la tarea**, no solo en `backend/.env`.
   - `ops_cron.py` solo inyecta `DATABASE_URL`.
   - `run_membership_renewals.py` y `send_scheduled_income_reports.py` cargan `backend/.env`; los drenajes de correo y push no lo hacen.
   - Si el cron no hereda esas variables, el correo falla aunque el backend web sí envíe.
2. Revisa el interruptor de correo del club para los avisos del personal. Apagado, la corrida lo informa y deja las entregas pendientes.
3. Para el correo de socios, confirma que el socio dio su consentimiento para esa categoría y que la dirección sigue coincidiendo con la guardada al encolar.
4. Revisa `logs/staff-email.log`, `logs/member-email.log` y `logs/income-reports.log`. Busca `fallidos`, `SMTP_HOST`, `Error` y trazas.
5. Reintenta desde el panel las entregas fallidas del personal. No borres filas para “resetear” la cola.
6. Recuerda que `sent` significa que el SMTP aceptó el mensaje, no que llegó a la bandeja. No hay un proveedor real conectado al webhook de acuses de entrega.
7. En staging, revisa Mailpit en `http://localhost:8025`; en producción, usa un destinatario de prueba consentido antes de tocar datos reales.

## F. Push atascado o sin entregar

1. Distingue los dos canales:
   - **Push del socio:** tokens de Expo; acuses en `logs/push-receipts.log`.
   - **Push web del personal:** suscripciones del navegador y VAPID; cola en `logs/staff-push.log`.
2. Confirma que `VAPID_PRIVATE_KEY` está configurada. Si se rotó, todos los navegadores quedaron invalidados y hay que volver a activarlos.
3. Revisa los acuses:
   - `DeviceNotRegistered`: el token se retira; el dispositivo debe volver a registrar el push.
   - Otro error: se escribe un aviso al personal y el operador decide si reenvía.
   - `vencidos`: el ticket de Expo superó las 24 horas.
4. Revisa pendientes y fallidas en `GET /admin/notifications/push-deliveries`, `GET /admin/staff/push/deliveries` y sus endpoints de reintento.
5. Ejecuta las pasadas manualmente si hace falta:

   ```bash
   cd /srv/gimnasio/backend
   DATABASE_URL="postgresql+psycopg://..." PYTHONPATH=src .venv/bin/python flush_staff_push.py
   DATABASE_URL="postgresql+psycopg://..." PYTHONPATH=src .venv/bin/python sync_push_receipts.py
   ```

6. La ventana de silencio del club o del socio puede retener un push; saldrá en la pasada siguiente. No lo fuerces desde la base.
7. `--preview` simula y no contacta al servicio de push; no demuestra que un dispositivo real suene. La prueba final requiere un navegador o teléfono real.

## G. Renovaciones y cobros

1. Mientras producción siga deshabilitada, `run_membership_renewals.py` puede terminar con código 2 al validar que solo opera en sandbox. Es esperado. **No habilites sandbox contra una base real para “hacer que funcione”.**
2. Para ver el estado sin escribir ni contactar a Conekta:

   ```bash
   cd /srv/gimnasio/backend
   DATABASE_URL="postgresql+psycopg://..." PYTHONPATH=src .venv/bin/python run_membership_renewals.py --dry-run
   ```

   Informa membresías vencidas e intentos `pending`, `processing` o `unknown` por conciliar.

3. Revisa `logs/membership-renewals.log` y busca vencidas, cobros iniciales, reintentos y conciliaciones.
4. Si un cobro quedó incierto, **no crees un segundo intento ni vuelvas a cobrar a mano**. Espera la conciliación, revisa el estado en Conekta y escala a gerencia. La regla del motor es no duplicar ante un resultado incierto.
5. Comprueba consentimiento, método de pago predeterminado, plan vigente, llave sandbox y clave de cifrado del método.
6. Para el flujo de negocio, consulta [renovacion-y-cobro-recurrente.md](../03-procesos/renovacion-y-cobro-recurrente.md) y [cobro-fallido-y-suspension.md](../03-procesos/cobro-fallido-y-suspension.md).
7. No se autorizan cobros productivos sin cerrar la validación E2E y la aprobación correspondiente.

## H. Acceso y kiosco

1. Identifica el motivo que muestra la tablet:
   - **Código inválido o vencido:** el socio debe generar uno nuevo; cada código sirve una sola vez.
   - **Membresía vencida:** cobra o regulariza antes de permitir la entrada.
   - **Demasiados intentos:** el kiosco alcanzó su límite; espera un minuto o usa otra tablet.
   - **Token inválido, revocado o caducado:** revisa el dispositivo en el panel. Si sigue en la lista, usa **Rotar token**; si aparece revocado, crea otro dispositivo.
2. Comprueba el token en `GET /admin/kiosk/devices`. Vive 90 días; el panel avisa con 15 días o menos.
3. Revisa la red de la tablet y del backend. **No hay validación offline:** un check-in sin red se pierde. Para una excepción, usa **Acceso manual** con su motivo y justificante.
4. Revisa `GET /admin/access-events` para distinguir un problema de membresía, horario, antipassback o código de un problema de red.
5. No busques torniquete, lector QR/RFID ni biometría: no están conectados en esta entrega.

## I. Reportes financieros

1. Revisa `logs/income-reports.log` y la línea `Reportes financieros: … intento(s), … enviado(s), … fallido(s), … omitido(s).` El script termina con código 1 si hubo fallos.
2. Comprueba los destinatarios:
   - Antes del primer guardado desde el panel se usa `INCOME_REPORT_RECIPIENTS`.
   - Después manda la configuración guardada.
   - `INCOME_REPORT_ALLOWED_DOMAINS` se aplica siempre; una dirección guardada que ya no cumple detiene la pasada. Hay un máximo de diez destinatarios.
3. Para ver la configuración sin abrir la base:

   ```bash
   cd /srv/gimnasio/backend
   PYTHONPATH=src .venv/bin/python send_scheduled_income_reports.py --dry-run
   ```

4. Para recuperar una pasada usa `--today AAAA-MM-DD`; para reintentar agotados, `--retry-exhausted`. `--preview` simula sin SMTP.
5. Revisa SMTP como en la sección E. El envío es “al menos una vez”: si el proceso cae después de que el SMTP acepta y antes de registrar el éxito, el reporte puede duplicarse.

## J. Disco y bitácoras

1. Mide:

   ```bash
   df -h /srv/gimnasio
   du -sh /srv/gimnasio/backend/logs
   du -sh "$PROGRESS_PHOTOS_DIR"
   ```

2. El cron **no rota ni comprime** las bitácoras. Configura una rotación externa; por ejemplo, un `logrotate` adaptado a la ruta real:

   ```text
   /srv/gimnasio/backend/logs/*.log {
       daily
       rotate 14
       compress
       missingok
       notifempty
       copytruncate
   }
   ```

   Es un ejemplo, no una configuración instalada. `copytruncate` evita tener que reiniciar el cron, pero puede perder las líneas escritas durante la copia.

3. No borres archivos de PostgreSQL, WAL, fotos de progreso ni tablas para liberar espacio. Usa las purgas aprobadas o la retención acordada.
4. Si el disco está lleno y el sistema sigue escribiendo, evita nuevas operaciones y escala. Un disco lleno puede impedir cobros, accesos y respaldos.

## K. Incidente de seguridad

1. Preserva logs, sesiones, base y evidencia. No borres ni “limpies” nada antes de entender el alcance.
2. Avisa a gerencia y al responsable técnico; si hay datos personales involucrados, activa el procedimiento de privacidad y derechos ARCO.
3. Si se expuso un secreto, rótalo **después** de preservar la evidencia y con autorización:
   - Contraseña de la base: actualízala y reinstala el cron, porque la URL queda escrita en el crontab.
   - `SECRET_KEY`: invalida los códigos vigentes del portal del socio.
   - SMTP, Conekta, VAPID o secretos de webhook: actualízalos en el entorno y verifica el servicio.
4. Si el incidente pudo permitir acceso no autorizado, mantén restringido el sistema hasta completar la investigación y la rotación.
5. No publiques la URL de la base, tokens del kiosco, contraseñas ni claves en tickets, chats o capturas.

## Recuperación segura

- **Reiniciar el servicio** solo corrige un proceso caído; no arregla una base corrupta ni un secreto ausente.
- **Restaurar la base** exige autorización, una copia verificada y un destino confirmado. Sigue [respaldos-y-recuperacion.md](respaldos-y-recuperacion.md); no sobrescribas producción sin conservar el estado previo cuando sea posible.
- **No recrees** pagos, accesos, facturas o membresías posteriores al punto restaurado. Identifícalos y concílialos por el proceso de negocio.
- Después de restaurar: valida la base, el esquema, el backend, las cuentas, los saldos, las fotos y las bitácoras; deja el cron detenido hasta que la validación termine. Puedes retirar el bloque con `ops_cron.py --uninstall` y reinstalarlo después.
- Si el incidente expuso credenciales, rótalas antes de reabrir y revisa el entorno del cron y del backend.

## Escalamiento y comunicación

1. Avisa a gerencia y al responsable técnico con severidad, alcance, hora de inicio y siguiente actualización.
2. Si el problema es de un proveedor (hosting, PostgreSQL, SMTP, Conekta o Expo), abre su canal de soporte con hora, identificadores y mensajes de error; no compartas secretos.
3. Si hay cobros o datos personales afectados, gerencia decide la comunicación al socio y la reapertura.
4. Mantén un registro único de hora, acción, resultado y responsable. No dependas de la memoria ni de capturas sueltas.

## Cierre del incidente

Registra, como mínimo:

- fecha, hora de detección y duración;
- severidad y módulos afectados;
- causa conocida o estado de la investigación;
- acciones ejecutadas y quién las autorizó;
- respaldo utilizado y punto temporal recuperado, si aplica;
- pérdida potencial y datos pendientes de reconciliación;
- validaciones realizadas antes de reabrir;
- secretos rotados y cambios de infraestructura;
- acciones preventivas, responsable y fecha de seguimiento.

Actualiza este manual, [monitoreo.md](monitoreo.md), el changelog y los umbrales si el incidente reveló una señal que faltaba. El cierre no es solo “ya funciona”: incluye la evidencia y la acción que evita que vuelva a ocurrir.
