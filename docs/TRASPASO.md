# Traspaso para retomar el trabajo

Actualizado: 2026-10-30 · Último commit: `7c8f65d` · Rama: `main` (sincronizada con `origin`).

Esta nota es el punto de entrada para otra persona o IA. El estado detallado vive en [README.md](README.md#estado-del-proyecto) y el histórico en [changelog.md](changelog.md); aquí solo se resume qué está hecho, qué sigue y qué no debe tocarse sin pedirlo.

## Dónde quedó el trabajo

Se cerró el ciclo de asistencia del personal (ADR-041 a ADR-049). El último corte, ADR-049 (`7c8f65d`), agregó el envío real de la cola de correos de asistencia, su reintento y la tarjeta «Correos de asistencia» del panel.

- La suite del backend quedó en **293 pruebas** (288 pasan; las 5 de PostgreSQL se omiten sin `TEST_POSTGRES_URL`).
- `npx tsc --noEmit` del panel quedó limpio y el incremento se verificó en navegador sobre la vista previa.
- El árbol de trabajo quedó limpio y sin commits pendientes de subir.

## Siguiente corte sugerido

En este orden, salvo que se pida otra cosa:

1. **Acuse de entrega de la cola de correo.** Hoy `sent` solo significa que el servidor SMTP aceptó el mensaje: no hay rebotes ni confirmación de bandeja. Requiere un proveedor con webhooks o consulta de estado; hasta entonces la tarjeta no debe presentarse como acuse.
2. **Extender el correo a los demás avisos del personal** (revisión de entrenamiento, ticket de mantenimiento asignado, vencimiento del token del kiosco). `STAFF_NOTIFICATION_EMAIL_KINDS` es el único punto que decide qué sale por correo y hoy lista solo los seis tipos de asistencia.
3. **Avisos push**, que siguen sin existir para socios ni para personal.

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
- Cada incremento deja evidencia en: ADR nuevo en `docs/05-decisiones/` (el siguiente sería ADR-050), `docs/README.md` (índice, fase y pendientes), el documento del módulo, `docs/01-arquitectura/modelo-de-datos.md` si cambia el esquema, `docs/07-pruebas/plan-de-pruebas.md` con el recuento de la suite, `docs/changelog.md` y, si aplica, `docs/deuda-tecnica.md`.
- La suite que cita la documentación debe coincidir con la ejecución real; si cambia el número, actualizarlo en README, plan de pruebas, changelog y deuda técnica.

## Trampas conocidas

- `FOR UPDATE` es efectivo solo en PostgreSQL; en SQLite (pruebas y vista previa) es no-op, por eso la concurrencia se prueba con la suite opt-in `TEST_POSTGRES_URL`.
- El correo en vista previa nunca sale: la entrega queda `simulated`. `sent` es aceptación del SMTP, no entrega.
- Un fallo de correo no se reintenta solo; el reintento es manual y solo aplica a `failed`.
- La pasada de correo corre tras la respuesta y no tiene worker: lo que se encola sin usar el panel espera a la próxima consulta o al envío manual.
