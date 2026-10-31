# Reporte y resolución de falla de equipo

## Objetivo

Establecer cómo reportar, priorizar, atender y cerrar una falla de equipo, protegiendo a socios y personal y dejando evidencia en el historial técnico.

## Alcance

Aplica a equipos registrados en la flota del gimnasio. Cubre desde la detección de una anomalía hasta la resolución o cancelación del ticket. El mantenimiento programado se documenta por separado en [mantenimiento-preventivo.md](mantenimiento-preventivo.md).

## Responsables y permisos

- Socios, instructores, recepción y mantenimiento pueden reportar una falla según sus permisos.
- Dueño, gerente y mantenimiento pueden gestionar y cerrar tickets.
- La persona responsable de mantenimiento coordina la atención y confirma que el equipo pueda volver al servicio.
- Recepción comunica restricciones operativas en el área y evita el uso de un equipo bloqueado.

## Procedimiento

### 1. Detectar y reportar
1. Identificar el equipo y su ubicación.
2. Describir la falla observada, cuándo ocurrió y cualquier condición que ayude a reproducirla.
3. Seleccionar el tipo correctivo y la severidad de acuerdo con el impacto y el riesgo.
4. Crear el ticket y revisar el folio generado para poder darle seguimiento.
5. Si existe un riesgo para la seguridad, detener el uso y marcar el equipo fuera de servicio de inmediato; no esperar a que comience la reparación.

### 2. Priorizar y asignar
1. Revisar los tickets abiertos y ordenar la atención según severidad, seguridad e impacto en la operación.
2. Asignar un técnico responsable y acordar la siguiente acción.
3. Si la falla es crítica, el sistema bloquea el equipo y guarda su estado anterior para restaurarlo al resolver o cancelar el ticket.
4. Si el ticket no es crítico, evaluar si hace falta cambiar el estado del equipo antes de iniciar el trabajo. No asumir que un ticket de baja severidad ya lo bloqueó.

### 3. Atender la falla
1. Confirmar que el equipo y el ticket corresponden antes de intervenir.
2. Al iniciar la reparación, registrar el avance y mantener fuera de servicio o en mantenimiento todo equipo que no sea seguro utilizar.
3. Registrar las observaciones relevantes y los costos aplicables en la actividad de mantenimiento correspondiente.
4. Si el diagnóstico revela una falla distinta o de mayor severidad, actualizar el ticket y aplicar las medidas de seguridad adecuadas.
5. Si se requiere proveedor, pieza o autorización que no está disponible, mantener la restricción necesaria y dejar el ticket abierto con el siguiente paso pendiente.

### 4. Resolver y validar
1. Probar el equipo después de la reparación y confirmar que funciona de forma segura.
2. Resolver el ticket con una descripción obligatoria del trabajo y resultado; incluir costo y responsable técnico cuando aplique.
3. El sistema agrega un registro correctivo al historial técnico y, si el ticket mantenía bloqueado el equipo, restaura el estado que tenía antes del bloqueo.
4. Confirmar que el estado resultante corresponde a la condición real. No retirar la restricción si el equipo aún necesita una inspección o reparación adicional.
5. Informar a recepción y al personal del área sobre la disponibilidad o las restricciones que permanezcan.

### 5. Cancelar un ticket
1. Cancelar solo si el reporte fue duplicado, incorrecto o ya no requiere atención por una razón documentada.
2. Registrar el motivo. Si el ticket tenía bloqueado el equipo, el motivo es obligatorio.
3. Confirmar el estado final del equipo; el sistema restaura el estado anterior cuando el ticket era quien lo mantenía bloqueado.
4. Si la falla continúa, crear o conservar un ticket válido para que no se pierda el seguimiento.

## Criterios de cierre

Un ticket queda correctamente resuelto cuando:
- tiene notas de resolución no vacías;
- se registró la actividad correctiva en la bitácora técnica;
- el equipo fue revisado y tiene un estado coherente con su seguridad y disponibilidad;
- las restricciones restantes y tareas de seguimiento están asignadas;
- recepción conoce si el equipo puede volver a utilizarse.

## Excepciones y seguridad

- Una falla que pueda causar lesiones debe tratarse como crítica: bloquear el equipo inmediatamente y escalarla a gerencia o mantenimiento.
- Si no se puede validar la reparación, mantener el equipo fuera de servicio o en inspección y continuar el ticket; no marcarlo como resuelto solo para limpiar la lista de pendientes.
- Un equipo retirado no admite tickets nuevos, cambios de estado ni registros técnicos.
- El historial técnico es append-only: la resolución agrega evidencia y no reemplaza los registros anteriores.
- Las reparaciones especializadas deben realizarse por personal calificado y de acuerdo con las indicaciones del fabricante.

## Estado de implementación

- El panel permite consultar la flota, crear y asignar tickets, iniciar su atención, resolverlos o cancelarlos.
- Un ticket crítico bloquea el equipo; al iniciar una reparación, los equipos operativos o en revisión pueden pasar a mantenimiento. La resolución o cancelación restaura el estado previo solo cuando ese ticket era quien lo retenía.
- La resolución exige notas y crea un registro correctivo en la bitácora. La cancelación exige motivo si el equipo estaba bloqueado por ese ticket.
- El estado de disponibilidad del equipo se consulta desde las superficies operativas descritas en el módulo de mantenimiento; su visibilidad no sustituye la señalización física ni la comunicación directa con recepción.
- Adjuntos o fotografías de evidencia en tickets, proveedores y órdenes de compra no forman parte del incremento implementado.

## Indicadores sugeridos

- tiempo desde el reporte hasta la asignación;
- tiempo fuera de servicio;
- tickets reabiertos o cancelados;
- fallas recurrentes por equipo;
- costo correctivo por equipo.
