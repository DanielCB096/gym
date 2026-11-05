#!/usr/bin/env python3
"""Buscador semantico local con memoria."""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

DB = Path(os.environ.get(
    "MEMORIA_DB",
    Path(__file__).resolve().parent / "memoria_db",
)).resolve()
EXTS = {
    ".txt", ".md", ".py", ".js", ".jsx", ".ts", ".tsx", ".json",
    ".csv", ".html", ".pdf", ".sql", ".sh", ".ps1", ".yaml", ".yml",
    ".toml", ".ini",
}
EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "node_modules", ".next", "__pycache__",
    "memoria_db", "artifacts", "clientes-real", "reales", "uploads",
    "photos-real", "postgres_data", "redis_data", ".demo_runtime",
}
EXCLUDED_FILE_NAMES = {".env", ".secrets"}
CHUNK, OVERLAP = 800, 150
DIM = 4096
MODELO = "paraphrase-multilingual-MiniLM-L12-v2"

_model = None


def cargar_modelo():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(MODELO)
        except Exception:
            _model = False
    return _model


def tokens(texto):
    return re.findall(r"\w+", texto.lower())


def vec_lexico(texto):
    vector = np.zeros(DIM, dtype=np.float32)
    for token in tokens(texto):
        hashed = int(hashlib.md5(token.encode()).hexdigest()[:8], 16) % DIM
        vector[hashed] += 1
    return np.log1p(vector)


def embed(textos, backend):
    if backend == "st":
        model = cargar_modelo()
        embeddings = model.encode(
            textos,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(embeddings, dtype=np.float32)
    return np.stack([vec_lexico(texto) for texto in textos])


def leer(path):
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
            texto = "\n".join(
                (pagina.extract_text() or "") for pagina in PdfReader(str(path)).pages
            )
            if not texto.strip():
                print(
                    f"  (omito {path.name}: sin texto extraible; "
                    "¿es un PDF escaneado que necesita OCR?)",
                    file=sys.stderr,
                )
            return texto
        except Exception as error:
            print(
                f"  (omito {path.name}: PDF corrupto o ilegible: "
                f"{type(error).__name__}: {error})",
                file=sys.stderr,
            )
            return ""
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception as error:
        print(
            f"  (omito {path.name}: archivo de texto ilegible: "
            f"{type(error).__name__}: {error})",
            file=sys.stderr,
        )
        return ""


def trocear(texto):
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    trozos = []
    inicio = 0
    while inicio < len(texto):
        fin = min(inicio + CHUNK, len(texto))
        if fin < len(texto):
            corte = max(texto.rfind("\n", inicio, fin), texto.rfind(". ", inicio, fin))
            if corte > inicio + CHUNK // 2:
                fin = corte + 1
        trozo = texto[inicio:fin].strip()
        if trozo:
            trozos.append(trozo)
        if fin >= len(texto):
            break
        inicio = fin - OVERLAP
    return trozos


def cargar_db():
    meta_path = DB / "meta.json"
    vectors_path = DB / "vecs.npy"
    if not meta_path.exists() or not vectors_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        vectors = np.load(vectors_path)
        if len(meta["chunks"]) != len(vectors):
            raise ValueError("meta.json y vecs.npy no coinciden")
        return meta, vectors
    except Exception as error:
        sello = time.strftime("%Y%m%d-%H%M%S")
        for path in (meta_path, vectors_path):
            if path.exists():
                path.replace(path.with_name(path.name + f".corrupto-{sello}"))
        print(
            f"Aviso: el indice estaba dañado ({error}). Se apartó una copia "
            f"(*.corrupto-{sello}) y se inicia limpio; reindexa la carpeta.",
            file=sys.stderr,
        )
        return None


def guardar_db(meta, vectors):
    DB.mkdir(parents=True, exist_ok=True)
    temp_meta = DB / "meta.json.tmp"
    temp_vectors = DB / "vecs.tmp.npy"
    temp_meta.write_text(
        json.dumps(meta, ensure_ascii=False),
        encoding="utf-8",
    )
    np.save(temp_vectors, vectors)
    os.replace(temp_vectors, DB / "vecs.npy")
    os.replace(temp_meta, DB / "meta.json")


def elegir_backend():
    return "st" if cargar_modelo() else "lex"


def agregar(trozos, backend):
    db = cargar_db()
    if db:
        meta, vectors = db
        if meta["backend"] != backend:
            sys.exit(
                f"El indice usa '{meta['backend']}' y ahora tienes '{backend}'. "
                "Reindexa con MEMORIA_DB limpio."
            )
        fuentes = {fuente for fuente, _ in trozos if not fuente.startswith("nota:")}
        keep = [
            index for index, chunk in enumerate(meta["chunks"])
            if chunk["fuente"] not in fuentes
        ]
        meta["chunks"] = [meta["chunks"][index] for index in keep]
        vectors = (
            vectors[keep] if keep
            else np.zeros((0, vectors.shape[1]), dtype=np.float32)
        )
    else:
        meta = {"backend": backend, "chunks": []}
        vectors = None
    nuevos = embed([texto for _, texto in trozos], backend)
    vectors = nuevos if vectors is None or len(vectors) == 0 else np.vstack([vectors, nuevos])
    meta["chunks"] += [
        {"fuente": fuente, "texto": texto, "t": time.time()}
        for fuente, texto in trozos
    ]
    guardar_db(meta, vectors)
    return len(meta["chunks"])


def cmd_indexar(carpeta):
    base = Path(carpeta).resolve()
    if not base.exists():
        sys.exit("Esa carpeta no existe.")
    trozos, archivos = [], 0
    for path in sorted(base.rglob("*")):
        resolved = path.resolve()
        if (
            not path.is_file()
            or DB in resolved.parents
            or any(parte in EXCLUDED_DIRS for parte in resolved.parts)
            or (
                path.name in EXCLUDED_FILE_NAMES
                or path.name.startswith(".env.")
                and path.name != ".env.example"
            )
        ):
            continue
        if path.suffix.lower() not in EXTS and path.name != ".env.example":
            continue
        texto = leer(path)
        fragmentos = trocear(texto)
        trozos += [(str(resolved), fragmento) for fragmento in fragmentos]
        if fragmentos:
            archivos += 1
    if not trozos:
        sys.exit("No encontré texto para indexar.")
    backend = elegir_backend()
    total = agregar(trozos, backend)
    print(
        f"Indexados {archivos} archivos, {len(trozos)} fragmentos nuevos "
        f"({total} en total). Motor: {backend}"
    )


def cmd_recordar(nota):
    backend = elegir_backend()
    total = agregar(
        [("nota:" + time.strftime("%Y-%m-%d %H:%M"), nota)],
        backend,
    )
    print(f"Guardado. La memoria tiene {total} fragmentos.")


def buscar(consulta, k=5):
    db = cargar_db()
    if not db:
        sys.exit("No hay índice. Usa primero: indexar CARPETA")
    meta, vectors = db
    backend = meta["backend"]
    query = embed([consulta], backend)[0]
    if backend == "lex":
        df = (vectors > 0).sum(0)
        idf = np.log((1 + len(vectors)) / (1 + df)) + 1
        matrix = vectors * idf
        matrix = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
        query = query * idf
        query = query / (np.linalg.norm(query) + 1e-9)
    else:
        matrix = vectors
    scores = matrix @ query
    indices = np.argsort(-scores)[:max(1, k)]
    return [
        (
            float(scores[index]),
            meta["chunks"][index]["fuente"],
            meta["chunks"][index]["texto"],
        )
        for index in indices
    ]


def cmd_buscar(consulta, k):
    for score, source, text in buscar(consulta, k):
        print(f"\n[{score:.2f}] {source}\n{text}\n{'-' * 60}")


def cmd_info():
    db = cargar_db()
    if not db:
        print("Sin índice todavía.")
        return
    meta, _ = db
    fuentes = {chunk["fuente"] for chunk in meta["chunks"]}
    print(
        f"Motor: {meta['backend']} | fragmentos: {len(meta['chunks'])} "
        f"| fuentes: {len(fuentes)}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    subparsers.add_parser("indexar").add_argument("carpeta")
    search = subparsers.add_parser("buscar")
    search.add_argument("consulta")
    search.add_argument("-k", type=int, default=5)
    subparsers.add_parser("recordar").add_argument("nota")
    subparsers.add_parser("info")
    args = parser.parse_args()
    if args.cmd == "indexar":
        cmd_indexar(args.carpeta)
    elif args.cmd == "buscar":
        cmd_buscar(args.consulta, args.k)
    elif args.cmd == "recordar":
        cmd_recordar(args.nota)
    else:
        cmd_info()
