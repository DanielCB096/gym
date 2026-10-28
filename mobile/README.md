# App móvil del socio

Aplicación Expo/React Native para el socio del club. En este incremento cubre el **acceso con código de un solo uso (OTP) por correo**, el **código rotativo de entrada al club**, la **consulta del perfil y la membresía**, la **reserva de clases**, la **consulta de rutinas y progreso con registro de entrenamientos (incluido el detalle por serie) y medidas**, la **carga y consulta de fotos de progreso con consentimiento**, los **pagos y el estado de cuenta** (solo lectura), las **facturas del socio** con descarga de PDF y XML y **solicitud de factura** de sus propias compras y cobros, y la **bandeja de avisos del gimnasio**; no incluye todavía pago en línea.

## Alcance implementado

- Inicio de sesión sin contraseña: el socio escribe su correo y recibe un código de 6 dígitos con vigencia de 10 minutos.
- Sesión de 30 días guardada en `expo-secure-store` (en web no se persiste).
- Pantalla de inicio con:
  - saludo y datos de contacto del socio;
  - estado de acceso (`Acceso habilitado` o el motivo por el que no lo está) como botón que abre el código de entrada; sin acceso la tarjeta se deshabilita;
  - plan, estado de la membresía, periodo y días restantes;
  - saldo de la cuenta del socio;
  - fecha de alta y estado del socio;
  - tarjeta «Avisos del gimnasio» con la insignia de avisos sin leer (tope visible `99+`);
  - tarjeta «Facturas» para consultar y descargar los comprobantes fiscales;
  - actualización manual y cierre de sesión.
- Pantalla del código de entrada (se abre desde la tarjeta «Acceso habilitado») con:
  - código de seis dígitos agrupado (`397 969`) para dictarlo o mostrarlo en recepción;
  - cuenta regresiva de cinco minutos y texto de qué hacer al llegar al club;
  - botón «Generar nuevo código» al vencer, con reemplazo del anterior;
  - validación de sesión expirada, mensajes de error y estados de carga;
  - el código no se guarda en el dispositivo ni en el historial.
- Pantalla de clases con:
  - cartelera de los próximos 14 días (fecha, tipo, salón, instructor y lugares disponibles);
  - reserva de un lugar o ingreso a la lista de espera cuando la clase está llena;
  - cancelación de la propia reserva, con aviso de la ventana sin penalización;
  - bloqueo explicado para clases premium, membresía inactiva, clases llenas sin lista de espera y clases ya iniciadas;
  - actualización manual con deslizamiento.
- Pantalla de rutinas y progreso con:
  - resumen de entrenamientos totales, de los últimos 30 días y del último peso registrado;
  - metas del socio con avance, valor actual, fecha objetivo y autoría («Creada desde tu app» o «Creada por el personal»);
  - formulario de **alta de metas** (medida y dirección como opciones, objetivo, fecha objetivo opcional y nota) y **cancelación en dos pasos** de las metas que creó desde la app;
  - últimas medidas corporales;
  - rutinas asignadas (estado, entrenador, versión, frecuencia y entrenamientos registrados);
  - detalle de cada rutina con el plan de la versión asignada (series, repeticiones, descanso y carga) y el historial de entrenamientos;
  - formulario para registrar un entrenamiento (fecha, duración, esfuerzo y notas) con un editor de **series opcional** por ejercicio del plan: repeticiones y peso por serie, con precarga de las repeticiones del plan y validación local de 1–100 repeticiones, 0–1000 kg, 60 series por entrenamiento y 20 por ejercicio;
  - historial de entrenamientos agrupado por ejercicio («8 × 24 kg · 8 × 26 kg») con su origen y estado;
  - «Cancelar meta» (en dos pasos) solo aparece en las metas activas creadas desde la app; las del entrenador se leen con la etiqueta «Creada por el personal» y se cancelan en recepción;
  - actualización manual con deslizamiento.
- Pantalla de fotos de progreso (se abre desde la tarjeta «Fotos de progreso» de Rutinas) con:
  - tarjeta de consentimiento con su casilla mientras el socio no haya autorizado el uso de sus fotos; después muestra «Consentimiento registrado.»;
  - botones «Tomar foto» y «Elegir de la galería» (`expo-image-picker`), selección de ángulo (frente, perfil, espalda u otra), fecha de la captura y nota opcional de hasta 300 caracteres;
  - validación del tamaño en el cliente (8 MB) y subida multipart con el enlace firmado de la foto recién creada;
  - galería de las fotos propias, de la más reciente a la más antigua, con la etiqueta «Recepción» en las que subió el personal;
  - visor ampliado con ángulo, fecha, tamaño, origen («Subida desde tu app»/«Subida en recepción») y nota, y eliminación en dos pasos con la aclaración de que solo el socio y el personal de Rutinas pueden verla;
  - estados vacío, de error y de sesión expirada, y actualización manual con deslizamiento (regenera los enlaces firmados).
- Pantalla de pagos y estado de cuenta con:
  - saldo de la cuenta, con aviso para saldo a favor o deuda, conteo de cargos y abonos, importe pagado en membresías y fecha de corte;
  - pagos de membresía con importe, plan, periodo, método y nota;
  - movimientos de cuenta en orden descendente, con importe con signo, saldo después del movimiento, referencia y método;
  - aviso cuando el historial supera los 100 movimientos que devuelve el backend;
  - estados vacíos, mensajes de error y actualización manual con deslizamiento.
- Pantalla de facturas con:
  - lista de los comprobantes emitidos a nombre del socio, del más reciente al más antiguo, con folio, estado, total, origen, fecha, IVA, método y forma de pago y folio fiscal;
  - botones «Descargar PDF» y «Descargar XML» que abren el documento en el navegador del sistema mediante un enlace firmado de 10 minutos, sin guardar archivos en el dispositivo;
  - aviso para facturas solicitadas o con error de timbrado («El comprobante estará disponible cuando el timbrado se complete») y para comprobantes simulados sin validez fiscal;
  - fecha de cancelación cuando aplica, estados vacíos, mensajes de error y actualización manual con deslizamiento para regenerar los enlaces.
- Pantalla de avisos con:
  - contador «Tienes N avisos sin leer.» o «Estás al día.»;
  - lista del más reciente al más antiguo con etiqueta de tipo (Membresía, Clase, Meta cumplida, Meta ajustada, Meta cancelada, Entrenamiento, Equipo), título, cuerpo y fecha con hora;
  - no leídos marcados con borde y punto de color, leídos atenúados;
  - toque sobre un aviso para marcarlo como leído (inmediato, sin recargar la lista);
  - «Marcar todas como leídas», visible solo cuando hay pendientes, con confirmación de cuántos se marcaron;
  - aviso cuando los pendientes superan los 30 de la primera página;
  - estados vacíos, mensajes de error y actualización manual con deslizamiento.
- Mensajes de error en español y comportamiento genérico para correos no registrados (no revela si el correo existe).

## Requisitos

- Node.js 24 y npm.
- Backend en ejecución (por defecto `http://127.0.0.1:8000`).
- Para el OTP real, `SMTP_*` configurado en el backend. Sin SMTP, `PREVIEW_MODE=true` muestra el código en la pantalla y registra el envío como `simulated`.

## Configuración

```bash
cd mobile
npm install
```

Variable pública (se incrusta en el bundle, no pongas secretos aquí):

```bash
EXPO_PUBLIC_API_URL=http://127.0.0.1:8000
```

Si se omite, la app usa `http://127.0.0.1:8000`. En un dispositivo físico o emulador, apunta a la IP de la máquina que corre el backend (por ejemplo `http://192.168.1.20:8000`) y agrega ese origen a `CORS_ORIGINS` solo si usas la vista web.

## Ejecución

```bash
npm start          # Expo Dev Tools (QR para Expo Go / emulador)
npm run web        # vista previa en navegador (http://localhost:8081)
npm run typecheck  # tsc --noEmit
```

Para la vista web, inicia el backend con ese origen permitido:

```bash
CORS_ORIGINS=http://localhost:8081,http://127.0.0.1:8081
```

`CORS_ORIGINS` solo aplica a Expo web; la app nativa no usa CORS. La app envía el token como `Authorization: Bearer`, por lo que el backend mantiene `allow_credentials=False`.

## Flujo de acceso

1. `POST /member/auth/request-code` con `{ "email": "..." }` responde `202` siempre (correo desconocido o inactivo incluido) y, solo en vista previa, devuelve `preview_code`.
2. El socio captura el código y `POST /member/auth/verify` devuelve el token y el resumen de la sesión.
3. `GET /member/me` con `Authorization: Bearer <token>` devuelve perfil, membresía, acceso y saldo.
4. `POST /member/auth/logout` revoca la sesión.

## Flujo de entrada con código

1. La tarjeta «Acceso habilitado» del inicio abre `AccessCodeScreen` y la pantalla pide `POST /member/access/code` con el Bearer del socio.
2. El backend exige membresía vigente y devuelve un código de seis dígitos con cinco minutos de vida; emitir otro invalida el anterior. La app solo lo mantiene en memoria y muestra la cuenta regresiva.
3. El socio dicta o muestra el código en recepción y la tablet lo valida con `POST /kiosk/check-in`; la app no sabe si se usó, así que el contador sigue hasta el vencimiento.
4. Al vencer, «Generar nuevo código» pide otro; un `401` cierra la sesión y vuelve al inicio de sesión.

## Flujo de clases

1. `GET /member/classes?days=14` devuelve la cartelera con `can_reserve`, `blocked_reason` y la reserva activa del socio.
2. `POST /member/classes/sessions/{session_id}/reservations` reserva un lugar o entra a la lista de espera; responde `409` con el motivo cuando el socio no puede reservar.
3. `POST /member/classes/reservations/{reservation_id}/cancel` cancela una reserva propia antes del inicio de la clase.
4. La app refresca la cartelera después de cada acción para mostrar el estado y los lugares actualizados.

Las reservas usan el origen `app`; el backend reutiliza las reglas del módulo de clases (aforo, bloqueo de fila, lista de espera y ventana de cancelación). Las clases premium se muestran pero no se pueden reservar desde la app hasta que exista el cobro del precio extra.

## Flujo de rutinas y progreso

1. `GET /member/routines` devuelve las asignaciones del socio, con las activas primero, y el resumen por estado.
2. `GET /member/routines/{assignment_id}` devuelve el plan de la **versión fijada al asignar**, el objetivo, las notas y los últimos 10 entrenamientos. Una asignación de otro socio responde `404`.
3. `GET /member/progress` devuelve entrenamientos totales y de los últimos 30 días, última medición, histórico de medidas y metas con su avance y su origen.
4. La app agrupa ambos resultados en una pantalla de resumen y abre el detalle de cada rutina.
5. `POST /member/routines/{assignment_id}/workouts` registra un entrenamiento (fecha, duración, esfuerzo y notas) en una asignación **activa**; queda como «Por revisar» hasta que el entrenador lo valida. Acepta `sets` con las series ejecutadas (`exercise_id`, `set_number`, `reps`, `weight_kg` opcional), validadas contra el plan de la versión asignada.
6. `POST /member/progress/measurements` registra peso, cintura, pecho y grasa (al menos uno) con notas; es append-only y actualiza las metas al momento.
7. `POST /member/progress/goals` crea una meta propia (`weight_kg`/`waist_cm`/`chest_cm`/`body_fat_percent`, dirección `decrease`/`increase`, objetivo, fecha opcional y nota) con `origin="app"` y la línea base de la última medición; `POST /member/progress/goals/{goal_id}/cancel` cierra una meta propia como `cancelled`.

El socio **no** edita ni borra entrenamientos ni medidas, y no edita metas: eso sigue siendo exclusivo del panel del personal (`routines.manage`). Las metas que creó el personal tampoco las cancela desde la app (`409`); se gestionan en recepción. Las fotos de progreso sí las captura y las elimina él mismo, con consentimiento (sección «Flujo de fotos de progreso»). Editar la plantilla de una rutina no cambia el plan que el socio ya tiene asignado.

En los formularios se valida en el cliente el formato de fecha, que no sea futura, la duración (0–600 min), el esfuerzo (1–10), los decimales con coma y al menos una medida. El campo de notas limita a 2000 caracteres en el entrenamiento y 300 en la medida y en la meta; el objetivo de la meta se acota a 100 como máximo para la grasa corporal y 1000 para las demás medidas, y la fecha objetivo no puede ser anterior a hoy. El detalle rotula cada registro como «Desde tu app» o «Desde recepción», con el estado «Por revisar» o «Revisado», y cada meta como «Creada desde tu app» o «Creada por el personal».

## Flujo de fotos de progreso

1. `GET /member/progress/photos` devuelve las fotos propias (máximo 100, más recientes primero) con su `origin` y un `file_path` firmado, más `consent_recorded`.
2. Si `consent_recorded` es `false`, la app muestra la tarjeta de consentimiento y exige marcarla antes de subir. El primer envío incluye `consent=true` y el backend guarda una sola fila en `member_consents` con el tipo `progress_photos` y la versión `fotos-progreso-v1`; si la imagen se rechaza, el consentimiento no queda registrado.
3. `POST /member/progress/photos` recibe `photo`, `angle`, `captured_at` opcional, `notes` y `consent` como multipart; la app lo envía con `FormData` sin fijar `Content-Type`, valida el tamaño (8 MB) y muestra el error del backend (tipo no admitido, firma binaria inválida, ángulo inválido o consentimiento faltante).
4. Las imágenes se cargan con el `file_path` firmado (`exp` + `sig`, HMAC-SHA256 de `photo:{id}:{exp}` con `SECRET_KEY`, **10 minutos**), porque un `<Image>` no envía el Bearer. Deslizar para actualizar regenera los enlaces.
5. `DELETE /member/progress/photos/{photo_id}` borra una foto propia en dos pasos en la app; también puede borrar las que subió el personal. La operación es irreversible y elimina la fila y el archivo.

El socio **no** edita el ángulo, la fecha ni la nota de una foto ya subida, no sube varias a la vez y no revoca el consentimiento desde la app: revocarlo hoy es un procedimiento manual en la base. La descarga de la foto no se audita y el enlace vale como credencial temporal de esa imagen durante sus 10 minutos (ADR-023).

## Flujo de pagos y estado de cuenta

1. `GET /member/payments?page=1&page_size=20` devuelve los pagos de membresía del socio, con el plan y el periodo cubierto, y el importe acumulado.
2. `GET /member/account` devuelve el resumen del estado de cuenta y hasta 100 movimientos —los más recientes primero— con el saldo después de cada uno.
3. La app muestra ambos en una sola pantalla; no hay pago en línea, cancelación ni descarga de facturas desde aquí.

El saldo puede ser negativo (saldo a favor); el aviso que lo acompaña indica que la liquidación se hace en recepción, igual que los cobros y abonos.

## Flujo de facturas

1. `GET /member/invoices?page=1&page_size=20` devuelve las facturas del socio —ventas, cobros de membresía y notas de crédito— con su estado y dos rutas de descarga ya firmadas.
2. La app no reenvía el token en las descargas: cada `pdf_path`/`xml_path` lleva `exp` y `sig` (HMAC-SHA256 con el `SECRET_KEY` del backend) y vence a los **10 minutos**. Al abrir el documento se usa `Linking.openURL(API_URL + path)`, así que el navegador del sistema lo descarga sin sesión.
3. Si un enlace vence, el botón responde con un error de enlace inválido; deslizar hacia abajo regenera los enlaces. No se guardan copias en el dispositivo ni se comparten archivos.

Las facturas solo se entregan si están timbradas o canceladas; las solicitadas o con error de timbrado no muestran botones.

## Flujo de solicitud de factura

1. `GET /member/invoices/origins?page=1&page_size=50` lista las operaciones propias pendientes de facturar y `GET /member/fiscal-profile` trae el perfil fiscal guardado (o `null`).
2. El socio elige una operación, revisa o corrige RFC, razón social, régimen fiscal, código postal, uso del CFDI y correo, y envía `POST /member/invoices` con `origin_type`, `origin_id`, `idempotency_key`, `receptor` y, opcionalmente, `payment_form`/`payment_method`.
3. La app valida el formato antes de enviar (RFC 12–13, nombre de al menos 2, régimen de 3 dígitos, CP de 5, uso de 3 y correo con `@`). La clave de idempotencia se deriva con FNV-1a del origen y del formulario normalizado: reintentar reutiliza la clave y corregir un dato genera otra.
4. La respuesta (`201`) trae la factura y `idempotent_replay`; la app muestra folio, estado e importe, quita la operación de la lista y ofrece «Ver mis facturas» o «Solicitar otra factura».
5. La solicitud queda en `requested`: **el socio no timbra**. Cuando el personal la timbra, el comprobante aparece con sus botones de descarga en la pantalla de facturas.

La app no ofrece PPD: envía siempre la forma derivada del cobro con método PUE. El perfil fiscal se guarda en el backend aunque la solicitud se rechace, para no perder la captura en el siguiente intento.

## Flujo de avisos

1. `GET /member/notifications?page=1&page_size=30` devuelve la bandeja del socio con `total`, `pages` y `unread_total`; los avisos los generan los eventos del club (revisión de un entrenamiento, meta cumplida, meta ajustada o cancelada por el personal, lugar liberado en lista de espera, vencimiento próximo de la membresía, equipo de la rutina que queda fuera de servicio y estado de una factura: timbrada, fallida o cancelada).
2. `POST /member/notifications/{id}/read` marca uno (idempotente) y `POST /member/notifications/read-all` marca todos devolviendo `{"updated": n}`. Los avisos `invoice_stamped`/`invoice_failed`/`invoice_cancelled` se etiquetan «Factura» y, al tocarlos, la app los marca leídos y abre la pantalla de Facturas; el resto solo cambia el estado de lectura.
3. `GET /member/notifications/unread-count` alimenta la insignia de la pantalla de inicio; se consulta al restaurar la sesión, al iniciar sesión, al actualizar el perfil y al salir de la bandeja.
4. Al abrir la bandeja el backend evalúa el vencimiento de la membresía y crea el recordatorio si falta ≤ 7, ≤ 3 o ≤ 1 días (una sola vez por ventana).

La app **no** crea, edita ni borra avisos, y no recibe notificaciones push: el aviso queda en la bandeja hasta que el socio abre la app. Un fallo al consultar el contador se ignora en silencio porque la bandeja muestra el conteo real al abrirla.

Límites del backend: 5 solicitudes por correo cada 15 minutos, 5 intentos por código, código de un solo uso y sesiones revocables. Los tokens y los códigos se guardan solo como hash.

## Estructura

```text
mobile/
├── App.tsx                 # máquina de estados restoring → email → code → home → classes → routines → routineDetail → progressPhotos → payments → invoices → invoiceRequest → notifications
├── index.ts                # registro de Expo
├── app.json                # nombre, slug, tema y plugin de SecureStore
└── src/
    ├── api.ts              # cliente HTTP con timeout y errores tipados
    ├── config.ts           # URL del backend y timeout
    ├── errors.ts           # mensajes en español para el usuario
    ├── format.ts           # fechas, dinero y estados en es-MX
    ├── storage.ts          # token en SecureStore (no persistente en web)
    ├── theme.ts            # colores y estilos compartidos
    ├── types.ts            # contratos de la API
    └── screens/
        ├── LoginScreen.tsx # captura del correo
        ├── CodeScreen.tsx  # código de 6 dígitos, reenvío y código de vista previa
        ├── HomeScreen.tsx  # perfil, acceso, membresía, saldo y accesos a avisos, clases, rutinas, pagos y facturas
        ├── AccessCodeScreen.tsx # código rotativo de seis dígitos con cuenta regresiva para el kiosco
        ├── ClassesScreen.tsx # cartelera, reserva, lista de espera y cancelación
        ├── RoutinesScreen.tsx # resumen de progreso, metas (con alta y cancelación), medidas (con alta) y rutinas asignadas
        ├── RoutineDetailScreen.tsx # plan, editor de series, historial y registro de entrenamientos
        ├── ProgressPhotosScreen.tsx # consentimiento, carga con cámara o galería, galería con visor y eliminación en dos pasos
        ├── PaymentsScreen.tsx # pagos de membresía y estado de cuenta (solo lectura)
        ├── InvoicesScreen.tsx # facturas del socio con descarga PDF/XML por enlace firmado y acceso a solicitar
        ├── InvoiceRequestScreen.tsx # operaciones por facturar, formulario fiscal y solicitud con idempotencia
        └── NotificationsScreen.tsx # bandeja de avisos del club, marcar leído individual o masivo
```

## Pendientes

- Edición de metas y edición/borrado de registros desde la app (hoy el socio captura entrenamientos con sus series, medidas y metas propias, y cancela estas últimas; su corrección se hace en recepción). Falta que el entrenador apruebe una meta creada desde la app.
- Series objetivo por sesión, series por tiempo o distancia y métricas de volumen por ejercicio.
- Cerrar el pendiente de revisión desde la app del entrenador: hoy el entrenador **sí recibe** `workout_pending_review` en la campana del panel (ADR-017), pero el aviso no se cierra al revisar y la app del socio no tiene vista de entrenador.
- Fotos de progreso: edición de ángulo, fecha o nota (corregir exige borrar y volver a subir), carga múltiple, revocación del consentimiento desde la app, compresión/miniaturas y almacenamiento de objetos con respaldo. Los permisos nativos de cámara y fotos todavía no se declaran en `app.json` con el config plugin de `expo-image-picker`, así que hay que agregarlo antes de una compilación de tienda.
- El aviso de equipo fuera de servicio **no enlaza con lo afectado**: la app no tiene pantalla de equipos y el detalle del plan todavía no renderiza `equipment_status`, así que el socio lee el aviso sin ver marcado el ejercicio cuya máquina se paró. Tampoco hay aviso cuando el equipo vuelve a estar operativo.
- Pago en línea y detalle de la venta detrás de cada cargo (hoy se consulta el movimiento). Las facturas se descargan y se solicitan desde la app, pero la lista pide solo la primera página (20), no hay historial de descargas, la solicitud no se timbra desde la app, no se puede elegir PPD ni se avisa cuando cambia el estado de la factura.
- Cobro del precio extra de las clases premium desde la app.
- Notificaciones push y recordatorios programados (renovación, clase, cobranza): la bandeja ya existe, pero el aviso solo se ve cuando el socio abre la app.
- Rotación de tokens, cierre de sesiones por inactividad y MFA opcional.
- Persistencia del token en la vista web (hoy se pierde al recargar) y almacenamiento seguro nativo con biometría.
- Deep links, iconos y splash definitivos, y publicación en tiendas.

## Notas de seguridad

- No commitear `.env`, credenciales SMTP ni tokens. `EXPO_PUBLIC_*` es público por diseño.
- En producción el backend debe tener `SECRET_KEY` propio (se usa para el HMAC de los códigos, de los enlaces de descarga de facturas y de las fotos de progreso) y `PREVIEW_MODE` desactivado; sin `SECRET_KEY` válido el portal responde `503`. Los enlaces de factura vencen a los 10 minutos y solo sirven para un documento y un tipo (PDF o XML); si se filtra uno, deja de funcionar al vencer y rotar `SECRET_KEY` los invalida antes. Los enlaces de foto vencen también a los 10 minutos y solo sirven para una foto; la descarga no se audita y el consentimiento del socio es la base para guardarlas.
- La app no revela si un correo pertenece a un socio: el mensaje de la pantalla de código lo dice explícitamente.
