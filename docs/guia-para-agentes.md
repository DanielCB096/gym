# Guía para agentes de desarrollo

## Propósito

Esta guía ayuda a agentes de IA y colaboradores a iniciar trabajo en el proyecto con el contexto correcto, respetar el trabajo concurrente y seleccionar herramientas o skills solo cuando aporten valor. No sustituye las reglas del repositorio ni la revisión profesional requerida para áreas reguladas.

## Antes de empezar

1. Lee [`CLAUDE.md`](../CLAUDE.md), [`docs/README.md`](README.md) y [`docs/00-contexto/glosario.md`](00-contexto/glosario.md).
2. Lee el documento del módulo y los procesos relacionados con la tarea. Revisa los ADR existentes antes de proponer un flujo o tecnología nuevos.
3. Comprueba la rama y el estado del árbol de trabajo. No sobrescribas, limpies ni reformatees cambios ajenos; si hay cambios en los archivos necesarios, elige una tarea aislada o coordina antes de editarlos.
4. Define el alcance y valida solo lo necesario para ese cambio. No ejecutes comandos que modifiquen datos o servicios compartidos sin autorización.
5. Si la documentación y el comportamiento implementado contradicen una regla de negocio, detente y consulta antes de decidir.

## Memoria local semantica

El proyecto incluye una herramienta local de recuperación en
[`tools/memoria`](../tools/memoria/README.md). Permite indexar el repositorio y
buscar fragmentos relacionados con reglas, ADR, procesos, modulo y traspasos.
Los resultados sirven como punto de entrada para una tarea; siempre se debe
verificar el documento fuente completo antes de implementar.

Generar el indice es opcional y local. Antes de indexar, confirma que no haya
base de datos, datos reales ni secretos en la carpeta objetivo. No subas
`tools/memoria/memoria_db/`; debe quedar excluido por Git. No uses el indice para
aplicar decisiones fiscales, financieras, legales o de seguridad sin revisar la
documentacion oficial y la revision profesional correspondiente.

## Selección de skills

Las skills disponibles dependen del entorno del agente y pueden cambiar. Son ayudas opcionales: no son dependencias del producto, no se deben instalar ni invocar por rutina y su ausencia no bloquea el trabajo. Usa una cuando su descripción coincida directamente con la tarea; continúa con las instrucciones del repositorio si no está disponible.

| Tipo de tarea | Skill sugerida, si está disponible | Cuándo usarla |
|---|---|---|
| Cambios en HTML, JSX/TSX, CSS o componentes web/móviles | `accessibility-lead` | Antes de implementar o modificar una interfaz. |
| Auditoría de accesibilidad de Markdown | `markdown-a11y-assistant` | Cuando se solicite una revisión específica de accesibilidad documental. |
| Revisión de código | `code-review` | Cuando el objetivo sea revisar cambios y reportar defectos, no implementarlos. |
| Solicitud explícita de revisión de seguridad o búsqueda de vulnerabilidades | `security-review` | Al inicio de una revisión de seguridad; no sustituirla por una auditoría general. |
| Cambios en instrucciones, agentes, prompts o skills del repositorio | `agent-customization` | Cuando se editen archivos de personalización de agentes. |
| Trabajo que requiera GitHub (issues, PR, Actions u otros recursos) | `github-hub` | Como punto de entrada para tareas de GitHub. |
| Auditoría guiada de una web completa | `web-accessibility-wizard` | Cuando el alcance sea evaluar la accesibilidad de un sitio, no solo cambiar un componente. |

Para preguntas simples, documentación ordinaria y cambios acotados, sigue el flujo normal del repositorio en lugar de invocar skills innecesarias. La skill no reemplaza leer los documentos del módulo, verificar los cambios ni probar el comportamiento.

## Trabajo concurrente y seguridad

- Antes de editar, comprueba qué archivos ya están modificados y evita archivos que otra persona o agente esté usando.
- Mantén los cambios pequeños y separados; no reviertas cambios preexistentes ni asumas que los archivos sin seguimiento son desechables.
- No copies secretos, credenciales, datos reales o archivos locales a servicios externos ni al repositorio.
- En cobros, facturación, nómina, datos personales, biométricos y control de acceso, respeta la documentación y solicita revisión profesional cuando corresponda.
- Si no puedes distinguir tu cambio de uno concurrente, detente y pide coordinación en vez de resolver el conflicto por tu cuenta.

## Al terminar

- Ejecuta la verificación más pequeña que cubra el cambio y reporta lo que no se pudo validar.
- Actualiza el documento del módulo, el modelo de datos o el ADR solo si el cambio los afecta; agrega la entrada de changelog requerida.
- En la respuesta final, enumera los archivos modificados, las verificaciones realizadas y cualquier limitación o documento pendiente.
