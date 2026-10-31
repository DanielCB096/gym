# Manual de usuario: mantenimiento

## Objetivo

Guiar al personal de mantenimiento en la consulta de equipos, atención de tickets, registro de trabajos y captura de rondas desde el panel administrativo.

## Acceso y permisos

Inicia sesión con tu cuenta de personal y abre la sección **Mantenimiento** del panel. Las opciones disponibles dependen del rol y los permisos asignados:

- `maintenance.read`: consultar equipos, tickets, bitácora y rondas.
- `maintenance.report`: reportar tickets y cambiar el estado del equipo.
- `maintenance.manage`: crear, editar o retirar equipos; gestionar y cerrar tickets; registrar trabajos y rondas.

Si no aparece una acción o el panel indica que no tienes permiso, solicita a gerencia que revise tu rol. No compartas tu cuenta ni uses la sesión de otra persona.

## Consultar equipos

1. Abre la pestaña **Equipos**.
2. Usa la búsqueda y los filtros disponibles para localizar el equipo por texto, estado, categoría o ubicación.
3. Revisa el estado, la ubicación y el indicador preventivo. Los equipos operativos o en revisión cuya fecha preventiva ya pasó pueden aparecer como vencidos.
4. Abre la ficha del equipo para consultar sus datos, historial técnico y tickets relacionados.
5. Si un equipo aparece en mantenimiento o fuera de servicio, no lo utilices ni indiques que está disponible. Sigue la señalización física y confirma el estado con la persona responsable.

Los estados de equipo que puedes encontrar son:

- **Operativo**: disponible para su uso normal.
- **En mantenimiento**: intervención en curso; no se debe usar mientras esté restringido.
- **Fuera de servicio**: bloqueado para evitar su uso.
- **En revisión**: requiere inspección antes de confirmar su disponibilidad.
- **Baja**: retirado del servicio; no admite nuevos tickets, cambios de estado ni registros.

## Reportar una falla

1. Abre **Tickets** y crea un ticket para el equipo correspondiente.
2. Describe el problema con información concreta: qué observaste, dónde y cuándo ocurrió.
3. Selecciona la severidad según el riesgo y el impacto operativo.
4. Si existe un riesgo de seguridad, detén el uso y avisa inmediatamente a gerencia o al responsable de mantenimiento. Si tienes el permiso correspondiente, cambia el equipo a **Fuera de servicio**; no esperes a que se asigne la reparación.
5. Revisa que el ticket aparezca en la lista y comunica el folio al responsable para facilitar el seguimiento.

Un ticket crítico bloquea el equipo automáticamente. Si no es crítico, el equipo no necesariamente cambia de estado al crear el ticket; solicita el bloqueo cuando la condición lo requiera.

## Atender un ticket

1. En **Tickets**, abre el ticket asignado o que te corresponde atender.
2. Confirma que el ticket y el equipo coinciden.
3. Asigna al técnico responsable si todavía no lo tiene.
4. Al comenzar, inicia la atención desde el panel. El equipo puede pasar a **En mantenimiento** cuando corresponda.
5. Registra avances relevantes en el ticket y mantén la restricción mientras no se haya validado que es seguro usar el equipo.
6. Si necesitas piezas, proveedor o autorización, deja el ticket abierto y coordina el seguimiento con gerencia. No lo marques como resuelto por falta de recursos.

La asignación puede avisar al colaborador desde el panel si tiene una cuenta activa vinculada a su perfil. Si no cuenta con ella, confirma la asignación por el canal operativo del gimnasio.

## Resolver una falla

1. Prueba el equipo después del trabajo y confirma que puede operar de forma segura.
2. En la acción de resolución, escribe una descripción no vacía de lo realizado y el resultado.
3. Registra el costo y el técnico responsable cuando apliquen.
4. Confirma la resolución. El sistema agrega el trabajo correctivo a la bitácora y puede restaurar el estado previo del equipo si ese ticket era el que lo mantenía bloqueado.
5. Revisa el estado resultante del equipo. Si todavía requiere inspección o reparación, no lo presentes como disponible y escala el caso.
6. Informa a recepción sobre la disponibilidad o las restricciones que permanezcan.

La resolución no sustituye la validación técnica. No cierres el ticket si no puedes confirmar que el equipo es seguro.

## Cancelar un ticket

1. Cancela solo cuando el ticket sea duplicado, se haya creado por error o ya no requiera atención.
2. Registra el motivo. El motivo es obligatorio si el ticket tenía bloqueado el equipo.
3. Confirma el estado final del equipo. La cancelación restaura el estado anterior cuando ese ticket era quien lo retenía.
4. Si la falla sigue presente, asegúrate de que permanezca otro ticket válido y asignado para darle seguimiento.

Cancelar un ticket no debe usarse para ocultar una falla pendiente.

## Registrar mantenimiento preventivo o inspección

1. Abre la ficha del equipo y consulta la fecha preventiva y el historial.
2. Confirma el trabajo recomendado y la frecuencia con el fabricante o la persona responsable; el panel no programa automáticamente las tareas.
3. Si la actividad requiere restringir el equipo, actualiza su estado antes de comenzar y señaliza el área.
4. Registra la actividad como preventiva, inspección, limpieza o calibración, según corresponda.
5. Incluye notas, responsable, costo si aplica y la próxima fecha preventiva solo cuando esté definida.
6. Si detectas una falla, crea un ticket correctivo; no la dejes únicamente en las notas del trabajo preventivo.

## Registrar una ronda

1. Abre la pestaña **Rondas**.
2. Selecciona o escribe el área y registra el resultado de la limpieza o inspección.
3. Elige **Con observación** cuando exista un hallazgo y escribe la observación; el sistema exige esa explicación.
4. Asigna al responsable y guarda el registro.
5. Si el hallazgo implica una falla de equipo o un riesgo, crea además un ticket y restringe el equipo si hace falta.

Las áreas se registran como texto; el sistema no tiene todavía un catálogo específico de áreas.

## Retirar un equipo

El retiro es una acción de gerencia o mantenimiento con permiso `maintenance.manage`:

1. Confirma con gerencia que el equipo debe darse de baja.
2. Verifica que no tenga tickets abiertos; el panel no permite retirarlo mientras los tenga.
3. Usa la acción **Retirar** y confirma la operación.
4. El equipo queda en estado **Baja** y conserva su historial. No se elimina.

## Buenas prácticas y seguridad

- Ante un posible riesgo de lesión, detén el uso, señaliza y escala inmediatamente.
- No cambies un equipo a operativo sin validar su seguridad.
- Mantén cada ticket asociado al equipo correcto y documenta el resultado con claridad.
- Los registros técnicos y la bitácora son históricos; agrega evidencia nueva en lugar de intentar reemplazar el pasado.
- Las reparaciones especializadas deben realizarlas personas calificadas conforme a las indicaciones del fabricante.
- El panel no incluye actualmente adjuntos o fotografías de evidencia en tickets, proveedores ni órdenes de compra.

## Si algo no funciona

- Si una acción está deshabilitada o recibes un error de permisos, pide a gerencia revisar tu rol.
- Si no encuentras un equipo, prueba la búsqueda sin filtros y confirma su nombre o ubicación con recepción.
- Si el panel no carga o no guarda un cambio, no asumas que se registró; actualiza la vista y verifica antes de repetir una operación.
- Si el equipo continúa apareciendo disponible pese a una condición insegura, detén su uso y avisa de inmediato a recepción y gerencia; la seguridad física no debe depender únicamente del panel.
