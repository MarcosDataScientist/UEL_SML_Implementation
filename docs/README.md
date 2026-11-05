# 📄 Project Documentation (`docs/`)

Concise technical documentation and visual diagrams for the **Public Budget SLM Automation (SEFA-PR / UEL)** project.

---

## 📁 Directory Structure

```text
docs/
├── 01_fine_tuning/                         # 🎯 Model selection & QLoRA fine-tuning
│   ├── README.md                           # Summary of CPU benchmarks & Qwen 2.5 1.5B training
│   └── fine_tuning_spec.pdf                # Compiled PDF report
├── 02_spec/                                # ⚙️ System & workflow specifications
│   ├── 01_system_architecture.md           # 3-layer stack (n8n, Ollama CPU, PostgreSQL) & hardware limits
│   ├── 02_kmedoids_and_session_memory.md   # Embeddings, K-Medoids clustering & multi-user session memory
│   └── main.pdf                            # Compiled academic paper (8 pages)
├── 03_diagrams/                            # 📐 Architecture & workflow diagrams
│   ├── README.md                           # Guide to opening and editing the diagrams
│   ├── diagrama.excalidraw                 # Complete 5-block Excalidraw board (Embeddings, K-Medoids & n8n flow)
│   ├── system_architecture.drawio          # 3-column Draw.io topology
│   └── slm_n8n_budget_architecture.drawio  # 5-swimlane Draw.io workflow diagram
└── assets/                                 # 🖼️ Static images & SVGs used by repository READMEs
```
