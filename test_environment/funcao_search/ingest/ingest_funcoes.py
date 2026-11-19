#!/usr/bin/env python3
"""Build the disposable pgvector store used by Função/Subfunção chat search.

The script reads the two CSV exports of the production reference tables, embeds
each label with a local Ollama model, and recreates two flat Postgres tables in
a dedicated database. It never connects to the production database.

The Compose job runs this script with the CSVs bind-mounted at
/app/data/funcoes.csv and /app/data/subfuncoes.csv. For a manual run from
`test_environment/`:

    python funcao_search/ingest/ingest_funcoes.py
    python funcao_search/ingest/ingest_funcoes.py --dry-run
    python funcao_search/ingest/ingest_funcoes.py --model qwen3-embedding:0.6b --dim 1024

Environment overrides:

    PGVECTOR_HOST / PGVECTOR_PORT / PGVECTOR_USER / PGVECTOR_PASSWORD
    FUNCAO_PGVECTOR_DB
    OLLAMA_BASE_URL / EMBED_MODEL / EMBED_DIM / EMBED_BATCH_SIZE
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from vector_store import (
    DEFAULT_EMBED_BATCH_SIZE,
    DEFAULT_EMBED_DIM,
    DEFAULT_EMBED_MODEL,
    DEFAULT_OLLAMA_BASE_URL,
    DatabaseSettings,
    EmbeddingError,
    StoreUnavailableError,
    connect_db,
    embed_texts,
    vector_literal,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FUNCOES_CSV = REPO_ROOT.parent / "sql" / "data" / "funcoes.csv"
SUBFUNCOES_CSV = REPO_ROOT.parent / "sql" / "data" / "subfuncoes.csv"

DEFAULT_DATABASE = "funcao_vectors"
FUNCAO_TABLE = "funcao"
SUBFUNCAO_TABLE = "subfuncao"
META_TABLE = "funcao_embedding_meta"
INSERT_PAGE_SIZE = 500

FUNCAO_FIELDS = ("idfuncao", "codigofuncao", "descricaofuncao")
SUBFUNCAO_FIELDS = (
    "idsubfuncao",
    "codigosubfuncao",
    "descricaosubfuncao",
    "funcao_idfuncao",
    "ativo",
    "excluido",
)

_WHITESPACE_RE = re.compile(r"\s+")
_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


class DatasetError(ValueError):
    """Raised when the exported CSVs cannot form a consistent dataset."""


@dataclass(frozen=True, slots=True)
class Funcao:
    """One *Função* row, ready to embed and store."""

    id: int
    codigo: str
    codigo_digits: str
    descricao: str
    embed_text: str


@dataclass(frozen=True, slots=True)
class Subfuncao:
    """One *Subfunção* row, ready to embed and store."""

    id: int
    codigo: str
    codigo_digits: str
    descricao: str
    funcao_id: int
    ativo: int
    excluido: int
    embed_text: str


def normalize_codigo(codigo: str) -> str:
    """Return the código as digits only, punctuation-insensitive."""
    return re.sub(r"\D", "", codigo or "")


def build_embed_text(descricao: str) -> str:
    """Build the text embedded for one row: the label, whitespace collapsed."""
    return _WHITESPACE_RE.sub(" ", (descricao or "")).strip()


def read_rows(path: str | Path, fields: Sequence[str]) -> list[dict[str, str]]:
    """Read one exported CSV, enforcing the expected columns."""
    source = Path(path)
    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = set(fields) - set(reader.fieldnames or ())
        if missing:
            raise DatasetError(f"{source} is missing columns: {', '.join(sorted(missing))}")
        return [{field: (row.get(field) or "") for field in fields} for row in reader]


def _to_int(value: str, field: str, source: Path) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise DatasetError(f"{source}: {field} is not an integer: {value!r}") from exc


def build_funcoes(rows: Sequence[Mapping[str, str]], source: Path) -> list[Funcao]:
    """Turn the função CSV rows into the table contract."""
    funcoes = []
    for row in rows:
        descricao = (row.get("descricaofuncao") or "").strip()
        codigo = (row.get("codigofuncao") or "").strip()
        if not descricao:
            raise DatasetError(f"{source}: função {row.get('idfuncao')} has an empty label")
        funcoes.append(
            Funcao(
                id=_to_int(row.get("idfuncao", ""), "idfuncao", source),
                codigo=codigo,
                codigo_digits=normalize_codigo(codigo),
                descricao=descricao,
                embed_text=build_embed_text(descricao),
            )
        )
    return funcoes


def build_subfuncoes(
    rows: Sequence[Mapping[str, str]],
    funcao_ids: set[int],
    source: Path,
) -> list[Subfuncao]:
    """Turn the subfunção CSV rows into the table contract, checking the FK."""
    subfuncoes = []
    orfas: list[int] = []
    for row in rows:
        descricao = (row.get("descricaosubfuncao") or "").strip()
        codigo = (row.get("codigosubfuncao") or "").strip()
        funcao_id = _to_int(row.get("funcao_idfuncao", ""), "funcao_idfuncao", source)
        if not descricao:
            raise DatasetError(f"{source}: subfunção {row.get('idsubfuncao')} has an empty label")
        if funcao_id not in funcao_ids:
            orfas.append(_to_int(row.get("idsubfuncao", ""), "idsubfuncao", source))
            continue
        subfuncoes.append(
            Subfuncao(
                id=_to_int(row.get("idsubfuncao", ""), "idsubfuncao", source),
                codigo=codigo,
                codigo_digits=normalize_codigo(codigo),
                descricao=descricao,
                funcao_id=funcao_id,
                ativo=_to_int(row.get("ativo", "1"), "ativo", source),
                excluido=_to_int(row.get("excluido", "0"), "excluido", source),
                embed_text=build_embed_text(descricao),
            )
        )
    if orfas:
        raise DatasetError(
            f"{source}: {len(orfas)} subfunção(ões) point at an unknown função: {sorted(orfas)}"
        )
    return subfuncoes


def build_dataset(
    funcoes_csv: str | Path = FUNCOES_CSV,
    subfuncoes_csv: str | Path = SUBFUNCOES_CSV,
) -> tuple[list[Funcao], list[Subfuncao]]:
    """Read both CSVs and validate the join between them."""
    funcoes_path = Path(funcoes_csv)
    subfuncoes_path = Path(subfuncoes_csv)
    funcoes = build_funcoes(read_rows(funcoes_path, FUNCAO_FIELDS), funcoes_path)
    funcao_ids = {funcao.id for funcao in funcoes}
    subfuncoes = build_subfuncoes(
        read_rows(subfuncoes_path, SUBFUNCAO_FIELDS), funcao_ids, subfuncoes_path
    )
    return funcoes, subfuncoes


def create_schema_sql(dim: int = DEFAULT_EMBED_DIM) -> str:
    """Return the DDL that recreates both tables and the metadata row."""
    if not isinstance(dim, int) or isinstance(dim, bool) or dim < 1:
        raise ValueError(f"embedding dimension must be a positive integer, got {dim!r}")

    return f"""
CREATE EXTENSION IF NOT EXISTS vector;
-- The lexical twin (funcao_search_lexical.json) ranks with unaccent() and
-- similarity(); a store built here must answer it without a manual psql step.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

DROP TABLE IF EXISTS {SUBFUNCAO_TABLE};
DROP TABLE IF EXISTS {FUNCAO_TABLE};
DROP TABLE IF EXISTS {META_TABLE};

CREATE TABLE {FUNCAO_TABLE} (
    idfuncao integer PRIMARY KEY,
    codigofuncao text NOT NULL,
    codigo_digits text NOT NULL,
    descricaofuncao text NOT NULL,
    embedding vector({dim}) NOT NULL
);

CREATE TABLE {SUBFUNCAO_TABLE} (
    idsubfuncao integer PRIMARY KEY,
    codigosubfuncao text NOT NULL,
    codigo_digits text NOT NULL,
    descricaosubfuncao text NOT NULL,
    funcao_idfuncao integer NOT NULL
        REFERENCES {FUNCAO_TABLE}(idfuncao),
    ativo integer NOT NULL DEFAULT 1,
    excluido integer NOT NULL DEFAULT 0,
    embedding vector({dim}) NOT NULL
);

CREATE INDEX {SUBFUNCAO_TABLE}_funcao_id_idx
    ON {SUBFUNCAO_TABLE} (funcao_idfuncao);

CREATE TABLE {META_TABLE} (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    model text NOT NULL,
    dim integer NOT NULL,
    funcao_count integer NOT NULL,
    subfuncao_count integer NOT NULL
);
""".strip()


def database_settings(env: Mapping[str, str] | None = None) -> DatabaseSettings:
    """Connection settings for the Função store, defaulting to another database."""
    source = os.environ if env is None else env
    settings = DatabaseSettings.from_env(source)
    dbname = source.get("FUNCAO_PGVECTOR_DB", DEFAULT_DATABASE)
    if not _IDENTIFIER_RE.match(dbname):
        raise DatasetError(f"invalid database name: {dbname!r}")
    return replace(settings, dbname=dbname)


def ensure_database(settings: DatabaseSettings) -> bool:
    """Create the database when missing. Returns True when it created one."""
    admin = replace(settings, dbname="postgres")
    connection = connect_db(admin)
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.dbname,))
            if cursor.fetchone() is not None:
                return False
            cursor.execute(f'CREATE DATABASE "{settings.dbname}"')
            return True
    finally:
        connection.close()


def rebuild_store(
    connection: Any,
    funcoes: Sequence[Funcao],
    subfuncoes: Sequence[Subfuncao],
    funcao_embeddings: Sequence[Sequence[float]],
    subfuncao_embeddings: Sequence[Sequence[float]],
    *,
    model: str,
    dim: int,
) -> None:
    """Recreate both tables and load every row in one transaction."""
    from psycopg2.extras import execute_values

    if len(funcoes) != len(funcao_embeddings):
        raise ValueError(f"got {len(funcoes)} funções but {len(funcao_embeddings)} embeddings")
    if len(subfuncoes) != len(subfuncao_embeddings):
        raise ValueError(
            f"got {len(subfuncoes)} subfunções but {len(subfuncao_embeddings)} embeddings"
        )

    funcao_values = []
    for funcao, vector in zip(funcoes, funcao_embeddings):
        if len(vector) != dim:
            raise EmbeddingError(
                f"função {funcao.id} has a {len(vector)}-dimension vector, expected {dim}"
            )
        funcao_values.append(
            (
                funcao.id,
                funcao.codigo,
                funcao.codigo_digits,
                funcao.descricao,
                vector_literal(vector),
            )
        )

    subfuncao_values = []
    for subfuncao, vector in zip(subfuncoes, subfuncao_embeddings):
        if len(vector) != dim:
            raise EmbeddingError(
                f"subfunção {subfuncao.id} has a {len(vector)}-dimension vector, expected {dim}"
            )
        subfuncao_values.append(
            (
                subfuncao.id,
                subfuncao.codigo,
                subfuncao.codigo_digits,
                subfuncao.descricao,
                subfuncao.funcao_id,
                subfuncao.ativo,
                subfuncao.excluido,
                vector_literal(vector),
            )
        )

    with connection:
        with connection.cursor() as cursor:
            cursor.execute(create_schema_sql(dim))
            execute_values(
                cursor,
                f"""
                INSERT INTO {FUNCAO_TABLE}
                    (idfuncao, codigofuncao, codigo_digits, descricaofuncao, embedding)
                VALUES %s
                """,
                funcao_values,
                page_size=INSERT_PAGE_SIZE,
            )
            execute_values(
                cursor,
                f"""
                INSERT INTO {SUBFUNCAO_TABLE}
                    (idsubfuncao, codigosubfuncao, codigo_digits, descricaosubfuncao,
                     funcao_idfuncao, ativo, excluido, embedding)
                VALUES %s
                """,
                subfuncao_values,
                page_size=INSERT_PAGE_SIZE,
            )
            cursor.execute(
                f"""
                INSERT INTO {META_TABLE}
                    (model, dim, funcao_count, subfuncao_count)
                VALUES (%s, %s, %s, %s)
                """,
                (model, dim, len(funcoes), len(subfuncoes)),
            )
            cursor.execute(f"ANALYZE {FUNCAO_TABLE}")
            cursor.execute(f"ANALYZE {SUBFUNCAO_TABLE}")


def ingest(
    funcoes_csv: str | Path = FUNCOES_CSV,
    subfuncoes_csv: str | Path = SUBFUNCOES_CSV,
    *,
    model: str = DEFAULT_EMBED_MODEL,
    dim: int = DEFAULT_EMBED_DIM,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    batch_size: int = DEFAULT_EMBED_BATCH_SIZE,
) -> dict[str, Any]:
    """Full rebuild: read both CSVs, embed every row, recreate the tables."""
    funcoes, subfuncoes = build_dataset(funcoes_csv, subfuncoes_csv)
    funcao_embeddings = embed_texts(
        [funcao.embed_text for funcao in funcoes],
        model=model,
        base_url=base_url,
        batch_size=batch_size,
        expected_dim=dim,
    )
    subfuncao_embeddings = embed_texts(
        [subfuncao.embed_text for subfuncao in subfuncoes],
        model=model,
        base_url=base_url,
        batch_size=batch_size,
        expected_dim=dim,
    )

    settings = database_settings()
    created = ensure_database(settings)
    connection = connect_db(settings)
    try:
        rebuild_store(
            connection,
            funcoes,
            subfuncoes,
            funcao_embeddings,
            subfuncao_embeddings,
            model=model,
            dim=dim,
        )
    finally:
        connection.close()

    return {
        "funcoes": len(funcoes),
        "subfuncoes": len(subfuncoes),
        "model": model,
        "dim": dim,
        "database": settings.describe(),
        "created_database": created,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild the disposable pgvector Função/Subfunção store."
    )
    parser.add_argument("--funcoes", default=str(FUNCOES_CSV), help="função CSV")
    parser.add_argument("--subfuncoes", default=str(SUBFUNCOES_CSV), help="subfunção CSV")
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
        default=int(os.environ.get("EMBED_BATCH_SIZE", DEFAULT_EMBED_BATCH_SIZE)),
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
        funcoes, subfuncoes = build_dataset(args.funcoes, args.subfuncoes)
        print(
            f"Would load {len(funcoes)} funções and {len(subfuncoes)} subfunções "
            f"into {database_settings().dbname} ({args.dim}-dim)"
        )
        print(f"First subfunção embed_text: {subfuncoes[0].embed_text[:160]}")
        return 0

    try:
        summary = ingest(
            args.funcoes,
            args.subfuncoes,
            model=args.model,
            dim=args.dim,
            base_url=args.ollama_url,
            batch_size=args.batch_size,
        )
    except (EmbeddingError, StoreUnavailableError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    created = " (created)" if summary["created_database"] else ""
    print(
        f"Loaded {summary['funcoes']} funções and {summary['subfuncoes']} subfunções "
        f"into {summary['database']}{created} using {summary['model']} "
        f"({summary['dim']}-dim)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
