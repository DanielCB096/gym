# Facturación y factura global

## Resumen

Este proceso atiende la solicitud de CFDI de una venta o pago, la preparación de la factura global para operaciones elegibles de público en general y la emisión de complementos de pago para facturas PPD. El pago, la solicitud fiscal y el timbrado son eventos separados y cada uno conserva su estado. Los criterios fiscales y calendarios deben configurarse con el contador y el PAC antes de producción.

## Implementación actual

Desde el 2026-10-24 el flujo **individual** de los pasos 1–6 y la **factura global** existen en backend y panel; desde el 2026-10-25 también existen las **notas de crédito (CFDI de egreso)** sobre facturas de ingreso timbradas, los **complementos de pago PPD** y la **conciliación bancaria** como bandeja propia, documentada en [conciliacion-bancaria.md](conciliacion-bancaria.md). El XML y el PDF se descargan de forma autenticada (`GET /admin/billing/invoices/{id}/xml` y `/pdf`); los del complemento usan `GET /admin/billing/payment-complements/{id}/xml` y `/pdf`. El PDF se genera al momento y solo existe para comprobantes timbrados o cancelados. El envío al cliente es explícito: `POST /admin/billing/invoices/{id}/send` manda el PDF y el XML al correo del receptor o a uno indicado por el operador y deja constancia en la bitácora; no es automático ni se ofrece para la global, cuyo receptor no tiene buzón. El timbrado es **simulado** en vista previa (sin UUID ni validez fiscal) porque el adaptador de un PAC real todavía no existe; en producción el timbrado responde `503` hasta integrarlo. El motivo de cancelación se registra con las claves del SAT (01–04) y, para el 01, el UUID sustituto, pero la aceptación final del receptor se valida con el PAC real cuando exista.

## Facturación individual

1. La venta o pago queda confirmado y disponible como operación de origen.
2. El cliente solicita factura y captura o confirma sus datos fiscales.
3. El sistema valida campos requeridos y revisa que la operación no tenga ya un CFDI vigente incompatible.
4. Un usuario autorizado revisa la solicitud y la envía al PAC con una clave idempotente.
5. El sistema registra el resultado. Si se confirma el timbrado, conserva UUID, XML, referencia al origen y genera la representación impresa (PDF) cuando se solicita; la factura queda disponible para descarga.
6. El cliente recibe acceso a sus archivos: descarga autenticada del XML y del PDF o envío por correo de ambos a petición de un usuario con `billing.request`. Si ocurre un error o timeout, la solicitud queda visible para consulta y reintento seguro; no se crea otra emisión a ciegas.

## Factura global

1. El usuario elige un mes ya cerrado en la pestaña **Factura global** de Facturación. Un mes en curso no se puede emitir: las ventas posteriores quedarían fuera y bloquearían la global regular.
2. El sistema calcula la elegibilidad sobre las ventas del mes local: solo completadas, sin devolución, con total positivo, con método distinto de `account`, sin socio y que no estén facturadas individualmente ni incluidas en otra global viva. La pantalla muestra las ventas incluidas, los conteos por motivo de exclusión y los totales con IVA.
3. El contador revisa periodo, ventas, exclusiones, subtotal, IVA y total; el receptor es fijo `XAXX010101000` / `PUBLICO EN GENERAL` (régimen `616`, uso `S01`, forma de pago `99`).
4. Un usuario con `billing.manage` solicita la emisión (`POST /admin/billing/global-invoices`) con una clave de idempotencia; el backend **recalcula** la elegibilidad y rechaza el periodo si está abierto, ya tiene una global viva o no quedan ventas. Puede timbrar en el mismo paso o después.
5. El CFDI agregado guarda el periodo, un concepto con la cantidad de operaciones, el desglose de IVA, `InformacionGlobal Periodicidad="03" Meses="MM" Año="YYYY"` y una fila por venta en `global_invoice_sales`. El XML y el PDF quedan disponibles para descarga autenticada.
6. Si una operación incluida necesita factura individual, primero se cancela la global con motivo del SAT; el periodo y sus ventas quedan libres, se emite la global sustituta y el lote anterior se conserva en el historial. Una factura individual de una venta incluida en una global viva responde `409`.

## Cancelación

1. Un usuario con `billing.manage` inicia la solicitud sobre una factura **timbrada** y registra el motivo del SAT (`01`–`04`), el UUID sustituto cuando el motivo es `01` y una nota opcional.
2. El sistema envía la solicitud al PAC y registra cada respuesta o requisito de aceptación. En vista previa la cancelación se registra sobre la simulación.
3. Se actualiza el estado solo con el resultado confirmado; el CFDI original permanece en el historial con folio, motivo, actor y fecha.
4. Una factura de ingreso con **notas de crédito timbradas vigentes** no se cancela: primero deben cancelarse las notas. La factura global se cancela para liberar el mes y permitir la sustitución.

## Nota de crédito (CFDI de egreso)

1. El operador abre una factura de ingreso **timbrada** (venta o cobro de membresía) y elige **Notas de crédito**. La factura global y otra nota de crédito no admiten notas.
2. Captura el importe a acreditar (parcial o total, hasta el saldo disponible), el motivo —devolución, descuento, corrección de importe u otro— y una nota opcional de hasta 300 caracteres.
3. El sistema valida el saldo contra las notas **timbradas y no canceladas** (una nota pendiente o fallida no lo consume), copia el receptor y la tasa de IVA de la factura original, congela el desglose y crea una nota en `requested` con su folio y clave de idempotencia.
4. Un usuario con `billing.manage` timbra la nota; al hacerlo se bloquea la factura original y se revalida que siga timbrada y que el saldo alcance. Si la validación falla, la nota queda `failed` con el evento y el motivo, sin tocar el saldo.
5. La nota timbrada conserva la relación `TipoRelacion="01"` con el UUID de la factura original (o el vínculo interno si la original es simulada), se rotula como CFDI de egreso en el PDF y el correo, y se consulta, descarga y envía como cualquier comprobante.
6. Si la nota se cancela con motivo del SAT, su importe vuelve al saldo acreditable de la factura; la nota y sus eventos permanecen en el historial. La factura original puede cancelarse cuando ya no tenga notas vigentes.

## Complemento de pago (PPD)

1. La factura se emite desde el alta con método **PPD**; el sistema fija `FormaPago="99"` y deja el total como saldo pendiente. El método PUE sigue siendo el flujo normal de pago inmediato.
2. Cuando el cliente paga una parcialidad o la totalidad, un usuario con `billing.manage` abre el detalle de la factura y captura el importe, la fecha real del pago y la forma en que se pagó (distinta de 99). El importe debe ser mayor que cero y no exceder el saldo; la fecha no puede ser futura ni anterior a la emisión.
3. El alta crea el complemento en `requested` con folio de la serie `P`, número de parcialidad preliminar y una clave de idempotencia. La solicitud **no** descuenta saldo: dos operadores pueden registrar parcialidades antes de timbrar y el saldo solo cambia cuando el PAC confirma.
4. `POST /admin/billing/payment-complements/{id}/stamp` bloquea la factura, revalida que siga timbrada y PPD, recalcula la parcialidad y los saldos con lo ya timbrado, y envía el CFDI tipo P al PAC. Si el importe ya no cabe en el saldo, el complemento queda `failed` con el evento y el saldo disponible; si el PAC falla, también queda `failed` para reintento.
5. El comprobante timbrado se relaciona con la factura original (`TipoRelacion="07"` e `IdDocumento` cuando hay UUID), declara en `pago20` la parcialidad, el saldo anterior, el importe pagado y el insoluto, y desglosa el IVA del pago. En simulación, sin UUID de la factura, la relación no se escribe y el XML lleva el aviso visible; el vínculo interno se conserva.
6. El XML y el PDF se descargan solo si el complemento está timbrado o cancelado. La representación impresa muestra la factura relacionada, la parcialidad, los saldos y la marca de simulación o cancelación.
7. Cancelar un complemento exige motivo del SAT (`01`–`04`), UUID sustituto para el `01` y una nota opcional; solo se permite la **última parcialidad vigente**. Al cancelarlo, su importe vuelve al saldo de la factura. Una factura con complementos timbrados vigentes no se cancela hasta cancelarlos, y una factura PPD no admite notas de crédito en esta versión.

## Conciliación bancaria (proceso separado)

La conciliación bancaria tiene su propio flujo en [conciliacion-bancaria.md](conciliacion-bancaria.md). En resumen:

1. Se da de alta la cuenta (nombre, banco, últimos cuatro dígitos y moneda) y se importa el estado de cuenta en **CSV**; la importación es idempotente y admite hasta 500 líneas.
2. La bandeja propone coincidencias con cobros, ventas, abonos y devoluciones **electrónicas** a ±7 días y 2% de tolerancia, con búsqueda manual a ±60 días. El efectivo nunca es candidato.
3. Un usuario con `finance.manage` confirma la operación (conciliado si el importe coincide; con diferencia y nota si no), desvincula con motivo o marca la línea para revisión. Cada decisión queda en la bitácora de la línea.
4. Una línea del banco solo puede apuntar a una operación interna y nunca crea ni ajusta dinero; las diferencias se documentan para revisión contable.

## Reglas clave

- No se elimina un CFDI emitido ni se considera cancelado hasta confirmar el estado final.
- Un pago exitoso no equivale a un CFDI timbrado.
- Los reintentos deben consultar el resultado anterior o usar idempotencia para evitar duplicados.
- Cada comprobante debe poder rastrearse hasta su venta, pago o lote de factura global.
- La factura global no debe duplicar operaciones facturadas individualmente.
- Solo puede existir una factura global viva por mes; el índice parcial libera el periodo al cancelarla.
- Una venta incluida en una global viva no se factura individualmente; la corrección exige cancelar la global y emitir la sustitución.
- La suma de notas de crédito **timbradas y no canceladas** nunca excede el total de la factura; el saldo se recalcula al timbrar y al cancelar una nota.
- Una factura con notas de crédito timbradas vigentes no se cancela hasta cancelar las notas.
- Una factura PPD nace con forma de pago 99 y saldo igual a su total; solo los complementos **timbrados** reducen el saldo, y la suma de complementos timbrados nunca excede el total.
- Una solicitud de complemento pendiente o fallida no consume saldo; el timbrado revalida el importe con la factura bloqueada y recalcula la parcialidad y los saldos.
- Solo se cancela la última parcialidad timbrada vigente; cancelarla libera su importe. Una factura con complementos vigentes no se cancela hasta cancelarlos.
- El complemento documenta fiscalmente un pago declarado por el operador: no crea ni modifica el cobro original, la caja o la conciliación. En esta versión una factura PPD no acepta notas de crédito.
- Los motivos, usuarios, fechas y respuestas del PAC quedan en la bitácora.
- Las reglas fiscales específicas se validan con el contador y el PAC; este proceso no reemplaza asesoría contable.

## Excepciones

- **Timeout del PAC:** conservar la solicitud como resultado incierto, consultar estado y evitar una nueva emisión hasta resolverla.
- **Datos fiscales incompletos:** dejar la solicitud pendiente y pedir corrección al cliente.
- **Pago revertido o devolución posterior:** enviar a revisión para definir el comprobante fiscal relacionado, sin borrar el original.
- **Operación incluida en factura global solicitada individualmente:** detener el ajuste automático y escalar a contador.
- **Mes en curso o ya facturado:** `POST /admin/billing/global-invoices` responde `409`; esperar el cierre o cancelar la global viva antes de emitir la sustitución.
- **Periodo sin ventas elegibles:** no se emite un comprobante en cero; la revisión muestra los conteos de exclusión para explicar el motivo.
- **Cancelación pendiente o rechazada:** mantener el estado informado por PAC y asignar seguimiento.
- **Fallo al enviar el CFDI por correo:** el envío es un paso separado del timbrado. Si falta configuración SMTP responde `503` y si el transporte falla `502`; la factura sigue timbrada y puede descargarse o reenviarse, y el intento fallido queda en la bitácora. No se marca como entregado ni se reintenta solo.
- **Correo del receptor ausente o inválido:** la factura ya está timbrada; se pide un destinatario válido o se entrega por descarga. El error no revierte el comprobante.
- **Nota de crédito que excede el saldo:** el alta responde `422` y no crea la nota. Si el saldo cambió entre el alta y el timbrado (otra nota se timbró antes), el timbrado deja la nota `failed` con `credit_balance_exceeded` y el importe disponible; se corrige emitiendo otra nota por el saldo vigente.
- **Nota sobre una factura global o sobre otra nota:** responde `409`; la global se corrige cancelándola y sustituyéndola, y una nota no se ajusta con otra nota.
- **Cancelación de la factura con notas vigentes:** responde `409`; primero se cancelan las notas (con motivo del SAT) y después la factura.
- **Nota cuya factura original ya no está timbrada:** el timbrado se rechaza y la nota queda `failed`; la nota no produce un egreso sin comprobante de ingreso vigente.
- **Nota de crédito sobre una factura PPD:** responde `409` en esta versión; se corrigen primero los complementos, luego se cancela la factura y se emite una sustitución.
- **Complemento que excede el saldo o con fecha inválida:** el alta responde `422` y no crea la parcialidad. Si el saldo bajó entre el alta y el timbrado, el complemento queda `failed` con `payment_balance_exceeded` y el saldo disponible, y se corrige con otro complemento por el importe vigente.
- **Timeout o respuesta incierta del PAC al timbrar un complemento:** el complemento queda en el estado registrado, sin liberar ni consumir saldo; se consulta con el PAC y se reintenta el timbrado del mismo complemento, sin registrar un pago nuevo a ciegas.
- **Cancelación de una parcialidad anterior o de un complemento no timbrado:** responde `409`; solo se cancela la última parcialidad vigente. Para corregir una anterior deben cancelarse las posteriores en orden.
- **Cancelación de la factura PPD con complementos timbrados:** responde `409`; primero se cancelan los complementos desde la última parcialidad y después la factura.
- **Factura PPD simulada (sin UUID):** el complemento se timbra en simulación, omite `IdDocumento` y deja el aviso visible; el vínculo interno con la factura se conserva en el sistema, pero no tiene validez fiscal.

## Responsables

- Recepción captura solicitudes y apoya al cliente.
- Contador revisa casos fiscales, factura global, cancelaciones y conciliación.
- Gerente supervisa pendientes operativos.
- El sistema aplica permisos, registra eventos y entrega archivos de forma controlada.

## KPIs

- porcentaje de solicitudes timbradas correctamente
- tiempo medio de timbrado desde que la solicitud está completa
- solicitudes con error o resultado incierto pendientes de resolución
- operaciones excluidas o pendientes en el lote global
- notas de crédito emitidas, canceladas y saldo acreditable pendiente por factura
- complementos PPD solicitados, timbrados, fallidos y cancelados, y saldo PPD pendiente por antigüedad
