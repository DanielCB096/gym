# Pruebas de carga

## Objetivo

Verificar la resiliencia del sistema con la carga esperada del gimnasio.

## Escenario base

- 3,000 socios activos
- 150-250 accesos por hora pico
- 50 usuarios concurrentes en app
- 30 usuarios concurrentes en panel

## Métricas a medir

- tiempo de respuesta de acceso
- latencia de consulta de socios
- tiempo de cortes de caja
- consumo de Redis y PostgreSQL
- reintentos de cobro y fallos de cola

## Resultado esperado

- acceso en <1 s
- pantallas en <2 s
- colas no bloquean la operación del negocio
