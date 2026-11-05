# 💡 Proposed Architecture: Session Mini-Memory & K-Medoids (`proposed/`)

## 📋 Overview
- **Workflow File:** [`local_ai_expense_nature_memory_kmedoids.json`](local_ai_expense_nature_memory_kmedoids.json)
- **Extracted Code Nodes:**
  - [`n8n_session_memory_router.js`](n8n_session_memory_router.js): Pre-SLM router & cluster expansion handler.
  - [`n8n_kmedoids_node.js`](n8n_kmedoids_node.js): In-memory $K$-Medoids (PAM, $k=4$) partitioner and memory saver.
- **Domain:** Expense Natures (`naturezadespesa`, 1,560 rows / ~72,300 tokens).

---

## 🏗️ Execution Topology

```
[User Webhook Input]
        │
        ▼
[Session Mini-Memory Router] ─── (Checks PostgreSQL slm_session_memory via session_id)
        │
   ┌────┴───────────────────────────┐
   │                                │
[route_to_slm = false]    [route_to_slm = true]
   │                                │
   │ (Greetings / Choice '2')       ▼
   │                          [Ollama Engine (Qwen 2.5 1.5B)]
   │                                │ (Extracts radicals)
   │                                ▼
   │                          [PostgreSQL pg_trgm Search (LIMIT 60)]
   │                                │
   │                                ▼
   │                          [K-Medoids Node (k=4)]
   │                                │ (N <= 8: Direct List)
   │                                │ (N >  8: 4 Representative Medoid Options)
   │                                ▼
   │                          [Save slm_session_memory]
   │                                │
   └────────────────┬───────────────┘
                    │
                    ▼
         [Respond to Webhook]
```

---

## 🧩 Modular Code Node Details

### 1. `n8n_session_memory_router.js` (Pre-SLM)
- **Role:** Evaluates whether incoming message requires SLM execution.
- **Bypasses SLM When:**
  - Message is a greeting (`"oi"`, `"bom dia"`) $\rightarrow$ returns instant onboarding message (**~160 ms**, 0 tokens).
  - Message is a cluster choice (`"1"`, `"opção 2"`) $\rightarrow$ expands cached items directly from database (**~176 ms**, 0 tokens).
  - Message is a reset command (`"reiniciar"`) $\rightarrow$ purges session memory.
- **Auto-Reset:** Resets after 3 consecutive refinement turns to prevent context drift.

### 2. `n8n_kmedoids_node.js` (Post-Database)
- **Role:** Partitions the Top-60 PostgreSQL candidates into $k = 4$ clusters using Partitioning Around Medoids (PAM).
- **Zero Hallucination ($H_{\text{rate}} = 0$):** Each medoid is an actual database row with an official SEFA-PR code and description.
- **Efficiency:** Pure JavaScript in-memory execution takes **$< 15$ ms** on CPU without external npm dependencies.
- **Token Reduction:** Reduces raw 60-row prompt payload (~4,100 tokens) down to ~200 tokens (**95.2% reduction**).

