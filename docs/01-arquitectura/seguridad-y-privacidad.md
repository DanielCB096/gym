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

## Facturación y documentos fiscales

- el XML y los datos del timbre se guardan en `invoices.xml_content` y se descargan con `billing.read` y `Cache-Control: no-store`; no hay PDF ni envío por correo en este incremento.
- las credenciales del PAC y del emisor viven solo en variables de entorno; nunca se guardan en la base, en la factura ni en la bitácora.
- `invoice_events` es append-only: solicitudes, intentos de timbrado y cancelaciones conservan actor, fecha, estado anterior/nuevo y detalle sin secretos. Una factura no se borra; cancelar conserva folio, motivo y UUID sustituto.
- en vista previa el timbrado es **simulado**: `SimulatedPac` no contacta al SAT, no produce UUID ni `TimbreFiscalDigital` y la UI lo marca como SIMULACIÓN. Nunca debe presentarse como comprobante fiscal válido. Con un PAC real configurado sin adaptador, el timbrado falla con `503` en vez de simular.

## Auditoría

Se registran:

- cambios de permisos
- accesos manuales
- cobros, descuentos y cancelaciones; cada cobro manual de membresía guarda intento idempotente, pago, periodo, turno de caja, usuario que cobró y nota opcional, sin datos de tarjeta
- ajustes de inventario
- envíos, recordatorios de cobranza y reintentos del estado de cuenta del socio (destinatario, formato, propósito, corte, resultado y enlace al intento original)
- decisiones salariales o de nómina
- facturas y anulaciones: cada solicitud, intento de timbrado y cancelación queda en `invoice_events` con actor, estado anterior/nuevo, motivo del SAT, UUID sustituto (si aplica) y referencia del PAC; el XML queda asociado a la factura y la cancelación nunca borra el comprobante

## Seguridad operativa

- respaldo diario automático
- política de copias por fecha, zona horaria y retención mínima
- bitácora de incidentes y recuperación ante desastres
- revisiones periódicas de permisos y sesión

⚠️ Los aspectos legales, fiscales y de datos biométricos deben ser validados por profesionales especializados.
