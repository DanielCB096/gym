# Memoria local para agentes

Esta herramienta crea un buscador semantico sobre el repositorio. Puede ayudar
a las personas y a los agentes futuros a recuperar reglas, decisiones, procesos,
modulos, ADR, notas de traspaso y ejemplos anteriores sin leer todo el proyecto
en cada sesion.

## Uso

Desde la raiz del gimnasio:

```powershell
pip install -r tools/memoria/requirements.txt
python tools/memoria/memoria.py indexar .
python tools/memoria/memoria.py buscar "decision sobre reservas premium"
python tools/memoria/memoria.py recordar "Pendiente validar el flujo con datos sintéticos"
python tools/memoria/memoria.py info
```

También puede iniciarse como servidor MCP (SDK MCP 1.x o 2.x):

```powershell
python tools/memoria/memoria_mcp.py
```

Expone `buscar_en_memoria`, `guardar_en_memoria` e `indexar_carpeta`. La variable
`MEMORIA_DB` permite cambiar la ubicación local del índice; por defecto se usa
`tools/memoria/memoria_db/`.

## Alcance seguro

- El indice se guarda localmente en `tools/memoria/memoria_db/`.
- No indexa `.git`, entornos virtuales, dependencias instaladas, bases de datos,
  carpetas de datos reales, capturas de artefactos ni archivos de secretos.
- No subir `memoria_db/`, conversaciones locales ni archivos `.env`.
- Revisar los resultados antes de usarlos: el buscador recupera contexto, pero
  no sustituye leer el documento fuente ni verificar la documentacion vigente.
- No usar el indice como memoria de decisiones legales, fiscales, financieras
  o de seguridad; esas reglas deben seguirse desde los documentos oficiales y
  una revision profesional cuando corresponda.

## Exclusion de datos sensibles

La herramienta excluye directorios como `postgres_data`, `redis_data`,
`clientes-real`, `reales`, `uploads`, `photos-real`, `artifacts` y `.demo_runtime`.
Tambien excluye `.env`, `.env.*` excepto `.env.example` y nombres locales de
secretos.
