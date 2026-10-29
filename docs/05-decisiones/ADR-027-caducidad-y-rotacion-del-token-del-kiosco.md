# ADR-027: Caducidad y rotación del token del kiosco

- Fecha: 2026-10-28
- Estado: propuesta inicial

## Contexto

El canal de entrada autónomo (ADR-024) autentica la tablet de recepción con un bearer de dispositivo guardado como SHA-256 y enviado en `X-Kiosk-Token`. Ese token se mostraba una sola vez al crear el dispositivo y vivía para siempre: solo se podía cortar revocando el kiosco, lo que además obligaba a crear otro dispositivo y perder su historial de actividad. La fuga era lenta y silenciosa: una tablet prestada, un `localStorage` copiado o una captura del token seguían siendo válidos mientras el dispositivo estuviera `active`, sin fecha de caducidad ni forma de renovar la credencial sin reemplazar el dispositivo.

El club necesitaba dos cosas concretas: que un token olvidado deje de servir solo, y que recepción pueda renovarlo desde el panel sin dar de baja la tablet ni perder el vínculo con los eventos ya registrados.

## Decisión

- **Vida útil de 90 días.** `KIOSK_TOKEN_LIFETIME = timedelta(days=90)` en `access.kiosk`. `create_kiosk_device` y `rotate_kiosk_device` fijan `token_expires_at = ahora + 90 días` con el reloj del servidor. No es configurable por club ni por dispositivo: un valor por pantalla obligaría a validar rangos y a explicar cada caso, y 90 días cubre un trimestre de operación sin rotaciones frecuentes.
- **La columna es nula para el pasado.** `kiosk_devices.token_expires_at` es `TIMESTAMP WITH TIME ZONE` **nullable**. Un `NULL` significa «creado antes de esta columna y nunca caduca»: solo puede aparecer en filas antiguas o insertadas fuera del servicio. La migración `20261028_0045_kiosk_token_expiry.py` rellena las filas existentes con `now() + INTERVAL '90 days'` —no con `created_at + 90 días`— para que una tablet en turno no quede cortada a media jornada por el despliegue; la vista previa hace lo mismo con `preview_patch.py` (`datetime('now', '+90 days')`).
- **El vencimiento se comprueba al autenticar.** `authenticate_kiosk_device` compara `token_expires_at` con el instante de la petición (normalizando a UTC) y, si ya pasó, lanza `InvalidKioskToken`. La respuesta HTTP es el mismo `401` genérico «Kiosk is not authorized» que produce un token revocado o inventado: el cliente no puede distinguir caducado de revocado, y el kiosco no necesita saberlo para volver a configuración. La comparación usa `<=`, así que el segundo exacto del vencimiento ya no vale.
- **Rotar es reemplazar, no extender.** `POST /admin/kiosk/devices/{id}/rotate-token` (`settings.manage`) genera un token nuevo con `secrets.token_urlsafe(32)`, sobrescribe `token_sha256`, reinicia `token_expires_at` a 90 días y devuelve el token en claro **una sola vez** en un `KioskDeviceCreatedResponse`, igual que el alta. El token anterior deja de funcionar en la siguiente petición porque su hash ya no existe: no hay periodo de gracia ni dos tokens válidos a la vez.
- **Solo se rota un kiosco activo.** `rotate_kiosk_device` responde `409` («Un kiosco revocado no puede recibir un token nuevo.») si el dispositivo está `revoked` y `404` si el UUID no existe. Recuperar un kiosco revocado exige crear uno nuevo, de modo que revocar sigue siendo una decisión definitiva y no una pausa.
- **El panel muestra el vencimiento y avisa antes.** La columna «TOKEN VENCE» de la página «Kiosco» pinta la fecha, «Vence en N días» en ámbar cuando faltan 15 o menos y «Caducó el …» con el estado «Caducado» cuando ya pasó; un kiosco caducado sigue siendo rotable porque su estado en la base sigue siendo `active`. La confirmación de rotación es un aviso en línea (no `window.confirm`), explica que el token actual dejará de servir de inmediato y que la tablet volverá a su pantalla de configuración, y el token nuevo se muestra en el panel de instalación con el aviso de que no se vuelve a mostrar.
- **La recuperación es presencial.** Tras rotar o caducar, el kiosco y el cartel reciben `401`, borran el token del `localStorage` y vuelven a su formulario con «El token del kiosco no es válido, fue revocado o caducó. Captura uno nuevo.» (el cartel cambia «kiosco» por «dispositivo»). Alguien tiene que estar frente a la pantalla para capturar el token nuevo: no hay aprovisionamiento remoto.
- **El service worker sube a `centrofit-kiosk-v3`.** El cambio de mensajes y de copia en `index.html`/`cartel.html` no puede quedar servido desde la caché anterior.

## Consecuencias y límites

- Un token filtrado deja de servir como máximo 90 días después de su emisión y, en la práctica, en cuanto recepción rote el dispositivo. Rotar corta el acceso al instante sin borrar el historial de eventos del kiosco ni su etiqueta.
- **La caducidad no revoca el dispositivo.** Un kiosco caducado sigue `active` y se puede rotar; también sigue contando para el listado y para el límite de intentos. Si el equipo se retira hay que revocarlo, no esperar a que venza.
- **Rotar es una operación manual y presencial.** No hay job que rote ni aviso por correo o push antes del vencimiento; el panel solo colorea los últimos 15 días. Un club que no mire la página «Kiosco» descubrirá la caducidad cuando la tablet vuelva a configuración.
- **No hay auditoría de la rotación.** La tabla guarda `token_expires_at` y el hash nuevo, pero no quién rotó, cuándo ni cuántas veces; `created_by` sigue apuntando al alta. Queda como deuda junto con el resto de la administración de dispositivos.
- **La rotación no es atómica con un check-in en vuelo.** Un check-in que ya autenticó el token anterior puede completarse después de la rotación y registrar un evento; el corte aplica desde la siguiente petición. El impacto es una entrada como máximo, no una sesión abierta.
- **El token sigue viviendo en `localStorage`.** La caducidad y la rotación acotan el daño de una fuga, pero no impiden que quien tenga acceso físico al navegador lea el token vigente. Siguen pendientes el límite por IP, el certificado de dispositivo y el bloqueo por pantalla.
- **El reloj importa.** El vencimiento se calcula con la hora del servidor, así que una tablet con el reloj muy desviado no adelanta ni retrasa la caducidad; quien decide es el backend.
- **Las filas con `NULL` no caducan nunca.** Es a propósito para no cortar instalaciones antiguas, pero significa que un `NULL` insertado a mano se salta la política; el servicio siempre escribe una fecha.

## Referencias

- `backend/src/app/modules/access/models.py` (`KioskDevice.token_expires_at`)
- `backend/src/app/modules/access/kiosk.py` (`KIOSK_TOKEN_LIFETIME`, `create_kiosk_device`, `rotate_kiosk_device`, `authenticate_kiosk_device`, `KioskDeviceRevoked`)
- `backend/alembic/versions/20261028_0045_kiosk_token_expiry.py`
- `backend/preview_patch.py` (columna y relleno de 90 días en la vista previa)
- `backend/src/app/main.py` (`KioskDeviceResponse.token_expires_at`, `POST /admin/kiosk/devices/{device_id}/rotate-token`)
- `backend/tests/test_kiosk_access_api.py` (2 pruebas de rotación y caducidad)
- `web/src/app/page.tsx` (`kioskTokenExpiry`, `rotateDevice`, columna «TOKEN VENCE»), `web/src/app/api/admin/kiosk/devices/[deviceId]/rotate-token/route.ts`
- `kiosk/app.js`, `kiosk/cartel.js` (mensaje de `401`), `kiosk/sw.js` (`centrofit-kiosk-v3`)
