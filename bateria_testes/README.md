# 🧪 Bateria de Testes: SLMs Locais em CPU com n8n e PostgreSQL

Ambiente de testes conteinerizado e automatizado para avaliação empírica, benchmarking e validação ponta a ponta de **Small Language Models (SLMs)** operando estritamente em **CPU (sem GPU)**, orquestrados pelo **n8n** e consultando bases orçamentárias públicas no **PostgreSQL** com busca fuzzy via extensões `pg_trgm` e `unaccent`.

Desenvolvido para o projeto de extensão universitária no **Laboratório de Pesquisa em Gestão Pública (LABGEP / NIGEP)** da **Universidade Estadual de Londrina (UEL)**.

---

## 🖥️ Alinhamento com o Hardware do Home Lab

Este ambiente foi planejado para executar com segurança dentro dos limites do servidor físico do Home Lab:

| Recurso | Especificação do Host | Alocação Docker (Limites) | Papel no Benchmark |
| :--- | :--- | :--- | :--- |
| **Processador** | Intel® Xeon® E5-2640 v2 (8C/16T @ 2.00 GHz) | Até 6.0 Cores para Ollama | Inferência vetorizada em C++ (`llama.cpp`) acelerada por AVX |
| **Memória (RAM)** | 8 GB DDR3 (2 × 4 GB) + 8 GB NVMe Swap | Ollama: 4 GB \| n8n: 1 GB \| PG: 512 MB | Mantém folga de ~2.5 GB para o SO e Portainer/cAdvisor |
| **Aceleração Gráfica** | NVIDIA GeForce 210 (Legada / Vídeo) | *Desabilitada* (CPU pura) | Simula o cenário real de órgãos e repartições públicas |
| **Rede** | Docker bridge `lab-network` | Integrada à rede do Home Lab | Métricas coletadas em tempo real pelo cAdvisor e Prometheus |

---

## 🏗️ Topologia da Bateria de Testes

```
                               ┌────────────────────────────────────────────────────────┐
                               │             Home Lab Ubuntu Server                     │
                               │                                                        │
    ┌────────────────────┐     │   ┌───────────────────┐        ┌───────────────────┐   │
    │  Benchmark Runner  │────┼───┼─▶│   n8n Workflow    │───────▶│   PostgreSQL 16   │   │
    │  (run_benchmark)   │     │   │   Porta: 5678         │        │   (pg_trgm/unacc) │   │
    │                    │     │   └─────────┬─────────┘        │   Porta: 5432     │   │
    │  - Latência (TTFT) │     │             │                  └───────────────────┘   │
    │  - Tokens/s (Tgen) │     │             ▼                                          │
    │  - Radicais SQL    │     │   ┌───────────────────┐                                │
    │  - Taxa Alucinação │     │   │   Ollama Engine   │                                │
    └─────────┬──────────┘     │   │   Porta: 11434    │                                │
              │                │   │   (Llama / Qwen)  │                                │
              └────────────────┼──▶└───────────────────┘                                │
                               │                                                        │
                               │   Observabilidade Ativa:                               │
                               │   - cAdvisor (8080) & Prometheus (9090)                │
                               │   - Grafana (3000): monitora CPU e RAM da inferência   │
                               └────────────────────────────────────────────────────────┘
```

---

## 📁 Estrutura de Arquivos

```
bateria_testes/
├── docker-compose.yml              # Definição dos contêineres Ollama, n8n e Postgres
├── .env.example                    # Modelo de configuração de portas e senhas
├── .env                            # Variáveis de ambiente ativas
├── Makefile                        # Comandos de automação do ciclo de vida
├── sql/
│   └── init.sql                    # Extensões pg_trgm + unaccent e massa de dados orçamentários
├── scripts/
│   └── setup_models.sh             # Script de download e verificação das SLMs no Ollama
├── benchmark/
│   ├── test_cases.json             # Casos de teste orçamentários (protocolo, busca, radicais)
│   ├── run_benchmark.py            # Executor Python de benchmarks diretos e ponta a ponta
│   ├── benchmark_report.md         # Relatório gerado em Markdown (para o artigo acadêmico)
│   └── benchmark_report.json       # Dados brutos estruturados para gráficos e tabelas
├── n8n_workflows/
│   └── local_ai_acao_orcamentaria.json # Fluxo adaptado para o Ollama e Postgres locais
└── README.md                       # Este guia
```

---

## 🚀 Guia Rápido de Execução

### 1. Iniciar os Serviços no Home Lab
No terminal do servidor (ou via SSH `ssh <user>@homelab.local`):
```bash
cd "projeto_SLM/bateria_testes"
make up
```
*O comando garante a criação da rede `lab-network` e inicializa os 3 contêineres com healthchecks automáticos.*

### 2. Baixar os Modelos Candidatos (SLMs)
Baixe os modelos recomendados para inferência em CPU:
```bash
make pull-models
```
Modelos instalados por padrão:
- `llama3.2:1b` (1.3 GB) — Ultraleve, latência mínima
- `llama3.2:3b` (2.0 GB) — Equilíbrio ideal entre raciocínio e velocidade
- `qwen2.5:1.5b` (1.0 GB) — Excelente vocabulário e aderência a instruções em português
- `qwen2.5:3b` (1.9 GB) — Referência em extração de parâmetros estruturados

> Se desejar baixar apenas um modelo específico:
> ```bash
> ./scripts/setup_models.sh llama3.2:3b
> ```

### 3. Executar o Benchmark Direto de SLMs
Avalie o desempenho do modelo no Ollama (medindo TTFT, tokens por segundo e precisão de radicais):
```bash
# Executa no modelo padrão (llama3.2:1b)
make test-direct

# Ou especifique qualquer outro modelo instalado
make test-direct MODEL=qwen2.5:1.5b
make test-direct MODEL=llama3.2:3b
```

### 4. Executar o Teste Ponta a Ponta no n8n
1. Acesse o n8n no navegador: `http://homelab.local:5678` (ou `http://localhost:5678`).
2. Crie sua conta inicial (primeiro acesso) e importe o fluxo:
   - Menu lateral: **Workflows** → **Import from File...**
   - Selecione: `n8n_workflows/local_ai_acao_orcamentaria.json`.
3. Ative o workflow (**Active: On**).
4. Execute o benchmark via Webhook:
```bash
make test-n8n
```

---

## 📊 Métricas Acadêmicas Apuradas

A suite de testes apura rigorosamente os índices formulados no documento de planejamento acadêmico (`docs/main.tex`):

1. **Time-To-First-Token (TTFT)**: Tempo decorrido até a geração do primeiro token (fase de *Prefill* do prompt).
2. **Throughput ($T_{\text{gen}}$)**: Taxa de geração autorregressiva em tokens por segundo (limitada pela largura de banda da RAM DDR3).
3. **Acurácia de Radicais ($Acc_{\text{rad}}$)**: Precisão na geração de radicais de 4 e 5 caracteres para os filtros de busca SQL (`pg_trgm`).
4. **Resistência a Alucinação ($H_{\text{rate}}$)**: Validação de que queries fora de escopo são rejeitadas educadamente, sem inventar tabelas fiscais inexistentes.

Os resultados são gravados automaticamente em:
- [benchmark/benchmark_report.md](file:///Users/marcosvinicius/Library/CloudStorage/GoogleDrive-beregula.marcos@gmail.com/My%20Drive/02_Estudos/02_Faculdade/11_AEX/Inidicada/projeto_SLM/bateria_testes/benchmark/benchmark_report.md) — Tabela formatada pronta para compilação no LaTeX.
- [benchmark/benchmark_report.json](file:///Users/marcosvinicius/Library/CloudStorage/GoogleDrive-beregula.marcos@gmail.com/My%20Drive/02_Estudos/02_Faculdade/11_AEX/Inidicada/projeto_SLM/bateria_testes/benchmark/benchmark_report.json) — Dados quantitativos brutos.

---

## 🔍 Observabilidade em Tempo Real no Home Lab

Enquanto os benchmarks estiverem rodando, você pode observar o impacto no hardware em tempo real:
- **Grafana**: `http://homelab.local:3000` (Dashboards de CPU, RAM e I/O de disco)
- **cAdvisor**: `http://homelab.local:8080/docker/` (Métricas isoladas por contêiner)
- **Terminal**:
  ```bash
  make status
  ```
  *Exibe o status do Docker Compose e a tabela `docker stats` em tempo real.*

---

## 🛠️ Comandos Úteis do Makefile

| Comando | Descrição |
| :--- | :--- |
| `make up` | Sobe todos os contêineres em background |
| `make down` | Interrompe contêineres e libera memória do host |
| `make restart` | Reinicia a stack |
| `make status` | Exibe status e consumo de RAM/CPU dos contêineres |
| `make pull-models` | Baixa as SLMs recomendadas |
| `make test-dry-run`| Valida a suite de testes offline sem depender de contêiner ativo |
| `make test-direct` | Executa o benchmark direto contra a API do Ollama |
| `make test-n8n` | Executa o teste ponta a ponta contra o Webhook do n8n |
| `make logs` | Visualiza logs unificados dos serviços |
| `make psql` | Conecta no terminal SQL do PostgreSQL |
| `make db-seed` | Recarrega a massa de dados do `sql/init.sql` |
