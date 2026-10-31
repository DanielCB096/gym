# Mantenimiento preventivo

## Objetivo

Planear y registrar inspecciones y tareas preventivas para reducir fallas, mantener los equipos seguros y conservar un historial técnico verificable.

## Alcance

Aplica a los equipos e instalaciones registrados en el módulo de mantenimiento. Cubre la revisión de vencimientos, asignación, ejecución, registro de resultados y programación de la siguiente fecha. Las reparaciones por una falla detectada se continúan como mantenimiento correctivo mediante un ticket.

## Frecuencia y responsables

- Gerencia o la persona responsable de mantenimiento revisa periódicamente los equipos próximos a vencer y prioriza por criticidad, estado y uso.
- El técnico asignado ejecuta la inspección y documenta el trabajo realizado.
- Recepción o el responsable del área restringe el uso cuando exista riesgo para socios o personal y confirma que la señalización sea visible.
- La frecuencia concreta depende de las recomendaciones del fabricante, garantías, uso e inspecciones profesionales; no debe inferirse solo por la fecha de compra.

## Procedimiento

### 1. Preparar el plan
1. Consultar la flota y las fechas de próximo mantenimiento.
2. Identificar equipos vencidos o próximos a vencer, priorizando los de mayor impacto operativo o de seguridad.
3. Confirmar con el proveedor o fabricante el tipo de inspección y la frecuencia recomendada cuando esa información esté disponible.
4. Asignar responsable y fecha de trabajo. Coordinar con recepción para reducir el impacto en clases y horarios de mayor afluencia.

### 2. Asegurar el área
1. Confirmar la identidad del equipo y su ubicación antes de intervenir.
2. Detener y señalizar el equipo si la tarea lo requiere o si se encuentra una condición insegura.
3. Cambiar su estado a mantenimiento o fuera de servicio según corresponda. Si se detecta una falla que requiere reparación, abrir o actualizar un ticket correctivo y seguir su proceso.
4. No devolver el equipo al servicio hasta que el técnico confirme que es seguro.

### 3. Ejecutar y registrar
1. Realizar las actividades autorizadas: inspección, limpieza técnica, lubricación, ajuste o calibración, según el equipo y las indicaciones aplicables.
2. Registrar el trabajo en la bitácora técnica, incluyendo fecha, responsable, notas y costo cuando aplique.
3. Si se detecta una anomalía, describirla y abrir un ticket correctivo con su severidad. Una condición crítica requiere bloquear el equipo de inmediato.
4. Registrar la siguiente fecha preventiva cuando se haya definido con una fuente válida.

### 4. Validar y cerrar
1. Verificar el funcionamiento seguro del equipo y que no queden herramientas o protecciones pendientes.
2. Actualizar el estado del equipo y retirar la señalización solo si la revisión confirma que puede volver a utilizarse.
3. Revisar que el registro técnico y cualquier ticket relacionado queden completos y asociados al equipo.
4. Informar a recepción sobre la disponibilidad y cualquier restricción temporal.

## Criterios de cierre

La actividad se considera cerrada cuando:
- el trabajo y su resultado quedaron registrados en el historial del equipo;
- se registró responsable y costo si aplica;
- existe fecha siguiente cuando la recomendación de mantenimiento está definida;
- las anomalías quedaron como tickets correctivos y no como observaciones informales;
- el estado del equipo refleja su condición real y, si está fuera de servicio, la operación puede verlo.

## Excepciones y seguridad

- Si el técnico no puede confirmar que el equipo es seguro, mantenerlo fuera de servicio y escalarlo a gerencia.
- Si faltan piezas, autorización o proveedor, dejar constancia de la causa y fecha de seguimiento; no marcar como realizado un trabajo incompleto.
- Si el equipo está cubierto por garantía, consultar sus condiciones antes de intervenirlo.
- Las tareas que requieran especialización, bloqueo eléctrico u otro procedimiento de seguridad deben realizarlas personas calificadas conforme a las indicaciones del fabricante y las reglas aplicables.

## Estado de implementación

- El módulo permite registrar tickets preventivos, registros técnicos con tipo preventivo y fecha de próximo mantenimiento; esa fecha alimenta el indicador de equipos vencidos.
- La flota, tickets, bitácora y rondas de limpieza/inspección se gestionan desde el panel, de acuerdo con [mantenimiento-equipo.md](../02-modulos/mantenimiento-equipo.md).
- La programación periódica y los recordatorios automáticos preventivos no están implementados. Hasta que exista esa automatización, la revisión de fechas y la asignación del trabajo son tareas manuales del responsable.
- No sustituye las recomendaciones del fabricante, la revisión de personal calificado ni las inspecciones obligatorias aplicables.

## Indicadores sugeridos

- porcentaje de preventivos realizados en fecha;
- equipos preventivos vencidos;
- fallas correctivas detectadas durante preventivos;
- tiempo fuera de servicio atribuible a mantenimiento;
- costo preventivo por equipo.
