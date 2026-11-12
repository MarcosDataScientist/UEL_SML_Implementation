#!/usr/bin/env bash
#
# Semantic-search helper for the existing test environment.
#
# Usage:
#   ./scripts/semantic_search.sh setup       first-run setup (idempotent)
#   ./scripts/semantic_search.sh models      pull qwen3:4b and the embedding model
#   ./scripts/semantic_search.sh import      re-import the credential and workflow
#   ./scripts/semantic_search.sh ingest      rebuild the 1,560-row pgvector index
#   ./scripts/semantic_search.sh smoke       POST a known code through the webhook
#   ./scripts/semantic_search.sh status      health, models, index, workflow state
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
N8N_CONTAINER="homelab-slm-n8n"
OLLAMA_CONTAINER="homelab-slm-ollama"
PGVECTOR_CONTAINER="homelab-slm-pgvector"
WORKFLOW_ID="semanticSearchFlow01"
WEBHOOK_PATH="semanticsearchflow01"
WORKFLOW_FILE="/semantic_search/chat_semantic_search.json"
CREDENTIAL_FILE="/semantic_search/credentials/pgvector.json"
CHAT_MODEL="qwen3:4b"
EMBED_MODEL="qwen3-embedding:0.6b"
EXPECTED_ROWS="1560"

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
  step "Importing the pgvector credential"
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
    --output=/tmp/semantic-status.json >/dev/null 2>&1 || return 1
  $COMPOSE exec -T -u node n8n cat /tmp/semantic-status.json 2>/dev/null \
    | grep -q '"active"[[:space:]]*:[[:space:]]*true'
}

import_workflow() {
  local force="${1:-0}"
  step "Checking the semantic-search workflow"
  if [ "$force" -eq 0 ] && workflow_exists && workflow_is_active; then
    info "Workflow $WORKFLOW_ID is already active; leaving it untouched."
    info "Use 'make semantic-import' after changing the workflow JSON."
    return 0
  fi

  step "Importing and publishing the semantic-search workflow"
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
  step "Rebuilding the pgvector index"
  $COMPOSE --profile setup run --rm semantic-ingest --dry-run
  $COMPOSE --profile setup run --rm semantic-ingest
}

smoke() {
  step "Running the semantic-search smoke test"
  local body response
  body='{"action":"sendMessage","sessionId":"smoke","chatInput":"3.3.90.30.01"}'

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
    die "The webhook did not answer after 30 seconds. Run 'make semantic-status'."
  fi

  printf '%s\n' "$response"
  printf '%s' "$response" | grep -q 'Código: 3.3.90.30.01' \
    || die "The reply did not contain 'Código: 3.3.90.30.01'."
  info "Smoke test passed."
}

status() {
  local failures=0 listing rows
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
    fail "$CHAT_MODEL is missing (run: make semantic-models)"
  fi
  if printf '%s\n' "$listing" | grep -q "^${EMBED_MODEL}[[:space:]]"; then
    pass "$EMBED_MODEL is present"
  else
    fail "$EMBED_MODEL is missing (run: make semantic-models)"
  fi

  printf '\n== Vector index ==\n'
  rows="$($COMPOSE exec -T pgvector sh -c \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select count(*) from natureza_linhas"' \
    2>/dev/null | tr -d '[:space:]' || true)"
  if [ "$rows" = "$EXPECTED_ROWS" ]; then
    pass "natureza_linhas has $rows linhas"
  else
    fail "natureza_linhas has '${rows:-no value}' rows; expected $EXPECTED_ROWS (run: make semantic-ingest)"
  fi

  printf '\n== n8n workflow ==\n'
  if $COMPOSE exec -T -u node n8n n8n list:workflow 2>/dev/null \
      | grep -q "^${WORKFLOW_ID}|"; then
    pass "workflow $WORKFLOW_ID is imported"
    if $COMPOSE exec -T -u node n8n n8n export:workflow --id="$WORKFLOW_ID" \
        --output=/tmp/semantic-status.json >/dev/null 2>&1 \
        && $COMPOSE exec -T -u node n8n cat /tmp/semantic-status.json 2>/dev/null \
          | grep -q '"active"[[:space:]]*:[[:space:]]*true'; then
      pass "workflow $WORKFLOW_ID is active"
    else
      fail "workflow $WORKFLOW_ID is not active (run: make semantic-import)"
    fi
  else
    fail "workflow $WORKFLOW_ID is missing (run: make semantic-import)"
  fi

  printf '\n== Endpoints ==\n'
  printf '  n8n UI:     http://localhost:%s/\n' "$N8N_PORT"
  printf '  chat hook:  http://localhost:%s/webhook/%s/chat\n' "$N8N_PORT" "$WEBHOOK_PATH"
  printf '  pgvector:   localhost:%s\n' "${PGVECTOR_PORT:-5434}"
  printf '  Ollama:     http://localhost:%s/\n' "${OLLAMA_PORT:-11434}"

  printf '\n'
  if [ "$failures" -eq 0 ]; then
    printf 'All semantic-search checks passed.\n'
    return 0
  fi
  printf '%s semantic-search check(s) failed.\n' "$failures" >&2
  return 1
}

setup() {
  require_stack
  import_credential
  import_workflow 0
  pull_models
  ingest
  smoke
  printf '\nSemantic search is ready.\n'
  printf 'Open http://localhost:%s/ and use the "Chat Semantic Search" workflow.\n' "$N8N_PORT"
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
