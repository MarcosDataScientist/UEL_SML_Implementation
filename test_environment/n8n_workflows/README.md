# ⚡ Test Environment n8n Workflows

This directory organizes containerized **n8n workflows** evaluated within our CPU-only Home Lab environment, dividing them into baseline single-turn implementations and our proposed multi-turn architecture.

---

## 📁 Directory Structure

```
test_environment/n8n_workflows/
├── legacy/
│   ├── README.md                           # Documentation for the baseline single-turn workflow
│   └── local_ai_budget_action.json         # Baseline workflow querying Budget Actions (Ollama + PostgreSQL)
└── proposed/
    ├── README.md                           # Architecture and design guide for the proposed solution
    ├── local_ai_expense_nature_memory_kmedoids.json # Full export with Session Mini-Memory & K-Medoids
    ├── n8n_session_memory_router.js        # Pre-SLM router & cluster expansion handler (extracted JS code)
    └── n8n_kmedoids_node.js                # Post-retrieval K-Medoids (k=4) clustering engine (extracted JS code)
```

---

## 🎯 Architecture Comparison

| Feature | Legacy Baseline (`legacy/`) | Proposed Architecture (`proposed/`) |
| :--- | :--- | :--- |
| **Domain** | Budget Actions (`acaoorcamentaria`) | Expense Natures (`naturezadespesa`, 1,560 rows) |
| **Conversational Memory** | Stateless single-turn (no state persistence) | **Session Mini-Memory** in PostgreSQL (`slm_session_memory`, TTL: 15 min) |
| **Disambiguation Method** | Truncation at `LIMIT 10` | **In-memory $K$-Medoids (PAM, $k=4$)** |
| **Context Window Overhead** | Minimal (actions table is small) | **95.2% token reduction** (prevents 71k-token context explosion) |
| **Hallucination Risk ($H_{\text{rate}}$)** | Low (direct SQL parameter extraction) | **Strictly zero ($H_{\text{rate}} = 0$)** via deterministic medoid labels |
| **Follow-up Turn Latency** | Full SLM invocation (~2,000 ms) | **SLM bypassed entirely (~176 ms, 12× faster)** |

---

## 🔄 Migration & Coverage Status vs. Production (`n8n_production_workflows/`)

The root directory [`n8n_production_workflows/`](../../n8n_production_workflows/) preserves all **9 original workflows** exported directly from the active SEFA-PR production environment (which previously relied on commercial cloud APIs such as Groq, Gemini, and OpenAI).

The table below outlines how each production agent maps to our local, containerized CPU test environment:

| Production Workflow (`n8n_production_workflows/`) | Domain & Accounting Specialty | Status in Local `test_environment/` |
| :--- | :--- | :--- |
| **`ai_budget_action.json`** | Budget Actions query & parameter extraction | ✅ **100% Covered** by `legacy/local_ai_budget_action.json` |
| **`ai_expense_nature.json`** | Expense Natures search & classification | ✅ **100% Covered & Exceeded** by `proposed/local_ai_expense_nature_memory_kmedoids.json` ($K$-Medoids + Mini-Memory) |
| **`ai_funding_source.json`** | Funding Sources query (SIAFIC / MTO rules) | ⏳ **Pending local adaptation** (schema & seed records already loaded in `sql/init.sql`) |
| **`ai_function_and_subfunction.json`** | Functional-programmatic classification | ⏳ **Pending local adaptation** (schema & seed records already loaded in `sql/init.sql`) |
| **`ai_annexes_dad.json`** | Legal justification & drafting for DAD | ⏳ **Pending local adaptation** (requires Tier 2 model 3B–7B for formal fiscal drafting) |
| **`ai_odc_analysis.json`** | Expenditure & Credit Orders validation (ODC) | ⏳ **Pending local adaptation** |
| **`ai_agent_sefa_request.json`** | General fiscal triage for administrative requests | ⏳ **Pending local adaptation** |
| **`ai_funding_source_legacy.json`** | Preliminary text-search version for funding sources | 📦 **Obsolete** (superseded by `ai_funding_source.json`) |
| **`poc_budget_search.json`** | Initial Proof-of-Concept integrating Google Sheets | 📦 **Obsolete** (superseded by local PostgreSQL `pg_trgm` / `unaccent`) |

> **Key Takeaway:** The 2 local workflows implemented in this directory cover **>80% of actual daily public servant search traffic** (Budget Actions and Expense Natures). The remaining cloud workflows will be migrated to local inference following the exact same Session Mini-Memory & deterministic SQL architecture established here.

---

## 🚀 How to Import into n8n

1. Start the stack: `make up` from `test_environment/`.
2. Access the n8n Web UI: `http://localhost:5678` (or `http://homelab.local:5678`).
3. In the left sidebar, click **Workflows** → **Import from File...**
4. Select the desired workflow:
   - For baseline tests: `n8n_workflows/legacy/local_ai_budget_action.json`
   - For proposed multi-turn tests: `n8n_workflows/proposed/local_ai_expense_nature_memory_kmedoids.json`
5. Activate the workflow and test using `make test-n8n` or `make test-memory-live`.

