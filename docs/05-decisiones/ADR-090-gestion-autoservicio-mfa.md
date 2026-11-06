# ADR-090: Gestión autoservicio de MFA

## Estado

Implementado en local para dueño, gerente y contador, en backend y panel. Pendiente de pruebas dedicadas en PostgreSQL y de revisión profesional antes de producción.

## Contexto

El ADR-089 dejó MFA TOTP operativo para iniciar sesión, pero no existía forma de activarlo en una cuenta existente, ni de rotar el autenticador ni de deshabilitar el segundo factor. Además, `authenticate_user` nunca marcaba `mfa_setup_required`, así que el aviso del inicio de sesión nunca se activaba y el alta quedaba inalcanzable.

## Decisión

Agregar gestión autoservicio de MFA para la propia cuenta, con un secreto pendiente en dos fases:

1. **Alta.** La cuenta autenticada confirma su contraseña y recibe un secreto TOTP pendiente. El secreto no sustituye al activo hasta que se confirma un código válido.
2. **Rotación.** La cuenta confirma contraseña y un código del autenticador actual. Se emite un secreto pendiente nuevo; el anterior sigue funcionando hasta que el nuevo se confirma. Así una rotación abandonada no deja a la cuenta sin segundo factor.
3. **Baja.** La cuenta confirma contraseña y un código actual (TOTP o de respaldo) y MFA queda deshabilitado.

En el alta y en la rotación se entregan diez códigos de respaldo nuevos, se borran los anteriores y se vencen los desafíos MFA abiertos. Los códigos se muestran una sola vez y solo se guardan como SHA-256.

### Endpoints

| Método | Ruta | Cuerpo | Respuesta |
|---|---|---|---|
| `GET` | `/auth/mfa/status` | — | `enabled`, `enabled_at`, `backup_codes_remaining`, `pending`, `available` |
| `POST` | `/auth/mfa/enroll` | `password` | `secret`, `otpauth_uri`, `expires_at` |
| `POST` | `/auth/mfa/enroll/confirm` | `code` | `rotated`, `backup_codes` |
| `POST` | `/auth/mfa/rotate` | `password`, `code` | `secret`, `otpauth_uri`, `expires_at` |
| `POST` | `/auth/mfa/rotate/confirm` | `code` | `rotated`, `backup_codes` |
| `POST` | `/auth/mfa/disable` | `password`, `code` | `204` sin cuerpo |

El panel expone las seis rutas por BFF bajo `/api/auth/mfa/*` y las usa el botón de escudo del perfil («Seguridad de la cuenta»). La pantalla muestra el estado, el secreto y su URI, la cuadrícula de códigos de respaldo y las acciones de activar, rotar y desactivar.

### Reglas de seguridad

- El secreto pendiente vive en `app_users.mfa_pending_secret_encrypted` y `app_users.mfa_pending_created_at` (migración `20261105_0091`) y caduca a los 15 minutos. Confirmarlo con el código correcto lo promueve a `mfa_secret_encrypted`.
- El alta y la rotación exigen contraseña; la rotación y la baja exigen además un código vigente. Rotar y deshabilitar aceptan un código de respaldo y lo consumen.
- La confirmación de un secreto nuevo acepta solo TOTP, no códigos de respaldo: el respaldo pertenece al secreto ya activo.
- Solo `owner`, `manager` y `accountant` pueden iniciar el alta; para el resto, `available` es `false` y el alta responde `403`. Rotar y deshabilitar siguen disponibles si la cuenta ya tenía MFA, aunque después pierda el rol.
- Cada fallo de contraseña o de código se registra como `mfa_management` con `result = failure` en `auth_events`. Cinco fallos en diez minutos bloquean la gestión con `429` (`MfaManagementLocked`); el bloqueo también rechaza un intento con credenciales correctas, se libera al pasar la ventana y confirmar un alta o rotación —o deshabilitar— reinicia el conteo. Los eventos exitosos son `mfa_enrollment_started`, `mfa_enabled`, `mfa_rotation_started`, `mfa_rotated`, `mfa_disabled` y `mfa_backup_code`.
- El mapa HTTP es: `429` bloqueo, `409` estado incompatible, `403` MFA no disponible o contraseña rechazada, `404` cuenta no disponible y `400` código o configuración pendiente inválidos.

## Justificación

- Cierra la brecha operativa del ADR-089 sin depender de soporte ni de acceso a la base para rotar o retirar el segundo factor.
- La fase pendiente evita el fallo más peligroso de una rotación: reemplazar el secreto antes de comprobar que el nuevo autenticador funciona.
- Reutiliza el cifrado AES-256-GCM, los códigos de respaldo y la bitácora existentes.
- El bloqueo por intentos reduce la fuerza bruta contra la contraseña y el código sin introducir un proveedor externo.

## Límites

- **MFA no es obligatorio al iniciar sesión.** Las cuentas privilegiadas siguen entrando solo con contraseña hasta que deciden activarlo. No hay plazo ni recordatorio de alta obligatoria.
- **No hay recuperación si se pierden el autenticador y los códigos de respaldo.** La baja exige un código vigente, así que la cuenta quedaría sin acceso y solo una intervención directa en la base podría limpiar el secreto. Falta definir un procedimiento de recuperación con verificación de identidad y auditoría.
- **Rotar o deshabilitar no revoca las sesiones abiertas.** Una sesión creada antes del cambio sigue vigente hasta su vencimiento de ocho horas; si el objetivo es expulsar a un intruso, hay que revocar sesiones aparte.
- Los códigos de respaldo nuevos se muestran una sola vez; si la pantalla se cierra sin copiarlos, hay que rotar de nuevo.
- La ventana de bloqueo cuenta sobre `auth_events` y no se apoya en un almacén distribuido; con varias instancias del backend el conteo sigue siendo consistente porque vive en la base, pero no hay alerta ni notificación al dueño.
- Faltan las pruebas dedicadas en PostgreSQL (el resto corre en SQLite) y la revisión profesional de seguridad. Hasta entonces no se debe presentar como control listo para producción.
