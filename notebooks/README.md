# 📓 Notebooks: Embeddings (`pgvector`), `K-Medoids` & QLoRA Fine-Tuning

This directory centralizes all interactive Jupyter notebooks for the **Public Budget SLM Automation (SEFA-PR / UEL)** project, covering both **semantic retrieval / clustering** and **QLoRA model fine-tuning**.

---

## 📂 Directory Structure

```text
notebooks/
├── embeddings_kmedoids_silhouette_exploration.ipynb # Local exploration of pgvector & K-Medoids (PAM)
├── environment.yml                                  # Conda environment for local exploration
├── fine_tuning/                                     # 🎯 QLoRA Fine-Tuning (Google Colab T4 GPU)
│   ├── train_qwen_colab.ipynb                       # QLoRA training & GGUF Q4_K_M export notebook
│   ├── dataset_budget_qwen_1500.jsonl               # 1,500 ChatML instruction pairs
│   ├── Modelfile                                    # Ollama configuration (qwen2.5-budget:1.5b)
│   └── README.md                                    # Quickstart guide for Colab & Ollama
└── README.md                                        # This document
```

---

## 🛠️ Local Conda Environment Setup

To run [`embeddings_kmedoids_silhouette_exploration.ipynb`](embeddings_kmedoids_silhouette_exploration.ipynb) locally:

```bash
conda env create -f notebooks/environment.yml
conda activate uel-slm-notebooks
python -m ipykernel install --user --name uel-slm-notebooks --display-name "Python (uel-slm-notebooks)"
```

---

## 📑 Available Notebooks

### 1. [`embeddings_kmedoids_silhouette_exploration.ipynb`](embeddings_kmedoids_silhouette_exploration.ipynb)
- **Section 1 — Dataset Audit & Text Cleaning:** Schema inspection (`1,560` rows, `1,223` unique budget codes), legal boilerplate removal (`"Registra o valor..."`), and token footprint analysis (`~72k` tokens total).
- **Section 2 — Embedding Generation & Cosine Search (`pgvector`):** L2-normalized vectorization ($\|v\|_2 = 1$) matching PostgreSQL's `1 - (embedding <=> q_vec)` operator.
- **Section 3 — Top-60 Retrieval vs. Raw Top-10 Redundancy:** Empirical comparison demonstrating how raw `LIMIT 10` queries suffer from prefix concentration compared to `LIMIT 60`.
- **Section 4 — `K-Medoids` (PAM), Elbow Curve & Silhouette Score ($k = 2 \dots 15$):** Evaluation over the Cosine distance matrix $D_{ij} = 1 - \cos(v_i, v_j)$, identifying $k = 4$ (conversational disambiguation) and $k = 10\text{–}12$ (diverse direct listing).
- **Section 5 — 2D PCA Projection & Elected Medoids:** Visual comparison between `K-Medoids` clusters with real medoid centers (`*`) and official budget element prefixes.
- **Section 6 — Conclusion:** Summary of the architectural parameters adopted in the n8n + PostgreSQL production workflow ($H_{\text{rate}} = 0$).

### 2. [`fine_tuning/train_qwen_colab.ipynb`](fine_tuning/train_qwen_colab.ipynb)
- Supervised QLoRA fine-tuning of **Qwen 2.5 1.5B Instruct** on 1,500 budgetary instruction pairs (`dataset_budget_qwen_1500.jsonl`) and direct GGUF (`Q4_K_M`) export for CPU execution in Ollama. See [`fine_tuning/README.md`](fine_tuning/README.md) for instructions.
