# ADR-087: Renovaciones automáticas con calendario local

- Fecha: 2026-11-02
- Estado: aceptada para diseño e implementación en sandbox; producción pendiente
- Complementa ADR-003, ADR-066 y ADR-086

## Contexto

La primera entrega incluye renovación automática, pero el checkout alojado de
ADR-066 solo procesa un pago inicial y no guarda un método de pago. La política
operativa debe respetar el consentimiento del socio, evitar cargos duplicados
y mantener el acceso separado del resultado de un checkout o una redirección.

## Decisiones

- El backend programa los cobros y controla los reintentos; no se delega el
  calendario de membresías a una suscripción administrada por Conekta.
- El socio debe aceptar expresamente la renovación automática antes de guardar
  una tarjeta. La llave privada y los datos de tarjeta nunca se exponen a la
  app; se usa el tokenizador de Conekta en una página web abierta desde la app.
- La llave/token de pago reutilizable se conserva cifrado en la base. Se guarda
  únicamente una referencia de Conekta; nunca PAN ni CVV. La clave de cifrado
  se configura por entorno y no se incluye en el repositorio.
- Para una membresía ya pagada, registrar el consentimiento no cobra ni guarda
  la tarjeta de inmediato. En la fecha de vencimiento, el socio completa la
  captura/tokenización y ese primer cobro corresponde a la renovación normal;
  las renovaciones posteriores pueden ejecutarse automáticamente.
- Se realiza un cobro inicial en la fecha de renovación. Si falla, se reintenta
  1, 3 y 5 días después del vencimiento. No hay periodo de gracia: el acceso se
  suspende al vencer la membresía, aunque los intentos posteriores continúen.
- Si un reintento cobra después del vencimiento, el nuevo periodo empieza en la
  fecha efectiva del pago y dura los días definidos por el plan. El socio no
  pierde días pagados mientras el acceso está suspendido.
- Un resultado de cobro desconocido no se reintenta como un cargo nuevo sin
  conciliación. La llave idempotente del intento permite consultar/repetir la
  misma operación sin crear otra orden.
- La automatización solo opera en sandbox hasta completar revisión profesional,
  pruebas de proveedor, conciliación y aprobación explícita para producción.

## Consecuencias

- Deben conservarse los consentimientos, eventos de membresía, intentos y pagos
  para auditar el ciclo completo.
- El tokenizador web requiere una página con permiso de un solo uso, de corta
  vigencia y ligada al socio y al plan; el secreto no debe aparecer en rutas,
  logs ni encabezados Referer.
- La tarea programada debe serializar las membresías vencidas y crear una clave
  idempotente estable por ciclo e intento.
- La primera renovación de un socio existente requiere su intervención en la
  fecha de vencimiento para capturar la tarjeta y completar el cargo; no se
  cobra un importe de verificación ni una mensualidad anticipada al aceptar.
- La baja de la renovación detiene ciclos futuros; no cancela ni acorta el
  periodo ya pagado.
- Los cargos productivos permanecen deshabilitados; esta ADR no sustituye la
  aprobación de Conekta, seguridad, negocio ni asesoría profesional.

## Estado de implementación

- Implementados `GET/POST /member/membership/auto-renewal` y el control desde
  la app. Cada aceptación conserva la versión y el SHA-256 del texto; cada
  activación/revocación genera un evento de membresía.
- El panel ya no puede otorgar el consentimiento en nombre del socio. La ruta
  de autorización no cobra ni crea intentos o pagos.
- Pendientes: tokenización web en la fecha de vencimiento, cifrado y custodia
  del método, motor local de renovaciones/reintentos, suspensión efectiva y
  validación sandbox. Producción no está habilitada.

## Referencias

- [Módulo de membresías y cobro](../02-modulos/membresias-y-cobro-recurrente.md)
- [Proceso de renovación](../03-procesos/renovacion-y-cobro-recurrente.md)
- [ADR-066: Primer pago en línea con checkout alojado](ADR-066-primer-pago-en-linea.md)
- [Tokenizador web de Conekta](https://developers.conekta.com/docs/web-tokenizer)
- [Cargo bajo demanda con tarjeta](https://developers.conekta.com/docs/cargo-bajo-demanda-1)
