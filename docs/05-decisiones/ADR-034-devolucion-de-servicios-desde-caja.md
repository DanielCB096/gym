# ADR-034: Devolución de servicios desde la caja con permiso de gerencia

- Fecha: 2026-10-29
- Estado: aceptada

## Contexto

ADR-033 cobró el extra de las clases premium como una venta de servicio ligada a la reserva y decidió que el reembolso solo se registrara desde el flujo de clases: marcar `no_show`, cancelar la reserva o cancelar la clase. La pestaña de devoluciones del POS rechaza las líneas de servicio con «La línea es un servicio: su reembolso se registra desde la reserva de la clase».

En la práctica el cobro se equivoca en la caja, no en la reserva: se marca la asistencia del socio equivocado, se cobra dos veces al mismo o se cobra una clase que ya estaba incluida. Corregirlo desde la reserva obliga a deshacer una asistencia que sí ocurrió (dejando al socio como inasistente) o a tocar directamente la base. Hacía falta una devolución del dinero **sin tocar la asistencia**, y el sitio natural es el historial de ventas del punto de venta, donde la venta ya aparece con su folio, socio y forma de pago.

No se podía reutilizar la devolución por cantidad (`POST /admin/sales/{id}/returns`): su contrato es devolver unidades de un producto con reingreso o merma, exige `sale_item_id` y cantidades, y su permiso (`sales.manage`) lo tiene recepción; reembolsar dinero es una decisión de supervisión.

## Decisión

- **Endpoint propio**: `POST /admin/sales/{sale_id}/service-refund` con cuerpo `{"reason": "..."}` (1 a 200 caracteres). Responde `201` con la devolución creada, `404` si la venta no existe, `409` si ya estaba reembolsada o si un reembolso en efectivo no tiene turno abierto, y `422` si el motivo viene vacío o la venta no es de servicio. La devolución se registra con el servicio `refund_service_sale` de ADR-033, sin lógica duplicada.
- **Solo la registra un supervisor**: permiso nuevo `sales.service_refund`, otorgado a dueño y gerente. Recepción conserva `sales.read`/`sales.manage` para vender y devolver productos, pero no puede devolver dinero de una clase; el instructor tampoco. La migración `20261029_0050_service_refund_permission.py` crea el permiso y las concesiones de forma idempotente, y `preview_patch.py` lo siembra en la vista previa.
- **La reserva no se toca.** La devolución no cambia el estado de la reserva: quien asistió sigue `attended` y el roster muestra «Asistió · reembolsado». Separar el dinero de la asistencia es justamente el motivo del incremento; si además la clase no debió marcarse, el personal la corrige con «No asistió», que no vuelve a reembolsar porque la venta ya está `refunded`.
- **La devolución es total y sin stock.** Se devuelve el importe completo de la venta con una línea `disposition="write_off"` y `product_id=NULL`; no hay mercancía que reingresar ni cantidad que capturar. La venta pasa a `refunded`, igual que en el flujo de la reserva.
- **El turno la paga como cualquier devolución.** Un reembolso en efectivo exige turno abierto y queda ligado a él (baja el efectivo esperado); tarjeta, transferencia y cuenta se registran sin turno y la cuenta se abona si la venta fue a cuenta. El endpoint cierra la transacción porque el flujo de clases comparte la suya con la reserva y `refund_service_sale` nunca confirma solo.
- **Doble clic y doble caja no pagan dos veces.** `refund_service_sale` bloquea la fila de la venta con `SELECT ... FOR UPDATE` y devuelve `None` cuando ya está reembolsada, así que la segunda petición —del mismo operador o de otra caja— recibe `409` y no crea otra devolución. La garantía es de PostgreSQL; en SQLite el bloqueo es no-op, así que la prueba de la carrera es opt-in. Verificado el 2026-10-29 contra PostgreSQL 16.4 portátil: con el bloqueo las dos peticiones simultáneas pagan una sola devolución y, al quitarlo, la misma prueba falla con dos.
- **El panel la ofrece solo donde corresponde.** El historial de ventas muestra «Reembolsar» en una venta de servicio completada con `sales.service_refund`, «Devolver» en una venta de producto y «—» cuando no hay nada que devolver; la columna de productos dice «Servicio de clase» en una venta que solo tiene servicios. El modal pide el motivo, avisa que la reserva conserva su estado y que un reembolso en efectivo exige turno abierto.

## Consecuencias y límites

- **La devolución no está atribuida a la reserva.** El rastro queda en `sale_returns` (motivo, actor, turno, importe) y en la venta `refunded`; la reserva solo refleja `charge_status = refunded` porque consulta su venta. No se escribe nada en la clase ni se avisa al socio.
- **Un reembolso parcial no existe.** Se devuelve el total de la venta de servicio; una venta mixta (producto + servicio) no es posible hoy porque el cargo de clase crea una venta de una sola línea, pero `refund_service_sale` asumiría que sí lo es: devolvería solo las líneas de servicio y anotaría el total de la venta como devuelto. Si en el futuro se venden servicios junto con productos, hay que decidir el importe antes de habilitarlo.
- **El permiso lo tienen solo dueño y gerente.** Si el club quiere que recepción reembolse clases, basta con concederlo desde la matriz de permisos; no hay regla por importe ni segunda firma.
- **Marcar de nuevo la asistencia vuelve a cobrar.** Una reserva con el cargo reembolsado desde caja no ofrece «Asistió» en el roster, así que la corrección en sentido contrario exige «No asistió» y volver a marcar; ese camino sí crea un cargo nuevo, que es lo deseable si el socio vuelve a asistir, pero conviene tenerlo presente al corregir errores.
- **La venta de servicio sigue sin impuestos ni clave de producto propias** (ADR-033): si se facturó antes de reembolsar, la nota de crédito se emite por el flujo fiscal de siempre.

## Referencias

- `backend/src/app/main.py` (`RefundServiceSaleRequest`, `refund_service_sale_endpoint`)
- `backend/src/app/modules/inventory/service.py` (`refund_service_sale`, `ServiceAlreadyRefunded`)
- `backend/src/app/modules/inventory/__init__.py`
- `backend/src/app/modules/identity/service.py` (`sales.service_refund` en `DEFAULT_ROLE_PERMISSIONS` y `DEFAULT_PERMISSIONS`)
- `backend/alembic/versions/20261029_0050_service_refund_permission.py`, `backend/preview_patch.py`
- `backend/tests/test_class_premium_charge.py`, `backend/tests/test_service_refund_postgres.py`
- `web/src/app/page.tsx` (`ServiceRefundModal`), `web/src/app/api/admin/sales/[saleId]/service-refund/route.ts`
- ADR-033
