#!/usr/bin/env bash
#
# Função/Subfunção-search helper for the existing test environment.
#
# Usage:
#   ./scripts/funcao_search.sh setup       first-run setup (idempotent)
#   ./scripts/funcao_search.sh models      pull qwen3:4b and the embedding model
#   ./scripts/funcao_search.sh import      re-import the credential and workflow
#   ./scripts/funcao_search.sh ingest      rebuild the 29/83-row pgvector store
#   ./scripts/funcao_search.sh smoke       POST a known código through the webhook
#   ./scripts/funcao_search.sh status      health, models, index, workflow state
#
# The script assumes `make up` has already started the stack. It never starts
# the normal `postgres` service and never touches the budget database.

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
  sed -n '3,14p' "$0" | sed 's/^# \{0,1\}//'
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
  $COMPOSE exec -T -u node n8n n8n list:workflow 2>/dev/null \
    | grep -q "^${WORKFLOW_ID}|"
}

workflow_is_active() {
  $COMPOSE exec -T -u node n8n n8n export:workflow --id="$WORKFLOW_ID" \
    --output=/tmp/funcao-status.json >/dev/null 2>&1 || return 1
  $COMPOSE exec -T -u node n8n cat /tmp/funcao-status.json 2>/dev/null \
    | grep -q '"active"[[:space:]]*:[[:space:]]*true'
}

import_workflow() {
  local force="${1:-0}"
  step "Checking the Função/Subfunção workflow"
  if [ "$force" -eq 0 ] && workflow_exists && workflow_is_active; then
    info "Workflow $WORKFLOW_ID is already active; leaving it untouched."
    info "Use 'make funcao-import' after changing the workflow JSON."
    return 0
  fi

  step "Importing and publishing the Função/Subfunção workflow"
  $COMPOSE exec -T -u node n8n \
    n8n import:workflow --input="$WORKFLOW_FILE"

  # n8n 2.x uses publish:workflow. Older images use update:workflow.
  if ! $COMPOSE exec -T -u node n8n \
      n8n publish:workflow --id="$WORKFLOW_ID"; then
    warn "publish:workflow failed; trying update:workflow --active=true."
    $COMPOSE exec -T -u node n8n \
      n8n update:workflow --id="$WORKFLOW_ID" --active=true
  fi

  step "Restarting n8n so the production webhook is registered"
  $COMPOSE restart n8n >/dev/null
  wait_for_n8n || die "n8n did not become healthy after the restart."
}

ingest() {
  step "Rebuilding the Função/Subfunção pgvector store"
  $COMPOSE --profile setup run --rm funcao-ingest --dry-run
  $COMPOSE --profile setup run --rm funcao-ingest
}

smoke() {
  step "Running the Função/Subfunção smoke test"
  local body response
  body='{"action":"sendMessage","sessionId":"smoke","chatInput":"061"}'

  response=""
  local attempt=1
  while [ "$attempt" -le 15 ]; do
    if command -v curl >/dev/null 2>&1; then
      if response="$(curl -sf -X POST \
          "http://localhost:${N8N_PORT}/webhook/${WEBHOOK_PATH}/chat" \
          -H 'Content-Type: application/json' \
          -d "$body" 2>/dev/null)"; then
        break
      fi
    else
      if response="$(docker run --rm --network lab-network curlimages/curl:8.23.0 \
          -sf -X POST "http://n8n:5678/webhook/${WEBHOOK_PATH}/chat" \
          -H 'Content-Type: application/json' \
          -d "$body" 2>/dev/null)"; then
        break
      fi
    fi
    sleep 2
    attempt=$((attempt + 1))
  done

  if [ -z "$response" ]; then
    die "The webhook did not answer after 30 seconds. Run 'make funcao-status'."
  fi

  printf '%s\n' "$response"
  printf '%s' "$response" | grep -q '| 061 | Ação Judiciária | 03 | Essencial à Justiça |' \
    || die "The reply did not contain the 061 row 'Ação Judiciária'."
  printf '%s' "$response" | grep -q '| 361 | Ensino Fundamental | 12 | Educação |' \
    || die "The reply did not contain the 361 row 'Ensino Fundamental'."
  info "Smoke test passed."
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
  local failures=0 listing funcoes subfuncoes meta expected_meta
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

  printf '\n== n8n workflow ==\n'
  if $COMPOSE exec -T -u node n8n n8n list:workflow 2>/dev/null \
      | grep -q "^${WORKFLOW_ID}|"; then
    pass "workflow $WORKFLOW_ID is imported"
    if $COMPOSE exec -T -u node n8n n8n export:workflow --id="$WORKFLOW_ID" \
        --output=/tmp/funcao-status.json >/dev/null 2>&1 \
        && $COMPOSE exec -T -u node n8n cat /tmp/funcao-status.json 2>/dev/null \
          | grep -q '"active"[[:space:]]*:[[:space:]]*true'; then
      pass "workflow $WORKFLOW_ID is active"
    else
      fail "workflow $WORKFLOW_ID is not active (run: make funcao-import)"
    fi
  else
    fail "workflow $WORKFLOW_ID is missing (run: make funcao-import)"
  fi

  printf '\n== Endpoints ==\n'
  printf '  n8n UI:     http://localhost:%s/\n' "$N8N_PORT"
  printf '  chat hook:  http://localhost:%s/webhook/%s/chat\n' "$N8N_PORT" "$WEBHOOK_PATH"
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
  import_workflow 0
  pull_models
  ingest
  smoke
  printf '\nFunção/Subfunção search is ready.\n'
  printf 'Open http://localhost:%s/ and use the "Chat Função e Subfunção" workflow.\n' "$N8N_PORT"
}

main() {
  local command="${1:-}"
  [ "$#" -gt 0 ] && shift || true
  require_docker

  case "$command" in
    setup) setup ;;
    models) require_stack; pull_models ;;
    import) require_stack; import_credential; import_workflow 1 ;;
    ingest) require_stack; ingest ;;
    smoke) require_stack; smoke ;;
    status) status ;;
    --help | -h | help | "") usage ;;
    *) usage >&2; die "unknown command: $command" ;;
  esac
}

main "$@"
