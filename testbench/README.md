# 🧪 SLM Testbench: Local CPU Inference with n8n & PostgreSQL

Containerized and automated testbench environment designed for empirical evaluation, benchmarking, and end-to-end integration of **Small Language Models (SLMs)** running strictly on **CPU (zero GPU dependency)**, orchestrated by **n8n** and querying public budget databases in **PostgreSQL** via fuzzy matching (`pg_trgm` and `unaccent` extensions).

Developed for the applied AI university research project at the **Public Management Research Laboratory (LABGEP / NIGEP)**, **State University of Londrina (UEL)**.

---

## 🖥️ Hardware Alignment with the Home Lab Host

This environment is tailored to execute safely within the physical limits of our Home Lab server:

| Resource | Host Specification | Docker Allocation (Limits) | Role in Benchmark |
| :--- | :--- | :--- | :--- |
| **Processor** | Intel® Xeon® E5-2640 v2 (8C/16T @ 2.00 GHz) | Up to 6.0 Cores for Ollama | AVX-accelerated SIMD C++ inference (`llama.cpp`) |
| **Memory (RAM)** | 8 GB DDR3 (2 × 4 GB) + 8 GB NVMe Swap | Ollama: 4 GB \| n8n: 1 GB \| PG: 512 MB | Preserves ~2.5 GB headroom for OS, Portainer & cAdvisor |
| **Graphics** | NVIDIA GeForce 210 (Legacy Display Only) | *Disabled* (Pure CPU) | Replicates commodity government office hardware |
| **Network** | Docker bridge `lab-network` | Shared Home Lab network | Real-time metric scraping by cAdvisor and Prometheus |

---

## 🏗️ Testbench Topology

```
                               ┌────────────────────────────────────────────────────────┐
                               │             Home Lab Ubuntu Server                     │
                               │                                                        │
    ┌────────────────────┐     │   ┌───────────────────┐        ┌───────────────────┐   │
    │  Benchmark Runner  │────┼───┼─▶│   n8n Workflow    │───────▶│   PostgreSQL 16   │   │
    │  (run_benchmark)   │     │   │   Port: 5678          │        │   (pg_trgm/unacc) │   │
    │                    │     │   └─────────┬─────────┘        │   Port: 5432      │   │
    │  - Latency (TTFT)  │     │             │                  └───────────────────┘   │
    │  - Tokens/s (Tgen) │     │             ▼                                          │
    │  - SQL Radicals    │     │   ┌───────────────────┐                                │
    │  - Hallucination % │     │   │   Ollama Engine   │                                │
    └─────────┬──────────┘     │   │   Port: 11434     │                                │
              │                │   │   (Llama / Qwen)  │                                │
              └────────────────┼──▶└───────────────────┘                                │
                               │                                                        │
                               │   Active Observability:                                │
                               │   - cAdvisor (8080) & Prometheus (9090)                │
                               │   - Grafana (3000): Real-time CPU/RAM profiling        │
                               └────────────────────────────────────────────────────────┘
```

---

## 📁 Directory Structure

```
testbench/
├── docker-compose.yml              # Container orchestration for Ollama, n8n, and Postgres
├── .env.example                    # Environment variable template
├── .env                            # Active environment configuration
├── Makefile                        # Lifecycle automation targets (make up, make pull-models, etc.)
├── sql/
│   └── init.sql                    # Database schema, pg_trgm + unaccent extensions, and seed data
├── scripts/
│   └── setup_models.sh             # Script to pull and verify candidate SLM models in Ollama
├── benchmark/
│   ├── test_cases.json             # Budget domain test cases (protocol, queries, search stems)
│   ├── run_benchmark.py            # Python benchmark execution suite (standalone standard library)
│   ├── benchmark_report.md         # Generated Markdown evaluation report
│   └── benchmark_report.json       # Structured raw execution data
├── n8n_workflows/
│   └── local_ai_budget_action.json # Pre-configured workflow for local Ollama & Postgres
└── README.md                       # This documentation
```

---

## 🚀 Quickstart Guide

### 1. Launch Containers
```bash
cd testbench
make up
```
*Ensures `lab-network` exists and boots the three services with automated health checks.*

### 2. Pull Candidate SLM Models
```bash
make pull-models
```
Default models downloaded:
- `llama3.2:1b` (1.3 GB) — Ultralight, minimal latency
- `llama3.2:3b` (2.0 GB) — Optimal balance between reasoning depth and CPU throughput
- `qwen2.5:1.5b` (1.0 GB) — Excellent instruction-following and Portuguese vocabulary
- `qwen2.5:3b` (1.9 GB) — High precision in structured JSON parameter extraction

> To download a specific model only:
> ```bash
> ./scripts/setup_models.sh llama3.2:3b
> ```

### 3. Run Direct SLM Benchmarks
Evaluate the model directly via the Ollama API (recording TTFT, tokens per second, and radical extraction precision):
```bash
# Test default model (Llama 3.2 1B)
make test-direct

# Test specific models from the candidate matrix:
make test-direct MODEL=qwen2.5:1.5b
make test-direct MODEL=llama3.2:3b
```

### 4. Run End-to-End Test via n8n
1. Open n8n in your browser: `http://homelab.local:5678` (or `http://localhost:5678`).
2. Complete initial onboarding and import the workflow:
   - Sidebar: **Workflows** → **Import from File...**
   - Choose: `n8n_workflows/local_ai_budget_action.json`.
3. Activate the workflow (**Active: On**).
4. Run the benchmark via the Webhook endpoint:
```bash
make test-n8n
```

---

## 📊 Recorded Benchmark Metrics

The benchmark suite evaluates metrics defined in our academic research methodology:

1. **Time-To-First-Token (TTFT)**: Elapsed time until the generation of the first token (Prompt Prefill phase).
2. **Throughput ($T_{\text{gen}}$)**: Autoregressive token generation rate in tokens/second (memory bandwidth bound).
3. **Radical Extraction Precision ($Acc_{\text{rad}}$)**: Accuracy in generating 4- and 5-character search stems for SQL fuzzy matching (`pg_trgm`).
4. **Hallucination Resistance ($H_{\text{rate}}$)**: Verification that out-of-domain queries are politely declined without inventing non-existent budget actions.

Reports are saved automatically to:
- [benchmark/benchmark_report.md](benchmark/benchmark_report.md)
- [benchmark/benchmark_report.json](benchmark/benchmark_report.json)

---

## 🛠️ Makefile Command Reference

| Command | Action |
| :--- | :--- |
| `make up` | Starts all containers in the background |
| `make down` | Stops containers and releases host RAM |
| `make restart` | Restarts the entire stack |
| `make status` | Displays container health and live RAM/CPU usage |
| `make pull-models` | Downloads recommended SLMs into Ollama |
| `make test-dry-run`| Offline validation test run |
| `make test-direct` | Runs benchmarks directly against the Ollama API |
| `make test-n8n` | Runs end-to-end benchmarks through the n8n Webhook |
| `make logs` | Follows logs from all services |
| `make psql` | Launches an interactive PostgreSQL shell |
| `make db-seed` | Reloads the database schema and seed data from `sql/init.sql` |
