# Plan de pruebas

## Objetivo

Probar que cada regla crítica del negocio funcione sin errores, especialmente acceso, pagos y facturación.

## Tipos de prueba

- unitarias
- de integración
- de automatización
- de carga
- de seguridad

## Casos prioritarios

- alta de socio y primer pago
- cobro recurrente con reintento
- acceso offline y realineación
- facturación CFDI con XML validado
- notas de crédito parciales y totales con control de saldo, cancelación y relación CFDI
- complementos de pago PPD: parcialidades, saldo, relación 07 y cancelación de la última
- conciliación bancaria: importación idempotente, vínculo uno a uno, diferencias con motivo y permisos
- permisos y bitácora
- corte de caja y inventario

## Cobertura de complementos de pago PPD

`backend/tests/test_billing_api.py` (6 pruebas PPD) cubre:

- factura PPD: forma de pago `99`, notas de crédito bloqueadas y complemento rechazado en una factura PUE.
- parcialidad y totalidad: dos complementos sobre la misma factura, idempotencia del alta, rechazo por exceder el saldo, revalidación del saldo al timbrar y descarga del XML/PDF solo para timbrados.
- XML: `TipoDeComprobante="P"`, totales en cero, `pago20`, receptor `CP01`, concepto de pago y `CfdiRelacionados TipoRelacion="07"`/`IdDocumento` cuando la factura tiene UUID.
- cancelación: solo la última parcialidad, motivo SAT, restauración del saldo y desbloqueo de la factura; rechazo de una parcialidad anterior.
- permisos y validaciones: lectura con `billing.read`, escritura con `billing.manage`, recepción `403`, forma `99` rechazada, fecha futura y UUID sustituto inválido.

## Cobertura de conciliación bancaria

`backend/tests/test_reconciliation_api.py` (5 pruebas) cubre:

- permisos: contador y dueño administran; gerente solo consulta; recepción recibe `403`; nombres duplicados e importes/last4 inválidos.
- importación: duplicados dentro del lote y en la base, repetición exacta del archivo, lote atómico con fila inválida y cuenta inactiva.
- sugerencias y vínculo: pago de membresía con referencia y monto exactos, venta y devolución por sentido, rechazo de un retiro contra un pago, conflicto al intentar conciliar la misma operación con dos líneas, desvinculación y reutilización.
- diferencias: nota obligatoria, importe de diferencia, resumen y evento con el texto correcto, marcado y reapertura.
- búsqueda manual: candidatos fuera de la ventana de ±7 días visibles a ±60 días.

Verificación manual en vista previa (2026-10-25): alta de cuenta, activación/desactivación, importación CSV con duplicado, conciliación exacta y con diferencia, desvinculación, marcado y reapertura, filtros por estado/fecha/texto, búsqueda manual y restricciones por rol en el panel. La vista previa no prueba la carga de archivos binarios ni un banco real.

## Evidencia esperada

- logs de prueba
- screenshots de flujo crítico
- salidas de auditoría y event logs
- resultados de carga bajo condiciones reales

## Estado

La suite automatizada del backend cierra en **134 pruebas** y el build de producción del panel pasa. La conciliación se verificó de extremo a extremo en vista previa; los complementos PPD cuentan con pruebas de API, un seed de vista previa y verificación en navegador (selector PUE/PPD con forma `99`, tabla de parcialidades, descargas XML/PDF y rechazo de un importe mayor al saldo). Pendiente de ejecución en proyecto real, con un estado de cuenta bancario real y con un PAC real (el timbrado sigue siendo simulado y sin validez fiscal).
