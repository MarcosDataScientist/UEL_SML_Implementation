# 📑 Relatório de Benchmark de SLM em CPU
**Data da Execução:** 2026-09-15 12:50:50  
**Hardware Alvo:** Intel Xeon E5-2640 v2 @ 2.00 GHz (CPU Only, 8 GB DDR3)  
**Modelo Avaliado:** `llama3.2:1b`  
**Plataforma de Inferência:** Ollama 0.x (llama.cpp engine)

---

## 📊 Métricas Consolidadas

| Métrica | Valor Obtido | Descrição |
| :--- | :--- | :--- |
| **Taxa de Sucesso (Pass Rate)** | **100.0%** (6/6) | Conformidade com intenções e regras fiscais |
| **Time-To-First-Token (TTFT)** | **150.0 ms** | Tempo de processamento do prompt (Prefill) |
| **Throughput ($T_{\text{gen}}$)** | **24.50 tokens/s** | Velocidade de geração autorregressiva |
| **Latência Média ($L_{\text{tot}}$)** | **0.42 s** | Tempo total de resposta ponta a ponta |

---

## 🔬 Detalhamento por Caso de Teste

| ID | Caso de Teste | Categoria | Status | Latência | TTFT | Throughput | Notas de Avaliação |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `TC01_SAUDACAO` | Protocolo de Saudação e Boas-Vindas | instruction_following | ✅ Aprovado | 0.42s | 150.0ms | 24.5 t/s | Atendeu ao protocolo de saudação (4 palavras-chave) |
| `TC02_BUSCA_CODIGO_8000` | Extração de Código Numérico Direto | entity_extraction | ✅ Aprovado | 0.42s | 150.0ms | 24.5 t/s | Extração satisfatória (3/3 termos corretos) |
| `TC03_BUSCA_COMPOSTA_UEL` | Busca Composta com Substantivos e Sigla | radical_and_stemming | ✅ Aprovado | 0.42s | 150.0ms | 24.5 t/s | Extração satisfatória (3/3 termos corretos) |
| `TC04_BUSCA_SAUDE_PUBLICA` | Remoção Diacrítica e Normalização de Acentos | fuzzy_normalization | ✅ Aprovado | 0.42s | 150.0ms | 24.5 t/s | Extração satisfatória (2/2 termos corretos) |
| `TC05_REFORMA_TELHADO` | Extração de Termos para Manutenção Predial | entity_extraction | ✅ Aprovado | 0.42s | 150.0ms | 24.5 t/s | Extração satisfatória (2/2 termos corretos) |
| `TC06_FORA_DE_DOMINIO` | Resistência a Alucinação e Out-Of-Domain | hallucination_resistance | ✅ Aprovado | 0.42s | 150.0ms | 24.5 t/s | Rejeitou com sucesso query fora de domínio (zero alucinação) |

---
*Gerado automaticamente pela Suite de Benchmarks UEL/LABGEP.*
