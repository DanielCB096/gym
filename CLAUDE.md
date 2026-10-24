# CLAUDE.md — Sistema de Gestión de Gimnasio

> Este archivo es la guía corta que debe leer la IA al iniciar una sesión de desarrollo.

## 1. Qué es este proyecto

Sistema integral para un único gimnasio en México. Gestiona memberships, acceso, clases, rutinas, punto de venta, facturación CFDI 4.0, mantenimiento de equipos y personal.

**Plataformas:** panel web administrativo, app móvil para socios, vista reducida para instructores y mantenimiento, y kiosco táctil en recepción.

## 2. Antes de escribir código

1. Leer `docs/README.md` y `docs/00-contexto/glosario.md`.
2. Leer el documento del módulo que se va a tocar.
3. Revisar el proceso transversal si aplica.
4. Revisar ADR antes de proponer tecnología o flujo nuevo.
5. Si una regla contradice la documentación, preguntar antes de implementar.

## 3. Stack y estructura

- Backend: Python + FastAPI
- Base de datos: PostgreSQL + Redis
- Web: Next.js + TypeScript
- Móvil: React Native + Expo
- Kiosco: React + Electron o PWA embebida en tableta
- Colas: Celery + Redis
- Pasarela de pago: Conekta
- PAC: Finkok o equivalente validado

Estructura base del monorepo:

```text
backend/
web/
mobile/
kiosk/
docs/
```

## 4. Comandos sugeridos

```bash
# backend
python -m venv .venv
pip install -r backend/requirements.txt
pytest backend/tests

# web
npm install
npm run dev
npm run lint

# mobile
npm install
npx expo start
```

## 5. Convenciones

- Nombres de entidades y tablas siguiendo el glosario.
- Nombres en inglés para código; textos visibles en español.
- Dinero siempre en centavos o decimal exacto; nunca float.
- Fechas en UTC y mostradas en zona horaria del gimnasio.
- Lógica de negocio en servicios, no en controladores.
- Cambios pequeños y verificables.

## 6. Reglas de negocio no negociables

1. El acceso solo permite personas con membresía vigente y sin adeudo bloqueante.
2. El acceso offline se apoya en caché local y sincronización posterior.
3. El sistema no guarda datos de tarjeta; solo tokens.
4. Los cobros son idempotentes.
5. El CFDI se emite mediante PAC respetando reglas del SAT.
6. Los biométricos se almacenan solo como plantilla cifrada.
7. Se registra auditoría para cambios sensibles.
8. Los permisos se validan en backend.
9. Los históricos no se borran; se archivan o marcan como anulados.
10. El equipo fuera de servicio se refleja en app y kiosco.

## 7. Rendimiento

- Pantallas menores a 2 s.
- Búsqueda de socio menor a 500 ms.
- Colas para cobros, notificaciones y reportes pesados.
- Archivos de histórico con archivado y partición de tablas.

## 8. Seguridad

- Secretos solo en variables de entorno.
- HTTPS y cifrado en reposo para datos sensibles.
- MFA para administradores.
- Auditoría de cambios críticos.

## 9. Pruebas

- Cobros y reintentos.
- Acceso online y offline.
- Facturación.
- Permisos.
- Nómina.
- Inventario.

## 10. Documentación obligatoria

- Actualizar el módulo tocado.
- Actualizar modelo de datos si cambia.
- Crear o actualizar ADR si hay decisión técnica.
- Añadir entrada al changelog.
- Registrar deuda técnica si hubo atajo.
- Indicar explícitamente qué documentos se cambiaron.

## 11. Control de versiones

- `main` estable.
- `feat/...`, `fix/...`, `docs/...`, `chore/...`.
- Commits pequeños y claros.
- No subir `.env`, llaves, certificados, bases de datos locales ni datos reales.

## 12. Orden de desarrollo

1. Base del proyecto.
2. Membresías, socios y cobro recurrente.
3. Control de acceso.
4. Punto de venta e inventario.
5. Facturación y reportes.
6. Clases y reservas.
7. Rutinas y progreso.
8. Mantenimiento de equipo.
9. Personal y nómina.
10. Comunicación y servicios extra.

⚠️ Cobros, facturación, nómina, biométricos y seguridad requieren revisión profesional.
