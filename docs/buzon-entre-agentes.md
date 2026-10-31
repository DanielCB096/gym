# Buzón entre agentes

Este archivo es el canal de coordinación de este agente. No sustituye `docs/guia-para-agentes.md` ni `docs/TRASPASO.md`. No edites archivos ajenos para «arreglar» este buzón.

**Cómo usarlo:** Quesera puede pedir a otros agentes que revisen este archivo y las tarjetas enlazadas. Cada tarjeta es una tarea independiente; quien la tome cambia su estado a **en curso** en esa tarjeta antes de editar. No hace falta editar este índice para reclamarla, así que las tareas se pueden tomar en paralelo.

## Este agente

- Conversación: `0b107887-3e05-448d-b931-704d23647dc3`
- Estado: **disponible** — puede publicar tareas para que otro agente las reclame
- No hace commit ni push salvo que Quesera lo pida.

## Qué puede tomar

Tareas pequeñas, verificables y que **no** pisen archivos ya sucios en el working tree. Ejemplos válidos: un incremento acotado en un módulo libre, una prueba o corrección aislada, documentación de un módulo que nadie esté editando.

No tomar: cobros en producción, SAT/Finkok, kiosco/lector, bloqueo por deuda, salidas reales de aforo, ni nada que la documentación marque como «no tocar sin pedirlo».

## Archivos ocupados ahora (no asignar trabajo que los edite)

Trabajo ajeno sin commit, observado el 2026-10-31. No pisarlo.

- Pagos Conekta (ADR-066): `backend/src/app/modules/memberships/*`, `backend/src/app/main.py`, `backend/tests/test_conekta_*`, `backend/tests/test_hosted_*`, `backend/tests/test_member_checkout_*`, `backend/alembic/versions/20261031_0075_*`, `backend/Dockerfile`, `compose.conekta-sandbox.yml`, `backend/scripts/conekta_*`, `.env.example`, `backend/requirements.txt`, `backend/README.md`
- Documentación operativa: `docs/guia-para-agentes.md`, `docs/03-procesos/apertura-y-cierre-del-gimnasio.md`, `docs/03-procesos/atencion-de-derechos-arco.md`, `docs/03-procesos/cierre-de-nomina.md`, `docs/03-procesos/mantenimiento-preventivo.md`, `docs/03-procesos/reporte-y-resolucion-de-falla-de-equipo.md`, `docs/03-procesos/respaldo-y-recuperacion.md`, `docs/06-operacion/manual-usuario-*.md`, `CLAUDE.md`
- Correo: `backend/tests/test_mailer.py`
- Documentos compartidos (varios frentes a la vez): `docs/README.md`, `docs/TRASPASO.md`, `docs/changelog.md`, `docs/07-pruebas/plan-de-pruebas.md`, `docs/01-arquitectura/modelo-de-datos.md`, `docs/01-arquitectura/seguridad-y-privacidad.md`

Si tu encargo necesita alguno de esos archivos, **no lo asignes**: termínalo tú o espera a que el árbol esté limpio.

## Encargos disponibles

1. [Pruebas del cobro de clases premium](buzon-tarea-clases-premium.md) — pausada; la retomará el asistente principal
2. [Pruebas de errores del instalador de cron](buzon-tarea-ops-cron.md) — disponible

## Protocolo

1. Antes de reclamar una tarjeta, el agente comprueba que sus archivos permitidos siguen libres y que no hay cambios ajenos en conflicto. No inicia una tarea cuya lista prohibida deba tocar.
2. Para reclamarla, actualiza **solo esa tarjeta**: añade su nombre y conversación en «Quién la toma» y cambia su estado a **en curso** antes de editar los archivos de código o prueba.
3. Las tarjetas tienen archivos permitidos distintos. No edites la tarjeta del otro encargo ni este índice para marcar el estado; así pueden trabajar en paralelo sin sobrescribir sus reclamaciones.
4. Al terminar, registra resultado, archivos y validaciones en su tarjeta y marca el estado **completado**. Si no puede respetar el alcance, explica el conflicto y marca **bloqueado**; no amplíes los archivos permitidos por cuenta propia.
5. Si el trabajo debe retomarse después, se marca **pausado**, se deja responsable y se conserva la evidencia parcial; nadie más lo toma mientras siga pausado.
6. Nadie borra las tarjetas ni sus resultados. Nadie usa este buzón para secretos, llaves, `.env` ni datos reales.
