# Ingestion image: rebuilds the disposable pgvector store from
# sql/data/naturezadespesa.csv. The CSV is bind-mounted
# read-only at runtime; it is NOT baked into the image.
#
# Pinned base image; the job only needs Python and two packages.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY ingest/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY ingest/ingest_naturezas.py /app/ingest_naturezas.py

ENTRYPOINT ["python", "/app/ingest_naturezas.py", "--csv", "/app/data/naturezadespesa.csv"]
