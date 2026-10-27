# ADR-012: Pagos y estado de cuenta de solo lectura en la app del socio

- Fecha: 2026-10-27
- Estado: propuesta inicial

## Contexto

Los pagos de membresía viven en `payments` (ligados a una membresía y a su plan, con periodo, método, turno de caja y cobrador) y la cuenta de la tienda en el estado de cuenta del módulo de inventario, que combina las ventas a cuenta, las devoluciones abonadas y los abonos en `member_account_payments`. El panel ya expone ambos con permisos del personal (`members.read`, `sales.read`) y con datos internos como el turno, la caja, el cobrador, el límite de crédito y la antigüedad de saldos.

El socio ya tiene sesión propia (ADR-009) y app móvil con perfil, reservas de clases (ADR-010) y rutinas de solo lectura (ADR-011). Desde el inicio de sesión ve su saldo y su membresía, pero no puede consultar qué pagó ni qué movimientos generaron ese saldo sin preguntar en recepción. Exponer las rutas del panel tal cual le mostraría datos del personal y de la operación que no le corresponden.

## Decisión

- La app **reutiliza los datos existentes**. No hay tablas, columnas ni migración nuevas: los pagos de membresía ya están en `payments` y el estado de cuenta se calcula con `member_account_statement` del módulo de inventario.
- `backend/src/app/modules/portal/payments.py` es una capa delgada **de solo lectura** con alcance de socio. Las reglas del saldo siguen en `app.modules.inventory.service`; la capa de portal solo decide **qué parte de esos datos ve el socio en su propio nombre**.
- Dos rutas, ambas con Bearer de socio:
  - `GET /member/payments`: pagos de membresía propios, más recientes primero (`paid_at`, luego `id` como desempate), paginados (`page ≥ 1`, `page_size` 1–50, por defecto 20). Devuelve importe, moneda, método, fecha, periodo cubierto, plan y nota, más el total de pagos y el importe pagado acumulado (`total_paid_cents`) sobre **todos** los pagos del socio, no solo la página.
  - `GET /member/account`: resumen del estado de cuenta (cargos, abonos, pagos, saldo, conteos, último movimiento y cargo más antiguo, fecha de corte) y hasta **100 movimientos** con su saldo acumulado después de cada uno. `entries_total` informa cuántos existen para poder avisar de la truncación.
- **Orden de los movimientos**: el servicio de inventario calcula el saldo cronológicamente y luego invierte la lista, así que la capa de portal toma los primeros `MAX_MEMBER_ACCOUNT_ENTRIES` elementos —los más recientes— sin recalcular nada.
- **Aislamiento**: el `member_id` sale siempre de la sesión autenticada; ninguna ruta acepta un identificador de socio. Un socio desconocido responde `404`. Un token de personal recibe `401` en `/member/*` y uno de socio en `/admin/*`.
- **Datos del personal que no se exponen**: el cobrador, el turno de caja, el identificador de la membresía, el límite de crédito, la antigüedad de saldos y el desglose por tramos se quedan en el panel. La app solo muestra el importe, el método, el plan, el periodo y las notas del movimiento.
- La app muestra un aviso cuando la sesión expira y vuelve al acceso, igual que el resto del portal.

## Consecuencias y límites

- El socio consulta, pero **no paga ni descarga facturas** desde la app. El cobro (efectivo, tarjeta declarada o transferencia) y la facturación siguen en recepción y en el panel.
- No se consultan pagos de una membresía anterior ni se agrupan por plan o periodo; la lista es plana y paginada. El primer pago de membresía se busca con la primera página.
- El estado de cuenta no distingue el origen de cada cargo o abono más allá de la referencia y el método que ya guarda el ledger; la app no muestra el detalle de la venta asociada.
- El saldo puede ser negativo (saldo a favor); la app lo etiqueta y no permite liquidarlo desde ahí.
- `total_paid_cents` suma todos los pagos del socio, incluidas membresías canceladas o antiguas; si en el futuro se quiere separar por vigencia habrá que agregar un filtro y documentarlo.
- Antes de producción: decidir si el socio podrá pagar en línea (pasarela), descargar sus facturas y consultar la antigüedad de su saldo, y definir la retención de los movimientos y notas en la app.

## Referencias

- `backend/src/app/modules/portal/payments.py`
- `backend/src/app/modules/inventory/service.py` (`member_account_statement`)
- `backend/src/app/modules/memberships/models.py` (`Payment`, `Membership`, `Plan`)
- `backend/src/app/main.py` (`/member/payments`, `/member/account`)
- `backend/tests/test_member_payments_api.py`
- `mobile/src/screens/PaymentsScreen.tsx`
- ADR-009 (autenticación del socio)
- ADR-010 (reservas de clases desde la app)
- ADR-011 (rutinas y progreso de solo lectura)
