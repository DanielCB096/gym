# Facturación y factura global

## Resumen

Este proceso atiende la solicitud de CFDI de una venta o pago y la preparación de la factura global para operaciones elegibles de público en general. El pago, la solicitud fiscal y el timbrado son eventos separados y cada uno conserva su estado. Los criterios fiscales y calendarios deben configurarse con el contador y el PAC antes de producción.

## Implementación actual

Desde el 2026-10-24 el flujo **individual** de los pasos 1–6 y la **factura global** existen en backend y panel. El XML y el PDF se descargan de forma autenticada (`GET /admin/billing/invoices/{id}/xml` y `/pdf`); el PDF se genera al momento y solo existe para facturas timbradas o canceladas. El envío al cliente es explícito: `POST /admin/billing/invoices/{id}/send` manda el PDF y el XML al correo del receptor o a uno indicado por el operador y deja constancia en la bitácora; no es automático ni se ofrece para la global, cuyo receptor no tiene buzón. El timbrado es **simulado** en vista previa (sin UUID ni validez fiscal) porque el adaptador de un PAC real todavía no existe; en producción el timbrado responde `503` hasta integrarlo. El motivo de cancelación se registra con las claves del SAT (01–04) y, para el 01, el UUID sustituto, pero la aceptación final del receptor se valida con el PAC real cuando exista. Las notas de crédito descritas abajo siguen en diseño.

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

## Cancelación o ajuste

1. Un usuario con permiso inicia la solicitud y registra el motivo y el comprobante relacionado.
2. El sistema envía la solicitud al PAC y registra cada respuesta o requisito de aceptación.
3. Se actualiza el estado solo con el resultado confirmado; el CFDI original permanece en el historial.
4. Si corresponde nota de crédito u otro comprobante relacionado, se conserva el vínculo con la operación original.

## Reglas clave

- No se elimina un CFDI emitido ni se considera cancelado hasta confirmar el estado final.
- Un pago exitoso no equivale a un CFDI timbrado.
- Los reintentos deben consultar el resultado anterior o usar idempotencia para evitar duplicados.
- Cada comprobante debe poder rastrearse hasta su venta, pago o lote de factura global.
- La factura global no debe duplicar operaciones facturadas individualmente.
- Solo puede existir una factura global viva por mes; el índice parcial libera el periodo al cancelarla.
- Una venta incluida en una global viva no se factura individualmente; la corrección exige cancelar la global y emitir la sustitución.
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
