# 📐 03 — Architecture & Workflow Diagrams

All editable vector diagrams for the project are centralized in this folder:

| File | Format | Contents |
| :--- | :---: | :--- |
| [**`diagrama.excalidraw`**](diagrama.excalidraw) | Excalidraw | **Complete 5-Block Visual Board:**<br>1. Context Explosion Problem vs. `K-Medoids`<br>2. Conversational Chat Flow (`k=4` options)<br>3. Detailed Sequence Diagram<br>4. How Embeddings (`paraphrase-multilingual-MiniLM-L12-v2`, 384d) & `K-Medoids` (Elbow/Silhouette) were built<br>5. Complete n8n Workflow Structure (`Session Mini-Memory` + `Ollama` + `PostgreSQL`) |
| [**`system_architecture.drawio`**](system_architecture.drawio) | Draw.io | High-level 3-column system architecture used in the academic paper (`User` $\rightarrow$ `n8n` $\rightarrow$ `CPU SLM & PostgreSQL`). |
| [**`slm_n8n_budget_architecture.drawio`**](slm_n8n_budget_architecture.drawio) | Draw.io | Detailed 5-swimlane systemic architecture diagram. |

### How to Open
- **`.excalidraw`**: Open directly in VS Code / Cursor with the *Excalidraw* extension or drag into [excalidraw.com](https://excalidraw.com).
- **`.drawio`**: Open in VS Code with the *Draw.io Integration* extension or at [app.diagrams.net](https://app.diagrams.net).

