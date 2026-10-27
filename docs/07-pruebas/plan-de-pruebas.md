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
- portal del socio: código OTP de un solo uso, límites de intentos y solicitudes, aislamiento de sesiones, perfil propio y reserva/cancelación de clases con lista de espera
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

## Cobertura del portal del socio

`backend/tests/test_member_portal_api.py` (4 pruebas) cubre:

- acceso completo: correo desconocido con respuesta genérica, correo conocido con código de vista previa, código incorrecto `401`, verificación exitosa, perfil con plan/acceso/saldo, bloqueo de un token de socio en `/admin/dashboard`, bloqueo de un token de personal en `/member/me`, logout `204` y sesión revocada.
- vencimiento y bloqueo: un código vencido y otro con 5 intentos fallidos dejan de servir.
- límite de solicitudes: no se emiten más de 5 códigos por socio en 15 minutos.
- privacidad: no se envía código a correos desconocidos ni a socios inactivos, y la respuesta no cambia.

La app móvil se valida con `npm run typecheck` y una prueba manual en la vista web de Expo contra el backend en vista previa; el job `mobile` de CI ejecuta el typecheck en cada push.

## Cobertura de reservas de clases del socio

`backend/tests/test_member_classes_api.py` (4 pruebas) cubre el ciclo completo sobre las reglas ya existentes del módulo de clases (aforo, bloqueo por fila, lista de espera y ventana de cancelación), sin duplicarlas:

- cartelera y reserva: el listado devuelve `200` con solo las sesiones futuras, los datos de tipo/salón/cupo y `blocked_reason = premium_class` o `membership_inactive`; reservar una clase incluida responde `201` con estado `reserved`, la repetición `409`, y el listado siguiente marca `already_reserved` con la reserva embebida. Una clase premium y una clase ya iniciada responden `409`, y el segundo socio de una clase con aforo uno queda en `waitlist` con posición `1`.
- propiedad y cancelación: cancelar la reserva de otro socio responde `404`; la cancelación antes del inicio devuelve `200`, `late_cancellation = false` y promueve al primero de la lista de espera a `reserved`; cancelar con la clase ya iniciada lanza `InvalidReservationState`.
- aforo sin lista de espera: con `waitlist_enabled = false` y la clase llena, el listado marca `blocked_reason = full` y la reserva lanza `SessionFull`.
- membresía vencida: una membresía fuera de periodo marca `membership_inactive` y bloquea la reserva con `MemberClassNotAllowed`.
- aislamiento: un token de personal recibe `401` en las tres rutas `/member/classes*`.

Verificación manual en vista previa (2026-10-27): con `ana.lopez@example.com` se abrió Inicio → Clases y reservas con 17 clases próximas; se canceló la reserva de recepción de «Funcional 07:00» (apareció «Reservar»), se volvió a reservar (cupo 12/20, estado «Confirmada») y la clase premium «Boxeo 20:00» quedó bloqueada con el aviso «Clase premium: reserva en recepción». Al terminar se restauró la base de vista previa y se detuvieron los servidores locales.

## Cobertura de rutinas y progreso del socio

`backend/tests/test_member_routines_api.py` (3 pruebas) cubre la capa de solo lectura sobre el módulo de rutinas, sin duplicar sus reglas:

- listado, detalle y progreso: el socio ve sus dos asignaciones (activa primero), el resumen `total`/`active`/`completed`/`cancelled` y los entrenamientos registrados; el detalle trae el objetivo, el plan de la versión asignada (nombre, series, repeticiones, descanso y carga) y los entrenamientos más recientes primero; el progreso devuelve entrenamientos totales y de 30 días, la última medición y la meta con línea base, valor actual y estado. Las respuestas no incluyen campos del socio (`member_id`, `member_email`) ni datos de otras asignaciones.
- propiedad: la asignación de otro socio y un identificador inexistente responden `AssignmentNotFound` (`404`); un socio sin asignaciones recibe una lista vacía y un progreso en ceros.
- aislamiento: un token de personal recibe `401` en `/member/routines`, `/member/routines/{id}` y `/member/progress`.

Verificación manual en vista previa (2026-10-27): con `ana.lopez@example.com` se abrió Inicio → Rutinas y progreso con 3 entrenamientos (los 3 en los últimos 30 días), peso actual 66.2 kg, la meta de peso 64.2 kg «En curso» con fecha 26 dic 2026, las últimas tres medidas y la rutina «Fuerza Full Body» activa (Carlos Ortiz, versión 2, 3 días por semana, desde 29 sep 2026); el detalle mostró 5 ejercicios con series, repeticiones, descanso y carga, el historial de 3 entrenamientos y el aviso de que el registro se hace con el entrenador o en recepción. Al terminar se restauró la base de vista previa y se detuvieron los servidores locales.

## Cobertura de pagos y estado de cuenta del socio

`backend/tests/test_member_payments_api.py` (2 pruebas) cubre la capa de solo lectura sobre los pagos de membresía y el estado de cuenta, sin duplicar el cálculo del saldo:

- historial y estado de cuenta: el socio ve sus dos pagos ordenados por fecha descendente con plan y periodo, el importe acumulado y la paginación; el estado de cuenta devuelve cargos, abonos, pagos y saldo, con los movimientos más recientes primero y el saldo después de cada uno. Las respuestas no incluyen `member_id`, cobrador, turno de caja ni límite de crédito.
- límites y aislamiento: un socio sin movimientos recibe todo en cero, `page = 0` se ajusta a 1 y `page_size = 500` a 50; un socio inexistente lanza `MemberPortalError` (`404`) y un token de personal recibe `401` en `/member/payments` y `/member/account`.
- otro socio no ve los pagos ni los movimientos ajenos.

Verificación manual en vista previa (2026-10-27): con `ana.lopez@example.com` se abrió Inicio → Pagos y estado de cuenta con saldo $20.00 MXN, 1 cargo, 1 abono, $1,100.00 pagados en membresías y corte al 27 oct 2026; la lista mostró dos pagos de $550.00 (plan Premium, 23 y 3 de octubre, efectivo) y, en movimientos, el pago de cuenta de −$20.00 con saldo $20.00 seguido de la venta a cuenta de +$40.00 con saldo $40.00, ambos del 27 oct. El botón «Volver al inicio» regresó al inicio con el saldo actualizado. Al terminar se restauró la base de vista previa y se detuvieron los servidores locales.

## Cobertura de registro de entrenamientos y medidas desde la app

`backend/tests/test_member_activity_api.py` (2 pruebas) cubre la escritura del socio sobre el módulo de rutinas, sin duplicar sus reglas:

- entrenamiento y medida: el socio registra un entrenamiento en su asignación activa y recibe `201` con `origin="app"`, estado `logged` y sin revisión; el detalle lo muestra con su nota. Registra una medida con peso, cintura y nota, y el progreso devuelve la última medida y la meta con el valor actualizado en la misma operación.
- reglas y límites: una asignación ajena responde `404`, una asignación completada `409`, una fecha futura y una medida vacía `422`; el panel ve el origen `app` en el listado de entrenamientos y en las medidas.
- revisión: el entrenador marca el entrenamiento como `reviewed` y el detalle del socio refleja el nuevo estado.
- aislamiento: un token de personal recibe `401` en las rutas de escritura del socio y uno de socio en la revisión del panel; las llamadas directas al portal rechazan una asignación ajena o inexistente (`AssignmentNotFound`) y un socio inexistente (`MemberPortalError`).

Verificación manual en vista previa (2026-10-27): con `ana.lopez@example.com` se abrió la rutina activa, se intentó guardar una medida vacía (rechazada), se registraron 65.8 kg y 81.2 cm (última medida «Desde tu app» y meta en 65.8 kg, 20 %), se rechazó un entrenamiento con fecha futura y se guardó uno de 50 min con esfuerzo 8 y nota, mostrado como «Desde tu app · Por revisar». En el panel, la tabla de medidas mostró ORIGEN «App»/«Personal» y el botón «Revisar» pasó el entrenamiento a «Revisado», visible después en el detalle del socio. Al terminar se restauró la base de vista previa y se detuvieron los servidores locales.

## Evidencia esperada

- logs de prueba
- screenshots de flujo crítico
- salidas de auditoría y event logs
- resultados de carga bajo condiciones reales

## Estado

La suite automatizada del backend cierra en **154 pruebas**, el build de producción del panel pasa y el typecheck de la app móvil pasa. La conciliación se verificó de extremo a extremo en vista previa; los complementos PPD cuentan con pruebas de API, un seed de vista previa y verificación en navegador (selector PUE/PPD con forma `99`, tabla de parcialidades, descargas XML/PDF y rechazo de un importe mayor al saldo). La cartera PPD cuenta con una prueba de API que backdatea facturas para cubrir los cuatro tramos, comprueba que los complementos solicitados no reducen el saldo, y valida filtros, paginación y liquidación; su pestaña se verificó en la vista previa. Las metas del socio se verificaron en navegador (activa, cancelada y cumplida; alta, edición y cancelación) y las fotos de progreso cuentan con una prueba de ciclo de vida que cubre permisos, validación por firma, límite de tamaño, almacenamiento, descarga autenticada y eliminación, además de verificación en navegador de la galería, el visor, la carga y la eliminación. La gráfica de evolución de medidas se verificó en navegador con las cuatro métricas, una serie plana, la meta activa de referencia y el estado con menos de dos mediciones, sin cambios de API. Las reservas de clases del socio cuentan con 4 pruebas de API (cartelera, reserva, lista de espera promovida, aforo, propiedad, clase iniciada y membresía vencida) y verificación en navegador de cancelación y reserva desde la app. Las rutinas y el progreso del socio cuentan con 3 pruebas de API (listado, detalle con versión fija, progreso con metas, propiedad y aislamiento) y verificación en navegador del resumen, la meta de peso, las medidas y el plan de 5 ejercicios. Los pagos y el estado de cuenta del socio cuentan con 2 pruebas de API (historial y saldo, orden descendente con saldo acumulado, paginación, límites, propiedad y aislamiento) y verificación en navegador del saldo, los pagos de membresía y los movimientos. El registro de entrenamientos y medidas desde la app cuenta con 2 pruebas de API (alta con origen y estado, actualización de meta, reglas, revisión del entrenador, propiedad y aislamiento) y verificación en navegador del alta, la validación, el origen en el panel y la revisión. La cartera PPD se verificó en Reportes → Ingresos como corte independiente del periodo y un complemento PPD timbrado se concilió con una línea bancaria en vista previa. Pendiente de ejecución en proyecto real, con un estado de cuenta bancario real y con un PAC real (el timbrado sigue siendo simulado y sin validez fiscal).
