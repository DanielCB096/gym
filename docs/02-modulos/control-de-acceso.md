# Módulo 2: Control de acceso

## 1. Resumen y alcance

Este módulo cubre el control de acceso al gimnasio, validación de membresía, horario, aforo, denegaciones, accesos manuales, gestión de credenciales y operación sin internet. Su objetivo es permitir entradas rápidas, seguras y trazables, incluso con cortes de energía o conectividad débil.

### Incluye
- lectura por QR, huella o tarjeta RFID
- validación de membresía vigente y sin adeudos
- control de horario por plan y política del gimnasio
- aforo en tiempo real y antipassback
- accesos manuales con bitácora
- modo offline con caché local y sincronización posterior

### No incluye
- seguridad física del perímetro completo del edificio
- control de vehículo o estacionamiento
- integración con alarma contra incendios o CCTV no relacionada con acceso

## 2. Actores y permisos

| Actor | Objetivo | Permisos principales |
|---|---|---|
| Socio | ingresar al gimnasio | presentar QR/huella/tarjeta; consultar su historial de acceso |
| Recepcionista | atender accesos y revisar denegaciones | activar acceso manual; revisar operaciones de la recepción |
| Gerente | supervisionar apertura y seguridad | configurar horarios, reglas, alertas y aforo |
| Dueño / administrador | ajustar políticas de seguridad | cambiar reglas globales de acceso y permisos de revisión |
| Personal de mantenimiento | revisar lectores y torniquetes | ver estado de hardware y logs técnicos |
| Sistema | validar acceso y sincronizar | ejecutar validación local, bitácora y cola de sincronización |

## 3. Flujos de usuario paso a paso

### Flujo implementado: código rotativo en el kiosco
1. El socio abre «Acceso habilitado» en la app y pulsa «Ver mi código».
2. La app pide `POST /member/access/code`; el backend exige socio activo y membresía vigente y devuelve un código de seis dígitos con cinco minutos de vida. Emitir otro invalida el anterior.
3. El socio dicta o muestra el código en recepción; la tablet del kiosco lo captura en el teclado numérico.
4. El kiosco envía `POST /kiosk/check-in` con `X-Kiosk-Token` y el código. El backend autentica el dispositivo, consume el código de forma atómica y evalúa la membresía con el motor de acceso.
5. La pantalla muestra «Acceso concedido» con el nombre abreviado o el motivo del rechazo («Código inválido o vencido.», «Membresía vencida. Pasa a recepción.» o «Demasiados intentos. Espera un momento.»).
6. La decisión queda en `access_events` con origen `reader` y lector «Kiosco <etiqueta>», y aparece en la bitácora del panel. Un código usado no se puede repetir.

### Flujo implementado: alta de un kiosco
1. El dueño entra al panel con `settings.manage` y abre «Kiosco».
2. Captura el nombre del dispositivo («Recepción») y lo crea.
3. El panel muestra el token **una sola vez**; se copia a la pantalla de configuración del kiosco junto con la URL del backend.
4. El kiosco prueba la conexión con `/health` y guarda `{apiUrl, token, label}` en el navegador.
5. Si la tablet se retira o se compromete, el panel revoca el dispositivo; el siguiente check-in responde `401`, el kiosco borra el token y vuelve a configuración.

### Flujo principal: acceso válido
1. El socio se acerca al lector.
2. El sistema intenta identificar la credencial: QR, huella o tarjeta RFID.
3. Se consulta la caché local primero; si no existe, se valida con backend.
4. El servicio confirma que la membresía está vigente, no congelada, no suspendida por adeudo, y que está dentro del horario permitido.
5. Si pasa validación, se abre el torniquete y se registra la entrada con fecha, hora, tipo de acceso e identidad.
6. La app y la recepción reciben el evento si se requiere mostrarlo.

### Flujo alterno: acceso denegado
1. El socio presenta una credencial válida pero no autorizada.
2. El sistema identifica el motivo: membresía vencida, adeudo, horario no permitido, aforo completo o antipassback.
3. Se muestra un aviso claro al usuario y la recepción.
4. El evento se registra en bitácora con motivo, lector, hora y responsable o sistema.

### Flujo de acceso manual
1. La recepcionista busca al socio en el panel.
2. Selecciona “Entrada manual autorizada”.
3. Ingresa un motivo (visita, cortesía, excepción, soporte de gerente, etc.).
4. El sistema valida que el usuario tenga permisos para autorizar la excepción.
5. El acceso se registra con timestamp y quién autorizó la acción.

### Flujo de modo offline
1. Si hay pérdida de internet, dispositivos locales siguen funcionando con caché.
2. Se valida la fecha de vigencia, la política global y el estado de la tarjeta/huella.
3. La entrada se guarda localmente en una cola de sincronización.
4. Cuando regresa la conectividad, el sistema envía los eventos y fija el estado de sincronización.

## 4. Pantallas / espacios

### 1. Kiosco de recepción y acceso
- Nombre: Entrada rápida de socio
- Objetivo: validar acceso en menos de 1 segundo
- Componentes (implementado el código rotativo, PWA en `kiosk/`):
  - teclado numérico de seis dígitos para el código que muestra la app del socio
  - pantalla de resultado con «Acceso concedido» o el motivo del rechazo y el nombre abreviado del socio
  - configuración del dispositivo (dirección del backend y token de kiosco) con prueba de conexión
  - indicador de conexión online/offline y reloj local
  - botón «Siguiente socio» y reinicio automático del teclado
- Componentes del diseño todavía pendientes:
  - barra de búsqueda por nombre, teléfono o ID
  - botón de escaneo QR
  - input para acceso manual
  - estado del aforo actual
- Estados: vacío, cargando, éxito, error, sin internet, acceso denegado

### 2. Panel web administrativo
- Nombre: Control de acceso y aforo
- Objetivo: monitorear entradas, salidas y alertas en tiempo real
- Componentes (implementado):
  - tablero con accesos del día y bitácora con filtros por estado y búsqueda
  - acceso manual con motivo
  - página «Kiosco» con los dispositivos autorizados, alta con token de una sola vista y revocación
- Componentes del diseño todavía pendientes:
  - filtros por horario, lector, plan o afiliación
  - tabla específica de accesos denegados
  - lista de lectores conectados y estado del hardware
  - apertura manual del torniquete para permisos autorizados
- Estados: normal, modo degradado, lector fuera de línea, aforo máximo

### 3. Móvil del socio
- Nombre: Mi código de acceso
- Objetivo: mostrar un código vigente para entrar al club y el estado de la membresía
- Componentes (implementado):
  - tarjeta «Acceso habilitado» que abre la pantalla del código y se deshabilita sin membresía
  - código de seis dígitos agrupado (`397 969`) con cuenta regresiva de cinco minutos
  - botón para generar otro código al vencer y mensaje de qué hacer en recepción
- Componentes del diseño todavía pendientes:
  - historial reciente de entradas y salidas
  - aviso de bloqueo por adeudo o congelamiento
  - botón de ayuda si el código no funciona

### 4. Bitácora de acceso
- Nombre: Historial de accesos
- Objetivo: auditoría forense y revisión de incidencias
- Componentes:
  - filtros por fecha, lector, tipo de acceso, usuario, motivo
  - exportación a CSV/PDF
  - tags de acceso exitoso / denegado / manual / offline

## 5. Reglas de negocio y casos límite

### Reglas clave
- Solo puede entrar quien tiene membresía vigente, no congelada, sin adeudo bloqueante y dentro del horario del plan.
- El sistema debe validar la política de visitas por plan y máximo de accesos permitidos.
- Si hay dos o más intentos de acceso con la misma credencial en un periodo corto, se debe detectar y registrar como posible antipassback o intento anómalo.
- Todo acceso manual requiere usuario, motivo y auditoría.
- Los datos biométricos nunca se guardan como imagen; solo la plantilla cifrada.
- Si un lector falla, el acceso aún puede funcionar en modo degradado con el sistema local.

### Casos límite
- Socio con tarjeta vencida o sin lectura reconocida.
- Huella no detectada en 3 intentos consecutivos.
- Torniquete bloqueado por hardware o energía.
- Aforo máximo alcanzado y un visitante intenta entrar.
- Miembro en periodo de gracia y aún tiene acceso restringido por política.
- Entrada manual autorizada por recepcionista fuera del horario permitido.

## 6. Entidades de datos

- Socio
- CredencialAcceso
- LectorAcceso
- Torniquete
- MembresiaSocio
- Plan
- ReglaHorario
- Aforo
- AccesoRegistro
- BitacoraAcceso
- ConfiguracionAcceso
- DenegacionAcceso
- SincronizacionOffline

### Campos clave
- CredencialAcceso: tipo (QR, RFID, huella), token, estado, versión, fecha de registro
- MembresiaSocio: estado, vigencia, periodo de gracia, horario permitido
- AccesoRegistro: socio_id, lector_id, tipo_acceso, timestamp, resultado, motivo, sincronizado
- BitacoraAcceso: accion, responsable, motivo, origen, fecha
- ConfiguracionAcceso: aforo max, regla antipassback, horarios activos, modo offline habilitado

## 7. Integraciones con otros módulos

- Membresías y pagos: el acceso depende del estado de la membresía y de los adeudos.
- Clases y reservas: si la clase requiere ingreso con etiqueta o horario, el acceso debe reflejar la validación de la clase.
- Mantenimiento de equipo: una máquina fuera de servicio no debe bloquear automáticamente la accesibilidad del gimnasio, pero sí debe reflejarse en la app y recepción.
- Comunicación: alertas por acceso denegado, ingreso manual y bloqueo por cuota.
- Facturación: los ingresos por tarifas por acceso o servicios adicionales se vinculan a la cuenta del socio.

## 8. Notificaciones y automatizaciones

- Alerta de acceso denegado para recepción y gerente.
- Aviso de aforo cercano al máximo.
- Notificación de lector fuera de servicio o sin sincronización.
- Confirmación de acceso manual con código, motivo y responsable.
- Registro diario de accesos y denegaciones para auditoría.

## 9. Consideraciones de rendimiento específicas del módulo

- caché local de membresías vigentes, horarios y acceso del día
- validación local ejecutada por un servicio en la controladora del lector
- sincronización asíncrona de accesos en cola con reintentos
- tablas de acceso con índice por `socio_id`, `estado`, `fecha_hora`, `lector_id`
- archivado por mes para accesos históricos y bitácoras
- lectura de aforo y validación en memoria para responder en <1 s
- procesos de reintento de sincronización al reconectar

## 10. KPIs

- tiempo medio de respuesta del lector
- porcentaje de accesos válidos vs denegados
- tasa de sincronización exitosa offline
- tiempo medio de resolución de un lector caído
- tasa de accesos manuales por día
- porcentaje de accesos con motivo de excepción

## 11. Preguntas abiertas

- ¿el gimnasio usará huella, QR o tarjetas como método principal? 
- ¿se desea permitir entradas por cortesía o con excepción según evento? 
- ¿se necesita bloquear la entrada por debilidad de red además del popular modo degradado?
- ¿el aforo se calcula por salón, por gimnasio completo o por área específica?

## 12. Criterios de aceptación

- Se valida el acceso con QR, tarjeta y huella según la configuración del gimnasio.
- La respuesta del lector es menor a 1 segundo en condiciones normales.
- El sistema sigue funcionando con internet caído usando caché local.
- Todo acceso manual queda registrado con usuario, motivo y timestamp.
- Las denegaciones muestran un motivo claro y se guardan en bitácora.
- Un socio con adeudo bloqueante no puede entrar sin excepción autorizada.
- El aforo real se refleja en el panel y la recepción.

## 13. Estado

Implementación inicial del motor offline y del kiosco de recepción con código rotativo

## 14. Historial de cambios

- 2026-10-15: documento ampliado con flujos, pantallas, reglas,.hardware, métricas y criterios de aceptación.
- 2026-10-28: se implementa el código rotativo en la app del socio, el endpoint del kiosco, la PWA de recepción y la administración de dispositivos en el panel (ADR-024).

## 15. Implementación actual y límites

- El kiosco de recepción es una PWA estática en `kiosk/` que captura el código de seis dígitos, lo valida con `POST /kiosk/check-in` mediante un token de dispositivo y muestra el resultado en pantalla.
- El código se emite desde la app (`POST /member/access/code`), dura cinco minutos, es de un solo uso, se guarda como HMAC-SHA256 y emitir otro invalida el anterior. Hay 6 emisiones por socio cada 10 minutos y 10 intentos por kiosco cada minuto; los intentos inválidos quedan en `kiosk_attempts` sin guardar el código.
- Los dispositivos se administran desde el panel con `settings.manage`: alta con token de una sola vista y revocación inmediata. El token se guarda como SHA-256 y la tableta lo conserva en `localStorage`.
- El kiosco reutiliza `evaluate_access` y escribe la decisión en `access_events` con origen `reader`; la bitácora del panel ya muestra lector «Kiosco <etiqueta>».
- El snapshot del kiosco solo aporta estado y fechas de la membresía: no consulta adeudo, horario, límite diario ni antipassback, y envía ocupación 0. Un socio moroso o fuera de horario entra si su membresía está vigente.
- No hay hardware conectado: el kiosco no abre torniquete ni registra salidas. Tampoco hay validación offline (el service worker solo cachea el shell) ni rotación o caducidad del token del dispositivo.
- El motor valida estado/vigencia de membresía, adeudo bloqueante, horario local, límite diario, antipassback y aforo.
- El snapshot y el outbox son persistentes en SQLite local; cada decisión usa `event_id` idempotente y queda pendiente hasta recibir confirmación de sincronización.
- Una salida se permite aunque no exista snapshot de membresía, para no impedir el egreso por una membresía vencida o una caché faltante.
- La vista previa obtiene estado de membresía desde SQLite; el indicador de adeudo y los horarios se proporcionan manualmente para simular reglas.
- Aún no existe integración con credenciales/biometría, controlador, torniquete, cálculo compartido de aforo ni sincronización con un backend en red.
- La vigencia máxima del snapshot, antipassback, política de visitas y aforo por área requieren configuración y validación con el gimnasio.
