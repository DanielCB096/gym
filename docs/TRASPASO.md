# Traspaso para retomar el trabajo

Actualizado: 2026-10-30 · Rama: `main` · ADR-050, ADR-051 y ADR-052 se publican en el commit de este corte; el anterior es `1fe7992`.

Esta nota es el punto de entrada para otra persona o IA. El estado detallado vive en [README.md](README.md#estado-del-proyecto) y el histórico en [changelog.md](changelog.md); aquí solo se resume qué está hecho, qué sigue y qué no debe tocarse sin pedirlo.

## Dónde quedó el trabajo

Se cerró el ciclo de asistencia del personal (ADR-041 a ADR-049). Después, ADR-050 llevó la cola de correo a los **nueve** avisos del personal —revisión de entrenamiento, ticket de mantenimiento asignado y vencimiento del token del kiosco incluidos—, con asunto y pie por área, y generalizó la tarjeta del panel como «Correos del personal».

Sobre eso, el corte de acuse y push añadió dos canales nuevos:

- **ADR-051 · acuse de entrega por webhook firmado**: cada entrega nace con un `message_id` (`<uuid>@centro-fit.local`) que viaja como `Message-ID`; `POST /webhooks/email/delivery` recibe `delivered`/`bounced`/`complained` firmado con `X-Email-Signature: sha256=…` (HMAC-SHA256 de `EMAIL_WEBHOOK_SECRET`), es idempotente por `provider_event_id`, solo acusa entregas `sent` y guarda en `staff_notification_delivery_receipts` (append-only). El panel suma la columna «ACUSE» con su estado, su hora y su detalle.
- **ADR-052 · push del socio desde la app**: la app registra su token de Expo (`POST /member/push-tokens`), el aviso escribe una `member_push_deliveries` por token activo en la misma transacción y `MemberPushFlush` envía tras la respuesta con reclamo compare-and-set; `DeviceNotRegistered` retira el token, el cierre de sesión apaga todos los dispositivos y la vista previa simula el envío.
- La suite del backend quedó en **321 pruebas** (316 pasan; las 5 de PostgreSQL se omiten sin `TEST_POSTGRES_URL`). La migración más reciente es `20261031_0067_member_push_deliveries`.
- `npx tsc --noEmit` quedó limpio en el panel y en la app móvil. En la vista previa, una entrega sintética en `sent` recibió un webhook firmado y el panel mostró su acuse «Entregado»; el registro de un token de push, su revocación y el cierre de sesión respondieron `201`/`204`/`204`. Los datos sintéticos, el hash de la cuenta de dirección y las sesiones temporales se revirtieron al terminar.
- **ADR-050, ADR-051 y ADR-052 van en el commit de este corte** (`feat(avisos): …`), empujado a `origin/main` junto con el código, las pruebas y la documentación. El commit anterior es `1fe7992`.

## Siguiente corte sugerido

En este orden, salvo que se pida otra cosa:

1. **Conectar los canales reales.** El acuse ya tiene contrato y cola, pero falta el adaptador del proveedor de correo (y el SMTP real): el webhook existe y se prueba firmado, pero nadie lo llama todavía. Del lado push, la app ya registra el token, pero sin un build de EAS con `extra.eas.projectId` y un dispositivo físico solo se ejerce la simulación.
2. **Cerrar los límites del canal nuevo**: ventana de tiempo y rotación de secreto en el webhook, retención de recibos, reintento manual del push fallido, preferencias por tipo y navegación al tocar el aviso. Están listados en `docs/deuda-tecnica.md`.

El resto de la lista pendiente (pago en línea, reportes programados, mensajería entrenador-socio, nómina, conexión bancaria, etc.) está en la sección «Estado del proyecto» del [README](README.md#estado-del-proyecto).

## Decisiones del usuario que no se deben revertir sin pedirlo

- **Penalizaciones por inasistencia o cancelación tardía**: fuera de alcance («eso de las penalizaciones no me interesa de momento»).
- **Accesos**: pospuestos («deja accesos para luego»); no reintroducir trabajo de kiosco o lector salvo que lo pida.
- **Bloqueo por deuda**: se queda como está, sin implementar.
- **Aforo**: se conserva la estimación actual; no registrar salidas reales.
- **Pagos con pasarela, SAT/Finkok**: no tocar salvo petición explícita. El timbrado sigue siendo simulado y sin validez fiscal.
- **Cierre del aviso del token del kiosco**: pospuesto con «continuemos con otra cosa de momento»; no empujarlo.

## Cómo levantar y verificar

- Backend: `cd backend && PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q`.
- Backend de vista previa: `PREVIEW_MODE=true APP_TIMEZONE=America/Mexico_City PYTHONPATH=src .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000`. **Reiniciarlo después de cambiar código del backend**: sin reinicio sirve el módulo viejo y las rutas nuevas responden `404`.
- Panel: `cd web && npx next dev` y abrirlo en `localhost:3000` (Next 16 bloquea recursos de desarrollo servidos a `127.0.0.1`). Typecheck: `npx tsc --noEmit`.
- App del socio: Expo web desde `app/` (ver su README).
- La vista previa usa `backend/gym_preview.db` y `preview_patch.py` para columnas y parches de esquema; las migraciones Alembic no se ejecutan en pruebas ni en la vista previa.

## Reglas de trabajo del proyecto

- Commits en español con alcance, p. ej. `feat(asistencia): …`; un incremento validado por commit.
- **Nunca** versionar `gym_preview.db`, sus `.bak`, `.env`, credenciales, tokens de kiosco ni códigos OTP del socio.
- Cada incremento deja evidencia en: ADR nuevo en `docs/05-decisiones/` (el siguiente sería ADR-053), `docs/README.md` (índice, fase y pendientes), el documento del módulo, `docs/01-arquitectura/modelo-de-datos.md` si cambia el esquema, `docs/07-pruebas/plan-de-pruebas.md` con el recuento de la suite, `docs/changelog.md` y, si aplica, `docs/deuda-tecnica.md`.
- La suite que cita la documentación debe coincidir con la ejecución real; si cambia el número, actualizarlo en README, plan de pruebas, changelog y deuda técnica.

## Trampas conocidas

- `FOR UPDATE` es efectivo solo en PostgreSQL; en SQLite (pruebas y vista previa) es no-op, por eso la concurrencia se prueba con la suite opt-in `TEST_POSTGRES_URL`.
- El correo en vista previa nunca sale: la entrega queda `simulated`. `sent` es aceptación del SMTP, no entrega.
- Un fallo de correo no se reintenta solo; el reintento es manual y solo aplica a `failed`.
- La pasada de correo corre tras la respuesta y no tiene worker: lo que se encola sin una petición que use el panel espera a la próxima consulta o al envío manual. Las rutas que emiten avisos de rutinas o de mantenimiento ya la disparan; el token del kiosco se emite perezosamente dentro de las lecturas de la bandeja, que también la disparan.
- El **acuse no cambia el estado del envío**: una entrega `sent` con `bounced` sigue contando como enviada y el reintento manual solo acepta `failed`. El acuse es información aparte, no un quinto estado.
- `EMAIL_WEBHOOK_SECRET` vacío hace que el webhook responda `503`; el secreto es único y manual, sin rotación. En vista previa hay que fijarlo para probar la firma.
- El **push del socio** se simula en vista previa (`simulated`), igual que el correo. El registro del token es best-effort: sin `extra.eas.projectId` en `app.json`/EAS la app no registra nada y no avisa, y el token se transfiere al último inicio de sesión del dispositivo.
- La pasada de push (`MemberPushFlush`) se cuelga de cada emisor de avisos del socio; un aviso que nazca sin una de esas rutas se queda `pending` hasta la siguiente pasada.
