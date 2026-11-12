.PHONY: help setup-network up down restart status logs logs-ollama logs-n8n register-finetuned pull-models test-dry-run test-direct test-n8n test-memory test-memory-live psql db-seed semantic-setup semantic-status semantic-models semantic-ingest semantic-import semantic-smoke

MODEL ?= qwen2.5-budget:1.5b
MODELS ?= qwen2.5-budget:1.5b,qwen2.5:1.5b,llama3.2:1b
MODE ?= json
OLLAMA_URL ?= http://localhost:11434
N8N_URL ?= http://localhost:5678

help:
	@echo "======================================================================"
	@echo " 🚀 SLM Test Environment - Home Lab (UEL / LABGEP)"
	@echo "======================================================================"
	@echo "make up            - Starts Ollama, PostgreSQL, and n8n in background"
	@echo "make down          - Stops all containers and frees host RAM"
	@echo "make restart       - Restarts the entire stack"
	@echo "make status        - Displays container status and live RAM/CPU usage"
	@echo "make register-finetuned - Registers local fine-tuned Qwen 2.5 1.5B (unsloth.Q4_K_M.gguf)"
	@echo "make pull-models   - Pulls recommended baseline SLMs (Llama 3.2, Qwen 2.5) into Ollama"
	@echo "make test-dry-run  - Runs test suite in offline mode (dry-run validation)"
	@echo "make test-direct   - Runs benchmark directly against Ollama (MODEL=$(MODEL), MODE=$(MODE))"
	@echo "make test-compare  - Runs comparative model benchmark (MODELS=$(MODELS))"
	@echo "make test-n8n      - Runs end-to-end benchmark against n8n Webhook"
	@echo "make test-memory   - Simulates Session Mini-Memory + K-Medoids (offline)"
	@echo "make test-memory-live - Runs 6-turn multi-user live benchmark against n8n Webhook"
	@echo "make logs          - Follows logs from all services"
	@echo "make logs-ollama   - Follows Ollama inference logs"
	@echo "make logs-n8n      - Follows n8n orchestrator logs"
	@echo "make psql          - Opens interactive PostgreSQL shell on orcamento_db"
	@echo "make db-seed       - Reloads database schema and seeds (sql/init.sql)"
	@echo "make semantic-setup - Imports the semantic workflow, pulls models, builds the index, smoke-tests"
	@echo "make semantic-status - Semantic-search health, models, index, and workflow state"
	@echo "make semantic-models - Pulls qwen3:4b and qwen3-embedding:0.6b"
	@echo "make semantic-ingest - Rebuilds the 1,560-row semantic pgvector index"
	@echo "make semantic-import - Re-imports the semantic workflow and credential"
	@echo "make semantic-smoke  - Tests the semantic chat webhook"
	@echo "======================================================================"

setup-network:
	@if ! docker network inspect lab-network >/dev/null 2>&1; then \
		echo "--> Creating 'lab-network' Docker bridge..."; \
		docker network create --driver bridge --attachable lab-network; \
	fi

up: setup-network
	docker compose up -d
	@echo ""
	@echo "✅ Stack started successfully!"
	@echo "   - n8n Web UI:     http://localhost:5678"
	@echo "   - Ollama Engine:  http://localhost:11434"
	@echo "   - PostgreSQL:     localhost:5432 (db: orcamento_db)"
	@echo "   - pgvector:       localhost:5434 (semantic search)"
	@echo ""
	@echo "💡 Next step: run 'make pull-models' to download candidate SLMs."
	@echo "   For the semantic search workflow: make semantic-setup"

down:
	docker compose down

restart:
	docker compose restart

status:
	docker compose ps
	@echo ""
	@echo "--> Real-time Resource Consumption:"
	docker stats --no-stream homelab-slm-ollama homelab-slm-n8n homelab-slm-postgres homelab-slm-pgvector 2>/dev/null || true

logs:
	docker compose logs -f

logs-ollama:
	docker compose logs -f ollama

logs-n8n:
	docker compose logs -f n8n

register-finetuned:
	docker exec -w /fine_tuning homelab-slm-ollama ollama create qwen2.5-budget:1.5b -f Modelfile
	@echo "✅ Fine-tuned model 'qwen2.5-budget:1.5b' registered from notebooks/fine_tuning/unsloth.Q4_K_M.gguf!"

pull-models:
	./scripts/setup_models.sh

test-dry-run:
	python3 model_selection_benchmark/run_benchmark.py --dry-run

test-direct:
	python3 model_selection_benchmark/run_benchmark.py --model $(MODEL) --mode $(MODE) --ollama-url $(OLLAMA_URL)

test-compare:
	python3 model_selection_benchmark/run_benchmark.py --models $(MODELS) --mode $(MODE) --ollama-url $(OLLAMA_URL)

test-n8n:
	python3 model_selection_benchmark/run_benchmark.py --mode n8n --n8n-url $(N8N_URL) --n8n-webhook acao-orcamentaria

test-memory:
	python3 scripts/test_session_memory_simulation.py

test-memory-live:
	python3 model_selection_benchmark/run_memory_kmedoids_benchmark.py --webhook-url $(N8N_URL)/webhook/natureza-despesa-memoria

psql:
	docker exec -it homelab-slm-postgres psql -U postgres -d orcamento_db

db-seed:
	docker exec -i homelab-slm-postgres psql -U postgres -d orcamento_db < sql/init.sql
	python3 scripts/seed_full_naturezadespesa.py
	@echo "✅ Database reloaded successfully (including 1,560 Natureza de Despesa records)!"

# Semantic search (pgvector) ----------------------------------------------------
# The workflow, credential, and ingestion job live in semantic_search/.
# `make semantic-setup` is idempotent; run it after `make up` on a fresh clone.

semantic-setup:
	./scripts/semantic_search.sh setup

semantic-status:
	./scripts/semantic_search.sh status

semantic-models:
	./scripts/semantic_search.sh models

semantic-ingest:
	./scripts/semantic_search.sh ingest

semantic-import:
	./scripts/semantic_search.sh import

semantic-smoke:
	./scripts/semantic_search.sh smoke
