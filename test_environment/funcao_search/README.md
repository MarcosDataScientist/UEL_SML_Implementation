# Chat Função e Subfunção

An n8n chat workflow that finds the right Brazilian budget função
("função orçamentária") and its subfunções from a free-text description or a
code. It reuses the n8n, Ollama, and pgvector containers from this test
environment and adds a second database to the existing vector store: 29
funções and 83 subfunções.

The package ships two answer paths over the same store: a semantic arm
(`funcao_search.json`, the default) and a lexical arm
(`funcao_search_lexical.json`, the tested fallback). Both share the trigger, the
code lookup, the extraction prompt and the reply format; only the text search
differs. See [Two retrieval arms](#two-retrieval-arms).

This is a separate workflow from
[`../semantic_search/`](../semantic_search/README.md). That one indexes the
1,560 expense natures in `natureza_vectors`; this one indexes the functional
classification in `funcao_vectors`. Both databases live in the same pgvector
container and neither workflow reads the budget tables in `orcamento_db`.

## What gets added

```text
test_environment/
├── docker-compose.yml                    # + funcao-ingest, + n8n mount
├── .env.example                          # + FUNCAO_PGVECTOR_DB
├── Makefile                              # + funcao-* targets
├── sql/data/funcoes.csv                  # 29-row reference table
├── sql/data/subfuncoes.csv               # 83-row reference table
├── scripts/
│   └── funcao_search.sh                  # setup, import, ingest, smoke, status
└── funcao_search/
    ├── .dockerignore                     # ingestion build context filter
    ├── funcao_search.json                # semantic arm, n8n workflow export
    ├── funcao_search_lexical.json        # lexical arm, n8n workflow export
    ├── credentials/pgvector-funcao.json  # fixed-id Postgres credential
    └── ingest/                           # containerized index builder
```

The two CSVs are the production export. The ingest builds `funcao_vectors`
from them and does not read `sql/init.sql`, whose short `funcao` and `subfuncao`
seed rows are demo data for the budget database and use different ids.

The store uses a new database (`funcao_vectors`) on the pgvector sidecar. The
Natureza index stays in `natureza_vectors`, and each index can be rebuilt or
dropped without touching the other.

## Requirements

- The stack from the parent directory must already run: `make up`.
- Docker Engine or Docker Desktop with Compose v2.
- 8 GB of RAM minimum, 12 GB recommended. `qwen3:4b` plus the embedding
  model peak at about 4.6 GB; the rest of the stack uses about 1 GB.
- About 4 GB of free disk for the two models, plus the images and volumes.
- Internet access on the first run. Later runs work offline.

The models are the same ones the semantic-search workflow uses, so a stack that
already ran `make semantic-setup` needs no new model downloads.

## Start it

From `test_environment/`:

```bash
make up
make funcao-setup
```

`make up` starts the existing services and the pgvector sidecar. It does not
pull the models or build either index.

`make funcao-setup` is idempotent and does the rest:

1. Waits for pgvector and n8n to become healthy.
2. Imports the pgvector credential with the fixed id `pgvectorFuncao1`.
3. Imports and publishes both `Chat Função e Subfunção` workflows
   (`funcaoSearchFlow01` and `funcaoSearchLexical01`) if they are missing or
   inactive, then restarts n8n once to register both webhooks.
4. Pulls `qwen3:4b` and `qwen3-embedding:0.6b` unless both are present.
5. Builds the 29-row função table and the 83-row subfunção table from
   `sql/data/funcoes.csv` and `sql/data/subfuncoes.csv`. The ingest creates
   `funcao_vectors` and the `vector`, `pg_trgm` and `unaccent` extensions when
   they are missing.
6. Sends the code `061` through the semantic webhook, then `saúde` through the
   lexical webhook, and checks both replies.

The first run takes 5 to 20 minutes depending on the network and CPU. Later
runs skip the model pull; the index rebuild usually finishes in under a minute
with a warm embedding model.

If n8n has no owner account yet, the credential import stops and prints the URL.
Open <http://localhost:5678/>, create the account, and run
`make funcao-setup` again. The webhook works before the account exists; the
account is only needed for the editor.

Check the result:

```bash
make funcao-status
make funcao-smoke
make funcao-lexical-smoke
```

`make funcao-status` checks the containers, both models, the extensions, the
29/83 row counts, the metadata row, and whether each workflow is imported and
active. `make funcao-smoke` posts `061` to the semantic webhook;
`make funcao-lexical-smoke` posts `saúde` to the lexical one and waits longer,
because that call loads `qwen3:4b` on a cold CPU. The semantic path must stay
green too, so run `make semantic-status` after changing shared services.

## Try the chat

Both arms publish a webhook and accept the same messages:

```text
semantic: http://localhost:5678/webhook/funcaosearchflow01/chat
lexical:  http://localhost:5678/webhook/funcaosearchlexical01/chat
```

```bash
# semantic arm, code path
curl -s -X POST http://localhost:5678/webhook/funcaosearchflow01/chat \
  -H 'Content-Type: application/json' \
  -d '{"action":"sendMessage","sessionId":"demo","chatInput":"061"}'

# lexical arm, free-text path
curl -s -X POST http://localhost:5678/webhook/funcaosearchlexical01/chat \
  -H 'Content-Type: application/json' \
  -d '{"action":"sendMessage","sessionId":"demo","chatInput":"saúde"}'
```

The code path skips both Ollama models and returns quickly. A free-text term
loads `qwen3:4b` on the first turn, in either arm. The lexical arm then calls no
embedding model; the semantic arm calls `qwen3-embedding:0.6b` as well.

Expected replies for a healthy store:

| Input | Reply |
| --- | --- |
| `061` | 2 rows: `061 Ação Judiciária / 03 Essencial à Justiça`, then `361 Ensino Fundamental / 12 Educação` |
| `bom dia` | the fixed orientation text (`Qual a Subfunção? Digite o código...`) |
| `saúde` | 5 rows, the whole função 10 |
| `merenda` | `Não encontrei nenhuma Subfunção para *merenda*. Tente outro termo.` |
| `policiamento` | 19 rows, exact hit first, then funções 06 and 04 inherited through the `GREATEST` lift (semantic) |

The first four rows read the same through either arm. The lexical arm answers
`dívida` with 3 rows where the semantic arm returns none; the semantic arm
answers `asfalto` and `meio ambiente` where the lexical arm returns none. The
next section has the measured difference.

Each message is independent. The workflow keeps no session state, so the same
`sessionId` is only needed to keep the chat UI grouped.

## What the workflow does

Each message takes one of three paths.

- A digits-only message becomes a lexical code lookup. One digit is enough; the
  message may also carry a `código:` label. Leading zeros are dropped before the
  match, and results are ordered exact subfunção, then função, then partial.
  This path calls neither model.
- Greetings and help questions return fixed orientation text. `qwen3:4b`
  classifies the message as `saudacao` or `ajuda`; neither path calls the
  embedding endpoint or the database.
- Any message classified as `busca` becomes a text search in one of the two
  arms. `qwen3:4b` returns a JSON object with the intent and the search term,
  accents included. In the semantic arm the term is embedded with
  `qwen3-embedding:0.6b` (1024 dimensions, no instruction prefix) and compared
  with the stored labels using cosine similarity. In the lexical arm the term
  goes straight to SQL and is scored by substring containment (`strpos`) plus
  trigram `similarity()`, with no embedding call. Both arms score a row by the
  greater of its subfunção and its função, so a term that names a função
  returns every subfunção under it, and both keep rows at or above
  `similarity_floor` up to `max_rows` (50). The floors differ: 0.75 semantic,
  0.55 lexical. Both values live in the `Search Config (floor, max_rows)` node
  in each file.

The reply is a fixed markdown table, never a model call. With no candidate rows
it renders the "não encontrei" sentence. When the SQL reports more matches than
the row cap returned, the reply inserts `Mostrando N de M resultados.` above the
table. Both SQL nodes return one sentinel row when nothing matches, so the
formatter always has the searched term and the untruncated total. If the
extraction call fails or returns malformed JSON, the raw message becomes the
search term and the workflow still answers.

The floor and the row cap were calibrated on 2026-11-18 against a 31-query eval
set exported from the production tables: 29 scored searches plus a greeting and
a help message. At 0.75 the mean reply is 5.4 rows; lower floors return dozens
of weak matches, and higher floors lose recall. The live side-by-side below
measures 5.2, because the live replies lowercase the term. The eval set and the
sweep report stay in the source repository, not here.

## Two retrieval arms

`funcao_search.json` is the default. `funcao_search_lexical.json` is the same
workflow with only the text half replaced. The ten nodes it shares with the
semantic file, from the code router to the reply formatter, are identical in
both. The lexical arm keeps the same store and reply format without a
per-query embedding call, and it answers `dívida`, which the semantic floor
misses.

The trade-off was measured on 2026-11-19 through both chat webhooks over 22
scored text queries, with n8n 2.39.5, Ollama 0.34.1, `qwen3:4b` and
`qwen3-embedding:0.6b`:

| Arm | recall@1 | recall@5 | MRR | coverage | mean rows | false not found | mean reply |
| --- | --- | --- | --- | --- | --- | --- | --- |
| semantic (0.75) | 0.727 | 0.818 | 0.773 | 0.818 | 5.2 | 0.182 | 5.1 s |
| lexical (0.55) | 0.682 | 0.773 | 0.727 | 0.773 | 4.4 | 0.227 | 4.4 s |

The code path is the same SQL in both files and scored 7/7, 1.0 on every
metric, 12.7 mean rows, about 0.25 s.

The margin is one text query, and the failure sets are complementary rather
than nested: the lexical arm answers `dívida` and misses `asfalto` and
`meio ambiente`; the semantic arm does the reverse; both miss `merenda`,
`coleta de lixo` and `creche`. A union answers 19 of the 22 queries, against 18
semantic and 17 lexical. The semantic arm stays the default. The lexical arm is
the tested alternative for a deployment that cannot pay the embedding call per
query, at the cost of `asfalto` and `meio ambiente`.

The lexical SQL needs `pg_trgm` for `similarity()` and `unaccent` for
`unaccent()`. The ingest creates both next to `vector`, so `make funcao-ingest`
produces a store that answers either arm with no manual psql step. Without them
the query fails with `function unaccent(text) does not exist` or
`function similarity(text, text) does not exist`.

## Ports and settings

This package adds no host port. It shares the pgvector sidecar with the
semantic-search workflow and writes to a second database on the same volume.

| Setting | Default | What it controls |
| --- | --- | --- |
| `PGVECTOR_PORT` | `5434` | pgvector on the host, for psql and debugging. n8n reaches `pgvector:5432`. |
| `FUNCAO_PGVECTOR_DB` | `funcao_vectors` | Database name for the Função store. |
| `PGVECTOR_USER` / `PGVECTOR_PASSWORD` | `natureza` / `natureza` | Database credentials, shared with the Natureza index. |
| `EMBED_MODEL` / `EMBED_DIM` | `qwen3-embedding:0.6b` / `1024` | Embedding model and expected dimension for ingestion. |
| `EMBED_BATCH_SIZE` | `32` | Texts per embedding request. |

n8n stays on `localhost:5678`, Ollama on `localhost:11434`, and the budget
Postgres on `localhost:5432`.

To change the database name, edit `.env`, update
`funcao_search/credentials/pgvector-funcao.json` so its `data` block matches,
then run `make funcao-setup`. The workflow nodes are bound to the credential id,
so a mismatch fails at query time.

The parent Compose file keeps `OLLAMA_MAX_LOADED_MODELS=2` and raises the Ollama
memory limit to 6 GB. With a 4 GB limit, the two resident models peak at about
4.6 GB and the embedding worker is OOM-killed on the first free-text query.

## Commands

Run these from `test_environment/`.

| Command | Action |
| --- | --- |
| `make up` | Start the full stack, including pgvector. |
| `make funcao-setup` | First-run setup: models, credential, both workflows, index, both smokes. |
| `make funcao-status` | Health, models, extensions, 29/83 rows, metadata, and both workflows. |
| `make funcao-models` | Pull `qwen3:4b` and `qwen3-embedding:0.6b`. |
| `make funcao-import` | Force re-import and publish both workflows and the credential. |
| `make funcao-lexical-import` | Force re-import and publish only the lexical workflow. |
| `make funcao-ingest` | Rebuild the 29/83-row Função/Subfunção store. |
| `make funcao-smoke` | POST `061` through the semantic webhook. |
| `make funcao-lexical-smoke` | POST `saúde` through the lexical webhook. |

`make funcao-setup` accepts no flags. For control over one step, run the
individual targets in the order above.

## Rebuilding the index

Run this after changing either CSV or the embedding model:

```bash
make funcao-ingest
```

The containerized job validates both CSVs, embeds the 29 função labels and the
83 subfunção labels through Ollama, and recreates both tables in one
transaction, followed by the `funcao_embedding_meta` row. It usually takes under
a minute with a warm embedding model.

Only the labels are embedded. Codes stay in `codigo_digits` and are searched by
the lexical path. The job creates `funcao_vectors` when it is missing and
recreates both tables on every run, so the row counts always match the CSVs.

If you change the embedding model, also update `EMBED_MODEL`, `EMBED_DIM`, the
model name in the `Embed Termo` node, and recalibrate `similarity_floor` in
`Search Config (floor, max_rows)` in the semantic file. The semantic floor is
model-specific. The lexical floor in `funcao_search_lexical.json` does not
depend on any model, but it depends on the term set; recalibrate it if the CSVs
change.

## Troubleshooting

### A webhook returns 404

One of the workflows is not active, or n8n has not registered its webhook. Run:

```bash
make funcao-import
make funcao-smoke
make funcao-lexical-smoke
```

`make funcao-status` names the missing workflow. The two webhooks are
`funcaosearchflow01` (semantic) and `funcaosearchlexical01` (lexical).

### `relation "subfuncao" does not exist`

The Função store is empty. Run `make funcao-ingest`. If the pgvector container
is not running, run `make up` first.

### The lexical query fails on `unaccent` or `similarity`

The store was built before the lexical arm existed, so it has `vector` but not
`pg_trgm` and `unaccent`. Run `make funcao-ingest`; the ingest creates all
three. `make funcao-status` reports the extension count.

### The ingest cannot create `funcao_vectors`

The `natureza` role must be allowed to `CREATE DATABASE`. The pgvector image
creates that role as the superuser, so this normally works on the first run.
If it fails, check `docker compose logs pgvector` and confirm the role and
password in `.env` match `funcao_search/credentials/pgvector-funcao.json`.

### The Postgres node cannot connect

From n8n the host is `pgvector:5432`, not `localhost:5434`. Check that the
`pgvector` container is healthy and that the credential still has the fixed id
`pgvectorFuncao1`.

### The extraction or embedding call times out

Ollama may still be loading `qwen3:4b`, or one of the models is missing. Run
`make funcao-status`; if a model is missing, run `make funcao-models`.

### A free-text query is slow

On CPU, `qwen3:4b` is the bottleneck. The first turn loads the model; later
turns reuse it for 30 minutes. Keep the `ollama` container running between
turns. A code query such as `061` skips both models and returns quickly.

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
`make funcao-setup` again. The CLI cannot create the owner account.

## Notes

- The workflow JSONs are the source of truth. After editing either
  `funcao_search/funcao_search.json` or `funcao_search_lexical.json`, run
  `make funcao-import` (or `make funcao-lexical-import` for the lexical one).
- `make funcao-setup` leaves an already active workflow untouched, so an edit
  made in the n8n editor is not overwritten by a routine setup run.
- The `funcao-ingest` service is behind the `setup` profile, so `make up` does
  not build the index or pull models. That keeps the existing quickstart fast.
- The extraction calls in both arms, and the embedding call in the semantic
  arm, use the Compose service at `ollama:11434`. The three Postgres nodes use
  the `pgvectorFuncao1` credential at `pgvector:5432`.
- The Função, lexical and semantic workflows can be active at the same time.
  They share the Ollama and pgvector containers but not a database.
- The workflow was built against n8n 2.39.5 and Ollama 0.34.1, and exercised
  against this stack's `latest` n8n and Ollama images.
