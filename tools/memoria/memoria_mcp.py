#!/usr/bin/env python3
"""Servidor MCP para memoria.py."""
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP

import memoria

mcp = FastMCP("memoria")


@mcp.tool()
def buscar_en_memoria(consulta: str, k: int = 5) -> str:
    """Busca fragmentos relevantes en documentos y notas locales."""
    try:
        results = memoria.buscar(consulta, max(1, min(k, 15)))
    except SystemExit as error:
        return f"Error: {error}"
    return "\n\n".join(
        f"[{score:.2f}] {source}\n{text}"
        for score, source, text in results
    ) or "Sin resultados."


@mcp.tool()
def guardar_en_memoria(nota: str) -> str:
    """Guarda una nota para recordarla en conversaciones futuras."""
    try:
        total = memoria.agregar(
            [("nota:" + memoria.time.strftime("%Y-%m-%d %H:%M"), nota)],
            memoria.elegir_backend(),
        )
    except SystemExit as error:
        return f"Error: {error}"
    return f"Guardado. La memoria tiene {total} fragmentos."


@mcp.tool()
def indexar_carpeta(ruta: str) -> str:
    """Indexa o reindexa una carpeta de archivos."""
    import contextlib
    import io

    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            memoria.cmd_indexar(ruta)
    except SystemExit as error:
        return f"Error: {error}"
    return output.getvalue().strip()


if __name__ == "__main__":
    mcp.run()
