# ADR-066: Primer pago en línea con checkout alojado

- Fecha: 2026-10-31
- Estado: aceptada para diseño e implementación en sandbox; producción pendiente de validación
- Complementa ADR-003 (pasarela de pago); el alcance de producto posterior se amplía en ADR-086

## Contexto

El backend ya tiene estados de intento, idempotencia, registro de pagos y procesamiento de webhooks verificados, pero el gateway disponible es de demostración. El cobro manual de mostrador sigue siendo el único flujo de pago conectado a la operación; tarjeta y transferencia en ese flujo se registran como declaradas, no autorizadas por una pasarela.

La primera integración debe permitir cobrar una membresía sin almacenar datos de tarjeta y sin activar el acceso antes de que Conekta confirme el pago. La app móvil debe poder abrir el checkout en iOS y Android sin incorporar datos sensibles de tarjeta al backend ni a la app.

## Decisión

- **Conekta es el proveedor de la primera etapa**, sujeto a completar onboarding y validar las condiciones comerciales y técnicas antes de producción.
- **El alcance técnico de este incremento es un pago único de membresía mediante checkout alojado por Conekta**, creado por el backend para una orden e intento internos concretos. No se reutiliza un enlace genérico de pago. La primera entrega del producto incluye renovación automática según ADR-086, pero requiere un flujo técnico y aprobación separados; esta decisión no afirma que ya esté implementada.
- **El monto, la moneda y el concepto se toman del plan y del intento interno**; no se aceptan montos enviados por el cliente como fuente de autoridad. El backend guarda la referencia de orden del proveedor y una relación inequívoca con el intento.
- **El retorno del navegador o de la app solo informa al usuario**. No confirma el pago ni activa la membresía. La activación ocurre únicamente después de verificar criptográficamente el webhook, validar que orden, monto, moneda y estado corresponden al intento, y procesarlo de forma idempotente.
- **Los resultados pendientes no se tratan como pagos fallidos**: SPEI u otros métodos diferidos mantienen la membresía en `pending_payment` hasta una confirmación válida o una conciliación explícita. Los pagos fallidos tampoco activan acceso.
- **No se guardan PAN, CVV ni credenciales del proveedor en base de datos o código.** La llave privada se configura por entorno; cualquier token necesario para cobros futuros requiere un flujo separado, revisión de cifrado y consentimiento explícito.
- **La renovación recurrente y los reintentos automáticos no forman parte del incremento de pago único documentado aquí.** ADR-086 los incluye en el alcance de producto y exige diseñarlos y validarlos antes de producción. Cualquier credencial o token de pago futuro requiere protección adecuada y consentimiento explícito.
- **No se habilita producción por configuración accidental.** El modo productivo requiere secretos del entorno productivo, webhook registrado, conciliación probada y aprobación explícita del responsable del gimnasio.

## Consecuencias

- La creación del checkout debe ser idempotente y almacenar la URL/referencia del checkout sin permitir que una repetición cree otra orden o cobre dos veces; este corte ya está implementado para sandbox.
- La firma y el formato de webhook deben implementarse conforme a la documentación vigente de Conekta y probarse con payloads reales de sandbox antes de aceptar eventos.
- Deben manejarse de forma segura pagos duplicados, eventos fuera de orden, checkout abandonado, pago pendiente y discrepancias de monto o moneda; una discrepancia se pone en revisión y nunca activa la membresía.
- El checkout alojado reduce el contacto de la app y del backend con datos de tarjeta y puede abrirse desde navegador móvil; la compatibilidad final debe probarse en Android e iOS.
- La autorización del pago y el timbrado CFDI son procesos separados: confirmar el cobro no equivale a timbrar una factura.
- Las pruebas automatizadas usarán respuestas simuladas y no realizarán cargos. Las pruebas de extremo a extremo usarán exclusivamente credenciales y métodos de sandbox.

## Estado de implementación

- Implementados `POST /member/membership/checkout`, el adaptador `HostedPayment` para tarjeta en sandbox y la migración `20261031_0075_hosted_membership_checkout.py`, con `provider_order_id` y `checkout_url` separados de la futura referencia del cargo.
- La app obtiene planes pagados con `GET /member/membership/plans` y abre el enlace de checkout alojado desde la pantalla de pagos. La lista se oculta si sandbox no está configurado o si el socio ya tiene una membresía no terminal; renovar y cambiar de plan siguen fuera del flujo en línea.
- La misma respuesta incluye el checkout pendiente del socio autenticado, con plan, clave idempotente y URL guardada, para reabrirlo o reintentar la creación después de cerrar la app. La consulta no crea una orden ni expone intentos de otros socios.
- Cada intento queda ligado a una sola membresía pendiente, obtiene importe y moneda del plan, y usa su UUID como clave idempotente en Conekta. La llamada de orden crea/recupera un checkout; no registra pago confirmado ni activa acceso.
- Implementado `POST /webhooks/conekta/membership`: valida RSA-SHA256 del `Digest` y el cuerpo original, `livemode=false`, tipo/estado aplicable, orden, importe, moneda y referencia del cargo antes de llamar `process_verified_webhook`. El procesamiento idempotente registra pago y activa la membresía en una sola transacción.
- Los eventos pendientes/no aplicables se ignoran. Los eventos pagados de orden/cargo se procesan; los rechazos reconocidos marcan fallido el intento sin activar acceso. Una discrepancia de método, importe o moneda queda guardada como evento `failed` con `rejected_*` para revisión y responde `409`.
- La ruta requiere `CONEKTA_MODE=sandbox` y una llave pública RSA en PEM (`CONEKTA_WEBHOOK_PUBLIC_KEY` o el archivo configurado mediante `CONEKTA_WEBHOOK_PUBLIC_KEY_FILE`). La validación está cubierta con claves efímeras y cuerpos simulados; el Compose se construyó e inició localmente con migraciones hasta `20261031_0075`, llave efímera montada y API saludable solo en localhost. Falta probar el payload real desde el sandbox de Conekta.
- Se añadió un entorno local desechable en `compose.conekta-sandbox.yml`: PostgreSQL independiente, backend con migraciones y puertos locales, relay de túnel limitado a la ruta del webhook y script para crear/consultar una orden sintética de sandbox. No publica la API completa ni usa credenciales ajenas del `.env`.
- El modo E2E requiere que el responsable del gimnasio cree la cuenta sandbox, obtenga la API key y llave pública, registre la URL temporal en el panel y use una tarjeta de prueba oficial. No se requiere compartir llaves; el flujo es temporal y no habilita producción.
- No se habilita modo productivo ni se han usado credenciales o realizado cargos.

## Requisitos para producción

1. Validar contrato, comisiones, métodos y condiciones de Conekta con el negocio y el proveedor.
2. Verificar la implementación de firma de webhook y los eventos aplicables en la versión vigente de la API.
3. Ejecutar pruebas de sandbox para tarjeta, pagos pendientes, duplicados, reintentos de entrega y discrepancias.
4. Probar apertura y retorno del checkout en Android, iOS y navegador administrativo.
5. Acordar operación de conciliación, reembolsos, cancelaciones y soporte para pagos sin webhook.
6. Revisar la integración con seguridad y con asesoría fiscal antes de habilitar producción.

## Referencias

- [ADR-003: Pasarela de pago](ADR-003-pasarela-de-pago.md)
- [Integración de pasarela de pago](../04-integraciones/pasarela-de-pago.md)
- [Módulo de membresías y cobro](../02-modulos/membresias-y-cobro-recurrente.md)
- [Checkout de Conekta](https://developers.conekta.com/docs/componente-de-pago)
- [Pagos con tarjeta en Checkout](https://developers.conekta.com/docs/cargo-unico-tarjetas-component)
- [Verificación de firmas de webhook](https://developers.conekta.com/docs/autenticación-webhooks)
- [Tokenizador móvil de Conekta](https://developers.conekta.com/docs/checkout-tokenizer-sdk)
- [Pagos de prueba de Conekta](https://developers.conekta.com/docs/realizar-pagos-sandbox)
- `backend/src/app/modules/memberships/conekta.py` (configuración de llave y verificador de firma)
- `backend/src/app/modules/memberships/conekta_webhooks.py` (parser y validación de eventos de sandbox)
- `backend/tests/test_member_conekta_webhook_api.py`
- `backend/tests/test_conekta_webhook_payload.py`
- `backend/scripts/conekta_webhook_relay.py`
- `backend/scripts/create_conekta_sandbox_checkout.py`
- `compose.conekta-sandbox.yml`
- `backend/tests/test_conekta_webhooks.py`
