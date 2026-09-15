# 🔄 n8n Workflows Exported from Active Production

This directory contains the production workflows and artificial intelligence agents **exported directly from the active n8n production instance** (SEFA-PR / NIGEP).

They represent the reference implementation used by public servants to automate budgetary queries and served as the functional specification for our migration to local **Small Language Models (SLMs)** running on CPU in [`testbench/`](../testbench/).

---

## 📋 Catalog of Exported Workflows

| File | Domain & Accounting Specialty | Original Cloud Model Providers |
| :--- | :--- | :--- |
| **`ai_budget_action.json`** | Query and ranking of Budget Actions by code, keywords, and search stems | Groq (`gpt-oss-120b`) / Gemini (`gemini-3.1-flash-lite`) |
| **`ai_odc_analysis.json`** | Analysis and validation of Expenditure and Credit Orders (ODC) | Groq (`llama3-70b`) |
| **`ai_annexes_dad.json`** | Extraction of legal justifications and drafting for Budget Adjustment Documents (DAD) | Gemini (`gemini-3.1-flash-lite`) |
| **`ai_funding_source.json`** | Advanced search for public funding sources with SIAFIC/MTO rules | Gemini (`gemini-3.1-flash-lite`) |
| **`ai_funding_source_legacy.json`** | Preliminary text-search version for public funding sources | Gemini (`gemini-3.1-flash-lite`) |
| **`ai_function_and_subfunction.json`** | Functional-programmatic classification (Education, Health, Administration) | Gemini (`gemini-3.1-flash-lite`) |
| **`ai_expense_nature.json`** | Identification of expense elements and sub-elements (materials, services) | Groq / Gemini |
| **`ai_agent_sefa_request.json`** | General fiscal triage assistant for administrative requests | DeepSeek Chat |
| **`poc_budget_search.json`** | Initial Proof-of-Concept integrating Google Sheets with OpenAI | OpenAI GPT |

---

## 🎯 From Commercial Cloud to Local Inference (SLM)

Originally, these production workflows relied on third-party commercial APIs (Groq, Gemini, OpenAI). To satisfy:
1. **Data Sovereignty & Fiscal Confidentiality** of state public records;
2. **Predictable Zero-Cost Operations** without recurring token billing;
3. **Strict CPU-Only Execution (Zero GPU)** on commodity on-premise hardware;

We created the adapted local workflows in [`testbench/n8n_workflows/`](../testbench/n8n_workflows/), where all external cloud nodes were replaced with local **Ollama** nodes running compact, quantized SLMs (`llama3.2:1b`, `llama3.2:3b`, `qwen2.5:1.5b`, etc.).
