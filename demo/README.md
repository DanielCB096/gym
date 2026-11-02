# Demo comercial

Demo guiada sobre el **sistema real** (panel, app del socio y kiosco), con una
base SQLite desechable y datos sintéticos. No es una maqueta ni una presentación
de diapositivas: todo lo que se muestra sale del backend.

## Arranque rápido

Desde la raíz del repositorio, en PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File demo\start-demo.ps1 -Reset -WithMobile
```

La primera vez tarda unos minutos porque copia la base de vista previa y vuelve
a sembrar los módulos. Las siguientes veces basta con:

```powershell
powershell -ExecutionPolicy Bypass -File demo\start-demo.ps1
```

Para incluir la app del socio como sitio web de Expo, agrega `-WithMobile` al
arranque; requiere `mobile/node_modules` instalado.

Al terminar imprime las URLs, las cuentas y el token del kiosco. Para apagar
todo:

```powershell
powershell -ExecutionPolicy Bypass -File demo\stop-demo.ps1
```

Antes de que entre el cliente, un chequeo rápido de backend, panel, kiosco,
login y OTP:

```powershell
powershell -ExecutionPolicy Bypass -File demo\check-demo.ps1
```

## Qué levanta

| Servicio | URL | Para qué |
| --- | --- | --- |
| Panel administrativo | <http://localhost:3001> | La demo principal |
| API y Swagger | <http://127.0.0.1:8010/docs> | Enseñar que hay backend real, si lo piden |
| Kiosco de recepción | <http://localhost:8090> | Check-in con el código del socio |
| App del socio (Expo web) | <http://localhost:8081> | Solo con `-WithMobile` |

El panel se abre solo al final (salvo que uses `-NoBrowser`).

## Cuentas

La contraseña compartida es `DemoGimnasio2026!` (se puede cambiar con
`-DemoPassword`, mínimo 12 caracteres).

| Rol | Correo | Para mostrar |
| --- | --- | --- |
| Dueño | `owner@centrofit.mx` | Todo el sistema y RBAC completo |
| Gerente | `gerente@centrofit.mx` | Operación y finanzas, sin roles ni sesiones |
| Recepción | `recepcion@centrofit.mx` | Vista reducida: socios, accesos, clases, caja |
| Entrenador | `carlos.ortiz@centrofit.mx` | Rutinas, clases y su propia jornada |
| Mantenimiento | `mantenimiento.preview@centrofit.mx` | Solo equipos y tickets |

Socio para la app: `ana.lopez@example.com`. En vista previa el código OTP se
muestra en la propia pantalla; no se envía correo real.

## Qué contiene la base

La copia parte de `backend/gym_preview.db` (la base curada de la vista previa,
ignorada por git) y vuelve a ejecutar los seeds de clases, fisioterapia,
rutinas, mantenimiento, reportes, cuentas de socio, devoluciones, facturación,
PPD y conciliación. `backend/seed_demo.py` remata el conjunto:

- cinco cuentas de personal con roles distintos y contraseña conocida;
- membresías vigentes: Ana vence en 3 días (caso «por vencer»), Sofía está
  congelada y Raúl aparece vencido (caso «acceso denegado»);
- un kiosco nuevo, `Recepción demo`, cuyo token se guarda en
  `backend/.secrets/demo-kiosk-token.txt` (ignorado por git).

Nada de esto toca `backend/gym_preview.db`: el runtime vive en
`backend/.demo_runtime/`, su base se vuelve a copiar con `-Reset` y sus
archivos locales están ignorados por Git. Detén la demo antes de reemplazar la
base.

## Antes de la reunión

1. Ejecuta el arranque con al menos 10 minutos de margen.
2. Entra al panel como dueño y abre un turno de caja en
   **Inventario → Caja y cortes** (si ya hay uno abierto, déjalo: la demo de
   punto de venta lo aprovecha).
3. Configura el kiosco con la URL `http://127.0.0.1:8010` y el token que imprimió
   el lanzador (**Kiosco → Nuevo dispositivo** también permite generar otro).
4. Deja el guion abierto en otra pantalla: [`GUION-DEMO.md`](GUION-DEMO.md).
5. Comprueba la app del socio con el OTP de Ana y genera un código de acceso.

## Problemas comunes

- **Puerto ocupado**: cierra el proceso o cambia el puerto, por ejemplo
  `-BackendPort 8011 -WebPort 3002`.
- **Falta `backend/gym_preview.db`**: es la base curada local, no está en git.
  Restáurala antes de la demo.
- **Falta el venv o `node_modules`**: el lanzador lo detecta y se detiene con un
  mensaje claro; instala `backend/requirements.txt` y `npm install` en `web/`.
- **Un seed falla**: el lanzador se detiene y muestra el error. Los logs quedan
  en `backend/.demo_runtime/logs/`.
- **El panel carga pero no hay datos**: revisa que el backend esté en `8010` y
  que `GYM_API_URL` apunte ahí; el lanzador ya lo configura.
- **`web/next-env.d.ts` aparece modificado**: es un archivo generado por
  `next dev` (cambia la ruta de tipos entre desarrollo y build). No forma parte
  de la demo; confirma que no tenga cambios propios antes de restaurar ese
  archivo generado.

## Límites que conviene decir en voz alta

La demo corre en **modo vista previa**: los pagos con Conekta están simulados o
en sandbox, el timbrado CFDI no llega al SAT, el correo y el push se marcan como
simulados, y no hay torniquete, biométrico ni lector físico conectado. Los datos
son sintéticos. Los servidores del panel, kiosco y app se enlazan a localhost;
la demo no está diseñada para exponerse en una red compartida. Para producción
faltan credenciales reales, certificación del PAC, despliegue, respaldos, MFA y
las decisiones de operación que están en `docs/`.
