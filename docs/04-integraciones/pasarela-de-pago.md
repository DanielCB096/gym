# Pasarela de pago

## Contexto

La pasarela debe soportar cobros recurrentes, tokenización, reintentos, Webhooks y conciliación con bancas y SPEI.

## Opciones comparadas

| Proveedor | Fortalezas | Consideraciones |
|---|---|---|
| Conekta | muy fuerte en México, suscripciones, tokens | requiere integración con API y webhooks |
| Stripe México | robusto global, excelente API | puede ser más costoso y con complejidad más global |
| OpenPay | popular en México y local | validación de infraestructura y soporte |
| Mercado Pago | local y muy conocida | suscripciones tienen matices propios y soporte variable |

## Recomendación

Se recomienda Conekta por su enfoque local, soporte de suscripción, tokenización y compatibilidad con pagos recurrentes en México.

## Reglas de diseño
- el sistema no guarda números de tarjeta
- se usa token del proveedor
- cada cobro genera event log y idempotency key
- los reintentos y webhooks quedan en cola y reintentos automáticos

⚠️ La decisión final debe validarse con el negocio y con el proveedor antes de producción.

## Primera etapa: pago único en línea

ADR-066 fija el primer alcance técnico: usar Conekta para un pago único de membresía mediante un checkout alojado, creado por el backend para un intento interno específico. No se usará un enlace genérico reutilizable ni se guardarán datos de tarjeta en la aplicación.

El endpoint autenticado `POST /member/membership/checkout` ya crea una orden `HostedPayment` de **tarjeta únicamente** para el plan seleccionado por el socio. Requiere `Idempotency-Key` y devuelve el intento junto con `checkout_url`; el importe y la moneda provienen del plan, y la orden contiene referencias internas para asociarla al intento. Los datos de checkout y la URL se guardan en la migración `20261031_0075_hosted_membership_checkout.py`. Si Conekta no responde, se conserva el intento pendiente y repetir la misma clave reintenta la creación con la misma clave idempotente del proveedor.

Esta ruta solo opera en sandbox: exige `CONEKTA_SANDBOX_API_KEY`, `CONEKTA_SUCCESS_URL` y `CONEKTA_FAILURE_URL` por entorno, y rechaza cualquier `CONEKTA_MODE` distinto de `sandbox` (el valor por defecto). La llave debe obtenerse desde el modo de pruebas del panel de Conekta; nunca se debe asignar una llave productiva a `CONEKTA_SANDBOX_API_KEY`. Los dos URL de retorno deben ser HTTPS. La integración todavía no habilita producción.

El endpoint público `POST /webhooks/conekta/membership` recibe el webhook y exige `CONEKTA_WEBHOOK_PUBLIC_KEY` (llave pública PEM RSA del webhook sandbox). Verifica RSA-SHA256 del cuerpo original mediante `Digest` antes de interpretar el JSON, exige `livemode=false` y solo reconoce estados de pago aplicables. El evento de verificación `webhook_ping` se acepta y responde como ignorado, sin requerir un objeto de pago. Correlaciona la orden por `provider_order_id` y compara importe/moneda con el intento interno antes de llamar `process_verified_webhook`. La activación y la creación del pago confirmado suceden en una transacción idempotente; los eventos de pago pendiente se ignoran y no activan membresías. Una discrepancia firmada se registra como evento fallido y responde `409` para revisión. Otro payload firmado que no cumple el formato esperado responde `422` y deja una advertencia con el ID, tipo y motivo del rechazo; no registra el cuerpo, la firma ni otros datos del evento. El retorno a la app o al navegador sigue siendo informativo. Métodos diferidos como SPEI no están habilitados.

**Estado:** checkout y endpoint de webhook implementados y limitados a sandbox. El 2026-10-31 se completó una prueba E2E de $10 MXN: Conekta envió el webhook firmado, el backend lo validó, el intento terminó en `succeeded` y la membresía en `active`. La ruta de retorno no confirma el pago; solo lo hace el webhook. Sigue pendiente la conciliación operativa y la aprobación del responsable; no existe integración productiva. Antes de liberar cobros reales se requiere validar las condiciones comerciales, configurar secretos solo en el entorno y obtener revisión técnica/profesional.

Para preparar la prueba E2E local sin publicar la API completa, el repositorio incluye `compose.conekta-sandbox.yml`, un relay que solo enruta `POST /webhooks/conekta/membership` y `backend/scripts/create_conekta_sandbox_checkout.py`. El backend queda ligado a localhost, PostgreSQL usa un volumen de prueba aparte y Cloudflare Quick Tunnel expone únicamente el relay temporal; el procedimiento paso a paso está en [backend/README.md](../../backend/README.md#prueba-e2e-local-de-conekta-sandbox). Crear la cuenta de Conekta y registrar el endpoint en su panel requiere intervención del responsable y no se automatiza ni necesita compartir credenciales con el equipo.

La renovación recurrente, el almacenamiento de métodos de pago y los reintentos automáticos no pertenecen a este primer incremento. Tampoco se iniciarán cargos reales ni se guardarán tokens en esta etapa.

Referencias: [ADR-066](../05-decisiones/ADR-066-primer-pago-en-linea.md), [Checkout de Conekta](https://developers.conekta.com/docs/componente-de-pago), [verificación de firmas de webhook](https://developers.conekta.com/docs/autenticación-webhooks), [sandbox de Conekta](https://developers.conekta.com/docs/realizar-pagos-sandbox).
