# 🎯 Fine-Tuning: Qwen 2.5 1.5B Instruct

Training and export files for the **Qwen 2.5 1.5B Instruct** model via **QLoRA (Unsloth)** for CPU inference in **Ollama**.  
👉 For the benchmark tables and training specification, see [`../../docs/01_fine_tuning/README.md`](../../docs/01_fine_tuning/README.md).

---

## 📂 Files

| File | Description |
| :--- | :--- |
| [**`train_qwen_colab.ipynb`**](train_qwen_colab.ipynb) | ⭐ **Colab Notebook:** Trains the QLoRA adapter on a free T4 GPU, merges weights, and exports to `Q4_K_M` GGUF. |
| **`dataset_budget_qwen_1500.jsonl`** | 📊 **Training Dataset:** 1,500 ChatML instruction pairs (600 NLU/SQL stems, 600 MTO-PR rules, 300 strict refusals). |
| [**`Modelfile`**](Modelfile) | ⚙️ **Ollama Config:** ChatML template, CPU thread settings (`num_thread 8`, `temperature 0.0`), and system prompt. |

---

## 🚀 Quickstart

### 1. Train in Google Colab
1. Upload [`train_qwen_colab.ipynb`](train_qwen_colab.ipynb) to [Google Colab](https://colab.research.google.com/) and select **T4 GPU**.
2. Upload `dataset_budget_qwen_1500.jsonl` to the Colab Files sidebar.
3. Click **Runtime $\rightarrow$ Run all** (~10–12 minutes) to generate `unsloth.Q4_K_M.gguf` (~1.6 GB).

### 2. Register & Run in Ollama
Place `unsloth.Q4_K_M.gguf` and [`Modelfile`](Modelfile) in the same folder and run:

```bash
ollama create qwen2.5-budget:1.5b -f Modelfile
ollama run qwen2.5-budget:1.5b "Preciso comprar material de expediente para a universidade"
```
