# ADR-085: Las cotas de clase, en una sola fuente y en tres capas

- **Fecha:** 2026-11-01
- **Estado:** aceptada
- **Relacionada con:** ADR-006 (clases y reservas), ADR-081 (catálogos en una sola fuente) y el módulo 4.

## Contexto

La capacidad de un salón y de una clase, y las horas de la ventana de cancelación, tenían suelo en la base (`capacity > 0`, `cancel_window_hours >= 0`) y techo solo en los modelos de petición: `le=500` estaba escrito tres veces —alta de salón, alta de clase y edición de clase— y `le=168` dos. Dos consecuencias. La primera: quien no pasara por la petición —el seed, un script, un CLI futuro— podía guardar una sala de dos mil personas o una ventana de un año; el servicio rechazaba el cero pero no el exceso. La segunda: cinco copias del mismo número podían separar su valor sin que ninguna prueba lo notara, que es exactamente el fallo que `tests/test_catalog_single_source.py` ya cierra para los vocabularios de estados.

## Decisión

- `MAX_CLASS_CAPACITY = 500` y `MAX_CANCEL_WINDOW_HOURS = 24 * 7` viven en `backend/src/app/modules/classes/models.py`, junto a `DEFAULT_CANCEL_WINDOW_HOURS`, que ya estaba ahí. El número de la cota pertenece al dominio, no a la capa que lo valida.
- Las tres capas leen esa constante: la petición (`le=MAX_CLASS_CAPACITY`), el servicio (`InvalidClassData` con el motivo escrito, antes de tocar la sesión) y el esquema, cuyo `CHECK` se renderiza con un f-string sobre la misma constante. `server_default` de `cancel_window_hours` deja de ser un `"4"` suelto y sale de `DEFAULT_CANCEL_WINDOW_HOURS`.
- `20261101_0082` añade `ck_class_rooms_capacity_max`, `ck_class_sessions_capacity_max` y `ck_class_sessions_window_max` como **restricciones nuevas**, en lugar de ensanchar las que ya revisaban el suelo. Así los nombres siguen describiendo lo que comprueban, la migración es aditiva y ninguna fila existente se revalida. El `downgrade` revierte en orden inverso.
- La custodia fija los dos extremos: `APPLIED_CHECKS` compara el SQL que produce el modelo, byte a byte, con el que dejó la migración —cambiar la constante sin escribir su migración falla ahí— y `ROUTE_BOUNDS` compara el `minimum`/`maximum` del contrato OpenAPI con la constante del modelo —volver a escribir el número a mano en la petición falla ahí—.
- Las cuatro pruebas de `tests/test_class_capacity_bounds.py` recorren la frontera por los dos lados (500 entra, 501 no) en las tres capas, y comprueban que después de cada rechazo la fila no quedó escrita.

## Consecuencias y límites

- El panel y la base rechazan el mismo número, y un llamador que no pase por la petición recibe un `InvalidClassData` con el motivo en lugar de un error de base de datos; solo quien escribe por ORM depende del `CHECK`.
- `500` y `168` son criterio del dominio, no una regla fiscal ni legal: una clase no puede llenar más que el aforo del club y una ventana de más de una semana deja de ser una ventana. Cambiarlos exige su migración, que es lo que recuerda el mensaje de la custodia.
- La migración se aplicó sin tocar datos: en la vista previa el máximo de capacidad guardado es 20 y la ventana es 4, muy dentro de la cota. El job **Database migrations (PostgreSQL)** de CI ya la corre —aplica la cadena completa, hace `downgrade -1` y reaplica la cabeza sobre PostgreSQL 16, verde en `cd27e71`—, así que el DDL de los tres `CHECK` es ejecutable ahí. Lo que ese job **no** cubre es un `ADD CONSTRAINT` sobre una base con filas: la suya está vacía, y en el club real una capacidad por encima del tope haría fallar la migración al desplegar. Las migraciones de esta familia tampoco son reproducibles en SQLite.
- El `except IntegrityError` de `create_class_room` (`classes/service.py:339`) convierte **cualquier** fallo de integridad en «Ya existe un salón con ese nombre». Con la guarda nueva, la capacidad ya no llega a ese camino, pero un `CHECK` distinto que se incumpla por esa vía seguiría reportándose como nombre duplicado. Queda anotado, no corregido.
- El barrido que produjo este corte encontró otras ocho familias con la misma forma (doce columnas con `le=` en la petición y sin tope en la base): duración de un servicio de fisioterapia, series y descanso de una rutina, sesiones y vigencia de un paquete, peso y medidas, objetivo del socio, minutos de un entrenamiento, series de un registro y vida útil de un equipo. Cada una necesita su propia migración y su prueba.
- También quedaron sin derivar cuatro `CHECK` de lista en las tablas de clase —`status` y `access_type` de la sesión, `status` y `origin` de la reserva—, que reescriben a mano listas que ya existen como tuplas en el mismo archivo (`SESSION_STATUSES`, `ACCESS_TYPES`, `RESERVATION_STATUSES`, `RESERVATION_ORIGINS`). Derivarlos no exige migración porque el SQL sale idéntico, y es el siguiente corte.
