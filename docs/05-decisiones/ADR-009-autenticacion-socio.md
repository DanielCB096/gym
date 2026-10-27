# ADR-009: Autenticación del socio con código OTP por correo

- Fecha: 2026-10-27
- Estado: propuesta inicial

## Contexto

La app del socio necesita una identidad propia, separada de las cuentas del personal. El club ya registra el correo del socio y no quiere administrar contraseñas adicionales para decenas o cientos de socios; al mismo tiempo, la app expone datos personales, membresía, acceso y saldo, así que no puede depender solo del correo escrito por el usuario.

## Decisión

- El socio inicia sesión con un **código de un solo uso de 6 dígitos enviado al correo registrado**. No hay contraseña de socio.
- El código vive 10 minutos, es de un solo uso y admite 5 intentos. El backend guarda solo un **HMAC-SHA256** calculado con `SECRET_KEY` sobre el id del código, el id del socio y el código; nunca guarda el código en claro.
- Se emiten como máximo 5 códigos por socio cada 15 minutos. Los intentos extra se descartan en silencio.
- `POST /member/auth/request-code` responde `202` para cualquier correo: desconocido, inactivo, limitado o con código enviado. Así no se puede usar para descubrir socios. Solo en `PREVIEW_MODE` devuelve `preview_code` para probar sin SMTP.
- `POST /member/auth/verify` compara en tiempo constante y responde `401` genérico ante código inválido, vencido, consumido o con intentos agotados.
- La sesión es un token opaco de 32 bytes con vigencia de 30 días; la base guarda solo su SHA-256. La sesión del socio vive en `member_sessions`, separada de `user_sessions` del personal, y se valida con una dependencia distinta (`get_current_member`). Un token no cruza entre `/member/*` y `/admin/*`.
- El cliente envía `Authorization: Bearer`; no se usan cookies ni `allow_credentials`. CORS es opcional y solo se monta con orígenes explícitos en `CORS_ORIGINS` (vista web de Expo).
- Cada solicitud, entrega, verificación, login y logout se registra en `member_auth_events` con resultado y motivo, sin código ni token.
- El perfil (`GET /member/me`) devuelve solo los datos del socio autenticado: contacto, alta, saldo, acceso habilitado y la membresía más reciente.

## Consecuencias y límites

- La seguridad del acceso depende de la **propiedad del correo**: si un tercero controla el buzón, puede entrar. No hay segundo factor para el socio, ni verificación de teléfono, ni biometría.
- El envío es síncrono con el transporte SMTP compartido (`app/mailer.py`), sin cola ni reintento automático: un fallo responde `502` y un SMTP ausente en producción `503`. La entregabilidad del correo es un requisito operativo.
- El rate limit es por socio (5 códigos/15 min) y por código (5 intentos), pero no hay límite global por IP, captcha ni bloqueo de cuenta; un atacante puede intentar códigos de un socio hasta agotar sus intentos, aunque no puede leerlos.
- Las sesiones no rotan ni se renuevan por sliding window: `last_seen_at` se actualiza, pero el token vive 30 días o hasta el logout. No hay cierre por inactividad, lista de dispositivos ni revocación por parte del socio.
- La app web de Expo no persiste el token (se pierde al recargar) porque `SecureStore` no está disponible; en nativo sí se guarda en el llavero/Keystore.
- El portal no expone reservas, rutinas, pagos ni facturas todavía: esta decisión cubre solo autenticación y consulta del perfil. Las notificaciones push y los recordatorios quedan fuera.
- Antes de producción: definir retención de `member_auth_events`, política de privacidad del correo, límites por IP, rotación de `SECRET_KEY` (invalidaría códigos vigentes, no sesiones porque solo se guarda su hash), alertas de accesos anómalos y MFA opcional.

## Referencias

- `backend/src/app/modules/portal/models.py`
- `backend/src/app/modules/portal/service.py`
- `backend/src/app/main.py` (`/member/auth/*`, `/member/me`, `get_current_member`, CORS)
- `backend/alembic/versions/20261027_0031_member_portal.py`
- `backend/tests/test_member_portal_api.py`
- `mobile/README.md`
- `docs/01-arquitectura/seguridad-y-privacidad.md`
