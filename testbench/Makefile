.PHONY: help setup-network up down restart status logs logs-ollama logs-n8n pull-models test-dry-run test-direct test-n8n psql db-seed

MODEL ?= llama3.2:1b
OLLAMA_URL ?= http://localhost:11434
N8N_URL ?= http://localhost:5678

help:
	@echo "======================================================================"
	@echo " 🚀 Bateria de Testes SLM - Home Lab (UEL / LABGEP)"
	@echo "======================================================================"
	@echo "make up            - Inicia Ollama, PostgreSQL e n8n em background"
	@echo "make down          - Interrompe todos os contêineres e libera memória"
	@echo "make restart       - Reinicia a stack inteira"
	@echo "make status        - Exibe status dos contêineres e consumo de RAM/CPU"
	@echo "make pull-models   - Baixa os SLMs recomendados (Llama 3.2, Qwen 2.5) no Ollama"
	@echo "make test-dry-run  - Executa a suite de testes em modo offline (validação)"
	@echo "make test-direct   - Executa benchmark contra o Ollama direto (MODEL=$(MODEL))"
	@echo "make test-n8n      - Executa benchmark contra o Webhook do n8n (ponta a ponta)"
	@echo "make logs          - Acompanha logs de todos os serviços"
	@echo "make logs-ollama   - Acompanha logs de inferência do Ollama"
	@echo "make logs-n8n      - Acompanha logs do orquestrador n8n"
	@echo "make psql          - Abre shell interativo do PostgreSQL no banco de dados"
	@echo "make db-seed       - Reaplica a carga do banco de dados (sql/init.sql)"
	@echo "======================================================================"

setup-network:
	@if ! docker network inspect lab-network >/dev/null 2>&1; then \
		echo "--> Criando rede 'lab-network'..."; \
		docker network create --driver bridge --attachable lab-network; \
	fi

up: setup-network
	docker compose up -d
	@echo ""
	@echo "✅ Stack iniciada com sucesso!"
	@echo "   - n8n Web UI:     http://localhost:5678"
	@echo "   - Ollama Engine:  http://localhost:11434"
	@echo "   - PostgreSQL:     localhost:5432 (db: orcamento_db)"
	@echo ""
	@echo "💡 Próximo passo: execute 'make pull-models' para baixar as SLMs."

down:
	docker compose down

restart:
	docker compose restart

status:
	docker compose ps
	@echo ""
	@echo "--> Consumo de Recursos em Tempo Real:"
	docker stats --no-stream homelab-slm-ollama homelab-slm-n8n homelab-slm-postgres 2>/dev/null || true

logs:
	docker compose logs -f

logs-ollama:
	docker compose logs -f ollama

logs-n8n:
	docker compose logs -f n8n

pull-models:
	./scripts/setup_models.sh

test-dry-run:
	python3 benchmark/run_benchmark.py --dry-run

test-direct:
	python3 benchmark/run_benchmark.py --model $(MODEL) --ollama-url $(OLLAMA_URL)

test-n8n:
	python3 benchmark/run_benchmark.py --n8n-url $(N8N_URL) --n8n-webhook acao-orcamentaria

psql:
	docker exec -it homelab-slm-postgres psql -U postgres -d orcamento_db

db-seed:
	docker exec -i homelab-slm-postgres psql -U postgres -d orcamento_db < sql/init.sql
	@echo "✅ Banco recarregado com sucesso!"
