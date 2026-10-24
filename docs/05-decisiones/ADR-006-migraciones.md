# ADR-006: Migraciones de base de datos

- Fecha: 2026-10-15
- Estado: propuesta

## Contexto

El backend declara SQLModel y PostgreSQL, pero todavía no tiene código ni un mecanismo para versionar el esquema. El primer flujo de implementación necesita cambios reproducibles y revisables sin recrear la base manualmente.

## Decisión

Usar Alembic para migraciones versionadas, con revisiones en `backend/alembic/versions/`. Las revisiones iniciales describen explícitamente las tablas y restricciones; el esquema se aplica usando `DATABASE_URL` del entorno y el driver `psycopg`.

## Consecuencias

- El esquema puede aplicarse desde una base vacía y su versión queda registrada en `alembic_version`.
- Ninguna migración contiene credenciales ni depende de una URL guardada en el repositorio.
- La primera migración cubre socios, membresías, consentimientos y cobros; otros dominios se agregan en revisiones posteriores.
- El downgrade de la migración inicial elimina sus tablas y datos; solo se usa en bases desechables o después de un respaldo verificado.
- La migración no sustituye pruebas de integración contra PostgreSQL ni validación de reglas de negocio en servicios.

## Alternativas consideradas

1. Scripts SQL manuales sin historial de revisiones: descartados por falta de seguimiento uniforme de versión.
2. Generación automática del esquema al iniciar la API: descartada porque oculta cambios y no proporciona una revisión de migración explícita.

## Referencias

- `backend/alembic.ini`
- `backend/alembic/versions/20261015_0001_memberships_billing.py`
- `docs/01-arquitectura/modelo-de-datos.md`