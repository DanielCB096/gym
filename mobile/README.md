# App móvil del socio

Aplicación Expo/React Native para el socio del club. En este incremento cubre el **acceso con código de un solo uso (OTP) por correo**, la **consulta del perfil y la membresía**, la **reserva de clases**, la **consulta de rutinas y progreso** y los **pagos y el estado de cuenta** (solo lectura); no incluye todavía pago en línea ni facturas.

## Alcance implementado

- Inicio de sesión sin contraseña: el socio escribe su correo y recibe un código de 6 dígitos con vigencia de 10 minutos.
- Sesión de 30 días guardada en `expo-secure-store` (en web no se persiste).
- Pantalla de inicio con:
  - saludo y datos de contacto del socio;
  - estado de acceso (`Acceso habilitado` o el motivo por el que no lo está);
  - plan, estado de la membresía, periodo y días restantes;
  - saldo de la cuenta del socio;
  - fecha de alta y estado del socio;
  - actualización manual y cierre de sesión.
- Pantalla de clases con:
  - cartelera de los próximos 14 días (fecha, tipo, salón, instructor y lugares disponibles);
  - reserva de un lugar o ingreso a la lista de espera cuando la clase está llena;
  - cancelación de la propia reserva, con aviso de la ventana sin penalización;
  - bloqueo explicado para clases premium, membresía inactiva, clases llenas sin lista de espera y clases ya iniciadas;
  - actualización manual con deslizamiento.
- Pantalla de rutinas y progreso con:
  - resumen de entrenamientos totales, de los últimos 30 días y del último peso registrado;
  - metas del socio con avance, valor actual y fecha objetivo;
  - últimas medidas corporales;
  - rutinas asignadas (estado, entrenador, versión, frecuencia y entrenamientos registrados);
  - detalle de cada rutina con el plan de la versión asignada (series, repeticiones, descanso y carga) y el historial de entrenamientos;
  - aviso de que el registro de entrenamientos, medidas y fotos se hace con el entrenador o en recepción;
  - actualización manual con deslizamiento.
- Pantalla de pagos y estado de cuenta con:
  - saldo de la cuenta, con aviso para saldo a favor o deuda, conteo de cargos y abonos, importe pagado en membresías y fecha de corte;
  - pagos de membresía con importe, plan, periodo, método y nota;
  - movimientos de cuenta en orden descendente, con importe con signo, saldo después del movimiento, referencia y método;
  - aviso cuando el historial supera los 100 movimientos que devuelve el backend;
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

## Flujo de clases

1. `GET /member/classes?days=14` devuelve la cartelera con `can_reserve`, `blocked_reason` y la reserva activa del socio.
2. `POST /member/classes/sessions/{session_id}/reservations` reserva un lugar o entra a la lista de espera; responde `409` con el motivo cuando el socio no puede reservar.
3. `POST /member/classes/reservations/{reservation_id}/cancel` cancela una reserva propia antes del inicio de la clase.
4. La app refresca la cartelera después de cada acción para mostrar el estado y los lugares actualizados.

Las reservas usan el origen `app`; el backend reutiliza las reglas del módulo de clases (aforo, bloqueo de fila, lista de espera y ventana de cancelación). Las clases premium se muestran pero no se pueden reservar desde la app hasta que exista el cobro del precio extra.

## Flujo de rutinas y progreso

1. `GET /member/routines` devuelve las asignaciones del socio, con las activas primero, y el resumen por estado.
2. `GET /member/routines/{assignment_id}` devuelve el plan de la **versión fijada al asignar**, el objetivo, las notas y los últimos 10 entrenamientos. Una asignación de otro socio responde `404`.
3. `GET /member/progress` devuelve entrenamientos totales y de los últimos 30 días, última medición, histórico de medidas y metas con su avance.
4. La app agrupa ambos resultados en una pantalla de resumen y abre el detalle de cada rutina.
5. `POST /member/routines/{assignment_id}/workouts` registra un entrenamiento (fecha, duración, esfuerzo y notas) en una asignación **activa**; queda como «Por revisar» hasta que el entrenador lo valida.
6. `POST /member/progress/measurements` registra peso, cintura, pecho y grasa (al menos uno) con notas; es append-only y actualiza las metas al momento.

El socio **no** edita ni borra registros, ni captura metas o fotos desde la app: eso sigue siendo exclusivo del panel del personal (`routines.manage`). Editar la plantilla de una rutina no cambia el plan que el socio ya tiene asignado.

En los formularios se valida en el cliente el formato de fecha, que no sea futura, la duración (0–600 min), el esfuerzo (1–10), los decimales con coma y al menos una medida. El campo de notas limita a 2000 caracteres en el entrenamiento y 300 en la medida. El detalle rotula cada registro como «Desde tu app» o «Desde recepción», con el estado «Por revisar» o «Revisado».

## Flujo de pagos y estado de cuenta

1. `GET /member/payments?page=1&page_size=20` devuelve los pagos de membresía del socio, con el plan y el periodo cubierto, y el importe acumulado.
2. `GET /member/account` devuelve el resumen del estado de cuenta y hasta 100 movimientos —los más recientes primero— con el saldo después de cada uno.
3. La app muestra ambos en una sola pantalla; no hay pago en línea, cancelación ni descarga de facturas desde aquí.

El saldo puede ser negativo (saldo a favor); el aviso que lo acompaña indica que la liquidación se hace en recepción, igual que los cobros y abonos.

Límites del backend: 5 solicitudes por correo cada 15 minutos, 5 intentos por código, código de un solo uso y sesiones revocables. Los tokens y los códigos se guardan solo como hash.

## Estructura

```text
mobile/
├── App.tsx                 # máquina de estados restoring → email → code → home → classes → routines → routineDetail → payments
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
        ├── HomeScreen.tsx  # perfil, acceso, membresía y saldo
        ├── ClassesScreen.tsx # cartelera, reserva, lista de espera y cancelación
        ├── RoutinesScreen.tsx # resumen de progreso, metas, medidas (con alta) y rutinas asignadas
        ├── RoutineDetailScreen.tsx # plan, historial y registro de entrenamientos
        └── PaymentsScreen.tsx # pagos de membresía y estado de cuenta (solo lectura)
```

## Pendientes

- Metas y edición/borrado de registros desde la app (hoy el socio solo captura entrenamientos y medidas; su corrección se hace en recepción).
- Detalle por serie (series, peso y esfuerzo por ejercicio) en el historial de entrenamientos.
- Aviso al entrenador de un entrenamiento pendiente de revisión y al socio cuando se revisa.
- Fotos de progreso en la app, con consentimiento y política de acceso.
- Pagos en línea, descarga de facturas y detalle de la venta detrás de cada cargo (hoy solo se consulta el movimiento).
- Cobro del precio extra de las clases premium desde la app.
- Notificaciones push y recordatorios (renovación, clase, cobranza).
- Rotación de tokens, cierre de sesiones por inactividad y MFA opcional.
- Persistencia del token en la vista web (hoy se pierde al recargar) y almacenamiento seguro nativo con biometría.
- Deep links, iconos y splash definitivos, y publicación en tiendas.

## Notas de seguridad

- No commitear `.env`, credenciales SMTP ni tokens. `EXPO_PUBLIC_*` es público por diseño.
- En producción el backend debe tener `SECRET_KEY` propio (se usa para el HMAC de los códigos) y `PREVIEW_MODE` desactivado; sin `SECRET_KEY` válido el portal responde `503`.
- La app no revela si un correo pertenece a un socio: el mensaje de la pantalla de código lo dice explícitamente.
