# Kiosco de recepción

PWA estática que valida el código rotativo que muestra la app del socio y registra
la entrada o la deniega con el motor de acceso del club.

## Estado actual

- Teclado numérico táctil de seis dígitos con autollenado y soporte de teclado físico.
- Resultado grande y accesible: «Acceso concedido» o «Acceso denegado» con el motivo.
- Reinicio automático del teclado a los pocos segundos para el siguiente socio.
- Configuración del kiosco por pantalla: dirección del servidor y token del dispositivo.
- Token guardado solo en `localStorage` del equipo; se puede revocar desde el panel.
- Manifest y service worker para instalar la PWA y conservar el shell sin conexión.
- Aviso explícito de que el registro de entrada necesita el servidor; no hay check-in offline.

## Cómo ejecutarlo

Desde la raíz del repositorio:

```bash
python -m http.server 8090 --directory kiosk
```

Abre `http://localhost:8090` en la tablet o navegador de recepción.

El backend debe incluir el origen del kiosco en `CORS_ORIGINS` y permitir el
encabezado `X-Kiosk-Token`. En vista previa:

```bash
CORS_ORIGINS="http://localhost:3000,http://localhost:8081,http://localhost:8090" \
PREVIEW_MODE=true ... uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Aprovisionamiento

1. En el panel, entra a **Kiosco** con una cuenta con `settings.manage`.
2. Crea el dispositivo con un nombre reconocible, por ejemplo «Recepción».
3. Copia el token que se muestra **una sola vez** y captúralo en la pantalla de
   configuración del kiosco (`Configurar kiosco`).
4. Guarda: el kiosco prueba `/health` y queda listo para recibir códigos.

Para retirar un equipo, revócalo en el panel; el kiosco recibe `401` en el
siguiente intento y pide un token nuevo.

## Flujo del socio

1. La app pide un código de seis dígitos a `POST /member/access/code` al abrir
   «Acceso habilitado».
2. El código vive cinco minutos, es de un solo uso y reemplaza al anterior.
3. Recepción captura el código en el kiosco; `POST /kiosk/check-in` lo consume y
   responde con la decisión del motor de acceso.
4. La entrada queda en la misma bitácora que los accesos manuales y de lector.

## Reglas y límites

- 6 códigos por socio cada 10 minutos.
- 10 intentos por kiosco cada minuto.
- Códigos guardados como HMAC; el token del kiosco como SHA-256.
- El kiosco no sustituye la validación de recepción: aplica membresía vigente y
  registra el evento, pero aún no valida horarios, adeudos, aforo ni hardware.

## Pendiente

- Antipassback y límite diario por plan.
- Modo offline con cola local y sincronización.
- QR, huella o tarjeta física y apertura de torniquete.
- Rotación automática de tokens y aprovisionamiento remoto.
