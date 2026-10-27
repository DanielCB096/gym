# App móvil del socio

Aplicación Expo/React Native para el socio del club. En este incremento cubre el **acceso con código de un solo uso (OTP) por correo**, la **consulta del perfil y la membresía** y la **reserva de clases**; no incluye todavía rutinas, pagos ni facturas.

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

Límites del backend: 5 solicitudes por correo cada 15 minutos, 5 intentos por código, código de un solo uso y sesiones revocables. Los tokens y los códigos se guardan solo como hash.

## Estructura

```text
mobile/
├── App.tsx                 # máquina de estados restoring → email → code → home → classes
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
        └── ClassesScreen.tsx # cartelera, reserva, lista de espera y cancelación
```

## Pendientes

- Rutinas asignadas, registro de entrenamientos, medidas, metas y fotos de progreso.
- Pagos, estado de cuenta y descarga de facturas.
- Cobro del precio extra de las clases premium desde la app.
- Notificaciones push y recordatorios (renovación, clase, cobranza).
- Rotación de tokens, cierre de sesiones por inactividad y MFA opcional.
- Persistencia del token en la vista web (hoy se pierde al recargar) y almacenamiento seguro nativo con biometría.
- Deep links, iconos y splash definitivos, y publicación en tiendas.

## Notas de seguridad

- No commitear `.env`, credenciales SMTP ni tokens. `EXPO_PUBLIC_*` es público por diseño.
- En producción el backend debe tener `SECRET_KEY` propio (se usa para el HMAC de los códigos) y `PREVIEW_MODE` desactivado; sin `SECRET_KEY` válido el portal responde `503`.
- La app no revela si un correo pertenece a un socio: el mensaje de la pantalla de código lo dice explícitamente.
