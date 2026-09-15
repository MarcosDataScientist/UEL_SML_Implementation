# 🔄 Fluxos n8n Exportados do Ambiente em Produção

Este diretório reúne os fluxos e agentes de inteligência artificial **exportados diretamente da instância n8n atualmente em execução no ambiente ativo/produção** (SEFA-PR / NIGEP).

Eles representam a implementação de referência utilizada pelos servidores públicos para automação de consultas orçamentárias e serviram como especificação funcional para a transição para inferência local com **Small Language Models (SLMs)** no diretório [`bateria_testes/`](../bateria_testes/).

---

## 📋 Catálogo de Workflows Exportados

| Arquivo de Workflow | Finalidade e Especialidade Fiscal | Provedores de IA Originais |
| :--- | :--- | :--- |
| **`AI Acao Orcamentaria.json`** | Consulta e ranqueamento de Ações Orçamentárias por código e radicais | Groq (`gpt-oss-120b`) / Gemini (`gemini-3.1-flash-lite`) |
| **`AI Analise ODC.json`** | Análise e validação de Ordens de Despesa e Crédito (ODC) | Groq (`llama3-70b`) |
| **`AI Anexos.json`** | Extração de justificativas e redação para documentos de adequação (DAD) | Gemini (`gemini-3.1-flash-lite`) |
| **`AI Fonte.json`** | Pesquisa avançada de fontes de recursos com regras SIAFIC/MTO | Gemini (`gemini-3.1-flash-lite`) |
| **`AI FonteAntigo.json`** | Versão preliminar da busca textual de fontes fiscais | Gemini (`gemini-3.1-flash-lite`) |
| **`AI Funcao e Subfuncao.json`** | Classificação funcional-programática (Educação, Saúde, etc.) | Gemini (`gemini-3.1-flash-lite`) |
| **`AI Natureza despesa.json`** | Localização de elementos e subelementos (material de consumo, serviços) | Groq / Gemini |
| **`Agente IA - Solicitação SEFA.json`** | Assistente geral de triagem de pedidos e solicitações fiscais | DeepSeek Chat |
| **`POC - Pesquisa Orçamentária.json`** | Prova de conceito inicial integrando Google Sheets e OpenAI | OpenAI GPT |

---

## 🎯 Da Nuvem para Inferência Local (SLM)

Originalmente, esses fluxos recorriam a APIs proprietárias na nuvem (Groq, Gemini, OpenAI). Para atender aos requisitos de:
1. **Soberania e Sigilo Fiscal** dos dados públicos do Estado;
2. **Independência de Custos por Token** de APIs comerciais;
3. **Execução Estrita em CPU (sem GPU)** em infraestrutura on-premise (como o [Home Lab](../../../Home_lab));

Desenvolvemos a versão adaptada dos fluxos em [`bateria_testes/n8n_workflows/`](../bateria_testes/n8n_workflows/), onde os nós de nuvem foram substituídos por nós locais do **Ollama** apontando para SLMs compactas (`llama3.2:1b`, `llama3.2:3b`, `qwen2.5:1.5b`, etc.).
