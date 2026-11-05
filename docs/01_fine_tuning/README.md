# 🎯 01 — Fine-Tuning Specification (`Qwen 2.5 1.5B`)

Direct summary of the model screening and QLoRA fine-tuning pipeline. Executable training files are located in [`../../notebooks/fine_tuning/`](../../notebooks/fine_tuning/).

---

## 1. Zero-Shot CPU Screening (Intel Xeon E5-2640 v2, 8 GB DDR3)

All candidate models were evaluated in **GGUF `Q4_K_M`** format running 100% on CPU:

| Model | Params | Throughput | Mean TTFT | Mean Latency | RAM Usage | Zero-Shot Accuracy | Key Bottleneck |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Llama 3.2 1B** | 1B | 10.5 t/s | 1,250 ms | 12.3 s | ~1.3 GB | 21.4% | Phonetic hallucinations (*"uele"*), invalid JSON refusals |
| **Llama 3.2 3B** | 3B | 6.5 t/s | 3,369 ms | 13.2 s | ~2.8 GB | 33.3% | 51% throughput drop (DDR3 memory bandwidth limit) |
| **Qwen 2.5 3B** | 3B | 6.6 t/s | 3,239 ms | 11.0 s | ~2.7 GB | 33.3% | Slow token generation on CPU |
| **Qwen 2.5 1.5B** ⭐ | **1.5B** | **13.3 t/s** | **1,558 ms** | **5.5 s** | **~1.6 GB** | **33.3%** | **Selected base model:** fastest throughput and lowest latency |

> **Why Zero-Shot capped at 33.3%:** Pre-trained Portuguese models strongly favor accented words (*"saúde"*, *"pública"*) and struggle with long negative system prompts (>300 tokens) instructing them to strip accents and extract 5-letter SQL stems.

---

## 2. QLoRA Fine-Tuning Setup

- **Dataset (`dataset_budget_qwen_1500.jsonl`):** 1,500 ChatML examples split into:
  - **600 Operational NLU pairs:** Extracts singular, unaccented keywords and 4–5 char stems in strict JSON (`{"tipo": "busca", "termo1": ..., "radical1": ...}`).
  - **600 Normative MTO-PR pairs:** Answers conceptual budget rules directly without triggering SQL searches.
  - **300 Out-of-Scope Refusals ($H_{\text{rate}} = 0$):** Politely declines non-budgetary questions.
- **Hyperparameters (Unsloth on Colab T4):**
  - Base: `unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit`
  - LoRA: $r = 16$, $\alpha = 32$, dropout $= 0$, target modules: all attention + MLP projections
  - Training: 3 epochs, batch size $= 16$, learning rate $= 2 \times 10^{-4}$ (`paged_adamw_8bit`)
  - Export: Merged directly to `Q4_K_M` GGUF (`qwen2.5-budget:1.5b`)

---

## 3. Post-Training Results on Home Lab CPU

| Metric | Zero-Shot Baseline | Fine-Tuned (`qwen2.5-budget:1.5b`) |
| :--- | :---: | :---: |
| **Throughput** | 13.3 t/s | **12.8 – 13.0 t/s** |
| **TTFT Latency** | 1,558 ms | **380 – 750 ms** (compact system prompt) |
| **RAM Usage** | ~1.6 GB | **~1.8 GB** |
| **SQL Stem & JSON Accuracy** | 33.3% | **100% on evaluated test cases** |
| **Out-of-Scope Refusal ($H_{\text{rate}} = 0$)** | 16.7% | **100%** |

📄 For the full compiled PDF document, see [`fine_tuning_spec.pdf`](fine_tuning_spec.pdf).

