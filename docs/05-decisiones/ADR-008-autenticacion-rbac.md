# ADR-008: Autenticación y autorización RBAC

- Fecha: 2026-10-15
- Estado: propuesta inicial

## Contexto

El panel requiere distinguir colaboradores de identidades de acceso y aplicar permisos en backend. El gimnasio tiene varios perfiles operativos y algunas acciones críticas deben quedar auditadas.

## Decisión

- Separar `Employee` de `AppUser`; una identidad puede vincularse a un empleado, pero no se obliga para la cuenta inicial del dueño.
- Aplicar RBAC con catálogo de `Role` y permisos granulares `resource.action`; las rutas verifican los permisos efectivos en el backend.
- Hashear contraseñas con Argon2 mediante `pwdlib`.
- Emitir tokens Bearer opacos aleatorios; persistir únicamente su SHA-256, con vencimiento de 8 horas y revocación server-side.
- Registrar eventos de login, logout, alta de cuenta y cambios de rol sin guardar contraseñas ni tokens.
- Crear el primer dueño mediante comando manual que solicita la contraseña por consola; no hay credencial predeterminada.

## Consecuencias y límites

- El logout revoca la sesión inmediatamente; los permisos se recalculan al autenticar cada solicitud.
- La revocación de roles conserva historial y no permite retirar el último rol dueño activo.
- MFA, rate limiting, lockout, recuperación de contraseña, rotación automática de tokens y alertas de sesión quedan pendientes antes de producción; la gestión básica de sesiones (listar y revocar) ya está conectada.
- El panel ya consume estos endpoints vía BFF con cookie `HttpOnly`; algunas secciones (aforo, lectores físicos, pagos) siguen marcadas como pendientes o de muestra.

## Referencias

- `backend/src/app/modules/identity/models.py`
- `backend/src/app/modules/identity/service.py`
- `backend/alembic/versions/20261015_0002_identity_rbac.py`
- `docs/02-modulos/personal-y-roles.md`