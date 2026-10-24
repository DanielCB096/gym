# Facturación y factura global

## Resumen

Este proceso atiende la solicitud de CFDI de una venta o pago y la preparación de la factura global para operaciones elegibles de público en general. El pago, la solicitud fiscal y el timbrado son eventos separados y cada uno conserva su estado. Los criterios fiscales y calendarios deben configurarse con el contador y el PAC antes de producción.

## Implementación actual

Desde el 2026-10-23 el flujo **individual** de los pasos 1–6 existe en backend y panel, con una diferencia: el paso 5 **no** genera representación PDF y el paso 6 **no** envía archivos al cliente; el XML queda disponible para descarga autenticada (`GET /admin/billing/invoices/{id}/xml`) y la factura conserva su bitácora. El timbrado es **simulado** en vista previa (sin UUID ni validez fiscal) porque el adaptador de un PAC real todavía no existe; en producción el timbrado responde `503` hasta integrarlo. El motivo de cancelación se registra con las claves del SAT (01–04) y, para el 01, el UUID sustituto, pero la aceptación final del receptor se valida con el PAC real cuando exista. La **factura global** y las notas de crédito descritas abajo siguen en diseño.

## Facturación individual

1. La venta o pago queda confirmado y disponible como operación de origen.
2. El cliente solicita factura y captura o confirma sus datos fiscales.
3. El sistema valida campos requeridos y revisa que la operación no tenga ya un CFDI vigente incompatible.
4. Un usuario autorizado revisa la solicitud y la envía al PAC con una clave idempotente.
5. El sistema registra el resultado. Si se confirma el timbrado, conserva UUID, XML, representación PDF y referencia al origen.
6. El cliente recibe acceso a sus archivos. Si ocurre un error o timeout, la solicitud queda visible para consulta y reintento seguro; no se crea otra emisión a ciegas.

## Factura global

1. Al cierre del periodo configurado, se identifican operaciones de público en general elegibles conforme a la política fiscal aprobada.
2. Se excluyen las operaciones con CFDI individual vigente, canceladas o con estado que requiera aclaración.
3. El contador revisa el periodo, las operaciones incluidas, exclusiones, montos e impuestos.
4. Un usuario autorizado solicita el timbrado al PAC y se registra la respuesta y el detalle de operaciones asociado.
5. Ante timbrado confirmado, se conserva el CFDI y se notifica a los responsables.
6. Si una operación requiere factura individual después de incorporarse al lote, se pausa el ajuste automático y se sigue el procedimiento fiscal de sustitución o corrección confirmado por el contador/PAC.

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
- Los motivos, usuarios, fechas y respuestas del PAC quedan en la bitácora.
- Las reglas fiscales específicas se validan con el contador y el PAC; este proceso no reemplaza asesoría contable.

## Excepciones

- **Timeout del PAC:** conservar la solicitud como resultado incierto, consultar estado y evitar una nueva emisión hasta resolverla.
- **Datos fiscales incompletos:** dejar la solicitud pendiente y pedir corrección al cliente.
- **Pago revertido o devolución posterior:** enviar a revisión para definir el comprobante fiscal relacionado, sin borrar el original.
- **Operación incluida en factura global solicitada individualmente:** detener el ajuste automático y escalar a contador.
- **Cancelación pendiente o rechazada:** mantener el estado informado por PAC y asignar seguimiento.

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
