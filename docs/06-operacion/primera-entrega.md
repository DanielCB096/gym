# Alcance y preparación de la primera entrega

## Alcance aprobado

La primera entrega es para un solo gimnasio. Incluye la operación no fiscal del
sistema y queda sujeta a las barreras de staging, seguridad, respaldo y
aceptación descritas abajo.

La fase de definición de alcance está cerrada. Se eligió VPS y el dueño asumirá
las responsabilidades de negocio, operación técnica y autorización de
recuperaciones. Aún falta seleccionar proveedor, región/plan, presupuesto y
dominio antes de provisionar staging.

### Incluido

- Cobro inicial y renovación automática de membresías. La renovación automática
  está aprobada como alcance, pero aún no está implementada ni autorizada para
  cobrar en producción.
- Acceso del socio con el código numérico de seis dígitos que captura recepción
  en el kiosco. No incluye lector QR, torniquete, RFID ni biometría en esta
  entrega.
- Registro de cobros externos/manuales en caja; no se integra una terminal
  bancaria física.
- Apertura a todos los socios desde el inicio de producción, después de superar
  los criterios de aceptación. No habrá un piloto productivo limitado a un
  grupo de socios; sí se requiere aceptación interna con datos sintéticos en
  staging.
- Operación de los módulos no fiscales acordados, como socios, membresías,
  acceso, caja, inventario, clases, rutinas, mantenimiento y fisioterapia.

### Excluido

- CFDI, timbrado, PAC/Finkok, facturas, complementos de pago y automatización
  fiscal. La primera entrega tampoco ofrecerá solicitudes, consulta ni descarga
  de facturas fiscales en los canales de usuario. Los reportes fiscales quedan
  fuera; los reportes operativos y financieros no fiscales permanecen dentro
  del alcance.
- Integración con terminal física, torniquete, lector QR/RFID o biométrico.
- Multi-sucursal.

## Decisiones de operación

| Tema | Decisión | Estado |
| --- | --- | --- |
| Hosting | VPS. | Tipo elegido; faltan proveedor, región/plan, presupuesto y dominio para provisionar staging. |
| Responsables | El dueño asume aprobación de negocio, operación técnica y autorización de recuperaciones. | Asignados; el procedimiento permite que una persona cubra varios roles. |
| Cobro de membresía | Incluir renovación automática además del pago inicial. | Alcance aprobado; diseño, implementación y validación pendientes. |
| Método de acceso | Código numérico de seis dígitos capturado en el kiosco existente. | Aprobado; sin lector QR ni torniquete. |
| Terminal bancaria | No integrar hardware; los cobros externos se registran manualmente. | Aprobado para esta entrega. |
| RPO | Pérdida máxima objetivo de 15 minutos. | Aprobado; requiere una estrategia que lo demuestre. |
| RTO | Recuperar el servicio en un máximo objetivo de 4 horas. | Aprobado; requiere una restauración ensayada. |
| Lanzamiento | Abrir a todos los socios después de las validaciones, sin piloto productivo limitado. | Aprobado; eleva el impacto de una falla y exige completar todas las barreras previas. |
| Fiscal | Excluir facturación y procesos fiscales de la primera entrega. | Aprobado. |

Estos acuerdos fijan alcance, no prueban que las capacidades estén listas. En
particular, el RPO de 15 minutos no se satisface con un respaldo diario: la
infraestructura elegida deberá ofrecer recuperación a un punto en el tiempo o
una estrategia equivalente y probar su restauración.

## Plan de ejecución

1. **Cerrar detalles de infraestructura:** seleccionar proveedor VPS,
   región/plan, presupuesto y dominio; definir cómo se administrarán DNS y
   secretos.
2. **Preparar staging:** reproducir backend, PostgreSQL, Redis, panel y procesos
   programados con HTTPS, secretos aislados, despliegue repetible y datos
   sintéticos.
3. **Cerrar seguridad y privacidad:** implementar MFA administrativo, revisar
   permisos, sesiones, secretos y exposición de servicios; definir retenciones y
   validar aviso de privacidad y atención ARCO con asesoría correspondiente.
4. **Configurar recuperación:** establecer copias cifradas fuera del servidor,
   cubrir la base y los archivos críticos, alertar fallos y demostrar RPO/RTO
   mediante una restauración aislada.
5. **Completar cobros recurrentes y operación de acceso:** diseñar consentimiento
   explícito y revocable para futuros cargos, baja de la renovación, manejo de
   rechazos, reintentos, periodo de gracia y conciliación. Validar webhooks,
   duplicados, discrepancias y recuperación de eventos en sandbox; no usar
   credenciales productivas antes de la aprobación correspondiente.
6. **Preparar operación:** configurar cron, monitoreo, alertas, bitácoras y
   manuales; comprobar caja, acceso, membresías, permisos, correo y tareas
   programadas en staging.
7. **Aceptar y liberar:** completar pruebas internas con datos sintéticos,
   ensayar reversa y recuperación, corregir bloqueadores y obtener aprobación
   explícita. Solo entonces abrir producción a todos los socios.

## Pendientes que bloquean la salida

- Seleccionar proveedor VPS, región/plan, presupuesto y dominio; configurar la
  administración de DNS y secretos.
- Diseñar, implementar y probar renovaciones automáticas con consentimiento
  explícito, cancelación clara y manejo de cobros fallidos. La integración
  existente de Conekta solo cubre un pago inicial en sandbox.
- Implementar MFA administrativo y cerrar la revisión de seguridad y privacidad.
- Configurar respaldos y demostrar recuperación dentro de los objetivos
  aprobados, incluyendo fotos de progreso si se conservan en archivos aparte.
- Validar en staging las migraciones, tareas programadas, correo, cobros y
  operación diaria del alcance no fiscal.
- Confirmar condiciones comerciales de proveedores y autorización de salida.

No se deben realizar cobros productivos ni cargar datos reales hasta cerrar esos
pendientes y aprobar la salida.
