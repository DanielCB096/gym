# ADR-067: Resaltar el ítem del aviso al abrir su pantalla

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Extiende ADR-060 (navegación al tocar la notificación push) y ADR-016 (bandeja de avisos del socio)

## Contexto

ADR-060 hizo que tocar un aviso —desde la bandeja o desde su push— abra la pantalla de su tipo, pero dejó el `ref_id` sin usar a propósito: se llegaba a la lista y el socio tenía que buscar por su cuenta la factura, la clase, la cita o la meta de la que le hablaban. En pantallas cortas eso es tolerable; en Facturas, en la cartelera de catorce días o en el historial de fisioterapia, el aviso puede señalar un renglón que queda fuera de vista o entre varios parecidos.

El backend ya guarda en `ref_id` el identificador del origen de cada aviso (factura, reserva, clase, cita o meta) como pista de navegación sin FK, y el push ya lo entrega en su payload. Faltaba que la app lo aprovechara.

## Decisión

- **Un mapa de `kind` a renglón, separado del mapa de pantallas.** `mobile/src/notificationRouting.ts` estrena `notificationFocus(kind, refId)` y su auxiliar `notificationRefTarget(kind)`. Un aviso solo enfoca un ítem cuando su `ref_id` apunta a una fila que la pantalla de destino realmente lista:
  - `invoice_*` → la factura.
  - `class_reserved`, `class_waitlist_promoted` y `class_reminder` → la reserva.
  - `class_cancelled` y `class_rescheduled` → la sesión de clase.
  - `physio_*` (los cuatro) → la cita de fisioterapia.
  - `goal_*` → la meta.
  - **Sin foco**: `workout_reviewed`, `equipment_out_of_service` y `membership_expiring`. El entrenamiento y el equipo no tienen renglón propio en la app y la membresía vive en el inicio, así que esos avisos siguen abriendo su sección sin resaltar nada. Un `kind` desconocido tampoco enfoca.
- **El foco viaja desde el aviso, no desde la pantalla.** `App.tsx` guarda un `NotificationFocus` en memoria al tocar un aviso de la bandeja o un push; el push ahora lee `ref_id` del payload (`PushTap.refId`) y la bandeja entrega `kind` y `ref_id` al mismo manejador. Cada pantalla recibe `focusRefId` ya resuelto para su destino: Facturas, Clases, Fisioterapia y Rutinas.
- **El foco se limpia al entrar por otro camino.** Abrir una sección desde el inicio, volver atrás, abrir el detalle de una rutina, solicitar una factura, cerrar sesión o expirar borra el foco, de modo que una pantalla reutilizada no siga resaltando el renglón de un aviso anterior.
- **Aviso visible y renglón resaltado.** Cada pantalla muestra el aviso «Desde tu aviso» (fondo informativo, `accessibilityRole="alert"` y `accessibilityLiveRegion="polite"`) y marca el renglón encontrado con el color de acento: borde completo en la tarjeta de factura y de clase, borde izquierdo en la fila del historial de fisioterapia y en la meta. El texto nombra lo resaltado —el folio, el título y la hora de la clase, el servicio y la hora de la cita, la medida de la meta— para que el socio sepa qué está viendo aunque tenga que desplazarse.
- **Cuando el ítem ya no está, el aviso lo dice.** Si la factura no está en la página, la clase ya no está en la cartelera, la cita no aparece en fisioterapia o la meta ya no está en el progreso, la pantalla mantiene el aviso con un texto que lo explica e invita a deslizar para actualizar, y no resalta nada. El aviso sigue en la bandeja como historial, igual que antes.
- **Sin cambios de backend.** El foco se calcula en la app con los datos que ya devuelven `/member/invoices`, `/member/classes`, `/member/physio` y el progreso de rutinas; no hay ruta ni migración nueva.

## Consecuencias y límites

- **El resaltado depende de que el renglón esté cargado.** Facturas pagina de veinte en veinte, la cartelera cubre los próximos catorce días y fisioterapia muestra la próxima cita y el historial que devuelve el servidor; un aviso viejo puede caer en el texto de reserva. Todavía no hay salto de página automático ni carga dirigida por identificador.
- **El foco es visual y de una sola pantalla.** No mueve el scroll hasta el renglón resaltado, no filtra la lista y no persiste si el socio recarga la app: el aviso sigue en la bandeja y puede volver a abrirse.
- **`ref_id` sigue siendo una pista sin FK.** Si el origen se borra o el aviso se guardó con otro identificador, la app resalta lo que encuentre o cae en el texto de reserva; nunca rompe la pantalla.
- **El push reutiliza el mismo camino.** El payload ya llevaba `ref_id`; la app ahora lo lee y lo aplica igual que la bandeja en nativo. La vista previa web no recibe respuestas de notificación, así que el camino del push se apoya en el mismo foco que sí se puede probar en web.
- **No cubre al personal.** La campana del panel no enlaza al ticket, al entrenamiento ni al kiosco; queda como pendiente.

## Referencias

- `mobile/src/notificationRouting.ts` (`notificationRefTarget`, `notificationFocus`)
- `mobile/src/push.ts` (`PushTap.refId`)
- `mobile/App.tsx` (`focus`, `openSection`, `handleOpenDestination`, `focusRefFor`)
- `mobile/src/screens/NotificationsScreen.tsx` (`onOpenDestination`)
- `mobile/src/screens/InvoicesScreen.tsx`
- `mobile/src/screens/ClassesScreen.tsx`
- `mobile/src/screens/PhysioScreen.tsx`
- `mobile/src/screens/RoutinesScreen.tsx`
- `backend/src/app/modules/notifications/push.py` (payload con `ref_id`)
- `docs/05-decisiones/ADR-016-notificaciones-del-socio.md`, `ADR-060-navegacion-al-tocar-la-notificacion-push.md`
