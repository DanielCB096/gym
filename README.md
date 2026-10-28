# Gym Manager

Sistema integral de gestión para un solo gimnasio en México. Este repositorio sigue una arquitectura monorepo para mantener juntos el backend, la web administrativa, la app móvil, el kiosco y la documentación de negocio.

## Objetivo

Gestionar la operación completa de un gimnasio con foco en:

- membresías y cobro recurrente
- acceso y seguridad
- clases y reservas
- rutinas y progreso
- punto de venta e inventario
- facturación CFDI 4.0
- mantenimiento de equipos
- gestión de personal
- extensibilidad para servicios extra futuros

## Estructura del repositorio

```text
/gym
├── .github/
│   └── workflows/
│       └── ci.yml
├── backend/
│   ├── src/
│   ├── tests/
│   └── README.md
├── web/
│   └── README.md
├── mobile/
│   └── README.md
├── kiosk/
│   └── README.md
├── docs/
│   ├── README.md
│   ├── roadmap.md
│   ├── changelog.md
│   ├── deuda-tecnica.md
│   ├── 00-contexto/
│   ├── 01-arquitectura/
│   ├── 02-modulos/
│   ├── 03-procesos/
│   ├── 04-integraciones/
│   ├── 05-decisiones/
│   ├── 06-operacion/
│   └── 07-pruebas/
├── .gitignore
├── .env.example
├── CLAUDE.md
├── package.json
└── README.md
```

## Stack propuesto

- Backend: Python + FastAPI
- Base de datos: PostgreSQL
- Cache y colas: Redis + Celery
- Web admin: Next.js + TypeScript
- App móvil: React Native + Expo (acceso del socio con código OTP por correo)
- Kiosco: PWA estática sin dependencias (`kiosk/`) para una tablet de recepción
- Autenticación: sesiones opacas Bearer con RBAC para el personal y OTP por correo para socios; MFA para administradores pendiente
- Facturación: integración con PAC vía XML/JSON
- Pagos: Conekta como pasarela recomendada para México

## Reglas de negocio clave

- El sistema no guarda datos de tarjeta; solo tokens de la pasarela.
- El acceso sin internet debe funcionar mediante caché local y sincronización al reconectar.
- Solo se permite acceso a socios con membresía vigente, sin adeudo bloqueante y dentro del horario del plan.
- Los datos biométricos se almacenan como plantillas cifradas; nunca como imagen.
- La auditoría debe registrar cambios sensibles y eventos críticos.

## Flujo de Git

- `main`: rama estable
- `feat/...`: nuevas funcionalidades
- `fix/...`: correcciones
- `docs/...`: documentación
- `chore/...`: mantenimiento y configuración

Formato sugerido de commits:

```bash
git commit -m "feat: agrega alta de socio con consentimientos"
```

## Guía rápida de arranque

1. Crear y activar entorno virtual Python.
2. Instalar dependencias del backend.
3. Configurar variables en `.env` copiando `.env.example`.
4. Levantar PostgreSQL y Redis.
5. Ejecutar migraciones.
6. Correr pruebas unitarias y de integración.
7. Iniciar web, móvil y kiosco por separado.

## Verificación

Se ejecutan pruebas y lint en CI para cada cambio (backend, panel web, typecheck de la app móvil y la cadena de migraciones Alembic contra PostgreSQL 16). La documentación se mantiene en este repositorio como contexto del proyecto. La app móvil del socio se inicia desde `mobile/` con `npm install` y `npm start`; apunta al backend con `EXPO_PUBLIC_API_URL` y el portal usa `SECRET_KEY` para firmar los códigos OTP. El kiosco de recepción se sirve como sitio estático con `python -m http.server 8090 --directory kiosk` y se configura con la URL del backend y el token que el panel muestra una sola vez. Ver `mobile/README.md` y `kiosk/README.md`.

## Importante

⚠️ Los cobros, facturación, nómina, seguridad, y datos biométricos deben ser validados por profesionales especializados antes de entrar en producción.
