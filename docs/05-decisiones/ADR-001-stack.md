# ADR-001: Stack tecnológico inicial

- Fecha: 2026-10-15
- Estado: propuesta inicial

## Contexto

El proyecto necesita un stack popular, bien documentado, fácil de mantener y con capacidad para crecer sin complejidad innecesaria. Debe soportar backend, panel web, app móvil, kiosco y tareas de segundo plano.

## Opciones consideradas

1. Python + FastAPI + PostgreSQL + React + React Native
2. Node.js + NestJS + PostgreSQL + React + React Native
3. Full-stack monolítico con Django

## Decisión

Se elige Python + FastAPI como base del backend, PostgreSQL como base de datos principal, Redis para caché y colas, Next.js para web y React Native + Expo para móvil. El kiosco se implementará como una app web táctil con wrapper de Electron o PWA embebida.

## Consecuencias

- buena velocidad de desarrollo para un solo desarrollador
- ecosistema sólido para APIs, pagos, seguridad y automatización
- facilidad de extensión para módulos futuros
- requiere disciplina para mantener una arquitectura limpia y pruebas automatizadas

## Nota

⚠️ La decisión se revisará cuando el proyecto entre en validación técnica con proveedores reales y entornos productivos.
