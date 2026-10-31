# ADR-060: Navegación al tocar la notificación push

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Extiende ADR-052 (push del socio desde la app) y ADR-016 (bandeja de avisos del socio)

## Contexto

ADR-052 dejó el payload del push como informativo: lleva `notification_id`, `kind` y `ref_id`, pero tocar la notificación solo abría la app en el estado en que estuviera. Un aviso de factura timbrada, de una clase cancelada o de una cita movida es más útil si el toque lleva a la pantalla donde el socio puede actuar. La bandeja ya resolvía eso para facturas, clases y fisioterapia con tres listas de tipos dentro de `NotificationsScreen`; el push no compartía esa decisión y además la bandeja no enviaba a ningún lado los avisos de rutinas, equipo ni membresía.

## Decisión

- **Un solo mapa de tipos a pantalla, compartido por la bandeja y el push.** `mobile/src/notificationRouting.ts` expone `notificationDestination(kind)` y lo usan ambos caminos, así que tocar un aviso en la bandeja o su push lleva al mismo lugar:
  - `invoice_*` → **Facturas**.
  - `class_reserved`, `class_reminder`, `class_cancelled`, `class_rescheduled` y `class_waitlist_promoted` → **Clases**.
  - Los cuatro tipos de fisioterapia → **Fisioterapia**.
  - `workout_reviewed`, `goal_achieved`, `goal_updated_by_staff`, `goal_cancelled_by_staff` y `equipment_out_of_service` → **Rutinas**, donde viven el avance, las metas y el plan que marca el equipo afectado.
  - `membership_expiring` → **Inicio**, donde está la tarjeta de membresía.
  - **Cualquier tipo desconocido** → la **bandeja de avisos**, para que un tipo nuevo del backend no pierda su aviso ni aterrice en una pantalla equivocada.
- **El toque se escucha solo en nativo.** `subscribePushTaps` carga `expo-notifications` con `import()` dinámico, se suscribe a las respuestas de notificación y, al arrancar, lee **una vez** la última respuesta —el toque que abrió la app— y la borra con `clearLastNotificationResponse()` para no repetir la navegación en un remontaje. En web no se registra nada, igual que el token.
- **El aviso se marca leído al abrir su pantalla, salvo cuando el destino es la bandeja.** El toque llama a `POST /member/notifications/{id}/read` (idempotente) y refresca la insignia; si falla, se ignora porque la bandeja vuelve a contar al abrirse y sigue siendo la fuente de verdad. Si el destino es la propia bandeja, el aviso conserva su punto de no leído hasta que el socio lo toca allí.
- **Un toque sin sesión espera al acceso.** Si el push llega antes de restaurar la sesión o con la sesión cerrada, la app guarda el destino en memoria y lo abre al terminar la restauración o el inicio de sesión. Cerrar sesión, expirar o cambiar de cuenta descarta ese pendiente para que el siguiente socio no herede la pantalla del anterior. Si la app se cierra antes de entrar, el toque se pierde pero el aviso sigue en la bandeja.
- **`ref_id` no se usa para abrir el detalle.** Los avisos de entrenamiento, meta y equipo apuntan a identificadores de dominio que no tienen pantalla propia en la app (el detalle de rutina se abre por asignación, no por entrenamiento), así que el destino es el resumen de Rutinas. Tampoco hay enlace al ítem concreto de una factura, clase o cita: esas pantallas abren la lista.
- **La bandeja usa el mismo mapa.** Tocar un aviso de rutina o equipo abre Rutinas y uno de membresía abre Inicio; antes solo cambiaban el estado de lectura. El texto de ayuda y los `accessibilityLabel` («Abrir rutinas: …», «Abrir el inicio: …») salen del mismo destino.

## Consecuencias y límites

- **El mapa es de código, no de configuración.** Un tipo nuevo sin entrada en `notificationRouting.ts` abre la bandeja; cambiarlo exige publicar una versión de la app, no tocar el backend.
- **Sin build nativo no se ejerce.** La vista previa web no recibe respuestas de notificación y sin `extra.eas.projectId` no hay push; el toque real solo se prueba con un build de EAS en un dispositivo físico.
- **El push es at-least-once.** Dos entregas del mismo aviso pueden abrir la misma pantalla dos veces; es inofensivo porque la navegación y el marcado de lectura son idempotentes.
- **La lectura es best-effort.** Si marcar leído falla por red, el aviso queda sin leer y la insignia se corrige al abrir la bandeja; la navegación no espera la respuesta del servidor.
- **No hay enlaces profundos a datos.** No se puede abrir una factura, una clase o una cita concreta desde el push, solo la pantalla que las contiene; hacerlo exigiría rutas con estado y un identificador de origen estable.
- **El pendiente no sobrevive a la app cerrada.** Un toque atendido sin sesión se pierde si el proceso muere antes de entrar; el aviso sigue en la bandeja.
- **Solo cubre al socio.** La campana del personal no navega desde su correo ni desde el panel; no se tocó.

## Referencias

- `mobile/src/notificationRouting.ts`
- `mobile/src/push.ts` (`subscribePushTaps`, `PushTap`)
- `mobile/App.tsx` (suscripción, pendiente de sesión y destino)
- `mobile/src/screens/NotificationsScreen.tsx`
- `backend/src/app/modules/notifications/push.py` (payload con `notification_id`, `kind` y `ref_id`)
- `docs/05-decisiones/ADR-016-notificaciones-del-socio.md`, `ADR-052-push-del-socio-desde-la-app.md`, `ADR-059-preferencias-del-socio-por-tipo-de-aviso.md`
