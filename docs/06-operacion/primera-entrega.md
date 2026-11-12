# Alcance y preparación de la primera entrega

## Alcance aprobado

La primera entrega es para un solo gimnasio. Incluye la operación no fiscal del
sistema y queda sujeta a las barreras de staging, seguridad, respaldo y
aceptación descritas abajo.

La fase de definición de alcance está cerrada. El dueño asumirá las
responsabilidades de negocio, operación técnica y autorización de
recuperaciones. El staging se prepara en una PC con Windows 11 y Docker
Desktop, accesible solo desde esa PC. La topología de producción queda
pendiente de una evaluación posterior.

### Incluido

- Registro manual de cobros de membresía y caja en recepción. No se ofrecerán
  checkout, captura de tarjeta, cobro en línea ni renovación automática en esta
  entrega.
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
- Correos operativos existentes y envío del estado de cuenta del socio a su
  correo registrado o a un destinatario alterno autorizado. Requiere configurar
  SMTP real; el buzón Mailpit solo sirve para pruebas locales.

### Excluido

- CFDI, timbrado, PAC/Finkok, facturas, complementos de pago y automatización
  fiscal. La primera entrega tampoco ofrecerá solicitudes, consulta ni descarga
  de facturas fiscales en los canales de usuario. Los reportes fiscales quedan
  fuera; los reportes operativos y financieros no fiscales permanecen dentro
  del alcance.
- Cobros en línea, captura o almacenamiento de métodos de pago y renovaciones
  automáticas.
- Integración con terminal física, torniquete, lector QR/RFID o biométrico.
- Multi-sucursal.

## Decisiones de operación

| Tema | Decisión | Estado |
| --- | --- | --- |
| Staging | PC local Windows 11, Docker Desktop Linux, acceso solo por `localhost`. | Acordado; usar datos sintéticos, PostgreSQL y servicios simulados. |
| Producción | Local o VPS, por definir. | No iniciar despliegue ni cargar datos reales hasta evaluar disponibilidad, seguridad y recuperación. |
| Responsables | El dueño asume aprobación de negocio, operación técnica y autorización de recuperaciones. | Asignados; el procedimiento permite que una persona cubra varios roles. |
| Cobro de membresía | Solo registro manual/presencial; sin checkout ni renovación automática. | Alcance actualizado para la primera entrega; probar registro manual en staging. |
| Método de acceso | Código numérico de seis dígitos capturado en el kiosco existente. | Aprobado; sin lector QR ni torniquete. |
| Terminal bancaria | No integrar hardware; los cobros externos se registran manualmente. | Aprobado para esta entrega. |
| RPO | Pérdida máxima objetivo de 15 minutos. | Aprobado; requiere una estrategia que lo demuestre. |
| RTO | Recuperar el servicio en un máximo objetivo de 4 horas. | Aprobado; requiere una restauración ensayada. |
| Lanzamiento | Abrir a todos los socios después de las validaciones, sin piloto productivo limitado. | Aprobado; eleva el impacto de una falla y exige completar todas las barreras previas. |
| Fiscal | Excluir facturación y procesos fiscales de la primera entrega. | Aprobado. |

El envío de mensajes libres redactados desde el panel no existe hoy. La primera
entrega conserva los correos de flujos definidos (por ejemplo, OTP, avisos y
estado de cuenta); cualquier redactor general requiere acordar contenido,
permisos y registro antes de implementarlo.

Estos acuerdos fijan alcance, no prueban que las capacidades estén listas. En
particular, el RPO de 15 minutos no se satisface con un respaldo diario: la
infraestructura elegida deberá ofrecer recuperación a un punto en el tiempo o
una estrategia equivalente y probar su restauración.

## Staging local

El Compose de staging levanta PostgreSQL 16, Redis, backend, panel y kiosco;
por defecto Mailpit captura el correo local. El Compose admite configurar un
servidor SMTP externo mediante `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
`SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS` y `SMTP_USE_SSL` en
`.env.staging.local`. Hasta que el responsable proporcione y configure las
credenciales del proveedor, el correo no sale a destinatarios externos. La app
del socio se agrega opcionalmente con `-WithMobile`. Todos los puertos del host
se enlazan a `127.0.0.1`, por lo que no se pueden usar desde el teléfono ni
desde otra computadora. No se debe publicar este entorno en Internet ni
reutilizar sus datos o secretos en producción.

Desde PowerShell, en la raíz del repositorio:

```powershell
powershell -ExecutionPolicy Bypass -File demo\start-local-staging.ps1
powershell -ExecutionPolicy Bypass -File demo\start-local-staging.ps1 -WithMobile
```

La primera ejecución crea `.env.staging.local` con secretos aleatorios, archivo
ignorado por Git. El arranque exige Docker Desktop con contenedores Linux y
memoria libre suficiente. La base está vacía: el dueño se crea una sola vez de
forma interactiva, sin poner la contraseña en el historial:

```powershell
docker compose --env-file .env.staging.local -f compose.staging.local.yml exec -it api python -m app.modules.identity.bootstrap_owner
```

Panel: `http://localhost:3001`; kiosco: `http://localhost:8090`; API:
`http://localhost:8010/docs`; captura de correo de prueba:
`http://localhost:8025`; app opcional: `http://localhost:8081`. Los OTP se
capturan en Mailpit si se usa la configuración predeterminada. Las funciones de
envío usan el transporte SMTP configurado; no se habilitan cobros en línea ni
facturación en esta entrega y el PAC queda simulado.

Para apagar los servicios sin borrar la base ni las fotos de staging:

```powershell
docker compose --env-file .env.staging.local -f compose.staging.local.yml down
```

La PC puede apagarse cuando el gimnasio esté cerrado; mientras esté apagada no
responderán las aplicaciones ni se ejecutarán tareas programadas. Este acuerdo
solo describe el staging local, no la disponibilidad de producción.

## Plan de ejecución

1. **Preparar staging local:** levantar backend, PostgreSQL, Redis, panel y
   kiosco con base vacía, cobros en línea y facturación deshabilitados y puertos
   publicados solo en `localhost`. Probar correos con Mailpit; antes de aceptar
   el envío externo, configurar SMTP real y verificar con destinatarios de
   prueba autorizados.
2. **Evaluar la topología de producción:** decidir local o VPS, dominio y acceso
   remoto seguro; no publicar el staging local en Internet.
3. **Cerrar seguridad y privacidad:** cerrar MFA administrativo (rotación y
   deshabilitación desde la UI, pruebas dedicadas en PostgreSQL y revisión
   profesional) y revisar permisos, sesiones, secretos y exposición de
   servicios; definir retenciones y validar aviso de privacidad y atención ARCO
   con asesoría correspondiente.
4. **Configurar recuperación:** establecer copias cifradas fuera del servidor,
   cubrir la base y los archivos críticos, alertar fallos y demostrar RPO/RTO
   mediante una restauración aislada.
5. **Completar operación de acceso y caja:** validar el registro manual de
   pagos presenciales, sus permisos, idempotencia, bitácora y conciliación
   operativa. Mantener deshabilitados los endpoints de checkout y renovación
   automática en esta entrega.
6. **Preparar operación:** configurar cron, monitoreo, alertas, bitácoras y
   manuales; comprobar caja, acceso, membresías, permisos, correo y tareas
   programadas en staging.
7. **Aceptar y liberar:** completar pruebas internas con datos sintéticos,
   ensayar reversa y recuperación, corregir bloqueadores y obtener aprobación
   explícita. Solo entonces abrir producción a todos los socios.

## Pendientes que bloquean la salida

- Completar y validar el staging local. La configuración actual exige al menos
  4 GB de RAM libre para construirlo; la app móvil opcional requiere 5 GB.
- Configurar SMTP real con credenciales autorizadas y probar la entrega externa
  con destinatarios de prueba antes de habilitar correos a socios.
- Elegir más adelante topología y dominio de producción, considerando acceso
  remoto seguro, disponibilidad, respaldos externos y recuperación.
- Validar MFA administrativo en PostgreSQL, definir la recuperación cuando se
  pierden el autenticador y los códigos de respaldo, y cerrar la revisión de
  seguridad y privacidad. La rotación y la deshabilitación desde el panel ya
  existen (ADR-090).
- Configurar respaldos productivos y demostrar recuperación dentro de los
  objetivos aprobados, incluyendo fotos de progreso si se conservan en
  archivos aparte. El ensayo local de staging y sus scripts ya están disponibles,
  pero no sustituyen cifrado, PITR, ubicación externa ni restauración real.
- Validar en staging las migraciones, tareas programadas, correo, registro
  manual de cobros y
  operación diaria del alcance no fiscal.
- Confirmar condiciones comerciales de proveedores y autorización de salida.

No se deben realizar cobros en línea ni cargar datos reales hasta cerrar esos
pendientes y aprobar la salida. Los cobros presenciales se registran como
operaciones manuales del gimnasio, no como cargos procesados por el sistema.
