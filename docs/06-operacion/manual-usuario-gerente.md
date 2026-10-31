# Manual de usuario: gerente

## Objetivo

Orientar a gerencia en la supervisión diaria del gimnasio desde el panel, con atención a permisos, caja, acceso, personal, mantenimiento e incidencias.

## Acceso y responsabilidades

Inicia sesión con tu propia cuenta. El rol de gerente cuenta con permisos operativos amplios, pero las acciones siguen sujetas a la matriz RBAC y a las validaciones del backend. No compartas credenciales ni solicites que otro colaborador registre acciones con tu cuenta.

Al comenzar la jornada:

1. Revisa que haya personal responsable asignado a recepción y a las áreas críticas.
2. Confirma la disponibilidad del panel, backend, base de datos, Redis y kiosco.
3. Revisa avisos, solicitudes pendientes e incidencias que requieran decisión.
4. Verifica los turnos de caja, las operaciones pendientes y el estado de los equipos fuera de servicio.

Consulta el procedimiento completo en [apertura-y-cierre-del-gimnasio.md](../03-procesos/apertura-y-cierre-del-gimnasio.md).

## Supervisar socios y acceso

- Usa el directorio de socios para localizar cuentas y revisar membresía y estado de acceso.
- Las activaciones sin cobro son cortesías: confirma el motivo y conserva la trazabilidad.
- Los cobros manuales de membresía requieren un turno de caja abierto; tarjeta y transferencia se registran como declaradas y no confirman un cargo bancario.
- Revisa los accesos manuales y sus motivos en la bitácora. No uses una excepción para saltarte las reglas de membresía o adeudo vigentes del club.
- En **Kiosco**, revisa dispositivos y vencimientos de token. Rota o revoca credenciales solo cuando corresponda y no compartas los tokens fuera del proceso autorizado.

Para la atención en mostrador, consulta el [manual-usuario-recepcion.md](manual-usuario-recepcion.md) y el proceso de [acceso-con-y-sin-internet.md](../03-procesos/acceso-con-y-sin-internet.md).

## Supervisar caja y cuentas por cobrar

1. Verifica que cada turno tenga responsable y fondo inicial registrados.
2. Revisa ventas, devoluciones, cobros de membresía y pagos de cuentas por cobrar en sus registros correspondientes.
3. Para cerrar un turno, confirma que no haya ventas offline pendientes y revisa el efectivo esperado contra el conteo.
4. Si hay una diferencia, exige que quede explicada antes de finalizar el cierre.
5. Fija o modifica límites de crédito solo con el permiso correspondiente (`sales.credit`); bajar un límite no elimina la deuda existente.
6. Revisa los recordatorios o estados de cuenta enviados y sus resultados antes de autorizar un nuevo intento.

No registres datos completos de tarjetas. Las formas `card` y `transfer` del flujo manual son declaraciones del operador, no autorización de una terminal o pasarela real.

Consulta los pasos y reglas en [venta-en-mostrador-y-corte-de-caja.md](../03-procesos/venta-en-mostrador-y-corte-de-caja.md).

## Supervisar al personal

- Revisa que cada cuenta tenga solo los roles y permisos necesarios para sus funciones.
- Atiende solicitudes de corrección de asistencia dentro de los plazos configurados y deja el motivo requerido.
- Consulta el historial antes de corregir o anular una marca; la marca previa y la decisión deben conservar trazabilidad.
- Confirma que las bajas de personal y la desactivación de cuentas se realicen por el flujo previsto.

Los cambios sensibles deben quedar auditados. No ajustes permisos para resolver una operación puntual sin validar la necesidad y el alcance.

## Atender fallas y disponibilidad

- Revisa tickets por severidad y antigüedad, y asigna responsable cuando haga falta.
- Ante un posible riesgo para personas, confirma que el equipo esté detenido, señalizado y marcado fuera de servicio.
- No autorices el regreso al servicio hasta que mantenimiento confirme una revisión segura.
- Revisa los preventivos vencidos y acuerda responsables y fechas; la programación automática todavía no está disponible.

Los pasos para operar el módulo están en [manual-usuario-mantenimiento.md](manual-usuario-mantenimiento.md), [reporte-y-resolucion-de-falla-de-equipo.md](../03-procesos/reporte-y-resolucion-de-falla-de-equipo.md) y [mantenimiento-preventivo.md](../03-procesos/mantenimiento-preventivo.md).

## Incidencias y cierre diario

1. Registra cualquier falla de servicio, diferencia de caja, acceso anómalo o riesgo físico por el canal operativo definido.
2. Asigna un responsable y un siguiente paso a cada incidencia que no se resuelva en el momento.
3. Al cierre, confirma turnos de caja cerrados, pendientes operativos documentados y equipos con estado actualizado.
4. Verifica que respaldos y tareas programadas estén configurados; una verificación visual no sustituye una prueba de recuperación.
5. Escala a dirección los incidentes de seguridad, financieros, fiscales o de privacidad que excedan tu autorización.

## Límites importantes

- La pasarela de pago, la terminal bancaria, la conexión bancaria y el PAC real no se consideran habilitados hasta que se validen con credenciales y operación reales.
- Los comprobantes simulados no tienen validez fiscal.
- Las decisiones fiscales, legales, de nómina y de privacidad requieren revisión profesional cuando corresponda.
- Los permisos se validan en backend; no supongas que una pantalla oculta una acción que tu rol no puede ejecutar.
