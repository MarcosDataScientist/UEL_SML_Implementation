#!/usr/bin/env bash
#
# Função/Subfunção-search helper for the existing test environment.
# Run with `--help` for the command list and assumptions.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Compose reads .env for the containers; the shell needs the same host ports
# for the smoke URL and the status display.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

COMPOSE="${COMPOSE:-docker compose}"
N8N_PORT="${N8N_PORT:-5678}"
PGVECTOR_PORT="${PGVECTOR_PORT:-5434}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
FUNCAO_DB="${FUNCAO_PGVECTOR_DB:-funcao_vectors}"
N8N_CONTAINER="homelab-slm-n8n"
OLLAMA_CONTAINER="homelab-slm-ollama"
PGVECTOR_CONTAINER="homelab-slm-pgvector"
WORKFLOW_ID="funcaoSearchFlow01"
WEBHOOK_PATH="funcaosearchflow01"
WORKFLOW_FILE="/funcao_search/funcao_search.json"
LEXICAL_WORKFLOW_ID="funcaoSearchLexical01"
LEXICAL_WEBHOOK_PATH="funcaosearchlexical01"
LEXICAL_WORKFLOW_FILE="/funcao_search/funcao_search_lexical.json"
CREDENTIAL_FILE="/funcao_search/credentials/pgvector-funcao.json"
CHAT_MODEL="qwen3:4b"
EMBED_MODEL="${EMBED_MODEL:-qwen3-embedding:0.6b}"
EMBED_DIM="${EMBED_DIM:-1024}"
EXPECTED_FUNCOES="29"
EXPECTED_SUBFUNCOES="83"

info() { printf '%s\n' "$*"; }
step() { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Função/Subfunção-search helper for the existing test environment.

Usage:
  ./scripts/funcao_search.sh setup            first-run setup for both arms (idempotent)
  ./scripts/funcao_search.sh models           pull qwen3:4b and the embedding model
  ./scripts/funcao_search.sh import           re-import the credential and both workflows
  ./scripts/funcao_search.sh import-lexical   re-import only the lexical workflow
  ./scripts/funcao_search.sh ingest           rebuild the 29/83-row pgvector store
  ./scripts/funcao_search.sh smoke            POST a known código through the semantic webhook
  ./scripts/funcao_search.sh smoke-lexical    POST saúde through the lexical webhook
  ./scripts/funcao_search.sh status           health, models, extensions, index, workflow state

The script assumes `make up` has already started the stack. It never starts
the normal `postgres` service and never touches the budget database.
EOF
}

require_docker() {
  docker --version >/dev/null 2>&1 || die "Docker is not available."
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is not available."
}

container_running() {
  [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || true)" = "true" ]
}

container_healthy() {
  [ "$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$1" 2>/dev/null || true)" = "healthy" ]
}

wait_for_container() {
  local name="$1" tries="${2:-60}" attempt=1
  while [ "$attempt" -le "$tries" ]; do
    if container_healthy "$name"; then
      return 0
    fi
    sleep 2
    attempt=$((attempt + 1))
  done
  return 1
}

n8n_healthy() {
  $COMPOSE exec -T -u node n8n \
    wget -qO- http://127.0.0.1:5678/healthz >/dev/null 2>&1
}

wait_for_n8n() {
  local attempt=1
  while [ "$attempt" -le 90 ]; do
    if $COMPOSE exec -T -u node n8n \
        wget -qO- http://127.0.0.1:5678/healthz >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
    attempt=$((attempt + 1))
  done
  return 1
}

require_stack() {
  container_running "$N8N_CONTAINER" \
    || die "n8n is not running. Start the stack with 'make up' first."
  container_running "$OLLAMA_CONTAINER" \
    || die "Ollama is not running. Start the stack with 'make up' first."
  if ! container_running "$PGVECTOR_CONTAINER"; then
    info "Starting the pgvector sidecar..."
    $COMPOSE up -d pgvector
  fi
  wait_for_container "$PGVECTOR_CONTAINER" 60 \
    || die "pgvector did not become healthy. Inspect: $COMPOSE logs pgvector"
  wait_for_n8n || die "n8n did not become healthy. Inspect: $COMPOSE logs n8n"
}

models_present() {
  local listing
  listing="$($COMPOSE exec -T ollama ollama list 2>/dev/null || true)"
  printf '%s\n' "$listing" | grep -q "^${CHAT_MODEL}[[:space:]]" \
    && printf '%s\n' "$listing" | grep -q "^${EMBED_MODEL}[[:space:]]"
}

pull_models() {
  step "Checking the Ollama models"
  if models_present; then
    info "Models already present ($CHAT_MODEL, $EMBED_MODEL); skipping pull."
    return 0
  fi
  info "Pulling $CHAT_MODEL and $EMBED_MODEL (several GB; this can take a while)..."
  $COMPOSE exec -T ollama ollama pull "$CHAT_MODEL"
  $COMPOSE exec -T ollama ollama pull "$EMBED_MODEL"
}

import_credential() {
  step "Importing the pgvector Função credential"
  if $COMPOSE exec -T -u node n8n \
      n8n import:credentials --input="$CREDENTIAL_FILE"; then
    return 0
  fi

  printf '\nOpen http://localhost:%s/, create the n8n owner account, then press Enter.\n' "$N8N_PORT"
  if [ -t 0 ]; then
    read -r _ || true
  else
    die "The credential import needs an n8n owner account. Run this again from a terminal."
  fi

  $COMPOSE exec -T -u node n8n \
    n8n import:credentials --input="$CREDENTIAL_FILE" \
    || die "The credential import failed after retrying."
}

workflow_exists() {
  local id="$1"
  $COMPOSE exec -T -u node n8n n8n list:workflow 2>/dev/null \
    | grep -q "^${id}|"
}

workflow_is_active() {
  local id="$1"
  $COMPOSE exec -T -u node n8n n8n export:workflow --id="$id" \
    --output=/tmp/funcao-status.json >/dev/null 2>&1 || return 1
  $COMPOSE exec -T -u node n8n cat /tmp/funcao-status.json 2>/dev/null \
    | grep -q '"active"[[:space:]]*:[[:space:]]*true'
}

# Imports and publishes one workflow. Returns 0 when it imported the workflow
# and 1 when the workflow was already active. Does not restart n8n; the caller
# does that once after both files are in place.
import_workflow() {
  local id="$1" file="$2" force="${3:-0}"
  if [ "$force" -eq 0 ] && workflow_exists "$id" && workflow_is_active "$id"; then
    return 1
  fi

  info "Importing and publishing $id..."
  $COMPOSE exec -T -u node n8n \
    n8n import:workflow --input="$file"

  # n8n 2.x uses publish:workflow. Older images use update:workflow.
  if ! $COMPOSE exec -T -u node n8n \
      n8n publish:workflow --id="$id"; then
    warn "publish:workflow failed for $id; trying update:workflow --active=true."
    $COMPOSE exec -T -u node n8n \
      n8n update:workflow --id="$id" --active=true
  fi
  return 0
}

import_workflows() {
  local force="${1:-0}" imported=0
  step "Checking the Função/Subfunção workflows"
  if import_workflow "$WORKFLOW_ID" "$WORKFLOW_FILE" "$force"; then
    imported=1
  fi
  if import_workflow "$LEXICAL_WORKFLOW_ID" "$LEXICAL_WORKFLOW_FILE" "$force"; then
    imported=1
  fi

  if [ "$imported" -eq 0 ]; then
    info "Both workflows are already active; leaving them untouched."
    info "Use 'make funcao-import' after changing a workflow JSON."
    return 0
  fi

  step "Restarting n8n so the production webhooks are registered"
  $COMPOSE restart n8n >/dev/null
  wait_for_n8n || die "n8n did not become healthy after the restart."
}

import_lexical_workflow() {
  step "Importing the lexical Função/Subfunção workflow"
  import_workflow "$LEXICAL_WORKFLOW_ID" "$LEXICAL_WORKFLOW_FILE" 1

  step "Restarting n8n so the lexical webhook is registered"
  $COMPOSE restart n8n >/dev/null
  wait_for_n8n || die "n8n did not become healthy after the restart."
}

ingest() {
  step "Rebuilding the Função/Subfunção pgvector store"
  # --build keeps the image in step with create_schema_sql: an image built
  # before the lexical arm lacks pg_trgm and unaccent, and a plain `run`
  # would reuse it and skip their creation.
  $COMPOSE --profile setup run --rm --build funcao-ingest --dry-run
  $COMPOSE --profile setup run --rm --build funcao-ingest
}

# POSTs one chat message and prints the reply. Tries every two seconds for
# `tries` attempts, so the timeout is `tries * 2` seconds. Falls back to a
# throwaway curl container when the host has no curl.
post_chat() {
  local webhook="$1" body="$2" tries="${3:-15}" response="" attempt=1
  while [ "$attempt" -le "$tries" ]; do
    if command -v curl >/dev/null 2>&1; then
      if response="$(curl -sf -X POST \
          "http://localhost:${N8N_PORT}/webhook/${webhook}/chat" \
          -H 'Content-Type: application/json' \
          -d "$body" 2>/dev/null)"; then
        break
      fi
    else
      if response="$(docker run --rm --network lab-network curlimages/curl:8.23.0 \
          -sf -X POST "http://n8n:5678/webhook/${webhook}/chat" \
          -H 'Content-Type: application/json' \
          -d "$body" 2>/dev/null)"; then
        break
      fi
    fi
    sleep 2
    attempt=$((attempt + 1))
  done
  printf '%s' "$response"
}

smoke() {
  step "Running the Função/Subfunção smoke test"
  local body response tries=15
  body='{"action":"sendMessage","sessionId":"smoke","chatInput":"061"}'

  response="$(post_chat "$WEBHOOK_PATH" "$body" "$tries")"
  if [ -z "$response" ]; then
    die "The semantic webhook did not answer after $((tries * 2)) seconds. Run 'make funcao-status'."
  fi

  printf '%s\n' "$response"
  printf '%s' "$response" | grep -q '| 061 | Ação Judiciária | 03 | Essencial à Justiça |' \
    || die "The reply did not contain the 061 row 'Ação Judiciária'."
  printf '%s' "$response" | grep -q '| 361 | Ensino Fundamental | 12 | Educação |' \
    || die "The reply did not contain the 361 row 'Ensino Fundamental'."
  info "Smoke test passed."
}

smoke_lexical() {
  step "Running the lexical Função/Subfunção smoke test"
  local body response tries=90
  body='{"action":"sendMessage","sessionId":"smoke","chatInput":"saúde"}'

  # The first free-text message loads qwen3:4b, which can take a minute on a
  # cold CPU, so this waits longer than the code smoke.
  response="$(post_chat "$LEXICAL_WEBHOOK_PATH" "$body" "$tries")"
  if [ -z "$response" ]; then
    die "The lexical webhook did not answer after $((tries * 2)) seconds. Run 'make funcao-status'."
  fi

  printf '%s\n' "$response"
  printf '%s' "$response" | grep -q '| 301 | Atenção Básica | 10 | Saúde |' \
    || die "The reply did not contain the 301 row 'Atenção Básica'."
  printf '%s' "$response" | grep -q '| 573 | Difusão do Conhecimento Científico e Tecnológico | 10 | Saúde |' \
    || die "The reply did not contain the 573 row 'Difusão do Conhecimento Científico e Tecnológico'."
  info "Lexical smoke test passed."
}

# Run one query against the Função database. `psql` reads POSTGRES_USER from
# the container; the database name comes from .env because the pgvector
# container only creates natureza_vectors at boot.
db_query() {
  local db="$1" sql="$2"
  $COMPOSE exec -T pgvector sh -c \
    'psql -U "$POSTGRES_USER" -d "$1" -tAc "$2"' sh "$db" "$sql" 2>/dev/null \
    | tr -d '[:space:]'
}

status() {
  local failures=0 listing funcoes subfuncoes meta expected_meta extensions
  local workflow_id webhook
  fail() { printf '  FAIL  %s\n' "$*" >&2; failures=$((failures + 1)); }
  pass() { printf '  ok    %s\n' "$*"; }

  printf '\n== Containers ==\n'
  $COMPOSE ps pgvector n8n ollama || true

  printf '\n== Health ==\n'
  if ! container_running "$PGVECTOR_CONTAINER"; then
    fail "pgvector is not running"
  elif ! container_healthy "$PGVECTOR_CONTAINER"; then
    fail "pgvector is running but not healthy"
  else
    pass "pgvector is healthy"
  fi
  if ! container_running "$OLLAMA_CONTAINER"; then
    fail "ollama is not running"
  elif ! container_healthy "$OLLAMA_CONTAINER"; then
    fail "ollama is running but not healthy"
  else
    pass "ollama is healthy"
  fi
  if ! container_running "$N8N_CONTAINER"; then
    fail "n8n is not running"
  elif ! n8n_healthy; then
    fail "n8n is running but its health endpoint is not responding"
  else
    pass "n8n is healthy"
  fi

  printf '\n== Ollama models ==\n'
  listing="$($COMPOSE exec -T ollama ollama list 2>/dev/null || true)"
  if printf '%s\n' "$listing" | grep -q "^${CHAT_MODEL}[[:space:]]"; then
    pass "$CHAT_MODEL is present"
  else
    fail "$CHAT_MODEL is missing (run: make funcao-models)"
  fi
  if printf '%s\n' "$listing" | grep -q "^${EMBED_MODEL}[[:space:]]"; then
    pass "$EMBED_MODEL is present"
  else
    fail "$EMBED_MODEL is missing (run: make funcao-models)"
  fi

  printf '\n== Vector index ==\n'
  funcoes="$(db_query "$FUNCAO_DB" 'select count(*) from funcao' || true)"
  subfuncoes="$(db_query "$FUNCAO_DB" 'select count(*) from subfuncao' || true)"
  meta="$(db_query "$FUNCAO_DB" \
    "select model || '|' || dim || '|' || funcao_count || '|' || subfuncao_count from funcao_embedding_meta" || true)"
  expected_meta="${EMBED_MODEL}|${EMBED_DIM}|${EXPECTED_FUNCOES}|${EXPECTED_SUBFUNCOES}"

  if [ "$funcoes" = "$EXPECTED_FUNCOES" ]; then
    pass "funcao has $funcoes rows"
  else
    fail "funcao has '${funcoes:-no value}' rows; expected $EXPECTED_FUNCOES (run: make funcao-ingest)"
  fi
  if [ "$subfuncoes" = "$EXPECTED_SUBFUNCOES" ]; then
    pass "subfuncao has $subfuncoes rows"
  else
    fail "subfuncao has '${subfuncoes:-no value}' rows; expected $EXPECTED_SUBFUNCOES (run: make funcao-ingest)"
  fi
  if [ "$meta" = "$expected_meta" ]; then
    pass "funcao_embedding_meta says ${meta}"
  else
    fail "funcao_embedding_meta is '${meta:-no value}'; expected '$expected_meta' (run: make funcao-ingest)"
  fi

  printf '\n== Extensions ==\n'
  extensions="$(db_query "$FUNCAO_DB" \
    "select count(*) from pg_extension where extname in ('vector','pg_trgm','unaccent')" || true)"
  if [ "$extensions" = "3" ]; then
    pass "vector, pg_trgm and unaccent are installed"
  else
    fail "pg_extension has '${extensions:-no value}' of vector/pg_trgm/unaccent; expected 3 (run: make funcao-ingest)"
  fi

  printf '\n== n8n workflows ==\n'
  for workflow_id in "$WORKFLOW_ID" "$LEXICAL_WORKFLOW_ID"; do
    if $COMPOSE exec -T -u node n8n n8n list:workflow 2>/dev/null \
        | grep -q "^${workflow_id}|"; then
      pass "workflow $workflow_id is imported"
      if $COMPOSE exec -T -u node n8n n8n export:workflow --id="$workflow_id" \
          --output=/tmp/funcao-status.json >/dev/null 2>&1 \
          && $COMPOSE exec -T -u node n8n cat /tmp/funcao-status.json 2>/dev/null \
            | grep -q '"active"[[:space:]]*:[[:space:]]*true'; then
        pass "workflow $workflow_id is active"
      else
        fail "workflow $workflow_id is not active (run: make funcao-import)"
      fi
    else
      fail "workflow $workflow_id is missing (run: make funcao-import)"
    fi
  done

  printf '\n== Endpoints ==\n'
  printf '  n8n UI:     http://localhost:%s/\n' "$N8N_PORT"
  for webhook in "$WEBHOOK_PATH" "$LEXICAL_WEBHOOK_PATH"; do
    printf '  chat hook:  http://localhost:%s/webhook/%s/chat\n' "$N8N_PORT" "$webhook"
  done
  printf '  pgvector:   localhost:%s (db: %s)\n' "$PGVECTOR_PORT" "$FUNCAO_DB"
  printf '  Ollama:     http://localhost:%s/\n' "$OLLAMA_PORT"

  printf '\n'
  if [ "$failures" -eq 0 ]; then
    printf 'All Função/Subfunção checks passed.\n'
    return 0
  fi
  printf '%s Função/Subfunção check(s) failed.\n' "$failures" >&2
  return 1
}

setup() {
  require_stack
  import_credential
  import_workflows 0
  pull_models
  ingest
  smoke
  smoke_lexical
  printf '\nFunção/Subfunção search is ready.\n'
  printf 'Open http://localhost:%s/ and use the "Chat Função e Subfunção" workflow.\n' "$N8N_PORT"
  printf 'The lexical arm is the "Chat Função e Subfunção (lexical)" workflow.\n'
}

main() {
  local command="${1:-}"
  [ "$#" -gt 0 ] && shift || true
  require_docker

  case "$command" in
    setup) setup ;;
    models) require_stack; pull_models ;;
    import) require_stack; import_credential; import_workflows 1 ;;
    import-lexical) require_stack; import_lexical_workflow ;;
    ingest) require_stack; ingest ;;
    smoke) require_stack; smoke ;;
    smoke-lexical)
      require_stack
      models_present || die "qwen3:4b is missing. Run 'make funcao-models' first."
      smoke_lexical
      ;;
    status) status ;;
    --help | -h | help | "") usage ;;
    *) usage >&2; die "unknown command: $command" ;;
  esac
}

main "$@"
