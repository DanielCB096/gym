# ADR-052: Push del socio desde la app Expo

- Fecha: 2026-10-30
- Estado: propuesta inicial
- Extiende ADR-016 (bandeja de avisos del socio)

## Contexto

La bandeja del socio guarda cada aviso con su texto congelado, pero solo habla cuando el socio abre la app. Una clase cancelada, una promoción de la lista de espera o una factura timbrada son útiles precisamente cuando nadie está mirando la pantalla. La app es Expo, así que el camino natural es que el dispositivo registre su token de Expo y que el club encole un push por aviso, con el mismo criterio de «fuera de la transacción» que ya usa el correo del personal (ADR-049): no hay worker en el proyecto.

## Decisión

- **Un token es una instalación, no una persona.** `member_push_tokens` guarda `token` (único), `platform` (`ios`/`android`), `active`, `created_at`, `last_seen_at` y `deactivated_at`. Se valida la forma que entrega Expo (`ExponentPushToken[...]`/`ExpoPushToken[...]`, hasta 255 caracteres). El mismo teléfono puede cambiar de socio: registrar un token que ya existía lo **transfiere** a la cuenta nueva y lo reactiva, en lugar de duplicarlo, para que el anterior deje de recibir avisos que no le tocan. Desactivar es una bandera: la entrega conserva el token como instantánea de adónde fue.
- **Una fila por aviso y dispositivo, dentro de la transacción del aviso.** `create_notification` escribe `member_push_deliveries` en la misma transacción que el aviso, una por token activo del socio, con el token copiado. Si la transacción se revierte no queda push huérfano, y la audiencia es la que existía al ocurrir el evento: un dispositivo registrado después no recibe avisos anteriores. El par `(notification_id, token)` es único.
- **Los recordatorios perezosos no se empujan.** Las tres materializaciones que corren al leer la bandeja —membresía por vencer, recordatorio de clase y recordatorio de fisioterapia— llaman a `create_notification` con `push=False`: anunciarle al socio lo que está viendo en ese momento no aporta y multiplicaría los envíos.
- **La pasada corre después de la respuesta.** `MemberPushFlush`, una dependencia explícita de FastAPI, toma el motor de la sesión y añade una tarea de fondo que abre su propia sesión y llama a `send_pending_member_push_deliveries` (lotes de 20, las más antiguas primero). Está colgada de todos los emisores que pueden escribir un aviso del socio: la bandeja, la reserva y cancelación de clases, la medición y la revisión de rutinas, las metas, el estado de equipo, el timbrado y cancelación de facturas, la solicitud de factura y las citas de fisioterapia. Sin worker ni planificador.
- **Reclamo atómico y estados del correo.** Cada fila se toma con un compare-and-set sobre `attempts` confirmado antes de salir; `sent` es que Expo aceptó el ticket, `simulated` es la vista previa sin proveedor y `failed` guarda el error truncado a 500. Un fallo no interrumpe el resto del lote y **no hay reintento**: lo que falló queda como registro.
- **Un dispositivo desinstalado se retira.** Si el ticket de Expo trae `DeviceNotRegistered`, la entrega queda `failed` y el token se desactiva con su fecha; los avisos siguientes del socio ya no se encolan para ese teléfono.
- **API del socio.** `POST /member/push-tokens` (`201`) registra o transfiere y responde el token con su plataforma, `POST /member/push-tokens/revoke` (`204`) desactiva uno propio, y el `logout` del socio desactiva **todos** sus tokens activos. Un token inválido o una plataforma fuera de `ios`/`android` responde `422`; un socio autenticado que no existe en `members` responde `404`.
- **La app registra sola.** Al restaurar la sesión y después de entrar, la app pide permiso de notificaciones una vez por sesión, obtiene el token de Expo con el `projectId` de EAS y lo registra; al salir, revoca el token antes de cerrar la sesión. `expo-notifications` se carga con `import()` dinámico y solo en iOS/Android: la vista previa web no intenta registrar nada. Sin `projectId` de EAS la app sigue funcionando y simplemente no suena.

## Consecuencias y límites

- **Sin proyecto EAS no hay token.** El token de Expo requiere `extra.eas.projectId` (o `Constants.easConfig`); mientras el club no configure su proyecto, la app pide permiso pero no registra. Es un requisito de despliegue, no un fallo.
- **No hay preferencias por tipo ni por horario.** El socio recibe todos los avisos de su cuenta en todos sus dispositivos activos; silenciar un tipo exigiría columnas o una tabla de preferencias que el club no pidió.
- **Ventana at-least-once.** El intento se confirma antes de llamar a Expo, así que un corte entre la aceptación y el `commit` puede repetir el push. No hay deduplicación en el dispositivo.
- **Sin reintento ni backoff.** Un `failed` es definitivo y se ve en la base; no hay tarjeta de push en el panel ni botón de reintento, a diferencia del correo.
- **El acuse del push no existe.** Se guarda el ticket de Expo (`sent`), no su recibo de entrega; saber si el teléfono lo mostró requeriría el receipt id de Expo y otra cola.
- **El payload es informativo.** El `data` lleva `notification_id`, `kind` y `ref_id` para que la app pueda abrir la pantalla correcta, pero este corte no toca la navegación al tocar la notificación.
- **La vista previa no toca dispositivos.** `PREVIEW_MODE` marca las entregas como `simulated`, igual que el transporte SMTP.

## Referencias

- `backend/src/app/modules/notifications/models.py` (`MemberPushToken`, `MemberPushDelivery`)
- `backend/src/app/modules/notifications/push.py` (registro, pasada, ticket y retiro del token)
- `backend/src/app/modules/notifications/service.py` (`create_notification(push=...)`, `_enqueue_member_push_deliveries`)
- `backend/src/app/main.py` (`MemberPushFlush`, rutas `/member/push-tokens`, `member_logout`)
- `backend/alembic/versions/20261031_0067_member_push_deliveries.py`
- `backend/tests/test_member_push.py`
- `mobile/src/push.ts`, `mobile/src/api.ts`, `mobile/App.tsx`, `mobile/app.json`
- `docs/05-decisiones/ADR-016-notificaciones-del-socio.md`, `ADR-049-envio-y-reintento-de-la-cola-de-correos-de-asistencia.md`
