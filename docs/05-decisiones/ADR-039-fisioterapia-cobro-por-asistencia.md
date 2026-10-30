# ADR-039: Fisioterapia con cobro por asistencia y agenda de recepción

- Fecha: 2026-10-29
- Estado: aceptada (los tres incrementos implementados; el 3 el 2026-10-30)

## Contexto

El club quiere ofrecer fisioterapia en un espacio propio: descargas musculares y atención de molestias o lesiones que no requieren diagnóstico médico. El módulo 9 ya diseñaba «servicios extra» de forma genérica —con un modelo de servicio, recurso, agenda y precio— y dejaba la nutrición como ejemplo; la fisioterapia cabía ahí, pero sus reglas de cobro tienen una particularidad que el modelo genérico no resolvía: el club no quiere cobrar una sesión que no se prestó.

La disyuntiva inicial era si el servicio va dentro de un plan con dos sesiones al mes o si se vende aparte. Se decidió que convivan: la sesión suelta se cobra al asistir y el paquete de dos sesiones se paga por adelantado con descuento. Eso obliga a separar dos ideas que suelen ir juntas:

- **el cargo**: dinero que se cobra por un servicio que el socio no había pagado;
- **el consumo**: un crédito de un paquete que el socio ya pagó.

El club decidió que la inasistencia no produce ninguno de los dos. No se cobra la sesión suelta y no se descuenta el crédito del paquete; el lugar vacío lo absorbe el club, no el socio. Es la misma línea que el club ya fijó para las clases —sin penalizaciones por inasistencia ni cancelación tardía—, aplicada ahora a un servicio que se cobra por separado.

Además, la agenda no la lleva el socio: la lleva recepción. La app del socio es una ventana para saber qué le queda y cuándo es su cita, no un motor de reservas. Eso evita disponibilidad pública, políticas de cancelación desde el teléfono y cobro en línea, que están fuera de alcance.

## Decisión

- **Solo la asistencia mueve dinero o saldo.** Marcar una cita como `attended` cobra la sesión suelta o descuenta un crédito del paquete. `no_show` y `cancelled` no hacen ninguna de las dos cosas. No hay ventana de cancelación, penalización ni deuda por inasistencia; una llegada a la que ya no se le puede dar la sesión se cierra como `no_show` y no se cobra.
- **La sesión suelta se cobra al asistir, no al agendar.** El cargo es una venta de servicio de una línea con SKU `FISIO`, ligada a la cita por `sales.physio_appointment_id`, con turno de caja abierto y la forma de pago elegida por recepción. Es el mismo camino que el cobro de una clase premium (ADR-033): el ledger, el turno, los reportes y la facturación no cambian.
- **El paquete es un saldo prepagado, no una suscripción.** Dos sesiones pagadas en una sola exhibición con 20 % de descuento sobre las dos sueltas. Se guarda el precio final y el de lista para mostrar el ahorro; el descuento vive en el catálogo y no se recalcula si cambia el precio suelto. No hay cargo recurrente, parcialidades ni renovación automática: si el club ofreciera parcialidades, el descuento no aplicaría.
- **El crédito se descuenta al asistir, nunca al agendar.** Una cita que no se presenta deja el paquete intacto. Para que no se pierda por descuido, los créditos se consumen en orden de vencimiento y la vigencia es de 31 días desde la compra; los no usados vencen, porque el paquete es una mensualidad y no una cartera perpetua.
- **La agenda la opera recepción.** `POST /admin/physio/appointments` y sus acciones de mover, cancelar y marcar viven en el panel con `physio.manage`; la app del socio solo consulta. El fisioterapeuta recibe `physio.read` para ver su día y `physio.manage` solo si el club decide que también marque la asistencia.
- **El socio se entera por su bandeja.** Al agendar, mover o cancelar se escribe un aviso en `member_notifications` dentro de la misma transacción, con tres tipos nuevos (`physio_appointment_scheduled`, `physio_appointment_cancelled`, `physio_appointment_rescheduled`) y su migración del `CHECK` de tipos. Sin push ni correo: el socio lo ve al abrir la app, como el resto de los avisos, y puede saltar a su pantalla de fisioterapia desde el aviso.
- **El paquete se corrige, no se reembolsa.** Gerencia puede extender la vigencia o anular los créditos restantes, con motivo obligatorio y bitácora (`physio_pack_adjustments`). Extender solo mueve la fecha de vencimiento; anular cancela las citas futuras cubiertas y las avisa, pero no devuelve dinero: la venta sigue en el turno y, si el club quiere devolverla, usa la devolución de servicios de caja (ADR-034). Ambas rutas exigen el permiso `physio.adjust`, que solo tienen dueño y gerente, para que recepción opere la agenda sin decidir sobre saldos ya cobrados.
- **La marca es atómica y corregible.** La cita y el paquete se leen con `SELECT ... FOR UPDATE`; dos marcas simultáneas no cobran ni descuentan dos veces. La corrección `attended ↔ no_show` se permite dentro de las 24 horas siguientes al fin de la cita, revirtiendo el cargo y el crédito. La garantía de concurrencia es de PostgreSQL, así que se comprueba con una prueba opt-in contra `TEST_POSTGRES_URL`, igual que la del reembolso de servicios.

## Consecuencias y límites

- **El club absorbe las inasistencias.** Es una decisión de negocio, no un olvido: no hay ingreso por una cita que no se presentó, pero tampoco deuda ni fricción con el socio. Si el club cambia de opinión, hará falta un cargo de penalización con su propia regla y su propio aviso.
- **El paquete vence.** Un crédito que nunca se agendó se pierde a los 31 días; el que sí se agendó y no se presentó no se pierde. La extensión y la anulación cubren los casos legítimos sin tocar el dinero; una devolución del paquete sigue sin modelarse y exigiría revertir la venta y sus créditos.
- **No hay autoservicio.** Mover o cancelar exige llamar o pasar a recepción. La app no tiene botones de reserva a propósito; si más adelante se abre, necesita disponibilidad pública, política de cancelación y cobro en línea.
- **No es un expediente clínico.** El sistema guarda la cita, el servicio y su estado; no guarda diagnósticos ni notas clínicas. Es una decisión de privacidad: si el club las necesita, exigen su propia entidad cifrada, control de acceso y retención.
- **La especialidad y el consultorio del fisioterapeuta son opcionales.** Desde el incremento 3 existe el catálogo, pero recepción sigue pudiendo agendar con cualquier colaborador activo: si no hay perfil, la cita se agenda sin especialidad y con el consultorio que se escriba. El consultorio tampoco se reserva como recurso; el recurso limitante sigue siendo el fisioterapeuta.
- **El traslape se valida en el servicio, no en la base.** Un índice único sobre el inicio exacto atrapa el duplicado idéntico, pero dos recepcionistas simultáneas podrían crear citas parcialmente encimadas del mismo fisioterapeuta. Es la misma deuda que ya tiene la agenda de clases.
- **El recordatorio se materializa al leer la bandeja.** No hay programador de tareas: el aviso de 24 horas se escribe la primera vez que el socio abre sus avisos dentro de esa ventana, con el mismo mecanismo de `class_reminder`. Un socio que no abre la app no lo recibe, igual que pasa con el resto de los avisos del club.
- **El reembolso del paquete no existe.** El cobro suelto sí se devuelve por la ruta de servicios de caja (ADR-034); un paquete se corrige anulándolo —que cancela créditos y citas futuras sin mover dinero— y, si el club debe devolver el importe, la venta se devuelve aparte por la caja.
- **La compra del paquete no avisa.** El socio lo ve en su saldo; el aviso se reserva para las citas, que es lo que tiene fecha. La anulación sí avisa, porque cancela citas.
- **El reporte del consultorio es propio y de solo lectura.** Calcula sobre las tablas de fisioterapia y el ledger de ventas, sin guardar agregados; los cargos siguen apareciendo además como «Servicios» en el reporte de ingresos. La ocupación es una estimación sobre 8 horas de agenda por fisioterapeuta y día.

## Referencias

- `docs/02-modulos/fisioterapia.md` (alcance, flujos, entidades e incrementos)
- `backend/src/app/modules/physio/service.py` (catálogo, paquetes, agenda, asistencia y cierre del día)
- `backend/src/app/modules/physio/reports.py` (reporte del consultorio y exportación CSV)
- `backend/alembic/versions/20261029_0055_physiotherapy.py`, `20261029_0056_physio_permissions.py`, `20261029_0057_physio_notifications.py`, `20261030_0058_physio_control.py`
- `backend/src/app/modules/portal/physio.py` (modelo de lectura del socio)
- `backend/src/app/modules/inventory/service.py` (`register_service_sale`, `refund_service_sale`)
- `backend/src/app/modules/classes/service.py` (`mark_attendance`, `_charge_premium_attendance` como precedente)
- `backend/src/app/modules/notifications/models.py`, `backend/src/app/modules/identity/service.py`
- ADR-033, ADR-034, ADR-036, ADR-037
