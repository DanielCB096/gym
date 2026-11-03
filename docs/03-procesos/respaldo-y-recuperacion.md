# Respaldo y recuperación

## Objetivo

Definir cómo preparar y verificar respaldos y cómo coordinar una recuperación ante pérdida de datos o indisponibilidad, protegiendo la información del gimnasio y evitando restauraciones que sobrescriban datos sin autorización.

## Alcance y límites

Este procedimiento cubre la base de datos PostgreSQL, los archivos necesarios para operar y las verificaciones posteriores a una recuperación. La infraestructura y el proveedor definitivos aún deben validarse.

Las tareas de purga y sincronización descritas en [despliegue.md](../06-operacion/despliegue.md) **no son respaldos**. El cron del repositorio ejecuta la purga de datos de kiosco, la purga de acuses de correo y la consulta de acuses de push; no crea ni verifica copias de recuperación.

## Responsables

- **Operador técnico**: configura y ejecuta respaldos, protege las copias, documenta resultados y coordina restauraciones.
- **Gerencia o dirección**: declara la prioridad operativa, autoriza la recuperación y decide cuándo reabrir el sistema.
- **Responsable del módulo**: valida los datos funcionales restaurados en caja, acceso, membresías y demás flujos críticos.

Una sola persona puede asumir más de un rol si el club es pequeño, pero las restauraciones de producción deben tener autorización explícita y dejar evidencia del operador y la hora.

## Preparación de respaldos

1. Aplicar los objetivos aprobados para la primera entrega: RPO máximo de 15 minutos y RTO máximo de 4 horas (ADR-086). Confirmar con negocio si cambian antes de contratar o configurar infraestructura.
2. Elegir un método de respaldo compatible con la infraestructura de PostgreSQL y documentar su responsable, frecuencia, retención, cifrado y ubicación.
3. Para ensayar staging en Windows, ejecutar `powershell -ExecutionPolicy Bypass -File demo\verify-local-recovery.ps1`. El script crea un respaldo de PostgreSQL y fotos, lo verifica y lo restaura en contenedores temporales. Solo usa `pg_dump` de la base sintética y archivos sintéticos.
4. Para guardar una copia sin restaurarla, ejecutar `powershell -ExecutionPolicy Bypass -File demo\backup-local-staging.ps1`.
5. Para restaurar una copia aislada, ejecutar `powershell -ExecutionPolicy Bypass -File demo\restore-local-staging.ps1 -BackupDir "C:\ruta\al\respaldo"`.
6. Incluir la base de datos y los archivos críticos que no se puedan reconstruir desde ella. En particular, confirmar si `PROGRESS_PHOTOS_DIR` contiene fotos de socios y proteger esa carpeta junto con su metadato en base de datos.
7. Guardar copias cifradas fuera del servidor principal, con acceso limitado a personal autorizado y protección frente a borrado o modificación no autorizados.
8. Mantener secretos y credenciales bajo un mecanismo seguro de gestión de secretos. No incluirlos en el repositorio, tickets, logs ni copias de acceso general.
9. Documentar la última ejecución, su resultado, tamaño, ubicación, periodo cubierto y la alerta responsable ante una falla.
10. Probar periódicamente que las copias se puedan leer y restaurar en un entorno aislado.

Redis y las cachés deben tratarse según su función: si son reconstruibles desde datos persistentes, no sustituyen el respaldo de PostgreSQL ni de archivos. La estrategia concreta debe validarse con la infraestructura desplegada.

## Detección y decisión de recuperación

1. Registrar el incidente, la hora de detección, síntomas, sistemas afectados y cambios recientes.
2. Detener o limitar las operaciones que puedan agravar la pérdida, sin borrar datos ni reiniciar servicios de forma indiscriminada.
3. Notificar a gerencia y al responsable técnico. Si hay indicios de acceso no autorizado, tratarlo también como incidente de seguridad y preservar evidencia.
4. Determinar si el problema es una caída recuperable del servicio, corrupción, borrado accidental o posible compromiso de credenciales.
5. Identificar la copia disponible más reciente y su intervalo de datos, y estimar la pérdida potencial frente al RPO acordado.
6. Gerencia o dirección autoriza la restauración y el entorno de destino. Si la integridad o la causa no está clara, mantener el sistema restringido y escalar antes de reabrirlo.

## Recuperación

1. Confirmar que se cuenta con la autorización, la copia correcta, las claves de descifrado y la infraestructura de destino.
2. Preferir un entorno aislado para validar la copia antes de tocar producción.
3. Restaurar la base de datos y los archivos que correspondan como un conjunto coherente, según el método aprobado por infraestructura.
4. No sobrescribir una base o carpeta de producción sin validar el destino y conservar una copia del estado previo cuando sea técnicamente posible.
5. Si el incidente pudo exponer credenciales o secretos, rotarlos antes de reabrir los servicios afectados.
6. Ejecutar las comprobaciones técnicas definidas para la plataforma: estado de la base, versión del esquema, conectividad de la aplicación y lectura de archivos críticos.
7. No aplicar migraciones ni ejecutar tareas de mantenimiento sobre una restauración sin confirmar compatibilidad y autorización técnica.

## Validación antes de reabrir

El responsable técnico y gerencia deben verificar, como mínimo:

- que el backend y el panel se conectan a la base restaurada;
- que las cuentas, permisos y sesiones siguen un estado seguro;
- que los socios, membresías, pagos, ventas y saldos consultados sean coherentes con el periodo recuperado;
- que se conserven las bitácoras relevantes de accesos, cambios y facturación;
- que las fotos y demás archivos críticos correspondan con sus registros;
- que los componentes reconstruibles, como Redis o cachés, puedan volver a operar;
- que los procesos programados estén activos solo cuando la base ya está validada.

Las transacciones que hayan ocurrido después del punto restaurado deben identificarse y conciliarse mediante los procesos de negocio; no se deben recrear cargos, pagos, accesos o facturas a ciegas.

Gerencia autoriza la reapertura cuando se hayan registrado los resultados, las limitaciones y cualquier dato pendiente de reconciliación. Si una verificación falla, mantener las funciones afectadas restringidas y continuar la investigación.

## Cierre del incidente

Registrar:

- fecha y duración del incidente;
- causa conocida o estado de investigación;
- respaldo utilizado y punto temporal recuperado;
- servicios y archivos restaurados;
- pérdida potencial y datos reconciliados;
- personas que autorizaron, ejecutaron y validaron;
- cambios de seguridad o infraestructura realizados;
- acciones preventivas, responsables y fecha de seguimiento.

## Estado actual y pendientes

- El proyecto documenta tareas cron para purgas operativas y consulta de acuses, pero estas no hacen respaldo.
- El documento operativo [respaldos-y-recuperacion.md](../06-operacion/respaldos-y-recuperacion.md) recomienda copias periódicas y pruebas de restauración, pero la herramienta y configuración final dependen de la infraestructura.
- `demo/backup-local-staging.ps1` crea copias consistentes de PostgreSQL y del volumen de fotos, valida SHA-256 y aplica una retención configurable. Es exclusivo de staging con datos sintéticos.
- `demo/restore-local-staging.ps1` valida el manifiesto y restaura en contenedores aislados por defecto; `-Apply` sustituye la base y fotos sintéticas actuales de staging.
- `demo/verify-local-recovery.ps1` realiza el respaldo, restaura en aislamiento y mide el tiempo RTO. No demuestra cumplimiento productivo.
- Estos scripts no implementan cifrado externo, replicación continua ni recuperación a un punto en el tiempo, por lo que no cumplen por sí solos el RPO de 15 minutos.
- Antes de producción deben definirse infraestructura, cifrado, ubicación externa, retención, PITR o equivalente, permisos, alertas y ensayos periódicos.
