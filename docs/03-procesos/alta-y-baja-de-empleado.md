# Alta y baja de empleado

## Resumen

Este proceso administra el directorio operativo, las cuentas de usuario y las asignaciones de rol. Contratos, obligaciones laborales, asistencia y nómina quedan fuera de esta primera implementación.

## Alta de empleado y cuenta

1. Un usuario con permiso `staff.manage` captura número, nombre, puesto y datos de contacto mínimos.
2. El sistema valida que el número de empleado y el correo no estén asignados.
3. Un usuario con `staff.manage` y `roles.manage` crea la cuenta con correo, contraseña y vínculo opcional al expediente.
4. La contraseña debe tener al menos 12 caracteres y se almacena con Argon2; no se guarda ni se devuelve en claro.
5. Se asignan uno o varios roles existentes, registrando actor y fecha.
6. El colaborador inicia sesión y recibe un token Bearer opaco con vencimiento de 8 horas.

## Primer usuario dueño

1. Después de aplicar las migraciones, una persona operadora ejecuta el comando local de bootstrap.
2. El comando solicita correo y contraseña en la consola; no hay contraseña predeterminada.
3. El bootstrap solo se admite mientras no exista ningún usuario y asigna el rol `owner`.

## Baja o revocación de acceso

1. Un usuario autorizado deshabilita la cuenta o revoca la asignación de rol.
2. Las sesiones existentes se revocan al cerrar sesión; al deshabilitar una cuenta, las solicitudes futuras se rechazan.
3. Asignaciones y eventos de auditoría se conservan; no se eliminan físicamente.
4. No se permite retirar el último rol de dueño activo.

## Reglas clave

- Los permisos se validan en cada endpoint del backend; ocultar acciones en la interfaz no es control de autorización.
- Login responde con mensaje genérico para credenciales incorrectas o cuentas no válidas.
- La base conserva únicamente el hash del token de sesión; el token crudo se muestra una sola vez al iniciar sesión.
- MFA, limitación de intentos, recuperación de contraseña y notificaciones de seguridad son pendientes antes de producción.

## KPIs

- cuentas activas por rol
- logins exitosos y fallidos
- sesiones y asignaciones revocadas
- cambios de rol por periodo

## Estado de implementación

- El alta ya se ejecuta desde el panel: el botón «Nuevo colaborador» (permiso `staff.manage`) crea el expediente (`POST /admin/staff`) y, si la cuenta tiene `roles.manage`, permite crear la cuenta de acceso con contraseña (mínimo 12 caracteres) y roles iniciales (`POST /admin/users`). El backend valida número de empleado y correo únicos (`409`), el colaborador activo y la existencia de los roles.
- La contraseña se guarda con Argon2 y nunca se devuelve; la creación queda auditada con el responsable (`account_created`, `employee_created`).
- La asignación y revocación de roles por cuenta ya se hacen desde la pestaña «Usuarios», con protección del último dueño (`409`), y las sesiones activas se listan y revocan desde «Sesiones».
- La baja ya se ejecuta desde el panel: la pestaña «Usuarios» permite deshabilitar o habilitar la cuenta (`PATCH /admin/users/{user_id}`). Al deshabilitar se revocan las sesiones abiertas de inmediato, se rechazan nuevos inicios de sesión y se impide dejar al club sin ningún dueño activo (`409`). El expediente, los roles y los eventos de auditoría se conservan; no se elimina nada físicamente. El reingreso se hace habilitando la cuenta de nuevo.
- Quedan pendientes: contratos y obligaciones laborales, MFA, limitación de intentos, recuperación de contraseña y el auto-marcaje de asistencia.