# ADR-073: Cierre programado del día de fisioterapia

- Fecha: 2026-10-31
- Estado: propuesta inicial
- Cierra el límite (7) de ADR-039 («no hay trabajo programado»)

## Contexto

La agenda de fisioterapia tiene un cierre manual: `POST /admin/physio/appointments/close-day` marca `no_show` las citas de un día que ya terminaron y siguen `scheduled`, sin cobrar ni descontar créditos (ADR-039). El botón funciona, pero nadie lo pulsa solo: un día que recepción no revisó deja sus citas `scheduled` para siempre, la agenda arrastra pendientes viejos y el reporte no distingue una inasistencia real de una cita que nadie marcó.

El instalador de cron (ADR-063) ya genera un bloque idempotente con las tareas de operación y ADR-071 sumó la cola del push del personal como cuarta entrada. El cierre del día era el único trabajo del módulo que dependía por completo de una persona.

## Decisión

- **Un script propio, no un planificador interno.** `backend/close_physio_day.py` abre una sesión y llama a `close_physio_day`, el mismo servicio del botón del panel; no agrega estado, tabla ni migración. Cierra **un día por corrida**, el anterior en la zona del club por defecto, y acepta `--date AAAA-MM-DD` para ponerse al día cuando una corrida se perdió.
- **Cierra el día, no la cita suelta.** La regla del servicio se conserva: solo pasan a `no_show` las citas `scheduled` del día elegido cuyo fin ya ocurrió; las `attended`, `no_show` y `cancelled` no se tocan y repetir la corrida devuelve cero. Un día futuro o en curso solo cierra lo que ya terminó.
- **No mueve dinero ni saldo.** Marcar inasistencia nunca cobra ni descuenta, igual que el cierre manual. Si el socio sí asistió, recepción puede corregir a `attended` mientras siga dentro de la ventana de asistencia —desde el inicio hasta 24 h después del fin— y ahí se cobra o descuenta como cualquier corrección; fuera de esa ventana la marca ya era definitiva aunque el cierre llegara tarde.
- **El actor es el sistema.** El script llama al servicio sin `actor_id`, así que la marca queda con `marked_by = NULL`; la corrección posterior sí registra a la persona, y la bitácora del módulo no cambia.
- **Vista previa explícita.** `--preview` apunta a `gym_preview.db` y **escribe**, como el botón del panel; `--database-url` apunta a otra base y sin ninguna de las dos se exige `DATABASE_URL`. Una configuración inválida —`--preview` con `--database-url`, una fecha mal escrita, sin URL— sale con código 2; una base inalcanzable, con código 1 y el motivo en la bitácora.
- **Quinta entrada del bloque de cron.** `ops_cron.py` agrega `close_physio_day.py` a las `00:30` por defecto (`--physio-close-at`, `HH:MM`), con la bitácora `logs/physio-close.log` y el mismo delimitador `# BEGIN gimnasio-ops` / `# END gimnasio-ops`. `--install` exige también ese script; `--print` sigue sin tocar el crontab.
- **Sin cambio de contrato.** El botón «Cerrar día» del panel sigue disponible para cerrar el día en curso o repetir uno; el script solo programa el día que ya pasó y no agrega rutas ni permisos.

## Consecuencias y límites

- **Depende del cron del host.** No hay planificador dentro de la aplicación y una corrida perdida no se repite: el día queda abierto hasta que el cron vuelva o alguien use `--date`. Tampoco avisa si el cron está detenido.
- **El cron usa la hora local del servidor, no `APP_TIMEZONE`.** El día que se cierra sí se calcula en la zona del club; si el servidor corre en otra zona, hay que ajustar `--physio-close-at` para que la corrida caiga después de la medianoche del club, o el cierre llegará con horas de retraso.
- **Cierra un día por corrida.** Un apagón de varios días necesita una corrida con `--date` por cada día perdido; no hay rango ni barrido automático de días viejos.
- **No marca asistencia.** El script nunca convierte `scheduled` en `attended`: la asistencia la decide quien atendió. Un socio que llegó y nadie marcó queda `no_show` y solo se corrige dentro de la ventana de 24 h.
- **No hay resumen ni acuse.** La corrida imprime cuántas citas cerró y lo deja en la bitácora; no manda correo ni aviso al panel, igual que el cierre manual.
- **La vista previa se modifica.** `--preview` escribe sobre `gym_preview.db`; para probar sin ensuciarla hay que usar una copia desechable o `--database-url`.

## Referencias

- `backend/close_physio_day.py`
- `backend/ops_cron.py` (`DEFAULT_PHYSIO_CLOSE_AT`, `--physio-close-at`, `close_physio_day.py` en `_SCRIPTS`)
- `backend/src/app/modules/physio/service.py` (`close_physio_day`, `mark_physio_attendance`)
- `backend/tests/test_close_physio_day.py`, `backend/tests/test_ops_cron.py`
- `docs/06-operacion/despliegue.md`
- `docs/05-decisiones/ADR-039-fisioterapia-cobro-por-asistencia.md`, `ADR-063-programacion-de-las-tareas-de-operacion.md`, `ADR-071-planificador-de-la-cola-del-push-del-personal.md`
