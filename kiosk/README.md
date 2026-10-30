# Kiosco de recepción

PWA estática que valida el código rotativo que muestra la app del socio y registra
la entrada o la deniega con el motor de acceso del club.

## Estado actual

- Teclado numérico táctil de seis dígitos con autollenado y soporte de teclado físico.
- Resultado grande y accesible: «Acceso concedido» o «Acceso denegado» con el motivo.
- Reinicio automático del teclado a los pocos segundos para el siguiente socio.
- Configuración del kiosco por pantalla: dirección del servidor y token del dispositivo.
- Token guardado solo en `localStorage` del equipo; vive 90 días y se puede rotar o revocar desde el panel.
- Manifest y service worker (`centrofit-kiosk-v3`) para instalar la PWA y conservar el shell sin conexión.
- Aviso explícito de que el registro de entrada necesita el servidor; no hay check-in offline.
- Banda «Equipos no disponibles hoy» con la flota en mantenimiento o fuera de servicio,
  refrescada cada minuto desde `GET /kiosk/equipment`.
- Control de duplicados configurable desde el panel: un código del socio que ya entró
  dentro de la ventana del club se deniega con «Entrada duplicada. Espera un momento.».
- Token de 90 días con fecha visible en el panel («TOKEN VENCE»). Al vencer o rotarse,
  el kiosco y el cartel reciben `401`, borran el token y vuelven a configuración con
  «El token del kiosco no es válido, fue revocado o caducó. Captura uno nuevo.».
- Cartel de recepción (`cartel.html`) como pantalla pasiva para una TV o monitor:
  lista grande de equipos no disponibles con ubicación y estado, estado vacío
  «Todos los equipos están operativos», reloj y fecha, y su propia configuración
  (`centrofit.sign.config.v1`) para usar un token de dispositivo independiente.

## Cómo ejecutarlo

Desde la raíz del repositorio:

```bash
python -m http.server 8090 --directory kiosk
```

Abre `http://localhost:8090` en la tablet o navegador de recepción y
`http://localhost:8090/cartel.html` en la pantalla del cartel.

El backend debe incluir el origen del kiosco en `CORS_ORIGINS` y permitir el
encabezado `X-Kiosk-Token`. En vista previa:

```bash
CORS_ORIGINS="http://localhost:3000,http://localhost:8081,http://localhost:8090" \
PREVIEW_MODE=true ... uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Aprovisionamiento

1. En el panel, entra a **Kiosco** con una cuenta con `settings.manage`.
2. Crea el dispositivo con un nombre reconocible, por ejemplo «Recepción».
3. Copia el token que se muestra **una sola vez** (vive 90 días) y captúralo en la
   pantalla de configuración del kiosco (`Configurar kiosco`).
4. Guarda: el kiosco prueba `/health` y queda listo para recibir códigos.

Para renovar el token antes de que venza —o cuando la tablet ya volvió a
configuración— usa **Rotar token** en el panel, confirma el aviso y captura el
token nuevo en la pantalla; el anterior deja de servir de inmediato y el
dispositivo conserva su historial. Un kiosco revocado no se puede rotar: hay que
crear uno nuevo.

Para retirar un equipo, revócalo en el panel; el kiosco recibe `401` en el
siguiente intento y pide un token nuevo.

Para el cartel, crea un **dispositivo aparte** (por ejemplo «Cartel de recepción»)
y captura su token en la configuración del cartel (`Configurar cartel`). Así se
puede revocar la pantalla sin detener el kiosco y viceversa. El cartel solo usa
`GET /kiosk/equipment`: no valida códigos ni registra accesos.

## Flujo del socio

1. La app pide un código de seis dígitos a `POST /member/access/code` al abrir
   «Acceso habilitado».
2. El código vive cinco minutos, es de un solo uso y reemplaza al anterior.
3. Recepción captura el código en el kiosco; `POST /kiosk/check-in` lo consume y
   responde con la decisión del motor de acceso.
4. La entrada queda en la misma bitácora que los accesos manuales y de lector.

El kiosco también consulta `GET /kiosk/equipment` con el mismo token para listar la
flota no disponible. Es un aviso de solo lectura: no bloquea el check-in ni consulta
la lista al validar un código.

## Reglas y límites

- 6 códigos por socio cada 10 minutos.
- 10 intentos por kiosco cada minuto.
- Códigos guardados como HMAC; el token del kiosco como SHA-256.
- Los códigos ya inutilizables y los intentos antiguos se purgan en el backend con
  `backend/purge_access_data.py` (7 días para códigos y 30 para intentos por
  defecto, configurable); la tablet no interviene y la bitácora de accesos no se
  purga.
- El token caduca a los 90 días (`KIOSK_TOKEN_LIFETIME`) y la rotación es manual y
  presencial; no hay aviso previo automático ni aprovisionamiento remoto, y la
  caducidad no revoca el dispositivo (sigue apareciendo como «Caducado» y se puede
  rotar). Un check-in que ya autenticó el token anterior puede completarse después
  de la rotación; el corte aplica desde la siguiente petición.
- La lista de equipos no disponibles se refresca cada minuto o al recuperar la red;
  si la consulta falla se conserva la última conocida, así que un cambio puede tardar
  hasta un minuto en verse y no hay push.
- El cartel muestra solo nombre, ubicación y estado. No hay horario estimado de
  reparación ni equipo alternativo porque el modelo de mantenimiento aún no los
  expone; la indicación es preguntar en recepción. Un `401` borra su token y vuelve
  a configuración, y si nunca pudo consultar muestra un aviso de error.
- El kiosco no sustituye la validación de recepción: aplica membresía vigente, límite
  diario del plan, control de duplicados y registra el evento, pero aún no valida
  horarios, adeudos, aforo ni hardware.
- Límite diario por plan: se configura en el panel (tarjeta «Límite diario de entradas»
  de la página «Kiosco») y el kiosco lo aplica contando las entradas autorizadas del
  socio en el día local del club, **incluidas las manuales de recepción**. Al agotarse,
  el check-in responde «Ya usaste tus entradas de hoy.»; un plan sin límite no consulta
  el conteo. La entrada manual sigue permitiéndose y emitir un código nunca se bloquea.
- Control de duplicados (antipassback): la tarjeta «Control de duplicados» de la página
  «Kiosco» fija una ventana global en segundos (`0` la desactiva). El check-in busca la
  última entrada autorizada del socio —también las manuales— y, si el código llega
  dentro de la ventana, responde «Entrada duplicada. Espera un momento.»; la entrada
  manual de recepción nunca se bloquea, pero cuenta para la ventana. Con `0` el
  comportamiento es el de siempre y no se consulta la última entrada.

## Pendiente

- Modo offline con cola local y sincronización.
- QR, huella o tarjeta física y apertura de torniquete.
- Rotación automática de tokens, aviso previo al vencimiento y aprovisionamiento remoto.
- Refresco por push del cartel y del kiosco (hoy ambos consultan cada minuto).
- Antipassback por área, lector o plan (hoy la ventana es global del club).
