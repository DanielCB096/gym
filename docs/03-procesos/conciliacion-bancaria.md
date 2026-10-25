# Conciliación bancaria

## Resumen

Este proceso compara las líneas del estado de cuenta bancario con las operaciones que el gimnasio ya registró —cobros de membresía, ventas del POS, abonos a cuenta del socio y devoluciones— para confirmar que el dinero que entró o salió del banco corresponde a una operación interna. La conciliación **no crea ni modifica dinero**: solo vincula una línea del banco con la fila que ya lo registró y deja constancia de la decisión. La diferencia entre ambas se documenta para revisión contable.

## Implementación actual

Desde el 2026-10-25 la conciliación bancaria está disponible en backend y panel con la migración `20261025_0027_bank_reconciliation.py` (`bank_accounts`, `bank_movements`, `bank_movement_events`) y el permiso `finance.manage` para dueño y contador. La importación es **CSV** procesado en el navegador y enviado por API; **no hay conexión real con bancos ni pasarela**. Las sugerencias son heurísticas (fecha, importe y referencia) y la confirmación siempre es humana. La bandeja, las cuentas y el detalle se consultan con `finance.read`; crear cuentas, cambiar su estado, importar, conciliar, desvincular y marcar exigen `finance.manage`. Gerente solo consulta y recepción no tiene acceso.

## Flujo paso a paso

### 1. Alta de la cuenta
1. Un usuario con `finance.manage` abre **Conciliación → Nueva cuenta**.
2. Captura un nombre único (sin distinguir mayúsculas), el banco, los **últimos cuatro dígitos** y la moneda (tres letras, `MXN` por defecto). No se guardan números de cuenta completos, CLABE ni credenciales.
3. La cuenta nace activa. Una cuenta inactiva conserva su historial, pero no admite importaciones hasta reactivarla; no existe borrado de cuentas.

### 2. Importación del estado de cuenta
1. El operador descarga el estado de cuenta de su banca en línea y lo convierte a CSV con, al menos, **fecha e importe**; opcionalmente referencia y descripción. La fecha acepta `AAAA-MM-DD` o `DD/MM/AAAA`; el importe acepta coma o punto decimal, paréntesis o signo negativo para retiros.
2. En **Importar movimientos** pega el CSV o carga el archivo. El panel detecta tabulador, punto y coma o coma; ignora una primera fila de encabezado (`Fecha`, `Date`, `Fecha de operación`, etc.), muestra una vista previa con los totales y señala los errores por línea (`Línea 3: importe inválido «abc».`).
3. Al confirmar, el backend valida **todo el lote**: hasta 500 líneas, importe distinto de cero, referencia ≤120 y descripción ≤240. Una fila inválida rechaza el lote completo con `422`; una cuenta inactiva responde `409`.
4. La importación es **idempotente**: se calcula un SHA-256 por cuenta, fecha, importe, referencia y descripción, y se omiten los duplicados dentro del lote y los ya guardados. La respuesta indica cuántas líneas se importaron, cuántas se omitieron y el total del lote. Reimportar el mismo archivo no duplica movimientos.

### 3. Revisión de la bandeja
1. La bandeja muestra las líneas ordenadas por prioridad (primero pendientes y con diferencia) con cuenta, fecha, referencia, importe **con signo** y estado.
2. El resumen superior cuenta pendientes, conciliadas, con diferencia y en revisión; suma entradas y salidas, el importe pendiente, el importe con diferencia y la línea pendiente más antigua. El «saldo» de la tarjeta es la suma de las líneas importadas, **no** el saldo real del banco.
3. Se filtra por cuenta, estado, rango de fechas y texto (referencia, descripción, operación vinculada o nota). La tabla pagina de 25 en 25.

### 4. Conciliación de una línea
1. El operador abre la línea. El detalle muestra fecha, importe, referencia, descripción, estado, nota e historial de eventos, y una lista de **candidatos** con la operación interna, su fecha, importe, diferencia y referencia.
2. Para un **depósito** se proponen pagos de membresía, ventas del POS y abonos a cuenta con método electrónico (`card`, `transfer`, `spei`). Para un **retiro** solo se proponen devoluciones con reembolso electrónico. El efectivo nunca aparece porque no pasa por el banco.
3. La sugerencia automática busca **±7 días** alrededor de la fecha de la línea con una tolerancia de importe de `max(100 centavos, 2%)`; ordena por importe exacto, coincidencia de referencia (folio, socio, plan) y cercanía de fecha. Si no aparece la operación, la **búsqueda manual** amplía la ventana a **±60 días** y acepta texto.
4. Si el importe coincide, **Conciliar** deja la línea `reconciled`. Si no coincide, el operador debe escribir el **motivo de la diferencia** y la línea queda `difference` con el importe de la diferencia. Una operación interna solo puede estar vinculada a una línea del banco: el índice único parcial lo impide y responde `409`.
5. **Desvincular** exige un motivo, vuelve la línea a `pending` y conserva en la bitácora la operación y el estado anteriores. Después se puede conciliar con otra operación.

### 5. Líneas sin operación o en revisión
- Si una línea no tiene operación interna (por ejemplo, una comisión bancaria o un depósito de un tercero), se marca **Con diferencia** o **En revisión** con una nota obligatoria. No se inventa una operación ni se ajusta el dinero.
- Una línea marcada puede volver a **Pendiente**; la nota se limpia y la bitácora registra la reapertura.
- Una línea vinculada no se puede marcar: primero se desvincula.

## Registro y auditoría

Cada línea conserva `imported_by`/`imported_at` y, según la última decisión, `reconciled_by`/`reconciled_at` y `reviewed_by`/`reviewed_at`. En `bank_movement_events` se agrega, sin sobrescribir:

- `imported`: línea importada, con su importe con signo.
- `matched`: operación vinculada, importe y diferencia con su motivo.
- `unmatched`: operación desvinculada, estado anterior y motivo.
- `flagged`: marcada como diferencia o revisión, con la nota.
- `reopened`: devuelta a pendiente.

Cada evento guarda actor y fecha; la consulta expone también el correo del actor. El historial no se borra.

## Reglas clave

- La conciliación no crea ingresos, egresos, asientos ni comisiones: solo vincula y documenta.
- Una línea del banco representa un movimiento con signo: depósito positivo, retiro o reembolso negativo.
- Una operación interna se concilia con **una sola** línea del banco; para corregir se desvincula y se vuelve a conciliar.
- Solo se ofrecen operaciones electrónicas; el efectivo y los cobros con tarjeta **declarada** que no llegaron al banco no pueden conciliarse.
- Una diferencia de importe exige una nota; el sistema no la ajusta ni la oculta.
- Una línea puede quedar pendiente indefinidamente; la antigüedad de pendientes es un indicador operativo, no una sanción automática.
- La importación es idempotente por hash; reimportar no duplica y dos líneas legítimamente idénticas del mismo día se consideran duplicadas.
- El saldo que muestra la cuenta es la suma de las líneas importadas, no el saldo del banco ni un saldo contable.

## Excepciones

- **Archivo con una fila inválida:** el lote completo se rechaza con el número de fila y el motivo; se corrige el CSV y se reimporta.
- **Cuenta inactiva:** la importación responde `409`; se reactiva la cuenta o se elige otra.
- **Línea duplicada:** se omite y se informa en el resultado; no genera error.
- **Operación ya conciliada con otra línea:** la API responde `409` y la lista de candidatos la excluye.
- **Diferencia sin motivo:** la conciliación responde `422`; se escribe el motivo o se corrige la operación de origen por su propio flujo.
- **Línea vinculada que se quiere marcar:** responde `409`; primero se desvincula.
- **Depósito agrupado o pago dividido:** el modelo actual es uno a uno y no lo representa; se deja pendiente o en revisión y se escala a contabilidad.
- **Comisión, rendimiento o cargo bancario:** no tiene operación interna; se marca con diferencia o revisión y su tratamiento contable se define fuera del sistema.
- **Dos usuarios concilian la misma línea a la vez:** el bloqueo de fila y el índice único lo impiden en PostgreSQL; la segunda operación recibe `409` y debe refrescar. En SQLite (vista previa y pruebas) el bloqueo es un no-op y la protección depende del índice único.
- **Banco conectado en el futuro:** la importación CSV se mantiene como respaldo y la conciliación se reutiliza; no se debe confundir con una conciliación automática.

## Responsables

- **Contador**: revisa y concilia, documenta diferencias y cierra el periodo.
- **Dueño**: puede conciliar y administrar cuentas; supervisa pendientes y antigüedad.
- **Gerente**: consulta la bandeja y el detalle, sin modificar cuentas ni conciliar.
- **Recepción**: no participa en la conciliación bancaria.
- **El sistema**: valida permisos, evita duplicados, propone candidatos y conserva la bitácora.

## KPIs

- porcentaje de líneas conciliadas sobre el total importado del periodo
- importe y antigüedad de líneas pendientes
- número e importe de diferencias abiertas por cuenta
- líneas en revisión sin resolver
- tiempo medio desde la importación hasta la conciliación
- operaciones electrónicas sin línea bancaria (cuando exista una fuente completa de estados de cuenta)

## Límites vigentes

No hay conexión bancaria ni de pasarela: el estado de cuenta se importa a mano en CSV y la frescura depende de cada carga. No se manejan depósitos agrupados, pagos divididos, conciliación parcial ni ajustes contables; el emparejamiento es uno a uno y una diferencia solo se documenta. No se auditan los cambios de la cuenta (solo su creador) ni se pueden borrar o fusionar cuentas. Los reportes financieros todavía no exponen el estado de conciliación y la vista previa no prueba la carga de archivos binarios ni un banco real. Estas limitaciones están detalladas en `docs/deuda-tecnica.md`.
