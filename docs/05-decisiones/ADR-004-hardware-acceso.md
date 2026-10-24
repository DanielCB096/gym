# ADR-004: Hardware de acceso

- Fecha: 2026-10-15
- Estado: propuesta inicial

## Contexto

El gimnasio necesita lectores de alta velocidad con soporte local y operación sin internet. El hardware debe ser confiable, económico y fácil de mantener.

## Opciones consideradas

1. Lector QR + RFID con torniquete simple
2. Lector biométrico + tarjeta + torniquete
3. Controladora local con tablet y app embebida

## Decisión

Se recomienda una solución híbrida con lector QR + RFID + huella en una controladora local y un torniquete que responda en <1 s. Para la fase inicial, la variación económica mantiene QR + RFID como base con la posibilidad de sumar huella en puntos críticos.

## Consecuencias

- buen equilibrio entre costo y velocidad
- mejor tolerancia a cortes de Internet
- requiere validación con proveedores de instalación local

⚠️ El hardware debe validarse con un instalador antes de compra final.
