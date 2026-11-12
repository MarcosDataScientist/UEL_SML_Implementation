#!/usr/bin/env python3
"""Build the disposable pgvector store used by semantic expense-nature search.

The script reads the reference CSV (one row per *Linha*), derives the text that
will be embedded, embeds it with a local Ollama model, and recreates a flat
Postgres table. It never connects to the production database.

The Compose job runs this script with the CSV bind-mounted at
/app/data/naturezadespesa.csv. For a manual run from `test_environment/`:

    python semantic_search/ingest/ingest_naturezas.py --csv sql/data/naturezadespesa.csv
    python semantic_search/ingest/ingest_naturezas.py --dry-run --csv sql/data/naturezadespesa.csv

Environment overrides:

    PGVECTOR_HOST / PGVECTOR_PORT / PGVECTOR_DB
    PGVECTOR_USER / PGVECTOR_PASSWORD
    OLLAMA_BASE_URL / EMBED_MODEL / EMBED_DIM / EMBED_BATCH_SIZE
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV_PATH = REPO_ROOT.parent / "sql" / "data" / "naturezadespesa.csv"

DEFAULT_EMBED_MODEL = "qwen3-embedding:0.6b"
DEFAULT_EMBED_DIM = 1024
DEFAULT_EMBED_BATCH_SIZE = 32
DEFAULT_EMBED_TIMEOUT_SECONDS = 180
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
INSERT_PAGE_SIZE = 500

TABLE_NAME = "natureza_linhas"
META_TABLE_NAME = "natureza_embedding_meta"
CSV_FIELDS = ("codigo", "descricao", "detalhe", "titulo")

_REPORTING_PREFIX_RE = re.compile(
    r"^\s*(?:Registra|Regista)m?\s+o\s+valor\b[\s,.;:]*", re.I
)
_WHITESPACE_RE = re.compile(r"\s+")


class EmbeddingError(RuntimeError):
    """Raised when Ollama cannot produce embeddings matching the schema."""


class StoreUnavailableError(RuntimeError):
    """Raised when the disposable vector store cannot be reached."""


@dataclass(frozen=True, slots=True)
class Linha:
    """One reference-table row, ready to embed and store."""

    id: int
    codigo: str
    codigo_digits: str
    descricao: str
    titulo: str
    detalhe: str
    embed_text: str


def normalize_codigo(codigo: str) -> str:
    """Return the *Código* as digits only, punctuation-insensitive."""
    return re.sub(r"\D", "", codigo or "")


def strip_reporting_prefix(detalhe: str) -> str:
    """Drop only the leading "Registra/Regista o valor" reporting phrase.

    The phrase repeats across hundreds of *Linhas*; the words after it carry
    the distinguishing detail and must stay in the embedding text.
    """
    text = (detalhe or "").strip()
    return _REPORTING_PREFIX_RE.sub("", text).strip()


def build_embed_text(descricao: str, titulo: str = "", detalhe: str = "") -> str:
    """Build the text embedded for one *Linha*: Descrição + Título + Detalhe."""
    parts = [
        (descricao or "").strip(),
        (titulo or "").strip(),
        strip_reporting_prefix(detalhe or ""),
    ]
    return _WHITESPACE_RE.sub(" ", " ".join(part for part in parts if part)).strip()


def build_linha(row: Mapping[str, str], linha_id: int) -> Linha:
    """Turn one CSV row into the table contract for a single *Linha*."""
    codigo = (row.get("codigo") or "").strip()
    descricao = (row.get("descricao") or "").strip()
    titulo = (row.get("titulo") or "").strip()
    detalhe = (row.get("detalhe") or "").strip()
    return Linha(
        id=linha_id,
        codigo=codigo,
        codigo_digits=normalize_codigo(codigo),
        descricao=descricao,
        titulo=titulo,
        detalhe=detalhe,
        embed_text=build_embed_text(descricao, titulo, detalhe),
    )


def read_reference_rows(csv_path: str | Path = DEFAULT_CSV_PATH) -> list[dict[str, str]]:
    """Read every reference *Linha* in CSV order."""
    path = Path(csv_path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = set(CSV_FIELDS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(sorted(missing))}")
        return [
            {field: (row.get(field) or "") for field in CSV_FIELDS}
            for row in reader
        ]


def build_dataset(csv_path: str | Path = DEFAULT_CSV_PATH) -> list[Linha]:
    """Build the deterministic table payload for every *Linha*."""
    rows = read_reference_rows(csv_path)
    return [build_linha(row, index) for index, row in enumerate(rows, start=1)]


def create_schema_sql(dim: int = DEFAULT_EMBED_DIM) -> str:
    """Return the DDL that recreates the disposable table and its metadata."""
    if not isinstance(dim, int) or isinstance(dim, bool) or dim < 1:
        raise ValueError(f"embedding dimension must be a positive integer, got {dim!r}")

    return f"""
CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS {TABLE_NAME};
DROP TABLE IF EXISTS {META_TABLE_NAME};

CREATE TABLE {TABLE_NAME} (
    id integer PRIMARY KEY,
    codigo text NOT NULL,
    codigo_digits text NOT NULL,
    descricao text NOT NULL,
    titulo text NOT NULL DEFAULT '',
    detalhe text NOT NULL DEFAULT '',
    embed_text text NOT NULL,
    embedding vector({dim}) NOT NULL
);

CREATE INDEX {TABLE_NAME}_codigo_digits_idx
    ON {TABLE_NAME} (codigo_digits text_pattern_ops);

CREATE INDEX {TABLE_NAME}_embedding_idx
    ON {TABLE_NAME} USING hnsw (embedding vector_cosine_ops);

CREATE TABLE {META_TABLE_NAME} (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    model text NOT NULL,
    dim integer NOT NULL,
    row_count integer NOT NULL
);
""".strip()


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Connection settings for the disposable pgvector container."""

    host: str = "localhost"
    port: int = 5434
    dbname: str = "natureza_vectors"
    user: str = "natureza"
    password: str = "natureza"
    connect_timeout: int = 5

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None
    ) -> "DatabaseSettings":
        source = os.environ if env is None else env
        return cls(
            host=source.get("PGVECTOR_HOST", "localhost"),
            port=int(source.get("PGVECTOR_PORT", "5434")),
            dbname=source.get("PGVECTOR_DB", "natureza_vectors"),
            user=source.get("PGVECTOR_USER", "natureza"),
            password=source.get("PGVECTOR_PASSWORD", "natureza"),
            connect_timeout=int(source.get("PGVECTOR_CONNECT_TIMEOUT", "5")),
        )

    def describe(self) -> str:
        return f"{self.host}:{self.port}/{self.dbname}"


def connect_db(settings: DatabaseSettings | None = None) -> Any:
    """Open a connection to the disposable store, failing with clear guidance."""
    try:
        import psycopg2
    except ImportError as exc:  # pragma: no cover - environment guard
        raise StoreUnavailableError(
            "psycopg2 is required to ingest the mock vector store"
        ) from exc

    settings = settings or DatabaseSettings.from_env()
    try:
        return psycopg2.connect(
            host=settings.host,
            port=settings.port,
            dbname=settings.dbname,
            user=settings.user,
            password=settings.password,
            connect_timeout=settings.connect_timeout,
        )
    except psycopg2.OperationalError as exc:
        raise StoreUnavailableError(
            "Mock pgvector store is not reachable at "
            f"{settings.describe()}. Start it with `docker compose up -d pgvector` "
            "and check PGVECTOR_* settings. "
            f"Original error: {exc}"
        ) from exc


def _batched(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    if size < 1:
        raise ValueError("batch size must be at least 1")
    for start in range(0, len(items), size):
        yield items[start : start + size]


def embed_texts(
    texts: Sequence[str],
    *,
    model: str = DEFAULT_EMBED_MODEL,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    batch_size: int = DEFAULT_EMBED_BATCH_SIZE,
    expected_dim: int | None = DEFAULT_EMBED_DIM,
    timeout: int = DEFAULT_EMBED_TIMEOUT_SECONDS,
    http_post: Any = None,
) -> list[list[float]]:
    """Embed texts through Ollama's batch endpoint.

    The model's actual dimensionality is checked against ``expected_dim`` so a
    model swap fails loudly instead of writing vectors the schema cannot hold.
    """
    post = http_post or requests.post
    endpoint = f"{base_url.rstrip('/')}/api/embed"
    vectors: list[list[float]] = []

    for batch in _batched(list(texts), batch_size):
        response = post(
            endpoint,
            json={
                "model": model,
                "input": list(batch),
                # Match the workflow's query embedding, which is pinned to CPU.
                # Building the index on a different device can shift the
                # vectors enough to change cosine clustering near a boundary.
                "options": {"num_gpu": 0},
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        batch_vectors = payload.get("embeddings")
        if not isinstance(batch_vectors, list) or len(batch_vectors) != len(batch):
            raise EmbeddingError(
                f"Ollama returned {len(batch_vectors or [])} embeddings for "
                f"{len(batch)} inputs (model {model})"
            )

        for vector in batch_vectors:
            if not isinstance(vector, list) or not vector:
                raise EmbeddingError(f"Ollama returned an invalid embedding: {vector!r}")
            if expected_dim is not None and len(vector) != expected_dim:
                raise EmbeddingError(
                    f"Embedding model {model} returned {len(vector)} dimensions, "
                    f"but the schema expects {expected_dim}. Set EMBED_DIM to the "
                    "model's dimensionality (and re-ingest) before using this store."
                )
            vectors.append([float(value) for value in vector])

    return vectors


def _vector_literal(vector: Sequence[float]) -> str:
    return json.dumps([float(value) for value in vector], separators=(",", ":"))


def rebuild_store(
    connection: Any,
    linhas: Sequence[Linha],
    embeddings: Sequence[Sequence[float]],
    *,
    model: str,
    dim: int,
) -> None:
    """Recreate the table and load all *Linhas* in one transaction."""
    from psycopg2.extras import execute_values

    if len(linhas) != len(embeddings):
        raise ValueError(
            f"got {len(linhas)} linhas but {len(embeddings)} embeddings"
        )

    values = []
    for linha, vector in zip(linhas, embeddings):
        if len(vector) != dim:
            raise EmbeddingError(
                f"linha {linha.id} has a {len(vector)}-dimension vector, expected {dim}"
            )
        values.append(
            (
                linha.id,
                linha.codigo,
                linha.codigo_digits,
                linha.descricao,
                linha.titulo,
                linha.detalhe,
                linha.embed_text,
                _vector_literal(vector),
            )
        )

    with connection:
        with connection.cursor() as cursor:
            cursor.execute(create_schema_sql(dim))
            execute_values(
                cursor,
                f"""
                INSERT INTO {TABLE_NAME}
                    (id, codigo, codigo_digits, descricao, titulo, detalhe,
                     embed_text, embedding)
                VALUES %s
                """,
                values,
                page_size=INSERT_PAGE_SIZE,
            )
            cursor.execute(
                f"INSERT INTO {META_TABLE_NAME} (model, dim, row_count) VALUES (%s, %s, %s)",
                (model, dim, len(linhas)),
            )
            cursor.execute(f"ANALYZE {TABLE_NAME}")


def ingest(
    csv_path: str | Path = DEFAULT_CSV_PATH,
    *,
    model: str = DEFAULT_EMBED_MODEL,
    dim: int = DEFAULT_EMBED_DIM,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    batch_size: int = DEFAULT_EMBED_BATCH_SIZE,
) -> dict[str, Any]:
    """Full rebuild: read CSV, embed every *Linha*, recreate the table."""
    linhas = build_dataset(csv_path)
    embeddings = embed_texts(
        [linha.embed_text for linha in linhas],
        model=model,
        base_url=base_url,
        batch_size=batch_size,
        expected_dim=dim,
    )
    settings = DatabaseSettings.from_env()
    connection = connect_db(settings)
    try:
        rebuild_store(
            connection,
            linhas,
            embeddings,
            model=model,
            dim=dim,
        )
    finally:
        connection.close()

    return {
        "rows": len(linhas),
        "model": model,
        "dim": dim,
        "database": settings.describe(),
        "table": TABLE_NAME,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild the disposable pgvector expense-nature store."
    )
    parser.add_argument("--csv", default=str(DEFAULT_CSV_PATH), help="reference CSV")
    parser.add_argument(
        "--model",
        default=os.environ.get("EMBED_MODEL", DEFAULT_EMBED_MODEL),
        help="Ollama embedding model",
    )
    parser.add_argument(
        "--dim",
        type=int,
        default=int(os.environ.get("EMBED_DIM", DEFAULT_EMBED_DIM)),
        help="expected embedding dimensionality",
    )
    parser.add_argument(
        "--ollama-url",
        default=os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL),
        help="Ollama base URL",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(
            os.environ.get("EMBED_BATCH_SIZE", DEFAULT_EMBED_BATCH_SIZE)
        ),
        help="texts embedded per Ollama request",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build and validate the dataset without embedding or writing",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.dry_run:
        linhas = build_dataset(args.csv)
        print(f"Would load {len(linhas)} linhas into {TABLE_NAME} ({args.dim}-dim)")
        print(f"First embed_text: {linhas[0].embed_text[:160]}")
        return 0

    try:
        summary = ingest(
            args.csv,
            model=args.model,
            dim=args.dim,
            base_url=args.ollama_url,
            batch_size=args.batch_size,
        )
    except (EmbeddingError, StoreUnavailableError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Loaded {summary['rows']} linhas into {summary['table']} at "
        f"{summary['database']} using {summary['model']} ({summary['dim']}-dim)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
