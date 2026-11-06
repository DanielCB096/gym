# ADR-089: MFA TOTP administrativo

## Estado

Implementado en local para dueño, gerente y contador; la gestión autoservicio (alta, rotación y baja) se completó en el ADR-090. Siguen pendientes las pruebas dedicadas en PostgreSQL, la recuperación ante pérdida de factores y la revisión profesional antes de producción.

## Decisión

Adoptar TOTP SHA-1 de seis dígitos con una ventana de ±30 segundos para cuentas `owner`, `manager` y `accountant`. El secreto se cifra con AES-256-GCM usando una llave exclusiva `MFA_ENCRYPTION_KEY`, con `SECRET_KEY` como fallback temporal. El login con contraseña válida que tiene MFA habilitado crea un desafío opaco de diez minutos; solo el código válido consume el desafío y crea la sesión. Al activar MFA se entregan diez códigos de respaldo de un solo uso, guardados solo como hash SHA-256.

## Justificación

- Reduce el riesgo de robo de contraseña en cuentas con control operacional o financiero.
- No requiere proveedor externo ni comunicación adicional.
- Reutiliza el modelo actual de sesiones opacas y la bitácora de autenticación.
- Mantiene compatible el comportamiento de cuentas sin MFA durante la migración.

## Límites

- El alta guiada desde el inicio de sesión nunca se activó (`authenticate_user` no marca `mfa_setup_required`); el alta, la rotación y la baja se ofrecen desde la pantalla de seguridad del perfil en el ADR-090. Este ADR conserva el modelo del desafío y los códigos de respaldo.
- Los secretos, desafíos y eventos requieren retención y recuperación acordadas antes de producción.
- MFA queda sujeto a pruebas PostgreSQL y revisión profesional; el bloqueo por intentos y la gestión autoservicio ya existen (ADR-090).
