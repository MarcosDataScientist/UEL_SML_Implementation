# 🏛️ Baseline Workflow: Local AI Budget Action (`legacy/`)

## 📋 Overview
- **Workflow File:** [`local_ai_budget_action.json`](local_ai_budget_action.json)
- **Domain:** Public Budget Actions (`acaoorcamentaria`) of the State of Paraná.
- **Role:** Served as the initial baseline during Phase 1 candidate model screening.

## 🏗️ Topology & Processing Flow
```
[Webhook / Chat Input]
         │
         ▼
[Ollama Model Node]  ─── (Extracts termo1, termo2, radical1, radical2)
         │
         ▼
[PostgreSQL Node]    ─── (SELECT via similarity(nomeacao, radical) > 0.05)
         │
         ▼
[Respond to Webhook] ─── (Formats table output to user)
```

## ⚠️ Known Limitations Resolved by the Proposed Architecture
1. **Stateless Single-Turn:** Does not track user conversation history across consecutive turns.
2. **Context Window Vulnerability:** Truncation at `LIMIT 10` hides valid categories when applied to dense catalogs like `naturezadespesa` (1,560 rows).
3. **No Disambiguation:** Cannot cluster broad queries (e.g., `"serviço"` returning 225 rows).

