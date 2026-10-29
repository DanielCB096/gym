# ADR-033: Cobro de clases premium en la lista de asistencia

- Fecha: 2026-10-29
- Estado: aceptada

## Contexto

Una clase puede configurarse como `access_type=premium` con un `extra_price_cents`, pero desde el primer incremento de Clases ese precio solo se guardaba: marcar asistencia no generaba ningún cargo, reporte ni movimiento de caja. La app del socio incluso bloquea reservar clases premium («reserva en recepción») porque no existía forma de cobrarlas.

El club necesitaba decidir **cuándo** se cobra. Las opciones eran al reservar, al marcar asistencia o como paquete previo. La reserva no obliga a que el socio llegue (una inasistencia dejaría un cobro con reembolso inmediato, con más ruido que ingreso), y el kiosco no cobra. Marcar la asistencia es el momento en que recepción y el socio se ven cara a cara y ya está abierto el turno de caja.

El sistema de dinero ya existe: una venta (`sales` + `sale_items`) con turno de caja, cuentas de socio, devoluciones (`sale_returns`), reportes y facturación. La decisión es no crear un ledger paralelo para servicios.

## Decisión

- **El extra se cobra al marcar «Asistió».** `POST /admin/classes/reservations/{id}/attendance` con `attended=true` crea, si la clase es premium y el precio es mayor que cero, una venta con **una línea de servicio** por el monto del extra. La venta nace `completed`, con `origin="online"`, folio normal `V-…` y `sales.class_reservation_id` apuntando a la reserva. Sin precio o sin clase premium no se cobra nada y el flujo sigue igual.
- **La forma de pago se elige en recepción.** El marcado acepta `payment_method` (`cash`, `card`, `transfer`, `account`) y forma parte del request de asistencia. Si falta en una clase premium, la respuesta es `409` con «Selecciona la forma de pago para cobrar la clase premium»: no se marca asistencia sin cobrar. Como cualquier venta, el cargo exige un turno de caja abierto aunque sea con tarjeta, transferencia o cuenta del socio. La cuenta del socio verifica su crédito disponible como cualquier venta a cuenta.
- **La línea de servicio no es un producto.** `sale_items.product_id` y `sale_return_items.product_id` pasan a nullable; la línea de servicio usa `product_id=NULL`, `sku="CLASE"`, `product_name="Clase premium: <título>"`, cantidad 1, la ubicación por defecto y no genera movimientos de inventario. Así el cargo entra en el turno, en los reportes de ingresos (agrupado en la categoría «Servicios»), en las facturas de la venta y en la conciliación sin columnas ni tablas nuevas.
- **Nunca se cobra dos veces.** Si la reserva ya tiene una venta `completed`, volver a marcarla como asistida devuelve esa misma venta y no crea otra. Es la forma en que el personal corrige un marcado, no un segundo ingreso.
- **Se reembolsa al deshacer la asistencia o cancelar.** Marcar `attended → no_show`, cancelar una reserva ya cobrada y cancelar la clase completa (que cancela sus reservas vivas) reembolsan la venta con `refund_service_sale`: una devolución con una línea de servicio (`product_id=NULL`, `disposition="write_off"`, sin movimientos de inventario). La forma del reembolso sigue la de la venta, y una venta a cuenta se abona a la cuenta. Un reembolso en efectivo exige turno abierto, igual que cualquier devolución; tarjeta, transferencia y cuenta no. Un reembolso repetido no hace nada porque la venta ya está `refunded`.
- **Las devoluciones de producto no pueden tocar una línea de servicio.** `POST /admin/sales/{id}/returns` rechaza una línea con `product_id=NULL` y remite a la reserva: devolver un servicio por la pantalla de devoluciones del POS dejaría la reserva sin relación con su reembolso.
- **La lista de espera cobra al promover y asistir, no al entrar.** La promoción solo cambia el estado a `reserved`; el cargo pendiente se muestra en la lista (`charge_status=null`, «cobro pendiente») y se crea al marcar la asistencia. Cancelar antes de asistir no reembolsa nada porque nunca hubo venta.
- **La lista de la clase es la superficie del cobro.** El roster expone `charge_sale_id`, `charge_cents`, `charge_payment_method`, `charge_folio` y `charge_status` por reserva y muestra «pagado», «reembolsado» o «cobro pendiente» según el caso. En una clase premium el modal pide la forma de pago antes de marcar y permite corregir una asistencia con «No asistió», que reembolsa. Los avisos confirman importe, método y folio del cobro y el importe reembolsado.
- **La reserva desde la app del socio sigue bloqueada.** Cobrar desde la app exigiría pasarela y elección de método; hasta entonces el socio reserva premium en recepción, donde se cobra al asistir.

## Consecuencias y límites

- **El turno de caja cuenta la venta aunque luego se reembolse.** Los totales del turno dejaron de filtrar `sales.status = "completed"` al sumar ventas: filtrarlas borraba el ingreso y seguía restando el reembolso, así que un cancelado premium dejaba el efectivo esperado en negativo. Ahora el turno suma todas las ventas del periodo y resta las devoluciones, y el esperado cuadra con el cajón (probado con una venta cobrada y reembolsada dentro del mismo turno). El arreglo también corrige el caso ya existente de una venta de producto devuelta por completo.
- **No hay penalización por inasistencia.** Marcar `no_show` reembolsa la clase premium; si el club decide cobrar una penalización, será un cargo propio con sus reglas.
- **Una venta de servicio no se puede devolver desde el POS**, solo desde la reserva que la originó. Es deliberado: la reserva es la fuente de verdad del vínculo y del estado de asistencia.
- **El análisis por producto agrupa los servicios bajo «Servicios».** En el reporte de ingresos, `by_category` y `top_products` incluyen la categoría «Servicios» con `product_id=NULL`; no es un producto del catálogo ni valoriza inventario.
- **La facturación no cambia de contrato.** La venta de servicio es un origen facturable más; su línea se factura con la clave y unidad configuradas para el origen, como cualquier venta de mostrador.
- **Deshacer la asistencia es la única corrección desde el panel.** El roster permite `attended → no_show`; no hay botón para volver a `reserved` (el backend tampoco lo admite).

## Referencias

- `backend/src/app/modules/inventory/service.py` (`register_service_sale`, `refund_service_sale`, `service_sale_for_reservation`, `SERVICE_SKU`, `_cash_session_totals`)
- `backend/src/app/modules/classes/service.py` (`mark_attendance`, `cancel_reservation`, `cancel_class_session`, `_charge_premium_attendance`, `_refund_premium_charge`, `ClassChargeFailed`)
- `backend/src/app/modules/inventory/models.py` (`Sale.class_reservation_id`, `SaleItem.product_id`, `SaleReturnItem.product_id`)
- `backend/src/app/main.py` (`MarkAttendanceRequest.payment_method`, `ReservationResponse.charge_*`)
- `backend/src/app/modules/reports/service.py` (`SERVICE_CATEGORY`, `_product_totals`)
- `backend/alembic/versions/20261029_0049_class_premium_charge.py`
- `backend/tests/test_class_premium_charge.py`
- `web/src/app/page.tsx` (`ClassRosterModal`)
- `docs/02-modulos/clases-y-reservaciones.md`, `docs/02-modulos/punto-de-venta-e-inventario.md`
