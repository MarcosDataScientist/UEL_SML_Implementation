# Documentação e Planejamento Acadêmico: Projeto SLM para Automação Orçamentária Pública

Este diretório reúne a documentação acadêmica formal, especificações teóricas e empíricas de engenharia de IA, referências bibliográficas padronizadas em BibTeX e artefatos visuais do projeto de avaliação, benchmark e fine-tuning de Small Language Models (SLMs) integrados à plataforma n8n, desenvolvido no âmbito do **Laboratório de Pesquisa em Gestão Pública (LABGEP / NIGEP)** da **Universidade Estadual de Londrina (UEL)**.

---

## 📁 Estrutura do Diretório

```
docs/
├── diagramas/
│   ├── fig.drawio                      # Diagrama editável do documento (Draw.io / diagrams.net)
│   └── arquitetura_slm_n8n_orcamento.drawio  # Diagrama completo em 5 raias (visão sistêmica)
├── latex/                              # Todo o ecossistema LaTeX (ignorado via .gitignore)
│   ├── fig/                            # Figuras e vetores (fig.pdf, uel_horizontal.jpg)
│   ├── main.tex                        # Código-fonte LaTeX acadêmico expandido (natbib / apalike)
│   ├── references.bib                  # Banco de referências bibliográficas (BibTeX)
│   └── ...                             # Arquivos auxiliares e intermediários (.aux, .log, .bbl, etc.)
├── main.pdf                            # Documento oficial compilado (8 páginas)
└── README.md                           # Este guia explicativo
```

---

## 📄 Conteúdo Detalhado do Documento (`main.pdf`)

O documento foi expandido para **8 páginas** com rigor científico e pedagógico, estruturado para servir de base tanto para os relatórios do laboratório de extensão quanto como guia prático de execução para a equipe:

1. **Contexto, Motivação e Desafio Tecnológico:**
   * Arcabouço orçamentário do Estado do Paraná (Lei Federal nº 4.320/1964, Resolução SEFA 01/2026 e MTO/PR).
   * Restrições críticas: soberania/sigilo fiscal local, inferência estritamente em **CPU comum (sem GPU)** e tolerância zero a alucinações ($H_{\text{rate}} = 0$).
2. **Fundamentação Teórica e de Engenharia de IA:**
   * **Small Language Models (SLMs) e Leis de Escala:** Leis de escala *Chinchilla* (Hoffmann et al., 2022) e densidade de dados sintéticos de alta qualidade.
   * **Mecânica da Quantização e Inferência em CPU:** Quantização em blocos (*k-quants* no formato GGUF), distinção entre a fase de decodificação autoregressiva (*Memory Bandwidth Bound*) e a fase de prefill (*Compute Bound*, acelerada por AVX-512 / ARM NEON).
   * **Fundamentos Matemáticos de LoRA e QLoRA:** Decomposição matricial de baixo posto ($W = W_0 + \frac{\alpha}{r} B \cdot A$), quantização 4-bit NormalFloat (NF4), quantização dupla (DQ) e fusão posterior dos adaptadores (*weight merging*) para exportação em GGUF.
   * **Arquitetura Geral Integrada:** Diagrama de blocos em TikZ detalhando o fluxo ponta a ponta (Usuário $\rightarrow$ n8n $\rightarrow$ SLM em CPU $\rightarrow$ PostgreSQL com `pg_trgm`).
3. **Metodologia Experimental e Roteiro de Execução:**
   * **Etapa 1 (Pesquisa Sistemática de Candidatos):** Matriz comparativa de 10 modelos (Classe A Ultraleves 1B a 3B e Classe B Intermediários 3.8B a 8B: Qwen 2.5, Llama 3.2, SmolLM2, Phi-3.5/Phi-4-mini, Gemma 2).
   * **Etapa 2 (Framework de Benchmarks em CPU):** Fórmulas matemáticas de Throughput ($T_{\text{gen}}$ em tokens/s), Time-To-First-Token (TTFT), Peak RSS RAM, acurácia de intenção, precisão na extração de radicais SQL, validade de JSON e taxa de alucinação orçamentária ($H_{\text{rate}}$).
   * **Etapa 3 (Curadoria de Dados e Fine-Tuning QLoRA):** Preparação do corpus do MTO-PR (1.500 pares de instrução-resposta) e hiperparâmetros de treinamento ($r=16$, $\alpha=32$, taxa de aprendizado $\eta = 2 \times 10^{-4}$).
   * **Etapa 4 (Integração Local no n8n):** Configuração do servidor HTTP local (`llama.cpp server` / `Ollama`) compatível com a API da OpenAI.
4. **Cronograma Quinzenal e Atribuições:** Detalhamento dos Ciclos 1 a 5 de setembro a dezembro de 2026.
5. **Referências Bibliográficas:** 20 referências formatadas em estilo APA com citações cruzadas ativas (`natbib` / `apalike`).

---

## 📐 Diagramas Draw.io (`docs/diagramas/`)

1. **`fig.drawio` (Diagrama Oficial da Figura 1 do Documento):**

   * Estrutura visual em 3 colunas limpas: **Servidor Público (Usuário)** $\rightarrow$ **Camada de Orquestração n8n** $\rightarrow$ **SLM Local em CPU e PostgreSQL**.
   * **Como ajustar e exportar:**
     - Abra o arquivo `docs/diagramas/fig.drawio` no aplicativo desktop do Draw.io, na extensão do VS Code (*Draw.io Integration*) ou em [app.diagrams.net](https://app.diagrams.net).
     - Faça os ajustes estéticos desejados.
     - Exporte como **PDF** (ou PNG) diretamente para `docs/latex/fig/fig.pdf` (ou `fig.png`).
     - Como o `main.tex` utiliza `\includegraphics[width=\textwidth]{fig/fig}`, o LaTeX atualizará a figura automaticamente na próxima compilação.
2. **`arquitetura_slm_n8n_orcamento.drawio` (Visão Sistêmica Detalhada em 5 Raias):**

   * 1. **Usuários e Canais:** Interfaces Web e requisições dos servidores públicos.
   * 2. **Orquestração n8n:** Triggers, memória de contexto (`Window Buffer Memory`), agentes especialistas (`natureza despesa`, `acao orcamentaria`, `fonte`, `anexos DAD`), guardrails e o nó `Postgres Tool`.
   * 3. **Camada de Inferência Local em CPU:** O servidor local (API OpenAI-compatible), otimizações de CPU (AVX-512/NEON), quantização GGUF (Q4/Q5) e divisão dos dois perfis de modelos.
   * 4. **Camada de Dados:** PostgreSQL com índices trigrama (`pg_trgm`) e tabelas fiscais.
   * 5. **Pipeline de Engenharia de IA:** Ciclo de vida metodológico (Triagem $\rightarrow$ Benchmarking $\rightarrow$ Curadoria MTO $\rightarrow$ QLoRA Fine-Tuning $\rightarrow$ Deploy).
