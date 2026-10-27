# Seguridad y privacidad

## Objetivos

- proteger datos sensibles, finanzas y biometría
- cumplir LFPDPPP, consentimiento y derecho ARCO
- mantener registros de auditoría para cambios críticos

## Principios

- cifrado en tránsito con HTTPS
- en reposo para datos sensibles y plantillas biométricas
- autenticación con MFA para administradores
- permisos validados en backend
- secretos solo en variables de entorno

## Datos personales y biométricos

- los datos sensibles requieren aviso de privacidad y consentimiento explícito
- la huella se almacena como plantilla cifrada, no como imagen
- se ofrece alternativa de acceso por QR o tarjeta para quien no autoriza biometría
- el socio puede ejercer derechos ARCO por medio de un flujo explícito en la app o web
- el estado de cuenta contiene datos financieros personales: solo se envía o reintenta a petición de un usuario con `sales.manage`, al correo registrado del socio o a un destinatario explícito; los recordatorios de cobranza solo se envían al correo registrado. En producción el transporte SMTP debe usar TLS y las descargas no se cachean (`Cache-Control: no-store`). El historial de envíos se lee con `sales.read` y muestra destinatario, usuario, formato, propósito, corte, estado y error; no expone el contenido del documento. Los recordatorios solo se envían a socios con saldo vencido, respetan un cooldown de 7 días y reportan el resultado por socio. En vista previa el envío se simula y no contacta un servidor real.
- el perfil fiscal (`member_fiscal_profiles`) y el snapshot del receptor de cada factura contienen datos personales/fiscales (RFC, razón social, régimen, domicilio y correo). Se capturan con `billing.request`, se consultan con `billing.read` y solo se usan para facturar; no se comparten con terceros fuera del PAC. Cada factura conserva su propio snapshot, así que editar el perfil no reescribe comprobantes emitidos. Falta definir con asesoría legal su retención y el procedimiento ARCO aplicable.
- la conciliación bancaria guarda solo nombre de cuenta, banco, últimos cuatro dígitos y moneda; **nunca** número completo, CLABE, credenciales bancarias ni el archivo del estado de cuenta. Las líneas importadas, sus referencias, descripciones, notas y la operación interna vinculada son datos financieros internos: se consultan con `finance.read` y solo se modifican con `finance.manage`, siempre con actor, fecha y motivo en `bank_movement_events`. Las notas de diferencia pueden contener datos de terceros; su retención y acceso deben definirse con asesoría legal. La conciliación no genera ni envía estados de cuenta a socios.
- las **fotos de progreso** son imágenes corporales del socio y se tratan como datos sensibles. La base solo guarda metadatos (`progress_photos`); los bytes se escriben fuera de la base en `PROGRESS_PHOTOS_DIR` (ignorado por Git) con nombre aleatorio, directorio `0700` y archivo `0600`, sin conservar el nombre original ni aceptar rutas del cliente. La carga valida la **firma binaria** y el tamaño máximo de 8 MB, y la descarga solo se sirve por una ruta autenticada con `routines.read` con `Cache-Control: private, no-store` y `X-Content-Type-Options: nosniff`. La eliminación es explícita e irreversible y no registra actor ni fecha: no hay bitácora de borrado, cifrado en reposo, consentimiento específico, retención ni acceso restringido al socio titular, así que antes de producción hay que definirlos y evaluar almacenamiento de objetos cifrado con respaldo.

## Facturación y documentos fiscales

- el XML y los datos del timbre se guardan en `invoices.xml_content` y se descargan con `billing.read` y `Cache-Control: no-store`. El PDF se genera al momento (no se almacena) y solo se entrega para facturas timbradas o canceladas; las simuladas llevan marca de agua y aviso de que no tienen validez fiscal.
- la factura global se consulta con `billing.read` y se emite o cancela con `billing.manage`; su lote (`global_invoice_sales`) solo conserva folio, fecha y total de ventas de público en general, sin datos del socio, y el receptor fijo no tiene correo ni envío. Una global viva bloquea la factura individual de sus ventas hasta cancelarla.
- la nota de crédito (CFDI de egreso) copia el snapshot del receptor de la factura original y solo puede emitirse, timbrarse o cancelarse con `billing.manage`; la relación (`related_invoice_id`) usa FK restrictiva y el saldo se revalida con la factura bloqueada. La nota conserva su motivo y la nota libre (hasta 300 caracteres) en `invoice_events`, no agrega datos del socio y no permite borrar la factura original.
- el complemento de pago PPD copia el snapshot fiscal del receptor de la factura original (RFC, razón social, régimen, código postal) y usa el uso `CP01`. Su XML se guarda en `invoice_payments.xml_content` y se descarga con `billing.read` y `Cache-Control: no-store`; el PDF se genera al momento y solo se entrega para complementos timbrados o cancelados, con marca de simulación cuando aplica. Registrar, timbrar o cancelar un complemento exige `billing.manage`; cada intento queda en `invoice_payment_events` (append-only, sin secretos) y el complemento **no se envía por correo** en esta versión.
- el envío por correo del CFDI exige `billing.request`, solo acepta facturas timbradas y adjunta PDF y XML al correo del receptor o a un destinatario explícito. Cada envío queda en `invoice_events` con destinatario, adjuntos, estado (`sent`/`simulated`) y error, sin guardar los archivos ni credenciales; en vista previa se simula y no contacta SMTP. En producción el transporte debe usar TLS y una cuenta dedicada; el envío es síncrono y no hay confirmación de entrega.
- el PDF y el correo contienen datos fiscales personales (RFC, razón social, domicilio y correo): se aplican las mismas reglas de acceso que el XML y falta definir con asesoría legal su retención y el procedimiento ARCO.
- las credenciales del PAC y del emisor viven solo en variables de entorno; nunca se guardan en la base, en la factura ni en la bitácora.
- `invoice_events` es append-only: solicitudes, intentos de timbrado, notas de crédito y cancelaciones conservan actor, fecha, estado anterior/nuevo y detalle sin secretos. Una factura o nota no se borra; cancelar conserva folio, motivo y UUID sustituto.
- en vista previa el timbrado es **simulado**: `SimulatedPac` no contacta al SAT, no produce UUID ni `TimbreFiscalDigital` y la UI lo marca como SIMULACIÓN. Nunca debe presentarse como comprobante fiscal válido. Con un PAC real configurado sin adaptador, el timbrado falla con `503` en vez de simular.

## Auditoría

Se registran:

- cambios de permisos
- accesos manuales
- cobros, descuentos y cancelaciones; cada cobro manual de membresía guarda intento idempotente, pago, periodo, turno de caja, usuario que cobró y nota opcional, sin datos de tarjeta
- ajustes de inventario
- envíos, recordatorios de cobranza y reintentos del estado de cuenta del socio (destinatario, formato, propósito, corte, resultado y enlace al intento original)
- decisiones de conciliación bancaria: importación de líneas, vínculo con una operación interna (con diferencia y motivo), desvinculación y marcado para revisión, con actor y fecha en `bank_movement_events`. La línea conserva solo su estado actual y actores/fechas de la última conciliación y revisión; los cambios de cuenta (alta y estado) no tienen bitácora propia más allá de `created_by`
- decisiones salariales o de nómina
- facturas y anulaciones: cada solicitud, intento de timbrado y cancelación queda en `invoice_events` con actor, estado anterior/nuevo, motivo del SAT, UUID sustituto (si aplica) y referencia del PAC; el XML queda asociado a la factura y la cancelación nunca borra el comprobante

## Seguridad operativa

- respaldo diario automático
- política de copias por fecha, zona horaria y retención mínima
- bitácora de incidentes y recuperación ante desastres
- revisiones periódicas de permisos y sesión
- los CSV de estados de cuenta se procesan en el navegador y solo se envían las filas necesarias por HTTPS; el archivo completo no se almacena en el servidor ni en la bitácora. La bandeja exige sesión autenticada y `finance.read`, y toda escritura valida `finance.manage` en el backend

⚠️ Los aspectos legales, fiscales y de datos biométricos deben ser validados por profesionales especializados.
