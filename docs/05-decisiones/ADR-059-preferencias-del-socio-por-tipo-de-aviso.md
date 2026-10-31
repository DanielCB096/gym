# ADR-059: Preferencias del socio por tipo de aviso

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Cierra el límite de ADR-052 («No hay preferencias por tipo ni por horario»)

## Contexto

El push del socio (ADR-052) avisa de todo lo que entra a su bandeja: una factura timbrada, un cambio de clase, una meta ajustada por recepción o un equipo fuera de servicio. Para muchos socios eso es demasiado ruido: quieren enterarse de lo urgente y consultar el resto cuando abren la app. Hasta hoy la única forma de apagar el canal era cerrar sesión, que además retira todos sus dispositivos y le quita el acceso, así que no era una respuesta.

La bandeja no es el problema. El club necesita dejar constancia de lo que comunicó —una factura timbrada o un equipo caído son avisos que el socio debe poder consultar después—; lo que el socio puede decidir es si eso **interrumpe** su teléfono. La decisión de este corte separa esas dos cosas: la bandeja conserva todo, y solo el push se apaga.

## Decisión

- **Seis categorías cubren los 18 tipos de aviso.** `membership` (vencimiento), `classes` (recordatorio, reserva, espera, cancelación y reprogramación), `training` (revisión de entrenamiento y metas), `billing` (facturas), `equipment` (equipo fuera de servicio) y `physio` (citas y recordatorio). El mapa `NOTIFICATION_CATEGORY_BY_KIND` es exhaustivo por contrato: una prueba compara ambas tuplas y falla si aparece un tipo sin categoría, y otra comprueba que cada categoría tenga al menos un tipo.
- **Las categorías viven en el código, no en una tabla configurable.** El club no necesita inventar categorías y un catálogo editable permitiría que un tipo quedara sin interruptor. Cambiar el mapa es una decisión de producto y una migración cuando toque, no configuración de operación.
- **Fila ausente significa encendido.** `member_notification_preferences` guarda solo las decisiones que el socio tomó: `(member_id, category)` único, `push_enabled` y `updated_at`. Un socio nuevo, o una categoría que nunca tocó, recibe push; el silencio es una elección, nunca un valor por defecto. Volver a encender conserva la fila para que el panel distinga un «sí» explícito de un socio que nunca la miró.
- **Apagar una categoría cancela lo que ya espera.** El aviso que la petición del socio todavía no había enviado se borra si está `pending` (nunca salió, no hay historia que perder) y una entrega `failed` con reintento programado pierde su `next_attempt_at` pero conserva su estado y su error (el panel sigue viendo el intento fallido). Un push ya `sent` o `simulated` no se toca: el teléfono ya lo recibió y el historial no se reescribe.
- **El aviso se sigue escribiendo.** `_enqueue_member_push_deliveries` consulta `is_push_enabled` antes de crear filas: una categoría apagada deja la bandeja, el contador de no leídos y el historial intactos, y solo omite el encolado. Los recordatorios diferidos (`push=False`) tampoco se ven afectados: nunca empujaban.
- **El interruptor es del socio, no del dispositivo.** Apagar «Clases» apaga ese tipo en todos sus teléfonos y tablets. Un interruptor por dispositivo multiplicaría filas y confundiría al socio sobre qué teléfono suena.
- **API de auto-servicio.** `GET /member/notification-preferences` devuelve las seis categorías en orden estable, con las que no tienen fila en `push_enabled: true` y `updated_at: null`. `PATCH /member/notification-preferences` recibe `{"categories": [{"category": "…", "push_enabled": false}]}`, aplica solo las categorías presentes (una actualización parcial no resetea las demás) y devuelve el conjunto completo. Una lista vacía, una categoría desconocida o repetida responde `422`; sin sesión de socio, `401`.
- **La app dibuja seis interruptores.** `NotificationsScreen` carga la bandeja y las preferencias juntas, muestra una tarjeta después de la lista con un `Switch` por categoría y actualiza de forma optimista: si el `PATCH` falla, restaura el estado anterior y muestra el error. El texto aclara que la bandeja conserva todo y que apagar solo deja de interrumpir.
- **Sin interruptor de horario.** El alcance de este corte es por tipo de aviso. Un horario de silencio (por ejemplo, no molestar de noche) es otra decisión y otra tabla; no se simula con una categoría.

## Consecuencias y límites

- **No hay historial de cambios de preferencia.** Se guarda el último estado con `updated_at`; no se audita quién apagó qué ni cuándo, a diferencia de las bitácoras del club. Si el club necesita esa traza, habrá que agregarla como tabla aparte.
- **El panel no muestra las preferencias del socio.** Recepción no puede ver ni cambiar los interruptores; hacerlo exigiría una pantalla con permiso propio y decidir si el club puede sobrescribir una decisión del socio.
- **Un tipo nuevo nace encendido.** Al agregar un tipo de aviso y su categoría, todos los socios lo reciben hasta que lo apaguen. Es coherente con «la ausencia de fila es sí», pero conviene anunciarlo en el despliegue si el tipo es ruidoso.
- **La carrera con una pasada en vuelo es at-least-once.** Si el socio apaga una categoría mientras otro proceso ya reclamó una entrega de esa categoría, ese push puede salir igual; la siguiente petición ya no encola nada. Es la misma ventana que ADR-052 documenta para la entrega.
- **Apagar una categoría no borra los avisos de la bandeja ni los marca leídos.** El contador de no leídos sigue contando lo que llegó; el socio puede marcarlo todo como leído con el botón que ya existe.
- **No hay preferencias por tipo de correo del personal.** Este corte es solo del push del socio. El correo del personal sigue con su interruptor global de club (ADR-048) y sin preferencias por cuenta o por tipo.
- **El mínimo de categorías es fijo.** Un socio no puede silenciar, por ejemplo, solo los recordatorios de clase sin silenciar las cancelaciones: ambos comparten `classes`. Separarlos exigiría otra categoría y otra decisión de producto (las cancelaciones son de las que casi nadie quiere perder).

## Referencias

- `backend/src/app/modules/notifications/models.py` (`MEMBER_NOTIFICATION_CATEGORIES`, `NOTIFICATION_CATEGORY_BY_KIND`, `MemberNotificationPreference`)
- `backend/src/app/modules/notifications/preferences.py` (`category_for_kind`, `list_member_preferences`, `update_member_preferences`, `is_push_enabled`)
- `backend/src/app/modules/notifications/service.py` (`_enqueue_member_push_deliveries` consulta `is_push_enabled`)
- `backend/src/app/main.py` (`GET`/`PATCH /member/notification-preferences`)
- `backend/alembic/versions/20261031_0071_member_notification_preferences.py`
- `backend/tests/test_member_notification_preferences.py` (13 pruebas)
- `mobile/src/screens/NotificationsScreen.tsx`, `mobile/src/api.ts`, `mobile/src/types.ts`
- ADR-052 (push del socio), ADR-053 (cola en el panel), ADR-054 (reintento automático), ADR-016 (bandeja del socio)
