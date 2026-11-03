# ADR-089: MFA TOTP administrativo

## Estado

Aprobado para implementación local y validación; pendiente de revisión profesional antes de producción.

## Decisión

Adoptar TOTP SHA-1 de seis dígitos con una ventana de ±30 segundos para cuentas `owner`, `manager` y `accountant`. El secreto se cifra con AES-256-GCM usando una llave exclusiva `MFA_ENCRYPTION_KEY`, con `SECRET_KEY` como fallback temporal. El login con contraseña válida que tiene MFA habilitado crea un desafío opaco de diez minutos; solo el código válido consume el desafío y crea la sesión.

## Justificación

- Reduce el riesgo de robo de contraseña en cuentas con control operacional o financiero.
- No requiere proveedor externo ni comunicación adicional.
- Reutiliza el modelo actual de sesiones opacas y la bitácora de autenticación.
- Mantiene compatible el comportamiento de cuentas sin MFA durante la migración.

## Límites

- No se incluyen códigos de respaldo, alta guiada persistente, rotación ni deshabilitación desde el panel en este incremento.
- Los secretos, desafíos y eventos requieren retención y recuperación acordadas antes de producción.
- MFA queda sujeto a pruebas PostgreSQL, controles de bloqueo/rate limiting y revisión profesional.
