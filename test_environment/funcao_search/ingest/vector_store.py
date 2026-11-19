"""Plumbing for the Função/Subfunção disposable pgvector store.

The ingest reads the two reference CSVs, embeds their labels through Ollama,
and rebuilds the flat tables inside the pgvector container.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import requests

DEFAULT_EMBED_MODEL = "qwen3-embedding:0.6b"
DEFAULT_EMBED_DIM = 1024
DEFAULT_EMBED_BATCH_SIZE = 32
DEFAULT_EMBED_TIMEOUT_SECONDS = 180
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"

class EmbeddingError(RuntimeError):
    """Raised when Ollama cannot produce embeddings matching the schema."""


class StoreUnavailableError(RuntimeError):
    """Raised when the disposable vector store cannot be reached."""


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


def vector_literal(vector: Sequence[float]) -> str:
    return json.dumps([float(value) for value in vector], separators=(",", ":"))
