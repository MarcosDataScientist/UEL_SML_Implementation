# Chat Semantic Search

An n8n chat workflow that finds the right Brazilian expense nature
("natureza de despesa") from a free-text description or an expense code. It
reuses the n8n and Ollama containers from this test environment and adds an
isolated pgvector container for the 1,560-row embedding index.

This is a separate workflow from
`n8n_workflows/proposed/local_ai_expense_nature_memory_kmedoids.json`. That one
searches with `pg_trgm` and K-Medoids. This one embeds the reference rows with
`qwen3-embedding:0.6b` and ranks them by cosine similarity. Neither workflow
imports, edits, or replaces the other.

## What gets added

```text
test_environment/
├── docker-compose.yml                  # + pgvector, + semantic-ingest
├── .env.example                        # + PGVECTOR_* and EMBED_* settings
├── Makefile                            # + semantic-* targets
├── sql/data/naturezadespesa.csv        # existing 1,560-row reference CSV
├── scripts/
│   └── semantic_search.sh              # setup, import, ingest, smoke, status
└── semantic_search/
    ├── chat_semantic_search.json       # n8n workflow export
    ├── credentials/pgvector.json       # fixed-id Postgres credential
    └── ingest/                         # containerized index builder
```

The sidecar uses its own database (`natureza_vectors`) and volume. The budget
database (`orcamento_db`) is never read or written by this workflow.

## Requirements

- The stack from the parent directory must already run: `make up`.
- Docker Engine or Docker Desktop with Compose v2.
- 8 GB of RAM recommended. `qwen3:4b` plus the embedding model use about
  3.5 GB; the rest of the stack uses about 1.5 GB.
- About 4 GB of free disk for the two models, plus the images and volumes.
- Internet access on the first run. Later runs work offline.

## Start it

From `test_environment/`:

```bash
make up
make semantic-setup
```

`make up` starts the existing services and the new pgvector sidecar. It does
not pull the semantic models or build the index.

`make semantic-setup` is idempotent and does the rest:

1. Waits for pgvector and n8n to become healthy.
2. Imports the pgvector credential with the fixed id `pgvectorNatureza1`.
3. Imports and publishes the `Chat Semantic Search` workflow
   (`semanticSearchFlow01`) if it is missing or inactive, then restarts n8n to
   register the webhook.
4. Pulls `qwen3:4b` and `qwen3-embedding:0.6b` unless both are present.
5. Builds the 1,560-row vector index from `sql/data/naturezadespesa.csv`.
6. Sends the code `3.3.90.30.01` through the webhook and checks the reply.

The first run takes 5 to 20 minutes depending on the network and CPU. Later
runs skip the model pull; the index rebuild usually finishes in under a minute
with a warm embedding model, but it can take longer on a busy CPU.

If n8n has no owner account yet, the credential import stops and prints the URL.
Open <http://localhost:5678/>, create the account, and run
`make semantic-setup` again. The webhook works before the account exists; the
account is only needed for the editor.

Check the result:

```bash
make semantic-status
make semantic-smoke
```

`make semantic-status` checks the containers, both models, the index row count,
and whether the workflow is imported and active. `make semantic-smoke` posts a
known code to the published webhook.

## Try the chat

The published webhook is at:

```text
http://localhost:5678/webhook/semanticsearchflow01/chat
```

```bash
curl -s -X POST http://localhost:5678/webhook/semanticsearchflow01/chat \
  -H 'Content-Type: application/json' \
  -d '{"action":"sendMessage","sessionId":"demo","chatInput":"gasolina"}'
```

A code lookup skips the chat model and returns quickly:

```bash
curl -s -X POST http://localhost:5678/webhook/semanticsearchflow01/chat \
  -H 'Content-Type: application/json' \
  -d '{"action":"sendMessage","sessionId":"demo","chatInput":"3.3.90.30.01"}'
```

Use the published webhook for multi-turn tests. The editor's chat panel and
"Execute workflow" run test executions, and n8n does not persist workflow static
data in test mode. A follow-up sent from the editor is treated as a new search
term.

## What the workflow does

Each message takes one of three paths.

- A code-shaped message becomes a code lookup. The message must be made only of
  digits, spaces, dots, dashes, or slashes, optionally prefixed with "código",
  and hold at least three digits. The lookup prefix-matches `codigo_digits` and
  orders by `id`, without calling the chat model or the embedding model.
- Greetings and help questions return fixed orientation text. `qwen3:4b`
  classifies the message as `saudacao` or `ajuda`; neither path calls the
  embedding endpoint or the database.
- Any message classified as `busca` becomes a semantic search. `qwen3:4b`
  returns the search term, which is embedded with `qwen3-embedding:0.6b` and
  compared with the stored vectors using cosine similarity. Rows at or above
  `similarity_floor` (0.55) are kept, up to `top_k` (20). Both values live in
  the `Search Config (floor, Top-K)` node.

The reply depends on how many candidates the lookup returns.

- 0 candidates: a fixed "não encontrei" message.
- 1 to 7 candidates: one PASSO 3 block per row, with code, description, title,
  and detail.
- 8 or more candidates: the workflow groups them into up to five subjects, asks
  `qwen3:4b` for a short label per subject, and offers lettered choices (A, B,
  C, and so on). If the candidates do not form a clear grouping, it renders
  them as PASSO 3 blocks instead of an offer.

A selection can be a letter, an ordinal ("primeiro", "segunda"), "opção x", or
the subject label. Selecting a subject expands it and re-queries the table, so an
edited row shows its current text. The offer ends when every subject has been
expanded, or after ten minutes without activity; each selection refreshes the
clock. A new search term discards the offer. The stored entry holds only labels,
row ids, the search term, and timestamps.

When a search returns exactly `top_k` rows, the reply says the results were
limited and suggests refining the term.

## Ports and settings

The new container binds only one host port. It does not reuse the ports from the
standalone bundle.

| Setting | Default | What it controls |
| --- | --- | --- |
| `PGVECTOR_PORT` | `5434` | pgvector on the host, for psql and debugging. n8n reaches `pgvector:5432`. |
| `PGVECTOR_DB` | `natureza_vectors` | Database name. |
| `PGVECTOR_USER` / `PGVECTOR_PASSWORD` | `natureza` / `natureza` | Database credentials. |
| `EMBED_MODEL` / `EMBED_DIM` | `qwen3-embedding:0.6b` / `1024` | Embedding model and expected dimension for ingestion. |
| `EMBED_BATCH_SIZE` | `32` | Texts per embedding request. |

n8n stays on `localhost:5678`, Ollama on `localhost:11434`, and the budget
Postgres on `localhost:5432`. If `5434` is taken, change `PGVECTOR_PORT` in
`.env`, then run `make down && make up`.

To change the database credentials, edit `.env`, update
`semantic_search/credentials/pgvector.json` so its `data` block matches, then
run `make semantic-setup`. The workflow nodes are bound to the credential id, so
a mismatch fails at query time.

The parent Compose file now sets `OLLAMA_MAX_LOADED_MODELS=2`. With the previous
value of `1`, each embedding call evicted `qwen3:4b`, which made every chat turn
reload the 4B model. Both models fit in the existing 4 GB Ollama limit.

## Commands

Run these from `test_environment/`.

| Command | Action |
| --- | --- |
| `make up` | Start the full stack, including pgvector. |
| `make semantic-setup` | First-run setup: models, credential, workflow, index, smoke. |
| `make semantic-status` | Health, models, index size, and workflow state. |
| `make semantic-models` | Pull `qwen3:4b` and `qwen3-embedding:0.6b`. |
| `make semantic-import` | Force re-import and publish the workflow and credential. |
| `make semantic-ingest` | Rebuild the 1,560-row pgvector index. |
| `make semantic-smoke` | POST a known code through the webhook. |

`make semantic-setup` accepts no flags. For control over one step, run the
individual targets in the order above.

## Rebuilding the index

Run this after changing the CSV or the embedding model:

```bash
make semantic-ingest
```

The containerized job embeds all 1,560 linhas through Ollama and recreates the
table in one transaction. It usually takes under a minute with a warm embedding
model; a cold or loaded CPU can take several minutes.
The job uses `sql/data/naturezadespesa.csv`, the same file as the lexical
workflow, so the two search paths stay on the same reference data.

If you change the embedding model, also update `EMBED_MODEL`, `EMBED_DIM`, the
model name in the `Embed Termo` node, and recalibrate `similarity_floor` in
`Search Config (floor, Top-K)`.

## Troubleshooting

### The webhook returns 404

The workflow is not active, or n8n has not registered the webhook. Run:

```bash
make semantic-import
make semantic-smoke
```

### `relation "natureza_linhas" does not exist`

The vector store is empty. Run `make semantic-ingest`. If the pgvector
container is not running, run `make up` first.

### The Postgres node cannot connect

From n8n the host is `pgvector:5432`, not `localhost:5434`. Check that the
`pgvector` container is healthy and that the credential still has the fixed id
`pgvectorNatureza1`.

### The extraction or naming call times out

Ollama may still be loading `qwen3:4b`, or the model is missing. Run
`make semantic-status`; if a model is missing, run `make semantic-models`.

### A semantic query is slow

On CPU, `qwen3:4b` is the bottleneck. The first turn loads the model; later turns
reuse it for 30 minutes. Keep the `ollama` container running between turns. A
code query such as `3.3.90.30.01` skips the chat model and returns quickly.

### Port 5434 is already in use

Change `PGVECTOR_PORT` in `.env`, then run `make down && make up`. The workflow
still reaches the container at `pgvector:5432`.

### `make up` reports that a container name is already in use

An older checkout may have left fixed-name containers from another Compose
project. Remove the containers only, not the volumes:

```bash
docker rm -f homelab-slm-n8n homelab-slm-postgres homelab-slm-ollama homelab-slm-pgvector
make up
```

### The credential import fails before the owner account exists

Open <http://localhost:5678/>, create the n8n owner account, then run
`make semantic-setup` again. The CLI cannot create the owner account.

## Notes

- The workflow JSON is the source of truth. After editing
  `semantic_search/chat_semantic_search.json`, run `make semantic-import`.
- `make semantic-setup` leaves an already active workflow untouched, so an edit
  made in the n8n editor is not overwritten by a routine setup run.
- The `semantic-ingest` service is behind the `setup` profile, so `make up` does
  not build the index or pull models. That keeps the existing quickstart fast.
- The three Ollama calls use the Compose service at `ollama:11434`. The two
  Postgres nodes use the `pgvectorNatureza1` credential at `pgvector:5432`.
- The workflow was built against n8n 2.39.5 and Ollama 0.34.1, and exercised
  against this stack's `latest` n8n and Ollama images. The HTTP API calls and
  workflow nodes used here are stable across those versions.
