# ADR-053: Cola de push del socio en el panel

- Fecha: 2026-10-30
- Estado: propuesta inicial
- Extiende ADR-052 (push del socio desde la app Expo)

## Contexto

ADR-052 dejó la cola de push escrita con cada aviso, pero sin pantalla y sin reintento: una fila `failed` solo se veía consultando la base y un push que Expo rechazaba por un corte pasajero quedaba perdido. La cola de correos del personal ya tiene tarjeta, conteos y reintento manual (ADR-049), así que el panel mostraba una asimetría difícil de explicar a recepción: el correo se podía rescatar y el push no.

## Decisión

- **Listado paginado con el aviso y el socio resueltos.** `GET /admin/notifications/push-deliveries` devuelve la página más reciente primero, con filtro opcional por `status` (`pending`, `sent`, `simulated`, `failed`), `page` y `page_size` (1–100, por defecto 20). Cada fila une la notificación y el socio para mostrar `member_name`, `member_email`, `kind` y `title` sin que el panel tenga que resolverlos por su cuenta. Un estado fuera del catálogo responde `422`.
- **El token se enmascara.** La API nunca devuelve el token completo: `device` queda como `…` más los últimos cuatro caracteres. El panel necesita distinguir dispositivos, no la dirección real, y un listado operativo no es un buen lugar para repartir identificadores de instalación.
- **Los conteos incluyen los dispositivos activos.** La cabecera suma `pending`, `sent`, `simulated` y `failed`, y añade `active_tokens` contando las filas activas de `member_push_tokens`, para que recepción sepa si el club tiene algún teléfono registrado antes de interpretar un cero.
- **Reintento manual solo de lo que falló.** `POST /admin/notifications/push-deliveries/{delivery_id}/retry` exige estado `failed`, toma la fila con el mismo compare-and-set sobre `attempts` que usa la pasada y conserva el historial: `attempts` sube, `last_attempt_at` se actualiza y el resultado se escribe igual que en un envío normal. Un id inexistente responde `404`; una fila ya enviada, simulada o pendiente responde `409`; dos reintentos concurrentes dejan ganar a uno y el otro recibe `409`.
- **El reintento respeta el retiro del dispositivo.** Si Expo responde `DeviceNotRegistered`, el token se desactiva igual que en la pasada y la entrega queda `failed` con el motivo; reintentar no resucita un teléfono desinstalado.
- **Pasada bajo demanda desde el panel.** `POST /admin/notifications/push-deliveries/send` ejecuta un lote de la misma función que corre después de las respuestas y devuelve `attempted`, `sent`, `simulated`, `failed`, `deactivated` y `remaining`. Sirve para drenar lo que quedó en cola sin esperar al siguiente aviso; la vista previa lo marca todo como `simulated`.
- **Se reutilizan los permisos y la pestaña del correo.** Leer la cola pide `attendance.read` y enviar o reintentar pide `attendance.manage`, igual que la tarjeta de correos. La tarjeta vive junto a ella en la pestaña Equipo, bajo el rótulo «Push del socio»: es la misma operación de recepción y separarla obligaría a inventar un permiso nuevo para la misma persona.

## Consecuencias y límites

- **No hay reintento automático ni backoff.** Una fila fallida espera a que alguien pulse «Reintentar»; no hay un programador que la reprograme ni un máximo de intentos distinto del que impone la pasada (que solo toma `pending`).
- **Sigue sin haber acuse del push.** Se conserva el ticket de Expo, no su recibo de entrega, así que `sent` no prueba que el teléfono lo mostró.
- **El enmascarado es de presentación.** El token completo sigue en la base porque la pasada lo necesita; la API y el panel no lo exponen.
- **Sin preferencias por tipo ni navegación al tocar.** Este corte solo agrega visibilidad y reintento; el comportamiento del aviso en el dispositivo no cambia.
- **Un reintento puede duplicar.** La ventana at-least-once de ADR-052 sigue vigente: si el primer intento llegó al teléfono pero el registro quedó en `failed`, reintentar lo repite.
- **Sin aviso al personal cuando falla un push.** La tarjeta lo muestra, pero nadie recibe un correo o campana por una entrega fallida; el club tendría que abrir la cola.

## Referencias

- `backend/src/app/modules/notifications/push.py` (`list_member_push_deliveries`, `member_push_delivery_counts`, `retry_member_push_delivery`, `mask_push_token`)
- `backend/src/app/main.py` (`/admin/notifications/push-deliveries`)
- `backend/tests/test_member_push_admin.py`
- `web/src/app/api/admin/notifications/push-deliveries/`, `web/src/app/page.tsx`
- `docs/05-decisiones/ADR-049-envio-y-reintento-de-la-cola-de-correos-de-asistencia.md`, `ADR-052-push-del-socio-desde-la-app.md`
