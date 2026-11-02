# Guion de la demo comercial

**Duración:** 25–30 minutos (hay una versión corta de 10 al final).
**Audiencia:** quien va a comprar el sistema; normalmente dueño o gerente.
**Idea central:** no enseñamos diapositivas, enseñamos la operación del club en
un sistema real. El panel, la app y el kiosco hablan con el mismo backend.

> La base es sintética y la demo corre en modo vista previa. Decirlo al inicio
> genera confianza: «los datos son de ejemplo; los pagos y el timbrado están
> simulados para no tocar dinero ni SAT».

---

## Antes de que entre el cliente

- [ ] Arrancar con margen: `powershell -ExecutionPolicy Bypass -File demo\start-demo.ps1 -Reset -WithMobile`
- [ ] Entrar al panel como `owner@centrofit.mx` / `DemoGimnasio2026!`.
- [ ] Abrir un turno de caja: **Inventario → Caja y cortes → Abrir turno**
      (si ya hay uno abierto, déjalo; el guion lo aprovecha).
- [ ] Configurar el kiosco en <http://localhost:8090> con la URL
      `http://127.0.0.1:8010` y el token que imprimió el lanzador.
- [ ] Probar la app con `ana.lopez@example.com`: pedir el código, entrar y
      generar un código de acceso. Luego cerrar sesión para hacerlo en vivo.
- [ ] Dejar abiertas tres pestañas: panel (`3001`), app (`8081`) y kiosco (`8090`).
- [ ] Tener este guion en otra pantalla o impreso.
- [ ] Si la reunión es otro día, volver a correr `seed_demo.py` (o `-Reset`) para
      que las fechas de «por vencer» sigan siendo creíbles.

---

## Versión corta (10 minutos)

Para una primera llamada o un cliente con prisa:

1. **Resumen** (2 min): KPIs, aforo, últimos accesos y pendientes.
2. **Socios** (2 min): buscar a Ana, abrir su ficha y mostrar «vence en 3 días».
3. **Clases** (1 min): agenda de hoy, una sesión con cupo y una premium.
4. **Punto de venta** (2 min): vender una bebida y mostrar el inventario y la caja.
5. **App + kiosco** (2 min): código de Ana y «Acceso concedido».
6. **Cierre** (1 min): reportes y qué falta para producción.

---

## Guion de 30 minutos

### 1. Apertura (2 min)

**Pantalla:** panel en «Resumen», sesión de dueño.

**Decir:**
- «Esto no es una maqueta: el panel, la app del socio y el kiosco están
  conectados al mismo backend. Lo que hacemos aquí se refleja en los otros dos.»
- «El sistema está pensado para un solo gimnasio, con roles para dueño,
  gerencia, recepción, entrenadores y mantenimiento.»
- «Los datos son de ejemplo y los pagos están simulados; no se mueve dinero real.»

**No decir:** que ya está en producción, que factura ante el SAT o que cobra con
tarjeta real. Eso se configura después.

---

### 2. Resumen: el pulso del club (3 min)

**Ruta:** Resumen.

**Recorrido:**
1. Señala los indicadores de socios, ingresos, accesos y ocupación.
2. Baja a «Últimos accesos»: entradas y salidas con hora y lector.
3. Muestra «Atención pendiente»: renovaciones próximas y avisos.
4. Abre la campana de notificaciones y explica que son avisos reales del backend.

**Decir:**
- «El dueño abre el sistema y en diez segundos sabe cómo va el día.»
- «La ocupación y la bitácora salen de los accesos, no de un contador manual.»
- «Los avisos llegan a la campana y, si se configura, también por correo o push.»

---

### 3. Socios: alta, cobro y estado (5 min)

**Ruta:** Socios.

**Recorrido:**
1. Busca «Ana». Abre la ficha.
2. Muestra plan, vigencia, saldo y estado. Ana vence en 3 días: aparece como
   «por vencer».
3. Pulsa **Cobrar renovación**, elige efectivo o tarjeta y confirma.
4. Vuelve a la ficha: la vigencia se extendió y quedó el pago registrado.
5. Muestra **Congelar** y **Cancelar membresía** sin ejecutarlos, o congela a
   Sofía si quieres enseñar el estado «congelada».
6. Opcional: **Nuevo socio** y llena solo nombre y correo; menciona que el alta
   guarda el consentimiento de privacidad.

**Decir:**
- «El cobro en mostrador queda ligado al socio, al plan y al turno de caja.»
- «No se puede cobrar dos veces la misma renovación por error: el sistema
  controla la vigencia.»
- «El estado de la membresía es lo que consulta el kiosco para dejar entrar.»

**Si pregunta por la pasarela:** «El cobro con tarjeta en línea está integrado
con Conekta en sandbox; para producción se conectan las llaves y se certifica el
flujo. Hoy la demo usa el cobro en mostrador».

---

### 4. Accesos y kiosco: quién entra y por qué (3 min)

**Ruta:** Accesos.

**Recorrido:**
1. Filtra por entradas o busca «Ana» en la bitácora.
2. Muestra hora, sentido, lector y motivo de la decisión.
3. Pulsa **Acceso manual** y registra una entrada con motivo (no lo guardes si no
   quieres ensuciar la bitácora).
4. Ve a **Kiosco** y muestra los dispositivos, el token y la fecha de
   vencimiento.

**Decir:**
- «El kiosco no decide solo: manda el código al backend y el backend aplica la
  regla de membresía, horario, duplicados y adeudo.»
- «Todo queda en bitácora, incluso las entradas manuales y sus motivos.»
- «El token del kiosco se puede rotar o revocar sin tocar la tablet.»

---

### 5. Clases: agenda, cupo y premium (4 min)

**Ruta:** Clases → Agenda.

**Recorrido:**
1. Cambia entre días. Hay clases incluidas y premium.
2. Abre una sesión con cupo; muestra el roster y la lista de espera.
3. Marca la asistencia de un socio.
4. Abre la clase **Boxeo 20:00** (premium, $50 extra) y explica el cobro.
5. Muestra el catálogo de tipos y salones.

**Decir:**
- «La capacidad y la ventana de cancelación se validan en la base, no solo en la
  pantalla.»
- «La clase premium cobra el extra al marcar asistencia y lo liga a la reserva.»
- «La lista de espera se mueve sola cuando alguien cancela.»

---

### 6. Fisioterapia: agenda, paquetes y cierre (3 min)

**Ruta:** Fisioterapia → Agenda.

**Recorrido:**
1. Muestra la agenda de hoy y una cita con su fisioterapeuta y consultorio.
2. Abre **Paquetes**: paquete de 2 descargas y su vigencia.
3. Muestra el **Reporte** del día y el cierre de jornada.
4. Menciona que una sesión suelta exige turno de caja abierto.

**Decir:**
- «Fisioterapia no es una hoja aparte: comparte socios, caja y avisos.»
- «El paquete descuenta sesiones y controla la vigencia; se puede extender o
  anular con motivo y queda auditado.»

---

### 7. Rutinas y progreso (3 min)

**Ruta:** Rutinas → Seguimiento.

**Recorrido:**
1. Abre la asignación de Ana.
2. Muestra la rutina, las mediciones y la gráfica de peso con la meta.
3. Abre las fotos de progreso (hay fotos sembradas) y el visor.
4. Cambia a **Rutinas** y **Ejercicios** para enseñar el catálogo.

**Decir:**
- «El entrenador asigna, el socio registra y el panel ve la evolución.»
- «Las fotos se guardan fuera de la base y se sirven con enlace firmado.»
- «El socio puede pedir revisión desde la app y al entrenador le llega un aviso.»

---

### 8. Punto de venta e inventario (4 min)

**Ruta:** Inventario → Punto de venta.

**Recorrido:**
1. Si no hay turno abierto, ábrelo en **Caja y cortes**; si ya está abierto,
   muestra el estado y el efectivo esperado.
2. Agrega una bebida o suplemento al carrito.
2. Elige efectivo, cobra y muestra el cambio y el folio.
3. Ve a **Catálogo**: la existencia bajó.
4. Ve a **Caja y cortes**: la venta suma al turno y al efectivo esperado.
5. Muestra **Devoluciones** y **Cuentas por cobrar**.

**Decir:**
- «El inventario nunca queda negativo y cada movimiento deja rastro.»
- «Si se cae la red, el POS guarda la venta en el navegador y la sincroniza al
  volver; no se pierde.»
- «El corte de caja cuadra ventas, efectivo y terminal.»

---

### 9. Facturación CFDI (3 min)

**Ruta:** Facturación → Comprobantes.

**Recorrido:**
1. Abre una factura existente; muestra folio, receptor, importe y estado.
2. Muestra el PDF/XML (en vista previa el timbrado es simulado).
3. Ve a **Factura global** y **Cartera PPD**.
4. Muestra los datos fiscales del socio y la solicitud desde la app.

**Decir:**
- «El flujo CFDI 4.0 está implementado: solicitud, datos fiscales, timbrado,
  cancelación, notas de crédito y complementos de pago.»
- «En producción se conecta el PAC y se certifica; aquí no se envía al SAT.»
- «El socio puede pedir su factura desde la app sin pasar a recepción.»

---

### 10. Conciliación y reportes (3 min)

**Ruta:** Conciliación y luego Reportes.

**Recorrido:**
1. En Conciliación, muestra una cuenta bancaria, un movimiento y una sugerencia
   de pago o complemento.
2. En Reportes, cambia entre **Resumen**, **Ingresos**, **Socios**,
   **Operación**, **Mantenimiento** e **Inventario**.
3. Exporta un CSV.
4. Abre la tarjeta de **envío programado** y muestra destinatarios y reportes.

**Decir:**
- «La conciliación propone el pago que coincide; una persona confirma.»
- «Los reportes se calculan de la operación, no se capturan a mano.»
- «Se pueden programar por correo con una lista de dominios permitidos.»

---

### 11. Mantenimiento y personal (3 min)

**Ruta:** Mantenimiento → Equipos.

**Recorrido:**
1. Muestra un equipo fuera de servicio y su ticket.
2. Abre **Tickets**, **Bitácora** y **Rondas**.
3. Ve a **Personal → Equipo**, **Roles y permisos**, **Usuarios** y **Sesiones**.
4. Muestra la matriz de permisos y cierra la sesión de un usuario si quieres.
5. Cambia a la cuenta de recepción para enseñar la vista reducida (opcional).

**Decir:**
- «El equipo que se marca fuera de servicio aparece en el kiosco y en el cartel
  de recepción.»
- «Los permisos se validan en el backend; esconder un botón no es seguridad.»
- «Cada cuenta tiene su rol y sus sesiones se pueden revocar.»

---

### 12. La app del socio y el kiosco (4 min)

**Pantalla:** app en `http://localhost:8081` y kiosco en `http://localhost:8090`.

**Recorrido:**
1. Entra con `ana.lopez@example.com`. En vista previa el OTP aparece en pantalla;
   en producción llega por correo.
2. Inicio: membresía, próximo pago y avisos.
3. **Código de acceso**: se genera un código de 6 dígitos y cuenta atrás.
4. En el kiosco, teclea el código → «Acceso concedido» con el nombre del socio.
5. Vuelve a teclear el mismo código → «Entrada duplicada» (si la regla está
   activa).
6. En la app: **Clases** (reservar), **Fisioterapia**, **Rutinas**,
   **Fotos de progreso**, **Pagos** y **Facturas**.
7. Cierra sesión y, si hay tiempo, entra con Sofía (`sofia.martinez@example.com`,
   membresía congelada) para enseñar el rechazo con motivo.

**Decir:**
- «El socio no depende de recepción para su código, su recibo o su factura.»
- «El kiosco sigue la regla del club: membresía, horario, duplicados y equipos.»
- «La app es React Native/Expo; esta es la versión web de la misma app.»

---

### 13. Cierre (2 min)

**Decir:**
- «Lo que viste es el sistema completo: operación, socios, clases, fisioterapia,
  rutinas, inventario, facturación, conciliación, reportes, mantenimiento y
  personal.»
- «Para producción faltan las llaves reales de pago y PAC, el despliegue, los
  respaldos, el MFA y la migración de tus datos. Eso se cotiza y se planea
  aparte.»
- «¿Qué módulo es el que más te urge operar el primer día? Podemos empezar por
  ahí.»

---

## Preguntas frecuentes

| Pregunta | Respuesta corta |
| --- | --- |
| ¿Es multi-sucursal? | No; está diseñado para un solo gimnasio. Se puede cotizar como evolución. |
| ¿Cobra solo con tarjeta? | Hay cobro en mostrador y Conekta en sandbox; producción requiere llaves y certificación. |
| ¿Factura al SAT? | El flujo CFDI 4.0 está; falta conectar el PAC y certificar en producción. |
| ¿Se conecta al banco? | La conciliación es con estados de cuenta y captura/asistida, no con API bancaria. |
| ¿Funciona sin internet? | El kiosco conserva el shell, pero el check-in necesita servidor; el POS encola ventas sin conexión. |
| ¿Tiene biometría o torniquete? | No en esta versión; el acceso es por código y la bitácora es del sistema. |
| ¿Nómina? | Hay permisos reservados, pero el módulo de nómina no está en la demo. |
| ¿App en tiendas? | Es Expo/React Native; publicar en App Store/Play es un paso aparte. |
| ¿Migran mis datos? | Es un proyecto aparte: limpieza, mapeo y validación con el cliente. |
| ¿Cuánto tarda? | Depende del alcance; no dar fecha en la demo sin levantamiento. |

---

## Qué no prometer

- Cobros reales, devoluciones o reembolsos con dinero real durante la demo.
- Timbrado ante el SAT, cancelaciones reales o complementos de pago reales.
- Correo, WhatsApp o push reales: en vista previa se marcan como simulados.
- Nómina, biometría, torniquete, multi-sucursal o app publicada en tiendas.
- Que los datos de ejemplo son del cliente o que ya están migrados.

---

## Plan B si algo falla

| Falla | Qué hacer |
| --- | --- |
| La app no carga | Sigue con el panel y el kiosco; el código de acceso se puede generar por API o mostrar en la sección Kiosco. |
| El kiosco no autoriza | Revisa URL y token; usa **Acceso manual** y explica la regla. |
| Un seed falló al arrancar | Reinicia con `-Reset`; los logs están en `backend/.demo_runtime/logs/`. |
| El puerto está ocupado | `start-demo.ps1 -BackendPort 8011 -WebPort 3002` (y ajusta el kiosco). |
| No hay datos | Confirma que `backend/gym_preview.db` existe y que el backend está en `8010`. |
| Se acabó el tiempo | Salta a Resumen → Socios → App/Kiosco → Reportes; deja el resto para una segunda sesión. |
