# Estrategia offline y rendimiento

## Objetivo

Asegurar que la operación del gimnasio continúe incluso con internet inestable o cortes de energía.

## Requerimientos críticos

- control de acceso: respuesta <1 segundo
- pantallas web y app: <2 segundos
- búsqueda de socios: <500 ms
- cobros masivos y reportes pesados en segundo plano

## Estrategia de offline

### Control de acceso
- caché local con membresías vigentes, horarios y reglas de acceso
- sincronización automática al reconectar
- validación local con fallback de lectura en memoria
- almacenamiento del evento en cola para reenvío

### Punto de venta y caja
- caché local del catálogo, precios y turno abierto en `localStorage`, refrescada en cada carga exitosa
- la venta se arma y se cobra sin red; se guarda en una cola local con un `client_reference` único y la marca de tiempo real
- solo efectivo, tarjeta o transferencia sin conexión; la cuenta del socio (saldo y límite de crédito) y las devoluciones requieren validar saldo, límite o cantidades contra el servidor
- sincronización por lote a `POST /admin/sales/offline` al reconectar, con resultado por venta y reintentos idempotentes (la cola no se pierde si el envío falla)
- los turnos cerrados son inmutables: la venta sincronizada se vincula al turno abierto al llegar, por eso el cierre se bloquea mientras haya pendientes
- los rechazos (stock insuficiente, socio inactivo, reloj adelantado) se muestran en la cola para revisarlos o descartarlos

## Estrategia de rendimiento

- índices en tablas de acceso, pagos, socios y facturación
- paginación y filtros con query params
- consultas N+1 evitadas por joins y prefetching
- caché de catálogo, planes, horarios y listas masivas
- colas para reportes pesados y recordatorios automáticos
- partición o archivado para accesos, pagos y bitácoras a mediano plazo

## Pruebas de carga sugeridas

- 150-250 accesos por hora pico
- 3,000 socios activos
- 50 usuarios concurrentes en app y 30 en panel
- transacciones de corte de caja y reintentos de cobro simultáneos

## Observaciones

- el uso de Redis para colas y caché reduce la presión sobre PostgreSQL
- la carga de reportes debe hacerse en segundo plano para no bloquear la operación del negocio
- la salida a archivos PDF/XML se hará asíncrona cuando sea pesada
