# ADR-084: Configuración de destinatarios de reportes financieros

- **Fecha:** 2026-11-01
- **Estado:** aceptada
- **Relacionada con:** ADR-082 (primer envío programado), ADR-083 (seis reportes programados) y el módulo 7.

## Contexto

ADR-083 dejó fija la audiencia de los seis reportes en variables de entorno. El equipo necesita poder ajustar destinatarios y preferencias por reporte desde el panel sin perder la restricción a dominios internos ni la configuración operativa existente.

## Decisión

- El panel gestiona una lista completa de hasta diez direcciones internas. Cada destinatario puede seleccionar cualquier subconjunto de `overview`, `revenue`, `memberships`, `operations`, `maintenance` e `inventory`.
- Solo quien tiene `finance.manage` puede consultar o cambiar la configuración. Los endpoints validan el permiso en backend; ocultar la sección en el panel no es la barrera de seguridad.
- `INCOME_REPORT_ALLOWED_DOMAINS` permanece como allowlist obligatoria y se aplica tanto a la configuración del panel como al envío del cron. Una configuración guardada que ya no cumpla la allowlist detiene el envío con un error explícito hasta que se corrija.
- Antes del primer guardado, el panel muestra `INCOME_REPORT_RECIPIENTS` y los seis reportes seleccionados por cada dirección, y el cron sigue leyendo ese entorno. El primer guardado persiste la lista completa y convierte esa configuración en la fuente principal. Una lista guardada vacía desactiva los envíos; no reactiva el fallback de entorno.
- Si no hay direcciones de entorno, el panel comienza con una lista vacía para permitir el alta inicial; el cron no envía y reporta que falta configurar destinatarios hasta que se guarde una lista.
- El cron conserva sus cadencias, exportaciones e idempotencia. Solo crea envíos para la combinación de destinatario y reporte que siga habilitada al ejecutar la pasada.
- La migración `20261101_0081` agrega el marcador singleton de configuración, la lista actual de destinatarios y una bitácora append-only. La bitácora guarda huellas SHA-256 de las direcciones y los reportes habilitados, no los correos en texto claro; la tabla de configuración conserva las direcciones actuales que necesita el envío.

## Consecuencias y límites

- Se pueden desactivar todos los reportes sin borrar el historial de cambios ni modificar la configuración de SMTP o del cron.
- Cambiar la allowlist del entorno puede invalidar destinatarios ya guardados. La API los muestra como no permitidos para que una persona con permiso los retire o reemplace; el cron no los usa.
- La tabla de auditoría conserva snapshots de las huellas y el conteo de reportes; la UI de administración muestra actor, fecha y cambios agregados, sin revelar las direcciones del snapshot.
- SMTP conserva la entrega at-least-once descrita en ADR-082/083. La migración debe validarse en PostgreSQL antes de desplegar; SQLite de pruebas y vista previa no sustituye esa comprobación.
