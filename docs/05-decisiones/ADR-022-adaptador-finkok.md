# ADR-022: El PAC real es Finkok y sella en su servidor

- Fecha: 2026-10-28
- Estado: propuesta inicial

## Contexto

Desde el primer incremento fiscal (2026-10-23) el club factura en **simulación**: `pac_gateway()` devuelve `SimulatedPac`, que no contacta al SAT y no produce UUID ni `TimbreFiscalDigital`. Para cualquier proveedor real respondía `503` en vez de simular, que era lo correcto mientras no existiera un adaptador, pero dejaba el módulo sin poder emitir un comprobante con validez fiscal.

El límite ya estaba bien dibujado: el pre-CFDI se construye sin sello ni certificado, el PAC devuelve un `StampOutcome`/`CancellationOutcome`, `PacRejected` se traduce a `502` y `PacUnavailable` a `503`. Faltaba decidir **cómo** cruzar ese límite sin arrastrar un stack de XML y criptografía que el club no puede mantener todavía.

Finkok ofrece dos caminos: `sign_stamp`, que sella el XML con el CSD cargado en el perfil del emisor y lo timbra en una sola llamada, y `cancel`, que exige el CSD en PEM con la llave cifrada en 3DES con una contraseña que entrega Finkok. La alternativa era firmar localmente la cadena original con `cryptography`, custodiar la llave privada en la aplicación y validar el sellado por nuestra cuenta.

## Decisión

- **Finkok es el primer PAC real**, seleccionado con `PAC_PROVIDER=finkok`. `FinkokPac` vive en `billing/finkok.py` y `pac_gateway()` lo importa de forma diferida para no crear un ciclo con los tipos de resultado.
- **El timbrado usa `sign_stamp`**: no hay firma local ni custodia de la llave para timbrar. El pre-CFDI viaja en base64 a `/servicios/soap/stamp` con `SOAPAction: sign_stamp`; antes de enviarlo se vacía el `NoCertificado` marcador de veinte ceros (`NoCertificado=""`) para que Finkok elija el CSD registrado para el RFC. El `UUID`, el XML timbrado y la `Fecha` de la respuesta llenan `StampOutcome`; la fecha se interpreta en el calendario del club y se guarda en UTC.
- **La cancelación usa `cancel`**: `/servicios/soap/cancel` con `SOAPAction: cancel`, el CSD en PEM leído de `PAC_CERT_PATH` y `PAC_KEY_PATH`, `taxpayer_id` de `PAC_TAXPAYER_ID` o `GYM_RFC`, y `store_pending=0`. La llave ya debe venir cifrada en 3DES con la contraseña de Finkok: **esa conversión se hace fuera del sistema** y el adaptador solo comprueba que los archivos existan y parezcan PEM.
- **Solo `201` y `205` se registran como canceladas.** `201` es la cancelación aceptada y `205` («ya cancelado») alcanza el mismo estado final. `202` deja la solicitud en proceso en el SAT: el adaptador devuelve `accepted=False` con el mensaje del PAC, el servicio responde `202 Accepted` y la factura **sigue `stamped`** pero marcada como pendiente. `203` y `204` se rechazan con su mensaje. El servicio ahora propaga `detail["message"]` en el `502` en vez de un texto genérico.
- **La cancelación pendiente se resuelve preguntando al SAT, no a la cola de Finkok.** `FinkokPac.sat_status` llama a `get_sat_status` en el mismo servicio `cancel` con `username`, `password`, `taxpayer_id`, `rtaxpayer_id` (RFC del receptor), `uuid` y `total`, y devuelve un `SatStatusOutcome` con `Estado`, `EsCancelable`, `EstatusCancelacion` y `CodigoEstatus`. `query_pending_cancellation` no se usa porque la solicitud viaja con `store_pending=0`, así que esa cola propia de Finkok no la contiene. El servicio guarda `cancellation_requested_at`/`cancellation_checked_at` y el motivo en la factura, expone `POST /admin/billing/invoices/{id}/cancellation-check` (`billing.manage`) y registra `invoice_cancellation_pending`, `invoice_cancellation_confirmed` o `invoice_cancellation_cleared`. Un «No Encontrado» del SAT es `502` sin mutar la factura.
- **Errores separados por causa.** Una incidencia de timbrado (`Incidencias` o un `CodEstatus` de error) es `PacRejected` (`502`), deja el comprobante `failed` y permite reintentar. Un fallo de transporte, timeout, SOAP fault, HTTP de error o un éxito sin XML es `PacUnavailable` (`503`) y no cambia el estado.
- **Configuración por llamada y solo en entorno**: `PAC_USER`, `PAC_PASSWORD`, `PAC_PRODUCTION`, `PAC_BASE_URL`, `PAC_TAXPAYER_ID`, `PAC_CERT_PATH`, `PAC_KEY_PATH` y `PAC_TIMEOUT_SECONDS`. Sin credenciales, `PAC_PROVIDER=finkok` responde `503`; nunca cae a simulación.
- **Pruebas con `httpx.MockTransport`**, sin red: timbrado, incidencia, fallo de transporte, SOAP fault, cancelación aceptada, pendiente, error sin folios, falta de CSD, selección del gateway por entorno y consulta del estado en el SAT (campos enviados, error del PAC y respuesta sin `sat`). La API cubre el flujo completo con un PAC de prueba: `202` pendiente, confirmación, limpieza, filtro `cancellation_pending`, `pending_cancellations`, permisos y factura simulada sin UUID.

## Consecuencias y límites

- El club ya puede timbrar y cancelar CFDIs reales en cuanto configure credenciales y CSD; la vista previa y las pruebas conservan `SimulatedPac`.
- **No hay custodia local de la llave para timbrar**: el CSD vive en Finkok. La cancelación sí necesita los archivos en el servidor y su preparación es manual.
- **La validación contra Finkok demo tiene script pero no se ejecutó**: `backend/finkok_demo.py` arma un CFDI de prueba con el constructor real, lo timbra, valida el XML y, con `--cancel`, lo cancela con el CSD; no toca la base ni consume folios y las pruebas cubren su mitad offline. La corrida real sigue pendiente porque faltan credenciales, CSD, RFC del emisor y la revisión del contador.
- **Una respuesta perdida puede duplicar el timbrado.** Si Finkok timbra y la respuesta no llega, la factura queda `requested`; reintentar puede emitir un segundo CFDI. No hay clave de idempotencia ante el PAC ni consulta previa del resultado.
- **Las cancelaciones pendientes se siguen a mano.** Un `202` ya no queda en el limbo: la factura guarda la solicitud y el detalle muestra «Consultar estado en el SAT». No hay tarea programada ni sondeo: si nadie pulsa el botón, la solicitud puede envejecer sin confirmarse. El complemento de pago tampoco se sigue todavía.
- **La aceptación del receptor no se modela por separado**, aunque el SAT puede exigirla para ciertos motivos: se resuelve implícitamente cuando `get_sat_status` reporta `Cancelado` o «En proceso».
- **Con varios CSD en la cuenta**, el `NoCertificado` vacío hace que Finkok use el último cargado; no hay selección explícita.
- **La zona de la `Fecha`** se asume igual a la del club: si el emisor está en otra zona, `issued_at` queda desplazado aunque el XML timbrado conserve su fecha original.
- Sin reintento, cola ni circuit breaker: un timeout llega al operador como `503`.
- Antes de producción: correr `backend/finkok_demo.py` contra el ambiente demo con el CSD real, documentar la preparación del CSD, revisar la retención del XML y decidir si la consulta de cancelaciones pendientes pasa a una tarea programada.
- **Verificación del panel pendiente**: el aviso de cancelación en proceso, la insignia del listado y el botón «Consultar estado en el SAT» están implementados y pasan `tsc`, pero no se recorrió el flujo en un navegador; la consulta real contra Finkok demo tampoco se ejecutó por falta de credenciales y CSD.

## Referencias

- `backend/src/app/modules/billing/finkok.py` (`FinkokPac`, `FinkokSettings`, `prepare_prestamp`)
- `backend/src/app/modules/billing/pac.py`, `service.py` (`stamp_invoice`, `cancel_invoice`, `stamp_payment_complement`, `cancel_payment_complement`), `errors.py`
- `backend/tests/test_finkok_pac.py`, `backend/tests/test_finkok_demo_script.py`
- `backend/finkok_demo.py` (prueba de humo contra el demo)
- `docs/04-integraciones/facturacion-cfdi.md` (contrato y operación)
- ADR-003 (pasarela de pago: mismo límite entre simulación y proveedor real)
