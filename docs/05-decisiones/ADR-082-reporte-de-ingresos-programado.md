# ADR-082: Reporte de ingresos programado por correo

- **Fecha:** 2026-11-01
- **Estado:** aceptada
- **Relacionada con:** ADR-063 (cron de operación), ADR-081 (correo del socio) y el módulo 7 (reportes financieros).

## Contexto

El reporte de ingresos ya se consulta y exporta como CSV desde el panel, pero el dueño y el equipo financiero necesitan recibir periódicamente una copia sin entrar al sistema. La primera entrega debe evitar que información financiera se envíe a direcciones de socios o a destinatarios no aprobados, y debe recuperarse cuando una corrida programada falla.

## Decisión

- **Solo ingresos y destinatarios configurados.** El primer incremento envía el CSV de ingresos a las direcciones explícitas de `INCOME_REPORT_RECIPIENTS`. Cada dominio debe estar en `INCOME_REPORT_ALLOWED_DOMAINS`; no se obtiene la audiencia de los socios ni de las cuentas. El máximo es diez destinatarios.
- **Cadencias sobre periodos cerrados del club.** La pasada diaria crea el reporte del día anterior; los lunes agrega la semana anterior completa y el primer día del mes agrega el mes anterior completo. Los periodos son inclusivos y usan `APP_TIMEZONE`.
- **Cron del host.** `ops_cron.py` instala una pasada diaria, a las 06:00 locales del servidor por defecto. El script decide las cadencias según la fecha local del club. `--today` permite recuperar manualmente una fecha omitida.
- **Registro mínimo e idempotencia.** `scheduled_report_deliveries` guarda frecuencia, periodo, hash del destinatario, estado, intentos y marcas de tiempo; no guarda correo ni adjunto. La clave determinista evita repetir un envío completado y permite reclamar una fila `sending` vencida o reintentar un fallo hasta cinco veces. `--retry-exhausted` habilita una recuperación manual de fallos agotados.
- **Transporte SMTP existente.** El reporte se adjunta como CSV y se entrega mediante `app/mailer.py`. Las direcciones y los dominios permitidos, junto con la configuración SMTP, se mantienen en el entorno operativo o en `backend/.env`, nunca en el repositorio. El CLI carga ese archivo sin sobrescribir variables ya presentes.
- **Vista previa sin correo real.** `--dry-run` valida configuración y muestra periodos sin abrir la base; `--preview` usa `gym_preview.db` y fuerza la simulación.

## Consecuencias y límites

- La entrega SMTP es **al menos una vez**, no exactamente una vez: una caída después de la aceptación del mensaje por SMTP y antes de registrar el éxito puede causar un duplicado al recuperar el intento vencido. Un `Message-ID` determinista ayuda a correlacionar, pero no obliga al proveedor a deduplicar.
- El CSV es una consulta operativa, no un cierre contable ni un CFDI. Un reintento vuelve a calcular el periodo y puede reflejar cambios retroactivos.
- La administración de destinatarios desde el panel, los otros cinco reportes y las alertas de fallos quedan fuera de este incremento.
- La tarea depende del cron del servidor y su bitácora; no hay bloqueo global de ejecuciones ni alerta automática si el job deja de correr.

## Implementación

- Migración `20261101_0079_scheduled_income_reports.py`.
- Registro idempotente en `scheduled_report_deliveries` y servicio en `app/modules/reports/scheduled.py`.
- CLI `backend/send_scheduled_income_reports.py`, integrado al cron mediante `--income-reports-at`.
- Pruebas en `backend/tests/test_scheduled_income_reports.py` y `backend/tests/test_ops_cron.py`.

## Actualización de alcance

ADR-083 extiende este primer incremento a los seis reportes existentes, manteniendo la misma audiencia, allowlist, cron y cadencias. La columna `report_name` permite idempotencia independiente y clasifica las filas ya existentes como `revenue`.
