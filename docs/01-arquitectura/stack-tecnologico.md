# Stack tecnológico

## Recomendación inicial

| Capa | Tecnología | Justificación |
|---|---|---|
| Backend | Python + FastAPI | desarrollo rápido, validación de tipos, ecosistema sólido |
| Base de datos | PostgreSQL | transacciones, integridad, soporte para datos históricos |
| Caché y colas | Redis + Celery | tareas asíncronas, reintentos, notificaciones |
| Panel web | Next.js + TypeScript | UI moderna, producto internacional, mantenimiento sencillo |
| Móvil | React Native + Expo | multi-plataforma, velocidad de desarrollo |
| Kiosco | React + Electron o PWA embebida | flujo táctil y pantalla grande |
| Autenticación | JWT + MFA | control centralizado y seguridad para administración |
| Pago | Conekta | soporte robusto en México, tokenización y recurrencia |
| Facturación | PAC SAT (Finkok o equivalente) | cumplimiento fiscal y XML |

## Por qué se eligió este stack

- el proyecto lo desarrolla una sola persona con ayuda de IA
- se prioriza variedad popular y bien documentada
- el backend Python con FastAPI permite casos de uso claros y pruebas de negocio
- PostgreSQL y Redis son suficientes para la primera fase y permiten crecer por módulos
- los estados de cuenta y la representación impresa del CFDI se generan con **ReportLab** (PDF); los estados de cuenta también exportan CSV con el módulo estándar `csv`. El correo sale por `smtplib` a través de un módulo compartido (`backend/src/app/mailer.py`) contra un SMTP configurable por variables de entorno; no se agregó un proveedor de correo externo en esta fase. El CFDI envía PDF y XML adjuntos y registra cada intento en `invoice_events`; el reintento es manual desde el historial de estados de cuenta (solo `failed`/`simulated`), y la cola y el reintento automático siguen pendientes

## Otras opciones sensatas

- Backend en Node/NestJS: buena opción si ya se tiene experiencia
- Base de datos MariaDB o MySQL: más simple pero menos fuerte para requerimientos de auditoría y transacciones complejas
- Kiosco nativo en Android: útil para hardware específico, pero más costoso y con más mantenimiento

⚠️ La decisión de pasarela y PAC debe validarse con proveedores reales antes de entrar en producción.
