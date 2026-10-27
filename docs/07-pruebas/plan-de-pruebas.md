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
- cartera PPD en reportes y conciliación: corte independiente del periodo y complementos electrónicos timbrados como candidatos
- conciliación bancaria: importación idempotente, vínculo uno a uno, diferencias con motivo y permisos
- metas del socio: línea base congelada, una meta activa por medida, avance y cierre automático
- fotos de progreso: validación por firma y tamaño, almacenamiento fuera de la base, descarga autenticada y eliminación explícita
- gráfica de evolución de medidas: serie por métrica, meta activa de referencia y estado con menos de dos mediciones
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

`backend/tests/test_reconciliation_api.py` (6 pruebas) cubre:

- permisos: contador y dueño administran; gerente solo consulta; recepción recibe `403`; nombres duplicados e importes/last4 inválidos.
- importación: duplicados dentro del lote y en la base, repetición exacta del archivo, lote atómico con fila inválida y cuenta inactiva.
- sugerencias y vínculo: pago de membresía con referencia y monto exactos, venta y devolución por sentido, rechazo de un retiro contra un pago, conflicto al intentar conciliar la misma operación con dos líneas, desvinculación y reutilización.
- diferencias: nota obligatoria, importe de diferencia, resumen y evento con el texto correcto, marcado y reapertura.
- búsqueda manual: candidatos fuera de la ventana de ±7 días visibles a ±60 días.

Verificación manual en vista previa (2026-10-25): alta de cuenta, activación/desactivación, importación CSV con duplicado, conciliación exacta y con diferencia, desvinculación, marcado y reapertura, filtros por estado/fecha/texto, búsqueda manual y restricciones por rol en el panel. La vista previa no prueba la carga de archivos binarios ni un banco real.

## Cobertura de cartera PPD en reportes y conciliación

La integración es de solo lectura y no cambia el esquema, así que la cobertura se reparte en dos pruebas nuevas:

- `backend/tests/test_reports_api.py` (`test_revenue_reports_ppd_receivables_snapshot`) siembra una factura PPD abierta con complementos timbrado, solicitado y fallido, más una factura PPD totalmente liquidada. Comprueba que `ppd_receivables` reporta una sola factura abierta, el saldo pendiente, el tramo 31–60 días, la antigüedad máxima y los importes/conteos de complementos; la factura liquidada queda fuera y el corte no cambia al consultar otro periodo.
- `backend/tests/test_reconciliation_api.py` (`test_ppd_complement_matching_uses_stamped_electronic_complements`) siembra una factura PPD con complementos timbrado (`03`), solicitado (`03`) y timbrado en efectivo (`01`). Verifica que solo el timbrado electrónico aparece como candidato `invoice_payment` de un depósito, que el folio y la factura se muestran en la etiqueta, que el vínculo queda `reconciled`, que un complemento solicitado o en efectivo responde `422`, y que un complemento no concilia un retiro.

Verificación manual en vista previa (2026-10-26): en Reportes → Ingresos se comprobó la cartera con 4 facturas abiertas, $1,475.25 pendientes, $2,254.00 facturados, $778.75 cobrados con 4 complementos timbrados, $533.25 por timbrar, 0 con error y los tramos $861.00 (0–30), $26.25 (31–60), $74.25 (61–90) y $513.75 (+90), con la factura abierta más antigua del 18 jul 2026; cambiar el periodo no altera el corte. En Conciliación se importó un depósito de $574.00 del 25 oct 2026: la bandeja mostró «1 sugerencia · Complemento PPD P-000001» y el detalle ofreció solo ese candidato (Factura A-000006 · Carlos Ramirez · Transferencia), que se concilió sin diferencia con el origen «Complemento PPD». Al terminar se restauró la base de vista previa desde el respaldo y se revocó la sesión temporal.

## Cobertura de metas del socio

`backend/tests/test_routines_api.py` (1 prueba de ciclo de vida) cubre:

- permisos: recepción recibe `403` en lectura y escritura; gerente y entrenador administran.
- validaciones: fecha objetivo pasada, grasa corporal fuera de 0–100, objetivo cero, objetivo ya cumplido por la última medición y una segunda meta activa de la misma medida (`409`).
- línea base: una meta creada sin mediciones queda sin línea base y la primera medición posterior la congela; con mediciones previas se usa la última.
- avance y edición: el porcentaje se calcula contra la línea base, `PATCH` mueve el objetivo, rechaza un objetivo ya cumplido y limpia o conserva la fecha y la nota.
- cierre automático: registrar una medición que alcanza el objetivo pasa la meta a `achieved` con valor y fecha; una meta cumplida ya no se edita ni se cancela y no bloquea crear otra de la misma medida.
- cancelación: una meta activa se cancela, permanece en el histórico con su fecha y el filtro por estado la devuelve.
- casos límite: socio inexistente o inactivo y meta inexistente responden `404`.

Verificación manual en vista previa (2026-10-25): en Rutinas → Seguimiento se abrió el detalle de una asignación con metas activa y cancelada (línea base, valor actual y avance) y el de una meta cumplida al 100 %; se creó una meta de pecho con objetivo, se editó su objetivo y nota, y se canceló. El registro de prueba se retiró de la base de vista previa al terminar.

## Cobertura de fotos de progreso

`backend/tests/test_routines_api.py` (1 prueba de ciclo de vida) cubre:

- permisos: recepción recibe `403` en listado, carga, descarga y eliminación; gerente y entrenador administran.
- validaciones: ángulo desconocido, tipo no admitido, contenido que no coincide con el tipo declarado, imagen vacía o basura (`422`) e imagen de más de 8 MB (`413`); una carga rechazada no crea el directorio de fotos.
- almacenamiento: la carga válida devuelve metadatos con la nota recortada, guarda un nombre aleatorio de 36 caracteres y no conserva el nombre original; el listado ordena de la más reciente a la más antigua; un socio inexistente responde `404`.
- descarga: devuelve los bytes, el `Content-Type`, `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff` y el nombre en línea; recepción recibe `403` y una foto inexistente `404`.
- eliminación: si el archivo falta, la descarga responde `404` pero la fila se puede borrar (`204`); borrar elimina fila y archivo, y repetir responde `404`; una clave de almacenamiento con `../` se rechaza antes de tocar el disco.
- aislamiento: cada caso usa un `tmp_path` propio mediante `PROGRESS_PHOTOS_DIR`, así que las pruebas no escriben en el directorio real de vista previa.

Verificación manual en vista previa (2026-10-26): en Rutinas → Seguimiento se abrió el detalle de una asignación con fotos sembradas; la galería mostró ángulo, fecha, tamaño y nota; el visor ampliado cargó la imagen desde el BFF; se subió una foto nueva con ángulo, fecha y nota (el contador pasó de 3 a 4) y se eliminó con confirmación (volvió a 3, con los avisos de éxito). Al terminar se restauró la base de vista previa y se revocó la sesión temporal de la verificación.

## Cobertura de la gráfica de evolución

La gráfica se calcula en el navegador con las mediciones que ya devuelve `GET /admin/routines/members/{id}/measurements` (máximo 36), así que **no agrega pruebas de API ni cambios de backend**. La cobertura automatizada del módulo sigue en `backend/tests/test_routines_api.py` (mediciones, metas y fotos), y el panel se valida con `npm run typecheck` y `npm run build`.

Verificación manual en vista previa (2026-10-26): en Rutinas → Seguimiento se abrió una asignación con tres mediciones y se alternaron las pestañas Peso, Cintura, Pecho y Grasa corporal. Peso mostró la serie descendente, el resumen «68 kg → 66.2 kg», el cambio «-1.8 kg» y la línea punteada de la meta activa (64.2 kg); Cintura y Grasa corporal mostraron su serie y resumen sin meta activa, y Pecho una serie plana con una sola marca en el eje y el texto «sin cambio». En una asignación con una sola medición aparecieron «Sin meta activa» y el aviso «Registra al menos dos mediciones de peso para ver la evolución.», sin SVG. La descripción accesible de la imagen conservó fechas y valores, y la tabla de mediciones siguió visible como registro completo. Al terminar se restauró la base de vista previa desde el respaldo y se detuvieron los servidores locales.

## Evidencia esperada

- logs de prueba
- screenshots de flujo crítico
- salidas de auditoría y event logs
- resultados de carga bajo condiciones reales

## Estado

La suite automatizada del backend cierra en **139 pruebas** y el build de producción del panel pasa. La conciliación se verificó de extremo a extremo en vista previa; los complementos PPD cuentan con pruebas de API, un seed de vista previa y verificación en navegador (selector PUE/PPD con forma `99`, tabla de parcialidades, descargas XML/PDF y rechazo de un importe mayor al saldo). La cartera PPD cuenta con una prueba de API que backdatea facturas para cubrir los cuatro tramos, comprueba que los complementos solicitados no reducen el saldo, y valida filtros, paginación y liquidación; su pestaña se verificó en la vista previa. Las metas del socio se verificaron en navegador (activa, cancelada y cumplida; alta, edición y cancelación) y las fotos de progreso cuentan con una prueba de ciclo de vida que cubre permisos, validación por firma, límite de tamaño, almacenamiento, descarga autenticada y eliminación, además de verificación en navegador de la galería, el visor, la carga y la eliminación. La gráfica de evolución de medidas se verificó en navegador con las cuatro métricas, una serie plana, la meta activa de referencia y el estado con menos de dos mediciones, sin cambios de API. La cartera PPD se verificó en Reportes → Ingresos como corte independiente del periodo y un complemento PPD timbrado se concilió con una línea bancaria en vista previa. Pendiente de ejecución en proyecto real, con un estado de cuenta bancario real y con un PAC real (el timbrado sigue siendo simulado y sin validez fiscal).
