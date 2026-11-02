# ADR-083: Envío programado de reportes financieros

- **Fecha:** 2026-11-01
- **Estado:** aceptada
- **Relacionada con:** ADR-063 (cron de operación), ADR-081 (correo del socio), ADR-082 (primer envío programado) y el módulo 7 (reportes financieros).

## Contexto

ADR-082 implementó primero el envío del CSV de ingresos, dejando fuera los otros cinco reportes para limitar el alcance inicial. Se aprobó extender ese mismo canal a los seis CSV ya existentes sin agregar destinatarios ni inferir direcciones de socios o usuarios.

## Decisión

- **Los seis reportes actuales.** La pasada incluye `overview`, `revenue`, `memberships`, `operations`, `maintenance` e `inventory`, usando `build_report` y `build_export` existentes. No se crean formatos ni consultas nuevos.
- **Misma audiencia y política de seguridad.** Se conservan `INCOME_REPORT_RECIPIENTS`, `INCOME_REPORT_ALLOWED_DOMAINS` y el máximo de diez destinatarios internos explícitos de ADR-082. Todos los tipos de reporte se envían a esa audiencia; no hay selección por reporte ni configuración desde el panel.
- **Mismas cadencias.** Cada reporte produce un CSV diario del día anterior; se agrega uno semanal el lunes y uno mensual el día 1. Los intervalos son periodos locales cerrados del club y respetan `APP_TIMEZONE`.
- **Una entrega idempotente por reporte, periodo y destinatario.** `scheduled_report_deliveries.report_name` diferencia la unicidad lógica de cada CSV. El valor previo se migra como `revenue`, conservando las claves idempotentes existentes de ingresos.
- **Migración aditiva.** `20261101_0080` agrega el nombre del reporte y restringe los valores al catálogo existente. El downgrade se niega si ya hay entregas de otros reportes, para no perder la identidad de esas filas.

## Consecuencias y límites

- El volumen por destinatario es de seis correos diarios; doce los lunes; y dieciocho cuando el primer día del mes coincide con lunes. Cada destinatario recibe todos los seis tipos, incluidos operación, mantenimiento e inventario.
- La administración de destinatarios y las preferencias por tipo desde el panel siguen fuera de alcance. Para dejar de recibir todos los reportes hay que retirar la dirección de la configuración operativa.
- Se conservan las limitaciones de ADR-082: SMTP es at-least-once ante una caída entre aceptación y registro; no hay alertas automáticas ni retención del historial de entregas.
- La migración debe aplicarse y probarse en PostgreSQL antes de desplegar; las pruebas locales SQLite no sustituyen esa verificación.

La audiencia fija y la selección idéntica por destinatario de esta decisión inicial fueron sustituidas por la configuración por destinatario descrita en ADR-084. Las cadencias, los seis formatos y la política de idempotencia no cambiaron.

## Implementación

- Migración `20261101_0080_scheduled_report_type.py`.
- El mismo CLI `backend/send_scheduled_income_reports.py` envía los seis CSV y conserva la cadencia configurada en `ops_cron.py`.
- Pruebas en `backend/tests/test_scheduled_income_reports.py`, sin conexión SMTP real.
