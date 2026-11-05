# Prueba visual de interfaces

Fecha: 2026-11-05
Entorno: demo local con datos sintéticos

## Resultado

- Backend, panel administrativo, app móvil Expo y kiosco levantados correctamente.
- Login administrativo, dashboard y navegación de módulos capturados.
- Login OTP móvil y navegación de clases, fisioterapia, rutinas, pagos y facturas capturados.
- Kiosco capturado en estado de configuración.
- Validación funcional ejecutada con `demo/check-demo.ps1`: todos los chequeos aprobaron.

## Matriz visual

| Plataforma | Estado o módulo | Evidencia |
| --- | --- | --- |
| Panel web | Login | `01-web-login.png` |
| Panel web | Resumen | `02-web-resumen.png` |
| Panel web | Accesos | `03-web-accesos.png` |
| Panel web | Socios | `04-web-socios.png` |
| Panel web | Personal | `05-web-personal.png` |
| Panel web | Clases | `06-web-clases.png` |
| Panel web | Fisioterapia | `07-web-fisioterapia.png` |
| Panel web | Rutinas | `08-web-rutinas.png` |
| Panel web | Inventario | `09-web-inventario.png` |
| Panel web | Mantenimiento | `10-web-mantenimiento.png` |
| Panel web | Facturación | `11-web-facturacion.png` |
| Panel web | Conciliación | `12-web-conciliacion.png` |
| Panel web | Reportes | `13-web-reportes.png` |
| Panel web | Kiosco | `14-web-kiosco.png` |
| App móvil | Login | `15-mobile-login.png` |
| App móvil | OTP | `16-mobile-otp.png` |
| App móvil | Dashboard | `17-mobile-dashboard.png` |
| App móvil | Clases | `19-mobile-clases.png` |
| App móvil | Fisioterapia | `20-mobile-fisioterapia.png` |
| App móvil | Rutinas | `21-mobile-rutinas.png` |
| App móvil | Pagos | `23-mobile-pagos.png` |
| App móvil | Facturas | `24-mobile-facturas.png` |
| Kiosco | Configuración | `27-kiosk-configuracion.png` |

## Limitaciones

- No se capturaron datos reales ni credenciales de producción.
- La captura visual móvil usa Expo Web, no una build física de iOS.
- Algunos módulos administrativos devolvieron HTTP 503 en endpoints secundarios y deben revisarse por separado.
- Las páginas restantes de fotos, avisos y solicitud de factura necesitan un recorrido adicional con selectores estables.
