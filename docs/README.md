# 📄 Academic Documentation & Theoretical Framework: Public Budget SLM Automation

This directory gathers the formal academic documentation, theoretical and empirical AI engineering specifications, standardized BibTeX references, and visual architecture artifacts developed at the **Public Management Research Laboratory (LABGEP / NIGEP)**, **State University of Londrina (UEL)**.

---

## 📁 Directory Layout

```
docs/
├── assets/                             # Visual assets, repository hero banners, and diagrams
├── diagrams/                           # Editable Draw.io diagrams (.drawio)
│   ├── system_architecture.drawio      # Official 3-column system architecture diagram
│   └── slm_n8n_budget_architecture.drawio # Detailed 5-swimlane systemic architecture
├── latex/                              # Full LaTeX compilation ecosystem
│   ├── fig/                            # Figures and vector assets (standalone_fig.tex, uel_horizontal.jpg)
│   ├── main.tex                        # Academic paper source code (natbib / apalike)
│   ├── references.bib                  # Standardized BibTeX bibliographical library (20 references)
│   └── ...                             # Intermediate compilation cache (.aux, .log, .bbl)
├── main.pdf                            # Compiled official scientific paper (8 pages)
└── README.md                           # This guide
```

---

## 📄 Scientific Paper Summary (`main.pdf`)

The academic document spans **8 pages** structured with scientific and pedagogical rigor, serving both as an institutional research report and an implementation handbook:

1. **Context, Motivation, and Technological Challenges:**
   - Public budget framework of Paraná (Federal Law 4,320/1964, SEFA Resolution 01/2026, and MTO/PR).
   - Critical operational constraints: on-premise fiscal data confidentiality, strict **CPU inference (zero GPU)**, and zero tolerance for hallucinations ($H_{\text{rate}} = 0$).
2. **Theoretical Foundations & AI Engineering:**
   - **Small Language Models (SLMs) & Scaling Laws:** *Chinchilla* scaling laws (Hoffmann et al., 2022) and high-quality synthetic data density.
   - **Quantization & CPU Inference Mechanics:** Block-level quantization (*k-quants* in GGUF format), contrasting memory-bandwidth-bound autoregressive decoding with compute-bound prompt prefill (accelerated by AVX SIMD instructions).
   - **Mathematical Principles of LoRA and QLoRA:** Low-rank matrix decomposition ($W = W_0 + \frac{\alpha}{r} B \cdot A$), 4-bit NormalFloat (NF4), double quantization (DQ), and post-training weight merging for GGUF export.
   - **End-to-End Integrated Architecture:** Vectorized block diagram detailing dataflow (User $\rightarrow$ n8n $\rightarrow$ CPU SLM $\rightarrow$ PostgreSQL with `pg_trgm`).
3. **Experimental Methodology & Roadmap:**
   - **Phase 1 (Systematic Candidate Screening):** 10-model evaluation matrix (Class A Ultralight 1B–3B and Class B Intermediate 3.8B–8B: Qwen 2.5, Llama 3.2, SmolLM2, Phi-3.5/Phi-4-mini, Gemma 2).
   - **Phase 2 (CPU Benchmark Framework):** Quantitative metrics: Throughput ($T_{\text{gen}}$ in tokens/s), Time-To-First-Token (TTFT), Peak RSS RAM, intent classification accuracy, SQL radical precision, JSON validity, and hallucination rate ($H_{\text{rate}}$).
   - **Phase 3 (Data Curation & QLoRA Fine-Tuning):** Corpus preparation from MTO-PR (1,500 instruction-response pairs) and fine-tuning hyperparameters ($r=16$, $\alpha=32$, $\eta = 2 \times 10^{-4}$).
   - **Phase 4 (Local n8n Integration):** Local OpenAI-compatible HTTP server (`llama.cpp server` / `Ollama`).
4. **Bi-Weekly Schedule & Responsibilities:** Implementation cycles across September–December 2026.
5. **Bibliography:** 20 peer-reviewed references formatted in APA style (`natbib` / `apalike`).

---

## 📐 Draw.io Diagrams (`docs/diagrams/`)

1. **`system_architecture.drawio` (Official Paper Architecture):**
   - Clean 3-column topology: **Public Servant (User)** $\rightarrow$ **n8n Orchestration Layer** $\rightarrow$ **Local CPU SLM & PostgreSQL**.
   - Can be edited in VS Code (*Draw.io Integration*) or via [app.diagrams.net](https://app.diagrams.net).
   - Export directly to **SVG** (`docs/assets/system_architecture.svg`) or **PDF** (`docs/latex/fig/fig.pdf`).
2. **`slm_n8n_budget_architecture.drawio` (Detailed 5-Swimlane View):**
   - 1. User & Access Channels (Web portals and chat clients).
   - 2. n8n Orchestration (Triggers, Memory buffers, Specialist Agents, Postgres Tool).
   - 3. Local CPU Inference Engine (Ollama / OpenAI API, AVX acceleration, GGUF models).
   - 4. Data Layer (PostgreSQL with `pg_trgm` and `unaccent`).
   - 5. AI Engineering Lifecycle (Screening $\rightarrow$ Benchmarking $\rightarrow$ Fine-Tuning $\rightarrow$ Deploy).

---

## 🛠️ How to Recompile the Academic Paper

To recompile `main.pdf` with updated citations and cross-references:
```bash
cd docs/latex/
pdflatex -interaction=nonstopmode main.tex
bibtex main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```
