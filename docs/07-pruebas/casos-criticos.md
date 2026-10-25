# Casos críticos

## Casos clave

- acceso offline con cambios de horario
- cobro duplicado por doble envío
- facturación CFDI con error de datos fiscales
- nota de crédito que excede el saldo o intenta acreditar una factura global
- importación repetida de un estado de cuenta sin duplicar líneas
- conciliación de dos líneas bancarias contra la misma operación interna (la segunda debe rechazarse)
- diferencia de importe sin motivo (debe rechazarse) y con motivo (debe documentarse)
- entrada manual no autorizada
- corte de caja con diferencia de saldo
- bloqueo de acceso por adeudo

## Casos de conciliación bancaria

- **Importación idempotente**: reimportar el mismo CSV no crea líneas nuevas; el resultado informa los duplicados omitidos.
- **Lote atómico**: una fila con importe cero o fecha inválida rechaza todo el lote con el número de fila.
- **Vínculo uno a uno**: una operación interna ya conciliada no se ofrece como candidata y el segundo intento responde `409`.
- **Sentido del movimiento**: un pago no concilia un retiro y una devolución no concilia un depósito; el efectivo nunca aparece como candidato.
- **Diferencia**: si el importe no coincide, la conciliación sin nota responde `422`; con nota queda `difference` y el importe se muestra en el resumen.
- **Desvinculación**: exige motivo, vuelve a `pending` y conserva la operación y el estado anterior en la bitácora.
- **Permisos**: gerente consulta sin administrar; recepción no accede; todas las escrituras se validan en backend.

## Criterio de éxito

Cada caso debe quedar cubierto por pruebas automatizadas o de integración.
