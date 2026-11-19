# Ingestion image: rebuilds the disposable pgvector store from
# sql/data/funcoes.csv and sql/data/subfuncoes.csv. The CSVs are bind-mounted
# read-only at runtime; they are NOT baked into the image.
#
# Pinned base image; the job only needs Python and two packages.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY ingest/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY ingest/ingest_funcoes.py /app/ingest_funcoes.py
COPY ingest/vector_store.py /app/vector_store.py

# The CSVs live under /app/data in the container, not next to the script.
# Passing both paths here keeps `--dry-run` composable onto the entrypoint.
ENTRYPOINT ["python", "/app/ingest_funcoes.py", "--funcoes", "/app/data/funcoes.csv", "--subfuncoes", "/app/data/subfuncoes.csv"]
