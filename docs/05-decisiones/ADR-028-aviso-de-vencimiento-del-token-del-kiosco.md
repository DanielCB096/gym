# ADR-028: Aviso de vencimiento del token del kiosco al personal

- Fecha: 2026-10-29
- Estado: propuesta inicial

## Contexto

ADR-027 puso fecha a la credencial de la tablet: 90 días, rotación manual desde el panel y una tabla que pinta en ámbar los últimos 15 días. El límite quedó escrito en su propia sección de consecuencias: «un club que no mire la página "Kiosco" descubrirá la caducidad cuando la tablet vuelva a configuración». El aviso existía solo si alguien abría esa página; nadie recibía nada.

El club no tiene programador ni correo transaccional para el personal. Lo que sí tiene desde ADR-017 es una campana con una bandeja real que se consulta al iniciar sesión y al abrir el popover. La pregunta era si un vencimiento de credencial podía caber en esa bandeja sin inventar un job.

## Decisión

- **El aviso se materializa al leer la bandeja, no al vencer el token.** `warn_expiring_kiosk_tokens(session)` corre como primera línea de `GET /admin/notifications` y `GET /admin/notifications/unread-count`, es decir, cada vez que alguien mira la campana. Es el mismo patrón que `_ensure_membership_expiring` (ADR-016): el hecho se deriva del reloj del servidor en el momento de la lectura y la base de datos impone la deduplicación. No hay job, cola ni worker, porque el proyecto no tiene ninguno y agregarlo por un aviso sería desproporcionado.
- **La ventana es de 15 días, la misma que el ámbar del panel.** `KIOSK_TOKEN_WARNING = timedelta(days=15)`. Quien ve «Vence en 5 días» en la página «Kiosco» ve el mismo número en la campana; dos umbrales distintos obligarían a explicar por qué la campana calla lo que la tabla ya pinta.
- **Un token ya vencido también avisa, y con otro texto.** Si `token_expires_at <= ahora`, el aviso dice que la tablet ya no valida códigos y pide rotar y capturar el token nuevo. La fase forma parte de la clave de deduplicación, así que un kiosco avisado «faltan 3 días» recibe además el aviso de caducidad cuando llega el día: son dos hechos distintos y el segundo no puede quedar silenciado por el primero.
- **La audiencia son las cuentas que pueden rotar.** `user_ids_with_permission(session, "settings.manage")` devuelve las cuentas activas cuyos roles conceden el permiso en el instante de la lectura (asignación vigente, no revocada y dentro de su ventana). Es la misma audiencia que exige `POST /admin/kiosk/devices/{id}/rotate-token`: avisar a quien no puede actuar sería ruido. A diferencia de los avisos por empleado de ADR-017, aquí no se resuelve un `employee_id`, se consultan `user_role_assignments` porque el permiso vive en el rol.
- **La clave de deduplicación incluye el vencimiento, la fase y la cuenta.** `kiosk_token_expiring:<device_id>:<YYYY-MM-DD>:<soon|expired>:<user_id>`. Rotar reinicia la fecha, así que el ciclo vuelve a empezar y el club recibe un aviso por cada ventana; volver a leer la bandeja el mismo día no escribe nada. El índice único parcial de `staff_notifications` (ADR-017) es quien lo garantiza, no una comprobación en Python.
- **Las filas sin fecha no avisan nunca.** Un `token_expires_at` nulo significa «creado antes de ADR-027»; inventarle una fecha para poder avisar convertiría una fila antigua en una urgencia falsa.
- **El texto se congela en español, con la fecha del club.** El cuerpo nombra el kiosco por su etiqueta, la fecha local (`to_club_timezone`) y los días restantes redondeados hacia arriba (`math.ceil`), para que «faltan 1 día» sea singular y las últimas horas de la ventana no digan «faltan 0 días». `ref_id` apunta al dispositivo para un futuro enlace a la página «Kiosco»; hoy el popover no navega.
- **El `kind` nuevo exige migración.** `kiosk_token_expiring` se suma a `ck_staff_notifications_kind` con `20261029_0046_staff_notification_kiosk_token.py` (downgrade borra las filas del tipo y restaura el `CHECK` de dos valores) y `preview_patch.py` reconstruye la tabla en la vista previa.

## Consecuencias y límites

- El club se entera del vencimiento **sin abrir la página «Kiosco»**, siempre que alguien con `settings.manage` abra la campana. Si nadie la abre, la tablet seguirá cayendo a configuración el día 91: el aviso reduce el riesgo, no lo elimina.
- **No hay push ni correo.** Igual que el resto de la bandeja, el aviso solo se ve al entrar al panel; el conteo se refresca al iniciar sesión y al abrir el popover.
- **Una fila por cuenta y por fase.** Un club con tres dueños recibe tres filas por kiosco y por ventana; con varios kioscos, una fila por kiosco. No hay resumen agrupado ni un aviso único que diga «tres tokens vencen».
- **Si no hay cuentas con `settings.manage`, no se escribe nada** y el aviso no se pierde: se vuelve a calcular en la siguiente lectura cuando exista un destinatario.
- **El aviso no se retira al rotar.** La fila vieja permanece en la bandeja como historial; el texto sigue diciendo la fecha anterior. Es coherente con la bandeja del personal (ADR-017: historial, no flujo de trabajo), pero puede confundir a quien lea avisos antiguos.
- **Una lectura fallida aborta la campana.** El materializador hace `commit()` dentro de la petición de lectura; un error de escritura responde `500` en vez de mostrar la bandeja sin el aviso nuevo. Se aceptó porque el patrón ya estaba en el recordatorio de membresía y porque la alternativa —silenciar el error— haría invisible una base llena.
- **La antigüedad del aviso no se purga.** La retención sigue pendiente para toda la bandeja.

## Referencias

- `backend/src/app/modules/access/kiosk.py` (`KIOSK_TOKEN_WARNING`, `warn_expiring_kiosk_tokens`)
- `backend/src/app/modules/identity/service.py` (`user_ids_with_permission`)
- `backend/src/app/modules/notifications/models.py` (`STAFF_NOTIFICATION_KINDS`, `ck_staff_notifications_kind`)
- `backend/alembic/versions/20261029_0046_staff_notification_kiosk_token.py`
- `backend/preview_patch.py` (reconstrucción del `CHECK` de `staff_notifications`)
- `backend/src/app/main.py` (`GET /admin/notifications`, `GET /admin/notifications/unread-count`)
- `backend/tests/test_kiosk_access_api.py` (`test_kiosk_token_expiry_is_announced_to_settings_managers`)
