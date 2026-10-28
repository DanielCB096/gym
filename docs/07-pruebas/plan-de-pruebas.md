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
- cancelación en proceso (`202`): seguimiento manual contra el SAT, confirmación, limpieza y aviso al socio
- cartera PPD en reportes y conciliación: corte independiente del periodo y complementos electrónicos timbrados como candidatos
- conciliación bancaria: importación idempotente, vínculo uno a uno, diferencias con motivo y permisos
- metas del socio: línea base congelada, una meta activa por medida, avance y cierre automático; alta y cancelación de metas propias desde la app con origen `app`
- fotos de progreso: validación por firma y tamaño, almacenamiento fuera de la base, descarga autenticada y eliminación explícita
- gráfica de evolución de medidas: serie por métrica, meta activa de referencia y estado con menos de dos mediciones
- portal del socio: código OTP de un solo uso, límites de intentos y solicitudes, aislamiento de sesiones, perfil propio y reserva/cancelación de clases con lista de espera
- facturas del socio: descarga por enlace firmado y solicitud de factura sobre operaciones propias, con perfil fiscal recordado e idempotencia
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

## Cobertura de metas desde la app del socio

`backend/tests/test_member_goals_api.py` (`test_member_manages_own_goals`, 1 prueba de ciclo completo) cubre:

- alta propia: `POST /member/progress/goals` responde `201` con `origin="app"`, línea base y valor actual de la última medición, avance en cero y nota recortada.
- reglas del panel reutilizadas: una segunda meta activa de la misma medida responde `409`, una fecha objetivo pasada, una grasa fuera de 0–100 y una medida desconocida responden `422`, y un objetivo ya cumplido por la última medición responde `422` cuando la medida queda libre.
- propiedad: cancelar la meta de otro socio responde `404`; una meta creada por el personal responde `409` en la app y solo se cancela desde el panel.
- aislamiento: un token de personal recibe `401` en ambas rutas.
- avance y reemplazo: una medición posterior mueve el avance al 10 %; al cancelar la meta queda con `cancelled_at`, repetir la cancelación responde `409`, y una nueva meta toma como línea base la última medición (69.5 kg) hasta alcanzar el 100 % con 63.5 kg (estado `achieved`).
- origen en el panel: el listado administrativo devuelve las metas `app`, `app` y `staff` en orden.

Verificación manual en vista previa (2026-10-27): en la app con `ana.lopez@example.com` se creó una meta de cintura (bajar a 75 cm) y otra de pecho (subir a 100 cm), se comprobó el `409` al repetir cintura, la etiqueta «Creada desde tu app» y la cancelación en dos pasos de la meta de cintura, que dejó intacta la meta de peso del personal. En el panel, Rutinas → Seguimiento → Ana López mostró «· App» en las metas de pecho (activa) y cintura (cancelada) y «· Personal» en la de peso. Los registros de prueba quedan en la base de vista previa local, que no se versiona.

## Cobertura de fotos de progreso

`backend/tests/test_routines_api.py` (1 prueba de ciclo de vida) cubre:

- permisos: recepción recibe `403` en listado, carga, descarga y eliminación; gerente y entrenador administran.
- validaciones: ángulo desconocido, tipo no admitido, contenido que no coincide con el tipo declarado, imagen vacía o basura (`422`) e imagen de más de 8 MB (`413`); una carga rechazada no crea el directorio de fotos.
- almacenamiento: la carga válida devuelve metadatos con la nota recortada, guarda un nombre aleatorio de 36 caracteres y no conserva el nombre original; el listado ordena de la más reciente a la más antigua; un socio inexistente responde `404`.
- descarga: devuelve los bytes, el `Content-Type`, `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff` y el nombre en línea; recepción recibe `403` y una foto inexistente `404`.
- eliminación: si el archivo falta, la descarga responde `404` pero la fila se puede borrar (`204`); borrar elimina fila y archivo, y repetir responde `404`; una clave de almacenamiento con `../` se rechaza antes de tocar el disco.
- aislamiento: cada caso usa un `tmp_path` propio mediante `PROGRESS_PHOTOS_DIR`, así que las pruebas no escriben en el directorio real de vista previa.

Verificación manual en vista previa (2026-10-26): en Rutinas → Seguimiento se abrió el detalle de una asignación con fotos sembradas; la galería mostró ángulo, fecha, tamaño y nota; el visor ampliado cargó la imagen desde el BFF; se subió una foto nueva con ángulo, fecha y nota (el contador pasó de 3 a 4) y se eliminó con confirmación (volvió a 3, con los avisos de éxito). Al terminar se restauró la base de vista previa y se revocó la sesión temporal de la verificación.

## Cobertura de fotos de progreso desde la app

`backend/tests/test_member_progress_photos_api.py` (1 prueba de ciclo completo) cubre:

- sesión: `GET` y `POST` sin Bearer responden `401`; el listado vacío devuelve `items: []` y `consent_recorded: false`.
- consentimiento como precondición: sin `consent=true` la carga responde `422` y no crea el directorio; una imagen con contenido inválido, un `image/gif` y un ángulo desconocido responden `422` con consentimiento y **no dejan consentimiento guardado**; una imagen de más de 8 MB responde `413`.
- primera carga: responde `201` con `origin="app"`, nota recortada, `captured_at`, tamaño y tipo; escribe una sola fila de `MemberConsent` con tipo `progress_photos`, versión `fotos-progreso-v1` y `revoked_at` nulo, y deja el archivo en `PROGRESS_PHOTOS_DIR` (vía `tmp_path`).
- cargas posteriores: una segunda foto no vuelve a pedir ni a duplicar el consentimiento; una foto creada por el personal con el mismo socio aparece en el listado del socio marcada `origin="staff"`, y el orden es la más reciente primero.
- propiedad: otro socio recibe una lista vacía con `consent_recorded: false` y `404` al borrar cualquiera de las fotos (propias del primero y del personal).
- enlaces firmados: el `file_path` del listado descarga sin Bearer (`200`); la ruta sin parámetros responde `422`, una firma alterada, una firma con otro `exp` y el mismo `sig`, y el `id` de otra foto con la firma original responden `403`; la descarga devuelve los bytes, `image/png`, `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff` y el nombre `foto-progreso-2026-10-20-front.png`.
- eliminación: `DELETE` propio responde `204`, borra fila y archivo y repetir responde `404`; la foto eliminada deja de descargarse (`404`) y el socio también puede borrar la foto que subió el personal.

Verificación manual en vista previa (2026-10-28): en la app web de Expo (`127.0.0.1:8083`) contra el backend en vista previa (`127.0.0.1:8013`) se entró con `ana.lopez@example.com`, se abrió Rutinas → Fotos de progreso y se comprobó que la carga estaba bloqueada hasta marcar la casilla de consentimiento. Se inyectó un PNG de prueba (81,723 bytes) por la galería, se eligió el ángulo «Perfil», se subió y la galería pasó a cuatro fotos; la imagen se renderizó desde el enlace firmado (240×320), el visor mostró «Subida desde tu app» con ángulo, fecha, tamaño y nota, y la eliminación en dos pasos dejó tres fotos. Al volver a subir no se pidió el consentimiento otra vez y la base conservó **una sola fila** de consentimiento. El segundo borrado devolvió el contador a tres, el backend no registró ningún `4xx`/`5xx` ni traza, y la consola del navegador quedó limpia. Al terminar se detuvieron los servidores locales y se borraron los archivos temporales de la prueba; los registros creados quedan en la base de vista previa local, que no se versiona.

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

## Cobertura de facturas del socio

`backend/tests/test_member_invoices_api.py` (2 pruebas) cubre la lectura de facturas propias y los enlaces firmados, reutilizando el timbrado simulado del módulo de facturación:

- alcance y contenido: con tres facturas de la socia (dos timbradas y una solo solicitada) y una del otro socio, `GET /member/invoices` devuelve solo las tres propias, más recientes primero, con folio con formato `A-000123`, total, origen (`sale`/`membership_payment`) e `is_simulated`; la factura solicitada no trae `pdf_path` ni `xml_path`, y la respuesta no expone `xml_content` ni `created_by`.
- paginación: `page=2&page_size=2` devuelve una fila de tres con dos páginas; el otro socio solo ve su factura.
- descargas: el PDF responde `200`, `application/pdf`, `Cache-Control: no-store` y empieza con `%PDF`; el XML responde `application/xml` y contiene el RFC del receptor. Una firma alterada responde `403` y una URL sin firma `422`.
- enlaces: una firma emitida con `now` anterior al vencimiento es rechazada por `verify_download_link`, y la firma de `pdf` no se puede reutilizar como `xml` (la válida sí pasa con el mismo instante).
- aislamiento: un token de personal recibe `401` en `/member/invoices` y uno de socio `401` en `/admin/billing/invoices`.
- límites: un socio sin facturas recibe lista vacía y `pages = 0`, `page = 0` se ajusta a 1 y `page_size = 500` a 50, y un socio inexistente lanza `MemberPortalError` (`404`).

Verificación manual en la vista previa (2026-10-28): con el backend en `PREVIEW_MODE` y PAC simulado, se abrió la app web de Expo (puerto 8081) e inició sesión con `ana.lopez@example.com` y el código de vista previa; el inicio mostró la tarjeta «Facturas» y la pantalla listó los **2 comprobantes** de la socia —`A-000007` timbrada por $75.00 (venta en mostrador, 18 ago 2026, IVA $10.35, aviso de comprobante simulado, botones PDF y XML) y `A-000003` solicitada por $60.00 (27 oct 2026, sin botones y con el aviso de que estará disponible al completarse el timbrado)—. Se capturó la URL que abre el botón (`/member/invoices/{id}/{kind}?exp=…&sig=…` sobre `http://127.0.0.1:8000`) y se descargó: el PDF respondió `200`, `application/pdf`, `Content-Disposition: attachment; filename="CFDI-A-000007-simulada.pdf"`, `Cache-Control: no-store` y 4,407 bytes que empiezan con `%PDF-1.4`; el XML respondió `application/xml; charset=utf-8` con el receptor del socio (`GARC850312AB1`, «Ana López») y la marca de simulación. Una firma alterada respondió `403`. La consola del navegador quedó limpia. Al terminar se detuvieron los servidores locales; la base de vista previa solo ganó el registro de acceso de la prueba, sin cambios en facturas.

## Cobertura de solicitud de facturas del socio

`backend/tests/test_member_invoice_requests_api.py` (2 pruebas) cubre la solicitud reutilizando `create_invoice` y el timbrado simulado:

- orígenes elegibles: con dos socios sembrados, la lista devuelve solo las operaciones propias pendientes —ventas completadas con tarjeta y un cobro de membresía— y excluye la venta a cuenta, la ya facturada, la de público en general y las de otro socio; el filtro `origin_type` y la paginación recortan el resultado.
- alta y perfil: `POST /member/invoices` crea una factura `requested` por una venta y otra por un cobro, sin exponer rutas de descarga ni UUID, y persiste el perfil fiscal de la socia; un perfil inexistente devuelve `{"profile": null}`.
- idempotencia: repetir la misma clave devuelve `idempotent_replay: true` y no crea otra factura; reutilizar la clave con otro origen responde `409` y solicitar un origen ya facturado con otra clave también.
- propiedad y validaciones: una venta o un pago de otro socio responde `404`, una venta a cuenta `409` y un RFC inválido `422`; PPD sin forma `99` responde `422` y con `99`/`PPD` se timbra como PPD.
- canal y aislamiento: el evento `invoice_requested` de la factura creada desde la app lleva `channel = "member_app"` con `actor_id` y `created_by` nulos; un token de personal recibe `401` en la ruta de socio y uno de socio `401` en la del panel.
- límites: un socio sin operaciones recibe lista vacía y `pages = 0`, `page = 0` se ajusta a 1 y `page_size = 500` a 50, un tipo de origen inválido y un socio inexistente responden `404`.

Verificación manual en la vista previa (2026-10-28): con el backend en `PREVIEW_MODE`, PAC simulado y la app web de Expo en el puerto 8082, se inició sesión con `ana.lopez@example.com`; Facturas → «Solicitar factura» listó **5 operaciones pendientes**. Se eligió el cobro `PAGO-A2651A7E` ($550.00), el formulario apareció vacío con los valores por defecto `612`/`G03`, se capturaron RFC `LOPA800101AAA`, razón social, CP `06700` y correo, y la solicitud devolvió `A-000009` en estado «Solicitada» por $550.00. «Ver mis facturas» mostró **3 comprobantes**, incluido `A-000009`, y la base de verificación confirmó `origin_type = membership_payment`, `created_by` nulo, el evento con `channel = "member_app"` y el perfil de la socia guardado. Al volver a la pantalla quedaban **4 operaciones** (la cobrada ya no aparece) y el formulario venía prellenado con el aviso «Usamos los datos que guardaste». La consola del navegador quedó limpia. Al terminar se detuvieron los servidores y se borraron la copia de la base y los artefactos temporales.

## Cobertura de registro de entrenamientos y medidas desde la app

`backend/tests/test_member_activity_api.py` (2 pruebas) cubre la escritura del socio sobre el módulo de rutinas, sin duplicar sus reglas:

- entrenamiento y medida: el socio registra un entrenamiento en su asignación activa y recibe `201` con `origin="app"`, estado `logged` y sin revisión; el detalle lo muestra con su nota. Registra una medida con peso, cintura y nota, y el progreso devuelve la última medida y la meta con el valor actualizado en la misma operación.
- reglas y límites: una asignación ajena responde `404`, una asignación completada `409`, una fecha futura y una medida vacía `422`; el panel ve el origen `app` en el listado de entrenamientos y en las medidas.
- revisión: el entrenador marca el entrenamiento como `reviewed` y el detalle del socio refleja el nuevo estado.
- aislamiento: un token de personal recibe `401` en las rutas de escritura del socio y uno de socio en la revisión del panel; las llamadas directas al portal rechazan una asignación ajena o inexistente (`AssignmentNotFound`) y un socio inexistente (`MemberPortalError`).

Verificación manual en vista previa (2026-10-27): con `ana.lopez@example.com` se abrió la rutina activa, se intentó guardar una medida vacía (rechazada), se registraron 65.8 kg y 81.2 cm (última medida «Desde tu app» y meta en 65.8 kg, 20 %), se rechazó un entrenamiento con fecha futura y se guardó uno de 50 min con esfuerzo 8 y nota, mostrado como «Desde tu app · Por revisar». En el panel, la tabla de medidas mostró ORIGEN «App»/«Personal» y el botón «Revisar» pasó el entrenamiento a «Revisado», visible después en el detalle del socio. Al terminar se restauró la base de vista previa y se detuvieron los servidores locales.

## Cobertura de series de entrenamiento

`backend/tests/test_workout_sets_api.py` (2 pruebas) cubre el detalle por serie sobre las reglas ya existentes del alta de entrenamientos:

- ciclo completo por API: el socio registra un entrenamiento con tres series repartidas en dos ejercicios y pesos distintos (uno nulo) y recibe `201`; el detalle del socio y el listado del panel devuelven las series ordenadas por la posición del ejercicio en el plan y luego por número de serie; un entrenamiento sin `sets` devuelve `sets: []`; el personal registra un entrenamiento con series (`origin="staff"`) y la revisión conserva las series.
- validaciones: un ejercicio fuera del plan responde `422` («no pertenece»), una serie repetida `422`, `reps = 0` `422`, peso `1001` `422` y más de 60 series `422`; la prueba directa del servicio confirma los rangos, los duplicados y la lectura ordenada tras persistir.
- límites del modelo: el índice único `(workout_id, exercise_id, set_number)` y los CHECK de `workout_sets` replican los límites del servicio; la migración `20261027_0033_workout_sets.py` se aplica sobre PostgreSQL y la base de vista previa la crea con `create_all`.

Verificación manual en vista previa (2026-10-27): en el panel se registró un entrenamiento de 60 min con esfuerzo 8 y tres series (Sentadilla 5×80 kg y 5×85 kg; Press banca 5×55 kg), visible en el historial como «Sentadilla con barra: 5 × 80 kg · 5 × 85 kg | Press banca: 5 × 55 kg». En la app, con `ana.lopez@example.com`, se registraron dos series de Remo con mancuerna (8×24 kg y 8×26 kg) y el historial las mostró como «8 × 24 kg · 8 × 26 kg» con origen «Desde tu app»; el panel mostró ese entrenamiento con sus series y origen «App». Al terminar se detuvieron los servidores locales.

## Cobertura de la bandeja de avisos del socio

`backend/tests/test_member_notifications_api.py` (2 pruebas) cubre los seis emisores originales y las cuatro rutas de auto-servicio; las reglas del dominio que los disparan ya están cubiertas en sus propios módulos, así que aquí solo se verifica el aviso que producen:

- recogida de eventos: una sola lectura del inbox crea el recordatorio `membership_expiring` («faltan 2 días») y una segunda lectura no lo repite; tras una revisión del entrenador (`workout_reviewed`), una meta propia cumplida con una medida de la app (`goal_achieved`, con `ref_id` de la meta y los valores 65 kg / 64 kg en el texto), una meta del personal editada y luego cancelada (`goal_updated_by_staff` y `goal_cancelled_by_staff`, ambas con el `ref_id` de la meta) y una reserva promovida desde la lista de espera (`class_waitlist_promoted`, con el título «Spinning 6am»), el inbox del socio contiene exactamente los cinco tipos y el del otro socio solo el suyo. La meta que el propio socio cancela desde la app no genera ningún aviso.
- lectura y confirmación: `unread-count` pasa de 5 a 4 al marcar uno, repetir la marcación responde `200` y deja el contador en 4 (idempotente), y `read-all` devuelve `{"updated": 4}` y deja el contador en 0.
- alcance y aislamiento: sin token y con un token de personal, `GET /member/notifications` responde `401`; marcar el aviso de otro socio responde `404`, igual que un identificador inexistente; el inbox de un socio sin avisos viene vacío y su `read-all` devuelve `{"updated": 0}` sin tocar la bandeja ajena.
- texto congelado: las aserciones sobre `body` («Full body», «78 cm», «cintura», «peso», «Spinning 6am») confirman que el aviso conserva el nombre y el valor del momento del evento, no una referencia viva.

Verificación manual en vista previa (2026-10-27): en la app, con `ana.lopez@example.com`, Inicio mostró la tarjeta «Avisos del gimnasio» con la insignia 6; al entrar, la bandeja listó los seis avisos con su etiqueta de tipo y los sin leer marcados con la barra de acento y el punto. Se tocó el aviso de la meta de peso y la insignia bajó a 5; con «Marcar todas como leídas» apareció «Marcaste 5 avisos como leídos.» y la insignia desapareció del inicio. Al terminar se detuvieron los servidores locales; los avisos de prueba quedan en la base de vista previa local, que no se versiona.

## Cobertura de la bandeja de avisos del personal

`backend/tests/test_staff_notifications_api.py` (2 pruebas) cubre la bandeja del panel, cuya audiencia se resuelve sobre `AppUser.employee_id`. El escenario siembra cuatro empleados: uno con cuenta de entrenador, otro con cuenta de mantenimiento, un tercero con la cuenta **desactivada** y un cuarto **sin cuenta**, además de un socio con rutina asignada.

- entrenador: el entrenamiento registrado desde la app (`POST /member/routines/{assignment_id}/workouts`) deja en su bandeja exactamente un `workout_pending_review` con `ref_id` del entrenamiento y el texto «Luis», «Full body» y «pendiente de tu revisión». El entrenamiento capturado por el personal (`POST /admin/routines/assignments/{id}/workouts`) **no** genera aviso, y el empleado con cuenta desactivada queda en 0 filas comprobado por SQL directo.
- técnico: un equipo y un ticket **sin** `assigned_to` no dejan avisos; al crear el ticket con `assigned_to` aparece un `maintenance_ticket_assigned` con «Cinta 1» y «Banda suelta» en el cuerpo. Reasignar el mismo técnico por `PATCH` mantiene un solo aviso (dedupe por `ticket`+`empleado`) y reasignar al empleado sin cuenta no agrega ninguno.
- lectura y confirmación: el marcado individual es idempotente, `read-all` del técnico devuelve `{"updated": 0}` mientras el entrenador conserva su pendiente, y el `read-all` del entrenador devuelve `{"updated": 1}` y deja su contador en 0.
- alcance y aislamiento: sin token y con un token de socio, las cuatro rutas `/admin/notifications*` responden `401`; el dueño ve `total = 0`, `unread = 0` y recibe `404` al intentar marcar el aviso del entrenador, igual que con un UUID inexistente; su `read-all` devuelve `{"updated": 0}` sin tocar bandeja ajena y el entrenamiento sigue en `status = "logged"`.
- texto congelado: las aserciones sobre `body` confirman que el aviso nombra socio, rutina, equipo y falla tal como eran en el momento del evento; los campos libres se recortan con `_clip` para que un texto editado largo no pueda violar el `CHECK` de 500 caracteres ni abortar la operación de dominio.

Verificación manual en vista previa (2026-10-27), con una cuenta de entrenador creada en la base local de vista previa (contraseña únicamente local, nunca versionada) y tres entrenamientos registrados desde la app del socio por API:

- el resumen del panel se firmó «carlos.ortiz@centrofit.mx · Entrenador» con la bitácora de accesos correctamente reemplazada por «Tu perfil no tiene permiso para consultar la bitácora de accesos», confirmando que la bandeja no dependió de permisos nuevos.
- la campana mostró la insignia y el `aria-label` «Notificaciones, 1 sin leer»; al abrirla, el popover listó «Entrenamiento pendiente de revisión — Ana López registró la rutina Fuerza Full Body del 27/10/2026 desde la app. Queda pendiente de tu revisión. · 27-oct, 05:01 p.m.», con el encabezado «1 sin leer».
- tocar el aviso lo dejó atenuado, cambió el encabezado a «Todo leído», hizo desaparecer la insignia y persistió `read_at` en la base; la apertura del popover hizo **una sola** llamada a `GET /api/admin/notifications?page_size=12` (sin duplicado por StrictMode).
- tras generar dos avisos más, el popover mostró tres líneas con «2 sin leer» en el encabezado y «Marcar todo leído» dejó la tabla en 3 filas con `read_at` y 0 no leídos en el servidor.
- `GET /api/admin/notifications`, `/unread-count` y `POST /read-all` sin cookie responden `401` a través del BFF y `GET /admin/notifications` sin token responde `401` en el backend. La consola del navegador quedó sin errores; las dos líneas de muestra que tenía la campana ya no existen en el código.

## Cobertura del aviso de equipo fuera de servicio

`backend/tests/test_equipment_out_of_service_notice.py` (2 pruebas) cubre el único emisor cuya audiencia **no viene en la mano del evento**: tres socios con membresía de 60 días (lejos de las ventanas 7/3/1 para que el recordatorio de vencimiento no ensucie los conteos), dos máquinas, tres ejercicios —dos vinculados a cada máquina y uno sin vínculo— y tres rutinas asignadas: Ana usa la bicicleta de ciclo, Beto el rack y Carlos recibe una asignación de ejercicio libre que luego se **cancela**.

- audiencia y texto por API: el cambio de estado por `POST /admin/maintenance/equipment/{id}/status` deja en el inbox de Ana (`GET /member/notifications` tras OTP de la app) exactamente un aviso `equipment_out_of_service` con `total = 1`, `unread_total = 1`, el título «Un equipo está fuera de servicio», el nombre «Bicicleta espacial» y el lugar «Sala de ciclo» en el cuerpo y `ref_id` del equipo. Beto y Carlos quedan en 0 filas: el primero usa otra máquina y el segundo tiene la asignación cancelada, así que **una asignación cerrada ya no es audiencia**.
- transiciones que no avisan: devolver la máquina a `operational` y volverla a parar **el mismo día** deja una sola fila (el día del club está en el `dedupe_key`), y pedir `out_of_service` sobre una máquina ya parada no escribe nada (el servicio sale antes si el estado no cambia).
- camino del ticket: un `create_ticket` con `severity = "critical"` sobre el rack deja en Beto exactamente `["equipment_out_of_service"]` y en Carlos ninguna fila, comprobado leyendo `MemberNotification` directo porque el DTO de la bandeja no expone `dedupe_key`.
- forma del aviso y ventana: la segunda prueba fija que el cuerpo **no** contiene el título del ticket (`Motor humea` ausente) pero sí la fecha formateada del día del club, y que la clave es `equipment_out_of_service:<equipo>:<socio>:<YYYYMMDD>`; un segundo ticket crítico el mismo día no agrega filas, y tras reparar la máquina, un ticket en **otro día del club** produce la segunda fila.

Verificación manual en vista previa (2026-10-27), con una cuenta de mantenimiento creada en la base local de vista previa (contraseña únicamente local, nunca versionada) que firma `maintenance.report`:

- vinculado localmente el ejercicio «Bicicleta fija» a la máquina «Bicicleta», `POST /admin/maintenance/equipment/{id}/status` con `out_of_service` respondió `200` y el inbox de `jorge.ramirez@example.com` quedó en `total = 1`, `unread_total = 1` con el texto «El equipo Bicicleta de Cardio quedó fuera de servicio el 27/10/2026…»; `ana.lopez@example.com`, cuyo plan no usa esa máquina, siguió sin avisos de equipo.
- la secuencia `operational` → `maintenance` → `out_of_service` sobre la misma máquina el mismo día dejó **una sola fila** en la tabla, comprobada por SQL directo junto con su `dedupe_key`.
- una máquina sin audiencia («Prensa», sin ejercicios vinculados) bloqueada por un ticket `critical` no escribió ninguna fila; tras vincularle «Prensa de piernas», un segundo ticket crítico sí dejó el aviso de Elena con «Prensa de Piso de pesas» en el cuerpo.
- la suite pasa en 79 s con las 164 pruebas; `flake8 src tests --select=E9,F63,F7,F82` limpio y `tsc --noEmit` de la app sin errores.

## Cobertura de los avisos de estado de factura

`backend/tests/test_invoice_notifications.py` (2 pruebas) cubre el primer emisor que no vive en el módulo de avisos sino en **facturación**, y cuyo disparador es el propio ciclo de vida de la factura. El escenario siembra un contador con `billing.manage`, dos socios con membresía de 60 días (fuera de las ventanas 7/3/1 de vencimiento) y ventas para Ana, Beto y un cliente de mostrador.

- camino feliz y aislamiento: solicitar la factura de Ana (`requested`) no escribe nada; timbrarla deja exactamente un `invoice_stamped` con folio `A-000001`, importe `$116.00 MXN`, sufijo de simulación y `ref_id` de la factura; volver a timbrar no duplica, cancelarla agrega `invoice_cancelled` como el más reciente y Beto sigue con la bandeja vacía. La factura de mostrador (`member_id = None`) no crea ninguna fila de `MemberNotification`.
- fallo y recuperación: un `FlakyPac` monkeypatcheado sobre `billing_service.pac_gateway` lanza `PacRejected(code="test_rejected")`; el `POST` responde `502` y deja un `invoice_failed`, repetir el intento devuelve `502` sin duplicar por el `dedupe_key`, y al desactivar el rechazo el timbrado responde `200` y la bandeja queda con `["invoice_stamped", "invoice_failed"]`, es decir, el aviso de fracaso no bloquea el de éxito.
- ambas pruebas leen `MemberNotification` directo además del DTO de la bandeja, porque el `dedupe_key` no se expone por API.

Verificación en navegador (2026-10-28) sobre una copia desechable de la base de vista previa, con el socio `ana.lopez@example.com` en Expo web: el inicio mostró la insignia «1 sin leer», la bandeja listó el aviso «Factura timbrada» con folio e importe y el botón accesible «Abrir facturas: Factura timbrada»; tocarlo respondió `200` en `POST /member/notifications/{id}/read` y abrió Facturas, donde `A-000003` apareció como «Timbrada» con sus botones de descarga; `GET /member/invoices` respondió `200` y la consola quedó sin errores.

## Cobertura del seguimiento de cancelaciones en proceso

`backend/tests/test_billing_api.py` (3 pruebas) cubre el flujo de una cancelación que el SAT deja en proceso, con un `_StubPac` que responde `cancel` y `sat_status` y deja el timbrado al PAC simulado:

- `202` pendiente: la cancelación responde `202 Accepted`, la factura sigue `stamped` con `cancellation_pending`, `cancellation_requested_at`, motivo y nota, y el último evento es `invoice_cancellation_pending`; el filtro `cancellation_pending=true` la devuelve, `false` no, y el resumen cuenta `pending_cancellations = 1`. Una consulta con `Vigente`/«En proceso» conserva la solicitud y actualiza `cancellation_checked_at`; con `Cancelado` pasa a `cancelled`, limpia la solicitud, registra `invoice_cancellation_confirmed` y deja un aviso `invoice_cancelled` al socio.
- limpieza: un `No Encontrado` del SAT responde `502` sin tocar la factura; un `Vigente`/«No cancelado» borra motivo, nota y fechas y registra `invoice_cancellation_cleared` con el motivo anterior en `detail.previous`.
- guardas: recepción (`billing.read`/`billing.request`) recibe `403`, una factura simulada sin UUID `409` sin llamar al PAC y un id inexistente `404`.

**Verificación en navegador pendiente (2026-10-28)**: el panel ya muestra la sección «CANCELACIÓN EN PROCESO», la insignia «Cancelación en proceso» en el listado, una insignia de `pending_cancellations` en el resumen y el botón «Consultar estado en el SAT», y oculta «Cancelar factura» mientras la solicitud está pendiente. `tsc --noEmit` pasa, pero el flujo no se recorrió en un navegador ni contra Finkok demo; queda como paso siguiente al retomar el incremento. La vista previa local necesita `backend/preview_patch.py` para agregar las dos columnas nuevas a `gym_preview.db`.

## Cobertura del adaptador de Finkok

`backend/tests/test_finkok_pac.py` (14 pruebas) cubre el primer PAC real **sin tocar la red**: `FinkokPac` recibe un `httpx.MockTransport` inyectado, así que cada caso inspecciona la petición SOAP y decide la respuesta. La suite completa queda en **192 pruebas**.

- timbrado: el sobre va a `/servicios/soap/stamp` con `SOAPAction: "sign_stamp"`, el XML viaja en base64 con `NoCertificado=""` y sin los veinte ceros del marcador, y el `UUID`, el XML timbrado y la `Fecha` de la respuesta llenan el resultado; la fecha `2026-10-28T10:15:30` del club se guarda como `16:15:30Z`.
- rechazo e indisponibilidad: una `Incidencia` (`CodigoError 301`, RFC inválido) produce `PacRejected` con su mensaje y su código; un `ConnectError` y un SOAP fault (`faultstring`) producen `PacUnavailable`.
- cancelación: el sobre va a `/servicios/soap/cancel` con `SOAPAction: "cancel"`, `taxpayer_id`, `store_pending=0`, el `Motivo` y el UUID sustituto en el atributo, y `cer`/`key` en base64 idénticos a los PEM; `201` se acepta, `202` no (mensaje de «en proceso»), un `CodEstatus` sin `Folios` se propaga y sin `PAC_CERT_PATH` responde `503`.
- consulta del estado: `sat_status` va a `/servicios/soap/cancel` con `SOAPAction: "get_sat_status"` y envía `username`, `password`, `taxpayer_id`, `rtaxpayer_id`, `uuid` y `total` (`116.00`); la respuesta llena `SatStatusOutcome` con `Estado`, `EsCancelable`, `EstatusCancelacion` y `CodigoEstatus`; un `error` del PAC es `502`, una respuesta sin `sat.Estado` es `503` y el gateway simulado informa un estado marcado como simulado.
- gateway: con `PAC_PROVIDER=finkok` y credenciales devuelve `FinkokPac`; sin `PAC_USER` responde `503` sin caer a simulación. `prepare_prestamp` conserva un `NoCertificado` explícito.
- sin credenciales reales: el adaptador **no se ha probado contra Finkok demo ni producción**, así que este incremento no sustituye la validación con el PAC y el contador.

## Prueba manual contra el demo de Finkok

`backend/finkok_demo.py` prepara la corrida real sin tocar la base ni consumir folios. `--dry-run` arma el CFDI de ejemplo y lo guarda en `finkok_demo_out/` para revisarlo; sin el flag timbra contra `https://demo-facturacion.finkok.com` y valida el sello, el certificado, el UUID, el emisor y los totales del XML devuelto; `--cancel` añade la cancelación con el CSD y el motivo `02` por defecto.

Verificado en esta máquina (2026-10-28): el dry run genera un CFDI 4.0 de $116.00 (base $100.00 + IVA $16.00) con `NoCertificado=""`, serie `DEMO`, autofactura y `resultado.json`; las guardas responden con código 1 y un mensaje claro cuando faltan `PAC_USER`/`PAC_PASSWORD`, cuando el entorno apunta a producción sin `--production --confirm-production` o cuando `--cancel` no tiene el CSD. **No se ejecutó contra el demo** porque no hay credenciales ni CSD: esa corrida es el paso pendiente.

`backend/tests/test_finkok_demo_script.py` (4 pruebas, la suite pasa a **192**) cubre la parte offline: el comprobante de prueba cuadra base/IVA/total, sale con el `NoCertificado` vacío y los datos del emisor, el validador acepta un timbre completo y detecta la falta de `TimbreFiscalDigital` o un UUID distinto del que devolvió el PAC, y un emisor con los marcadores de ejemplo se reporta antes de timbrar.

## Cobertura del resumen de la agenda filtrado por búsqueda

`backend/tests/test_classes_api.py` (`test_summary_and_total_are_not_inflated_by_the_search_filter`, 1 prueba) cubre la corrección del 2026-10-27 en la que el filtro de texto inflamaba los conteos de `GET /admin/classes/sessions`:

- escenario: tres tipos de clase (Spinning, Yoga y Boxeo) y tres sesiones —«Spinning 6am» (tipo Spinning), «Cardio 7am» (**tipo Yoga**, con un título que no menciona su tipo) y «Boxeo 8am» (tipo Spinning)—, con dos reservas confirmadas y una en lista de espera, todas sobre la primera clase por su tope de aforo. Así la búsqueda puede coincidir solo por título, solo por nombre de tipo o por nada.
- sin filtro: `total = 3` y el resumen completo (`scheduled = 3`, `upcoming = 3`, `reserved_total = 2`, `waitlist_total = 1`), para confirmar que el `JOIN` adicional no altera la consulta sin `search`.
- búsqueda por título (`spinning 6am`): `total = 1` y `summary.total = 1` con sus dos reservas y su lista de espera; **antes de la corrección este caso devolvía 3** porque cada sesión se multiplicaba por el número de tipos de clase.
- búsqueda por nombre de tipo (`yoga`): los `items` coinciden exactamente con «Cardio 7am» y su resumen marca `total = 1` con `reserved_total = 0` y `waitlist_total = 0`, es decir, el agregado de asistencia solo cuenta las sesiones filtradas.
- búsqueda sin coincidencias (`sal`): `total = 0` y `summary.total = 0`.
- señal de calidad: el `SAWarning` de producto cartesiano de SQLAlchemy, que aparecía en cada consulta con búsqueda, ya **no aparece ninguna vez** en la suite completa.

Verificación sobre la base de vista previa real (2026-10-27, 5 tipos, 19 sesiones y 131 reservas): con la corrección cada filtro cuadra `items = total = summary.total` (funcional 5, spinning 5, boxeo 3, yoga 3, «core» 0) mientras que la forma sin unir los contaba como 39, 39, 31 y 31. No se repitió en el navegador porque el panel no calcula nada: solo pinta el resumen que devuelve la API.

## Cobertura del código rotativo y el kiosco de recepción

`backend/tests/test_kiosk_access_api.py` (4 pruebas) cubre el primer canal de entrada autónomo del socio, reutilizando el motor de acceso existente:

- alta de dispositivos: `GET /admin/kiosk/devices` sin sesión responde `401` y un recepcionista sin `settings.manage` recibe `403`; la lista arranca vacía; etiqueta vacía o en blanco responde `422`; crear devuelve `201` con un token que **no** aparece en el listado y solo se almacena su SHA-256; el dispositivo queda `active` con `last_seen_at` nulo.
- emisión y consumo: el socio entra con OTP, un primer código se invalida al emitir el segundo, el check-in sin token y con token falso responde `401`, el código viejo responde `400`, el vigente concede (`authorized=true`, `reason=entry_allowed`, «Acceso concedido», «Ana L.», lector «Kiosco Recepción»), el replay del mismo código responde `400` y un código mal formado también; el evento queda en `access_events` con `source="reader"` y visible en la bitácora.
- revocación: el panel revoca el dispositivo, el check-in posterior responde `401`, recepción sin permiso no puede revocar (`403`), un id inexistente responde `404` y el dispositivo sigue listado como `revoked`.
- membresía: una membresía vencida o todavía no iniciada responde `409` al emitir; si vence entre la emisión y la captura, el check-in responde `200` con `authorized=false`, `reason="membership_expired"`, el mensaje «Membresía vencida. Pasa a recepción.», consume el código (el segundo intento da `400`) y deja el evento denegado.
- límites: seis emisiones seguidas responden `201` y la séptima `429`; diez códigos incorrectos responden `400` y el código válido siguiente `429`; quedan diez filas en `kiosk_attempts` con resultado `invalid`; un segundo dispositivo no comparte el límite del primero y concede el acceso.
- vigencia: `test_access_code_expires_five_minutes_after_issue` emite con `SECRET_KEY` de prueba y comprueba que a los 7 minutos el código ya no vale y que a los 5 minutos exactos tampoco (frontera).

Verificación manual en navegador (2026-10-28, backend `127.0.0.1:8000`, kiosco `localhost:8090`, panel `localhost:3000`, Expo web `127.0.0.1:8081`):

- **App**: el inicio mostró la tarjeta «Acceso habilitado» como botón; al abrirla se generó `397 969` con «Vence en 4:58», sin recargar ni pedir confirmación.
- **Kiosco**: la configuración aceptó `http://127.0.0.1:8000` y el token del dispositivo, probó `/health` y abrió el teclado; al capturar el código mostró «Acceso concedido», «Ana L.» y «Siguiente socio». El mismo código reingresado mostró «Código inválido o vencido.».
- **Panel**: el resumen listó el acceso de Ana López de las 17:10:40 con lector «Kiosco Recepción» y resultado «Autorizado»; la página «Kiosco» mostró el dispositivo con última actividad, el token se mostró una sola vez al crearlo y la revocación con confirmación dejó el estado «Revocado» y el aviso «Kiosco Recepción revocado.».
- **Revocación**: tras revocar, el check-in del kiosco respondió `401`, borró el token y volvió a la pantalla de configuración con «El token del kiosco no es válido o fue revocado. Captura uno nuevo.»; se creó un segundo dispositivo y, con un código nuevo (`073 347`), el kiosco volvió a conceder el acceso. Al terminar se dejó el kiosco configurado con el dispositivo nuevo.
- **Límites de la verificación**: no se probó en una tablet real ni sin red; el intento `429` del kiosco se cubrió en la suite, no en el navegador.

## Validación de la cadena de migraciones

Las migraciones Alembic **no se ejecutan en ningún camino local**: la vista previa usa SQLite y arma el esquema con `create_all` más `preview_patch.py`, y la suite de pytest corre sobre SQLite en memoria. Una migración mal escrita solo se descubría al desplegar, y los `CHECK` que se ensanchan soltando y recreando la restricción (`20261027_0037`) no tienen otra verificación más que la lectura del humano.

Por eso el job `migrations` de `.github/workflows/ci.yml` levanta `postgres:16-alpine` como servicio y, en cada push:

1. `alembic upgrade head` — aplica la cadena completa (0001 → la revisión más reciente) sobre PostgreSQL real.
2. `alembic downgrade -1` + `alembic upgrade head` — comprueba que la migración más reciente **y su revertido** funcionan; el revertido del tipo `equipment_out_of_service` debe negarse si existen filas de ese tipo, y con la base recién construida no las hay.
3. `alembic check` — compara los modelos contra el esquema migrado y falla si un modelo declara una tabla o columna que ninguna migración crea.
4. una aserción sobre `pg_get_constraintdef('ck_member_notifications_kind')` que falla si el `CHECK` no quedó con el tipo de aviso de equipo o con los tres tipos de estado de factura (`invoice_stamped`, `invoice_failed`, `invoice_cancelled`).

## Lo que `alembic check` encontró en su primera corrida

Al correrlo por primera vez contra PostgreSQL 16 el check **detectó una migración que nunca existió**: `staff_shifts`, `staff_attendance` y `staff_attendance_events` estaban en los modelos de `staffing`, las consume el panel y la vista previa las tiene porque `create_all` construye lo que los modelos declaran, pero ninguna de las 37 migraciones las creaba. Una base producida con `alembic upgrade head` no tenía la tabla de turnos: cualquier `GET /admin/staff/{id}/shifts` habría caído con `relation does not exist`. Se corrigió con `20261027_0038_staffing_shifts_and_attendance.py`, escrita contra lo que publican los modelos.

Verificación de la migración nueva, sobre una base PostgreSQL desechable: `upgrade head` deja 69 tablas y `alembic check` responde *«No new upgrade operations detected»*; el `pg_get_constraintdef` de las ocho restricciones (`ck_staff_shifts_period_valid`, `ck_staff_shifts_status`, `ck_staff_attendance_status`, `ck_staff_attendance_checkout_order`, `ck_staff_attendance_events_type`, `ck_staff_attendance_events_source`, `uq_staff_attendance_shift`, `uq_staff_attendance_events_request`) y los cinco índices coinciden con los `__table_args__` de los modelos y con la misma `sqlite_master` de la base de vista previa, que es la que ya funcionaba. Como el check **no compara los `CHECK`**, eso se comprobó a mano: al cambiar `ck_staff_shifts_status` para aceptar solo `scheduled`, `alembic check` siguió diciendo «No new upgrade operations detected» — de ahí el paso 4 del job, que sí lee las restricciones desde `pg_constraint`.

El check también se probó en la dirección que importa: con la base en `head` y las tres tablas de turnos borradas a mano, reporta `Detected added table` sobre las tres y **termina en distinto de cero**, que es lo que rompe el push. Su primer guardia es que la base esté en `head`; si está atrás, falla con «Target database is not up to date» sin listar la divergencia, así que el paso debe ir después de `upgrade head`.

## Validaciones complementarias

La aserción del paso 4 se validó en las dos direcciones antes de subir el job: con `0037` aplicada imprime el `CHECK` con los siete tipos y sale `0`; tras un `downgrade -1` termina en `1` con el texto del `CHECK` viejo. La cadena completa también se aplicó de forma local y desechable sobre el mismo contenedor `postgres:16-alpine` (`upgrade head` → `downgrade -1` → `upgrade head`, y además `downgrade base` → `upgrade head` para confirmar que **todo el revertido**, no solo el de la última revisión, regresa a una base vacía y vuelve a subir sin dejar restos). Este trabajo no reemplaza las pruebas de API —que siguen corriendo sobre SQLite— ni sustituye el respaldo y la revisión de `alembic upgrade head --sql` antes de producción; cubre que el SQL de las migraciones sea válido en el motor real y que el esquema migrado sea el que los modelos prometen.

## Una prueba de metas que solo fallaba de madrugada

`tests/test_member_goals_api.py` cayó al correr la suite completa cerca de la medianoche UTC: la prueba tomaba `today` de `datetime.now(timezone.utc).date()` y el servicio rechaza la meta con `target_date < club_date(...)`, que usa `APP_TIMEZONE` (`America/Mexico_City`, UTC−6). Entre las 00:00 y las 05:59 UTC el «hoy» de la prueba y el «hoy» del club son días distintos, así que «ayer» según la prueba es hoy según el club y el `POST` responde `201` donde la prueba exige `422`. Se corrigió la prueba, no la regla: ahora toma `club_date(datetime.now(timezone.utc))` de `app.timezone`, el mismo helper que consume el servicio, porque lo que se quiere fijar es la **ventana de un día** de la regla, no dos calendarios que solo coinciden ocho horas al día. Las demás pruebas con fecha relativa (`test_reports_api`, `test_reconciliation_api`, `test_maintenance_api`, `test_routines_api`) usan márgenes de 14, 30 o 60 días, donde un día de desfase no cambia el resultado; quedan como están y se revisará si alguna se vuelve sensible.

## Evidencia esperada

- logs de prueba
- screenshots de flujo crítico
- salidas de auditoría y event logs
- resultados de carga bajo condiciones reales

## Estado

La suite automatizada del backend cubre 200 pruebas, el build de producción del panel pasa y el typecheck de la app móvil pasa. La conciliación se verificó de extremo a extremo en vista previa; los complementos PPD cuentan con pruebas de API, un seed de vista previa y verificación en navegador (selector PUE/PPD con forma `99`, tabla de parcialidades, descargas XML/PDF y rechazo de un importe mayor al saldo). La cartera PPD cuenta con una prueba de API que backdatea facturas para cubrir los cuatro tramos, comprueba que los complementos solicitados no reducen el saldo, y valida filtros, paginación y liquidación; su pestaña se verificó en la vista previa. Las metas del socio se verificaron en navegador (activa, cancelada y cumplida; alta, edición y cancelación) y las fotos de progreso cuentan con una prueba de ciclo de vida que cubre permisos, validación por firma, límite de tamaño, almacenamiento, descarga autenticada y eliminación, además de verificación en navegador de la galería, el visor, la carga y la eliminación. Las fotos de progreso desde la app cuentan con 1 prueba de ciclo completo (consentimiento como precondición y sin duplicado, origen `app`/`staff`, propiedad con `404`, enlaces firmados y eliminación de fotos propias y del personal) y verificación en navegador de la casilla de consentimiento, la carga de un PNG, la galería, el visor con origen y los dos borrados. La gráfica de evolución de medidas se verificó en navegador con las cuatro métricas, una serie plana, la meta activa de referencia y el estado con menos de dos mediciones, sin cambios de API. Las reservas de clases del socio cuentan con 4 pruebas de API (cartelera, reserva, lista de espera promovida, aforo, propiedad, clase iniciada y membresía vencida) y verificación en navegador de cancelación y reserva desde la app. Las rutinas y el progreso del socio cuentan con 3 pruebas de API (listado, detalle con versión fija, progreso con metas, propiedad y aislamiento) y verificación en navegador del resumen, la meta de peso, las medidas y el plan de 5 ejercicios. Los pagos y el estado de cuenta del socio cuentan con 2 pruebas de API (historial y saldo, orden descendente con saldo acumulado, paginación, límites, propiedad y aislamiento) y verificación en navegador del saldo, los pagos de membresía y los movimientos. Las facturas del socio cuentan con 2 pruebas de API (alcance por socio, orden, paginación, factura sin timbre sin enlaces, descargas PDF/XML, firma alterada y vencida, reutilización de firma entre tipos y aislamiento de tokens) y verificación en navegador de la tarjeta del inicio, la lista de dos comprobantes, la factura sin timbre sin botones y la descarga real de PDF y XML por enlace firmado. La solicitud de facturas del socio cuenta con 2 pruebas de API (operaciones elegibles y exclusiones, perfil persistido, replay y conflictos de idempotencia, origen ajeno o robado, venta a cuenta, RFC inválido, PPD, canal `member_app` con actor nulo y aislamiento de tokens) y verificación en navegador de la lista de cinco operaciones, la solicitud de una factura en estado «Solicitada», el perfil guardado, el prellenado en el siguiente intento y las cuatro operaciones restantes. Los avisos de estado de factura cuentan con 2 pruebas de API (silencio en `requested`, timbrado con folio/importe y sin duplicado al reintentar, cancelación, aislamiento entre socios, factura de mostrador sin destinatario, rechazo del PAC con `502` y recuperación posterior) y verificación en navegador del aviso «Factura timbrada», su marcado como leído y la apertura de Facturas. El registro de entrenamientos y medidas desde la app cuenta con 2 pruebas de API (alta con origen y estado, actualización de meta, reglas, revisión del entrenador, propiedad y aislamiento) y verificación en navegador del alta, la validación, el origen en el panel y la revisión. Las series de entrenamiento cuentan con 2 pruebas de API (ciclo completo con orden por plan, entrenamiento sin series, alta del personal y revisión; ejercicio fuera del plan, duplicados y rangos) y verificación en navegador del panel y de la app, con el registro visible en el otro canal. Las metas desde la app cuentan con 1 prueba de ciclo completo (alta con origen `app`, reglas reutilizadas, propiedad, aislamiento, avance, cancelación y logro automático, origen en el panel) y verificación en navegador en ambos canales. La bandeja de avisos del socio cuenta con 2 pruebas de API (los seis tipos de aviso, el recordatorio diferido de vencimiento y su deduplicación, marcación idempotente, `read-all`, alcance por sesión y texto congelado) y verificación en navegador de la insignia del inicio, la lectura individual y el marcado en bloque. El aviso de equipo fuera de servicio cuenta con 2 pruebas adicionales (audiencia por versión congelada de la asignación, asignación cancelada fuera, deduplicación por día del club en los dos caminos: `set_equipment_status` y el ticket `critical`) y verificación por API en vista previa con una cuenta de mantenimiento creada en la base local. El resumen de la agenda filtrado por búsqueda cuenta con 1 prueba que falla sin la corrección (`total = 3` en lugar de `1`) y, con ella, el aviso de producto cartesiano desaparece de toda la suite; además se cotejó sobre los datos reales de vista previa. La bandeja de avisos del personal cuenta con 2 pruebas de API: la primera siembra entrenador y técnico con cuenta, un empleado con cuenta desactivada y otro sin cuenta, y verifica que el entrenamiento desde la app deja exactamente un `workout_pending_review` (con socio, rutina, `ref_id` y texto correctos) mientras el registro del personal no genera nada, que el empleado desactivado queda sin filas, que el ticket sin asignar no avisa y el asignado sí, que reasignar al mismo técnico no duplica por el `dedupe_key`, que reasignar a un empleado sin cuenta no agrega avisos y que el marcado individual y el `read-all` no tocan la bandeja de otra cuenta; la segunda cubre el alcance: `401` sin token y con token de socio (en las tres rutas de escritura y lectura), el dueño viendo `total 0` y recibiendo `404` al marcar el aviso ajeno, `404` de un UUID inexistente, `read-all` del dueño devolviendo `{"updated": 0}` y el entrenamiento quedando en `status = "logged"`. En el panel se verificó en navegador con una cuenta de entrenador creada en la base local de vista previa (contraseña únicamente local, nunca versionada): el resumen firmado como «Entrenador» con la bitácora de accesos oculta por RBAC, la campana con «Notificaciones, 1 sin leer» y su insignia, el popover listando el aviso real («Ana López registró la rutina Fuerza Full Body del 27/10/2026 desde la app»), el toque individual que dejó «Todo leído» con la insignia desaparecida y `read_at` persistido en la base, y «Marcar todo leído» dejando la bandeja en 0 no leídos tras tres avisos. `GET /api/admin/notifications` y `/unread-count` sin cookie responden `401` y la consola del navegador quedó limpia; las rutas de muestra («7 membresías requieren seguimiento», «Todos los lectores están conectados») ya no existen en el código. La cartera PPD se verificó en Reportes → Ingresos como corte independiente del periodo y un complemento PPD timbrado se concilió con una línea bancaria en vista previa. La cadena de migraciones se aplica en CI contra PostgreSQL 16, con revertido y re-aplicación de la más reciente, `alembic check` entre los modelos y el esquema migrado y la aserción del `CHECK` de tipos de aviso; ese check encontró que las tres tablas de turnos y asistencia del personal no tenían migración, corregido con `20261027_0038_staffing_shifts_and_attendance.py` y verificado construyendo una base desde cero (69 tablas, check limpio, `downgrade base` → `upgrade head` sin restos). La validación de `APP_TIMEZONE` al arranque cuenta con 4 pruebas en `test_timezone_config.py` (la zona por defecto, el rechazo de una zona desconocida con el valor en el mensaje, el arranque de la app que no levanta con una zona inválida y la lectura que sigue degradando a UTC). Pendiente de ejecución en proyecto real, con un estado de cuenta bancario real y con un PAC real (el timbrado sigue siendo simulado y sin validez fiscal).
