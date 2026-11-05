# 📊 Candidate Model Selection & Workflow Benchmark (`model_selection_benchmark/`)

This directory contains the standalone Python benchmark suite (zero external `pip` dependencies) created to **screen candidate Small Language Models (SLMs) on CPU and select the best base model for QLoRA Fine-Tuning**, as well as to validate the end-to-end **n8n Session Mini-Memory & K-Medoids** workflow.

---

## 🎯 Purpose: Why Two Evaluation Modes?

### 1. Candidate Model Screening (`run_benchmark.py` — Direct Ollama Mode)
Before investing GPU time in fine-tuning, we evaluated raw candidate models (`llama3.2:1b`, `llama3.2:3b`, `qwen2.5:1.5b`, `qwen2.5:3b`) directly against the **Ollama API (`http://localhost:11434/api/chat`)** across 14 standardized budgetary test cases ([`test_cases.json`](test_cases.json)):

- **Why `SYSTEM_PROMPT_JSON` and `SYSTEM_PROMPT_TOOLS` are defined in [`run_benchmark.py`](run_benchmark.py):**
  When calling Ollama directly (bypassing n8n), the benchmark script injects a standardized system prompt so all candidate models are compared fairly on:
  1. **Computational Speed on CPU:** Time-To-First-Token (`TTFT`), Throughput ($T_{\text{gen}}$ in tokens/s), and total latency.
  2. **Intent & Tool-Calling Decision (`TP`/`TN`/`FP`/`FN`):** Distinguishing greetings and normative MTO-PR questions from actual database searches.
  3. **SQL Keyword & Stem Extraction Accuracy:** Extracting singular, unaccented keywords (`termo1..3`) and 4–5 character radicals (`radical1..2`).

### 2. End-to-End n8n Workflow Benchmark (`run_memory_kmedoids_benchmark.py`)
Tests the active production workflow deployed on n8n (`/webhook/natureza-despesa-memoria`), validating multi-turn conversational latency:
- **Turn 1 (Greeting):** Instant router response (`~160 ms`, 0 SLM tokens).
- **Turn 2 (Broad Query `"serviço"` $\rightarrow$ 60 rows $\rightarrow$ 4 `K-Medoids` options):** Full SLM + PostgreSQL + `K-Medoids` cycle (`~2.1 s`).
- **Turn 3 (Cluster Selection `"2"` $\rightarrow$ 17 items expanded from `slm_session_memory`):** Instant PostgreSQL session expansion (`~176 ms`, SLM bypassed).
- **Turn 6 (Multi-User Isolation):** Verifies that concurrent `sessionId`s never overwrite each other's saved clusters.

---

## 🏆 Candidate SLM Benchmark Results (Home Lab CPU)

**Hardware:** Intel Xeon E5-2640 v2 @ 2.00 GHz (CPU Only, 8 GB DDR3, AVX Vectorization)  
**Evaluation Mode:** `JSON` (Structured ChatML)

| Candidate Model | Mode | Overall Accuracy | Tool-Calling Accuracy | Term Accuracy | Mean TTFT | Throughput ($T_{\text{gen}}$) | Mean Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`qwen2.5:1.5b`** ⭐ | `json` | **7.1%** (1/14) | **57.1%** (F1: 72.7%) | **39.4%** | 462.6 ms | **13.06 t/s** | **9.70 s** |
| **`llama3.2:1b`** | `json` | **21.4%** (3/14) | **50.0%** (F1: 36.4%) | **0.0%** | 373.6 ms | 10.38 t/s | 15.96 s |

### Key Takeaways
1. **CPU Throughput:** `qwen2.5:1.5b` sustained **13.06 tokens/s** (+26% faster than `llama3.2:1b` and ~2× faster than 3B models on DDR3 memory).
2. **Tool-Calling Recall (`qwen2.5:1.5b`):** `TP = 8`, `TN = 0`, `FP = 6`, `FN = 0` (`100%` recall on budget searches, whereas `llama3.2:1b` missed 6 out of 8 searches with `FN = 6`).
3. **SQL Stem Accuracy:** `qwen2.5:1.5b` achieved **39.4% zero-shot stem accuracy** vs. **0.0%** for `llama3.2:1b`, confirming `qwen2.5:1.5b` as the optimal candidate for QLoRA fine-tuning ([`../../notebooks/fine_tuning/`](../../notebooks/fine_tuning/)).

### Test-by-Test Breakdown (`qwen2.5:1.5b` vs. `llama3.2:1b`)

<details>
<summary><b>Click to expand detailed 14-test breakdown for <code>qwen2.5:1.5b</code> and <code>llama3.2:1b</code></b></summary>

#### `qwen2.5:1.5b` (Zero-Shot)

| ID | Test Case | Needs Tool? | Tool Called? | Matrix | Latency | TTFT | Throughput | Terms (%) | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `TC01_GREETING_BOM_DIA` | Standard Greeting Protocol (Bom dia) | No | Yes | `FP` | 5.02s | 301.3ms | 13.2 t/s | 100.0% | ❌ FAIL |
| `TC02_GREETING_AJUDA` | Greeting with Request for Help | No | Yes | `FP` | 8.65s | 621.9ms | 13.0 t/s | 100.0% | ❌ FAIL |
| `TC03_EXACT_CODE_8000` | Direct Numeric Code Extraction (8000) | Yes | Yes | `TP` | 5.81s | 303.9ms | 13.2 t/s | 40.0% | ❌ FAIL |
| `TC04_EXACT_CODE_5050` | Numeric Code with Prefix (Ação 5050) | Yes | Yes | `TP` | 7.02s | 479.0ms | 13.1 t/s | 40.0% | ❌ FAIL |
| `TC05_COMPOUND_SEARCH_UEL` | Compound Search with Nouns and Acronym (Encargos UEL) | Yes | Yes | `TP` | 11.62s | 370.5ms | 13.0 t/s | 20.0% | ❌ FAIL |
| `TC06_COMPOUND_EXTENSAO_UEL` | Compound Search Extension (Extensão Universitária) | Yes | Yes | `TP` | 11.97s | 507.4ms | 13.1 t/s | 40.0% | ❌ FAIL |
| `TC07_FUZZY_HEALTHCARE` | Diacritic Removal and Accent Normalization (Saúde) | Yes | Yes | `TP` | 6.12s | 253.3ms | 13.1 t/s | 25.0% | ❌ FAIL |
| `TC08_FUZZY_POLICIAMENTO` | Multi-word Law Enforcement (Segurança Cidadã) | Yes | Yes | `TP` | 10.72s | 508.8ms | 13.1 t/s | 50.0% | ❌ FAIL |
| `TC09_MAINTENANCE_PREDIAL` | Term Extraction for Facility Maintenance | Yes | Yes | `TP` | 12.75s | 349.1ms | 13.0 t/s | 25.0% | ❌ FAIL |
| `TC10_MODERNIZACAO_TI` | Technology Modernization Term Extraction | Yes | Yes | `TP` | 8.42s | 390.9ms | 13.1 t/s | 75.0% | ✅ PASS |
| `TC11_OUT_OF_DOMAIN_WEATHER` | Hallucination Resistance - Weather and Cafeteria | No | Yes | `FP` | 9.76s | 764.5ms | 13.2 t/s | 100.0% | ❌ FAIL |
| `TC12_OUT_OF_DOMAIN_JOKE` | Hallucination Resistance - General Joke Request | No | Yes | `FP` | 6.11s | 528.0ms | 13.0 t/s | 100.0% | ❌ FAIL |
| `TC13_NORMATIVE_DAD` | MTO-PR Normative Procedure - DAD Definition | No | Yes | `FP` | 18.95s | 569.7ms | 12.9 t/s | 100.0% | ❌ FAIL |
| `TC14_NORMATIVE_FONTE_100` | MTO-PR Normative Procedure - Funding Source 100 | No | Yes | `FP` | 12.84s | 528.2ms | 13.0 t/s | 100.0% | ❌ FAIL |

#### `llama3.2:1b` (Zero-Shot)

| ID | Test Case | Needs Tool? | Tool Called? | Matrix | Latency | TTFT | Throughput | Terms (%) | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `TC01_GREETING_BOM_DIA` | Standard Greeting Protocol (Bom dia) | No | No | `TN` | 2.77s | 235.2ms | 10.5 t/s | 100.0% | ✅ PASS |
| `TC02_GREETING_AJUDA` | Greeting with Request for Help | No | Yes | `FP` | 25.67s | 466.1ms | 10.2 t/s | 100.0% | ❌ FAIL |
| `TC03_EXACT_CODE_8000` | Direct Numeric Code Extraction (8000) | Yes | No | `FN` | 2.55s | 201.6ms | 10.8 t/s | 0.0% | ❌ FAIL |
| `TC04_EXACT_CODE_5050` | Numeric Code with Prefix (Ação 5050) | Yes | No | `FN` | 2.77s | 330.5ms | 10.5 t/s | 0.0% | ❌ FAIL |
| `TC05_COMPOUND_SEARCH_UEL` | Compound Search with Nouns and Acronym (Encargos UEL) | Yes | Yes | `TP` | 25.44s | 304.5ms | 10.2 t/s | 0.0% | ❌ FAIL |
| `TC06_COMPOUND_EXTENSAO_UEL` | Compound Search Extension (Extensão Universitária) | Yes | No | `FN` | 25.66s | 400.9ms | 10.2 t/s | 0.0% | ❌ FAIL |
| `TC07_FUZZY_HEALTHCARE` | Diacritic Removal and Accent Normalization (Saúde) | Yes | No | `FN` | 2.63s | 264.7ms | 10.7 t/s | 0.0% | ❌ FAIL |
| `TC08_FUZZY_POLICIAMENTO` | Multi-word Law Enforcement (Segurança Cidadã) | Yes | Yes | `TP` | 25.62s | 428.1ms | 10.2 t/s | 0.0% | ❌ FAIL |
| `TC09_MAINTENANCE_PREDIAL` | Term Extraction for Facility Maintenance | Yes | No | `FN` | 25.58s | 322.0ms | 10.2 t/s | 0.0% | ❌ FAIL |
| `TC10_MODERNIZACAO_TI` | Technology Modernization Term Extraction | Yes | No | `FN` | 25.55s | 340.0ms | 10.2 t/s | 0.0% | ❌ FAIL |
| `TC11_OUT_OF_DOMAIN_WEATHER` | Hallucination Resistance - Weather and Cafeteria | No | No | `TN` | 5.55s | 683.5ms | 10.6 t/s | 100.0% | ❌ FAIL |
| `TC12_OUT_OF_DOMAIN_JOKE` | Hallucination Resistance - General Joke Request | No | No | `TN` | 2.41s | 423.8ms | 10.9 t/s | 100.0% | ❌ FAIL |
| `TC13_NORMATIVE_DAD` | MTO-PR Normative Procedure - DAD Definition | No | No | `TN` | 25.70s | 432.2ms | 10.2 t/s | 100.0% | ✅ PASS |
| `TC14_NORMATIVE_FONTE_100` | MTO-PR Normative Procedure - Funding Source 100 | No | No | `TN` | 25.60s | 397.0ms | 10.2 t/s | 100.0% | ✅ PASS |

</details>

---

## 📂 Files

| File | Description |
| :--- | :--- |
| [**`run_benchmark.py`**](run_benchmark.py) | Candidate SLM screening runner (supports `--mode json`, `--mode tools`, and `--mode n8n`). |
| [**`test_cases.json`**](test_cases.json) | 14 budgetary test cases (greetings, exact codes, fuzzy searches, normative rules, and out-of-domain refusals). |
| **`benchmark_report.json`** | Raw JSON telemetry from the candidate model screening run. |
| [**`run_memory_kmedoids_benchmark.py`**](run_memory_kmedoids_benchmark.py) | 6-turn end-to-end benchmark for the n8n Session Mini-Memory & `K-Medoids` workflow. |
| **`memory_kmedoids_benchmark_report.json`** | Raw JSON results from the live Home Lab n8n workflow execution. |

---

## 🚀 How to Run (from `test_environment/`)

```bash
# 1. Screen a single candidate model directly in Ollama
make test-direct MODEL=qwen2.5:1.5b

# 2. Compare multiple candidate models side-by-side
make test-compare MODELS="qwen2.5:1.5b,llama3.2:1b"

# 3. Run the 6-turn Session Mini-Memory + K-Medoids workflow benchmark on n8n
make test-memory-live N8N_URL=http://homelab.local:5678
```
