#!/usr/bin/env python3
# ==============================================================================
# Suite de Benchmarks Acadêmicos para SLMs em CPU (Xeon E5-2640 v2 / 8 GB RAM)
# Projeto: UEL / LABGEP - Automação Orçamentária Pública com n8n e SLMs
# ==============================================================================

import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

SYSTEM_PROMPT = """Você é o assistente oficial do Ministério da Fazenda do Paraná, especialista em Ações Orçamentárias.
Quando o usuário enviar saudação ("oi", "olá", "bom dia", etc.), responda EXATAMENTE:
"Qual a Ação Orçamentária? Digite o código, nome ou palavra-chave para localizar:"

Se o usuário fornecer código, nome ou palavra-chave, extraia os parâmetros estruturados:
termo1: palavra principal sem acento no singular (ou código numérico)
termo2: segunda palavra relevante
termo3: terceira palavra ou radical
radical1: primeiros 4 ou 5 caracteres de termo1
radical2: primeiros 4 ou 5 caracteres de termo2

Responda sempre em formato JSON válido contendo as chaves:
{"tipo": "saudacao" | "busca", "termo1": "...", "termo2": "...", "termo3": "...", "radical1": "...", "radical2": "..."}
"""

def load_test_cases(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_ollama_inference(ollama_url, model, user_input, system_prompt, timeout=120):
    endpoint = f"{ollama_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ],
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 256
        }
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"})
    
    start_time = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed_time = time.perf_counter() - start_time
            result = json.loads(resp.read().decode("utf-8"))
            
            content = result.get("message", {}).get("content", "")
            eval_count = result.get("eval_count", 0)
            eval_duration_ns = result.get("eval_duration", 0)
            prompt_eval_count = result.get("prompt_eval_count", 0)
            prompt_eval_duration_ns = result.get("prompt_eval_duration", 0)
            
            # Cálculo de métricas
            tokens_per_sec = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns > 0 else 0.0
            ttft_ms = (prompt_eval_duration_ns / 1e6) if prompt_eval_duration_ns > 0 else (elapsed_time * 1000)
            
            return {
                "success": True,
                "content": content,
                "total_time_s": elapsed_time,
                "ttft_ms": round(ttft_ms, 2),
                "tokens_per_sec": round(tokens_per_sec, 2),
                "eval_tokens": eval_count,
                "prompt_tokens": prompt_eval_count,
                "raw": result
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "total_time_s": time.perf_counter() - start_time,
            "ttft_ms": 0.0,
            "tokens_per_sec": 0.0,
            "eval_tokens": 0,
            "prompt_tokens": 0,
            "content": ""
        }

def run_n8n_inference(n8n_url, webhook_path, user_input, timeout=120):
    endpoint = f"{n8n_url.rstrip('/')}/webhook/{webhook_path.lstrip('/')}"
    payload = {
        "message": user_input,
        "sessionId": "benchmark-session-" + str(int(time.time()))
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"})
    
    start_time = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed_time = time.perf_counter() - start_time
            response_text = resp.read().decode("utf-8")
            return {
                "success": True,
                "content": response_text,
                "total_time_s": elapsed_time,
                "ttft_ms": round(elapsed_time * 1000, 2),
                "tokens_per_sec": 0.0,
                "eval_tokens": len(response_text.split()),
                "prompt_tokens": len(user_input.split())
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "total_time_s": time.perf_counter() - start_time,
            "ttft_ms": 0.0,
            "tokens_per_sec": 0.0,
            "eval_tokens": 0,
            "prompt_tokens": 0,
            "content": ""
        }

def mock_inference(model, tc):
    """Simulação de inferência para verificação sintática e testes offline."""
    time.sleep(0.05)
    tc_id = tc["id"]
    if tc_id == "TC01_SAUDACAO":
        content = "Qual a Ação Orçamentária? Digite o código, nome ou palavra-chave para localizar:"
    elif tc_id == "TC02_BUSCA_CODIGO_8000":
        content = '{"tipo": "busca", "termo1": "8000", "termo2": "8000", "termo3": "8000", "radical1": "8000", "radical2": "8000"}'
    elif tc_id == "TC03_BUSCA_COMPOSTA_UEL":
        content = '{"tipo": "busca", "termo1": "encargo", "termo2": "especial", "termo3": "uel", "radical1": "encar", "radical2": "espec"}'
    elif tc_id == "TC04_BUSCA_SAUDE_PUBLICA":
        content = '{"tipo": "busca", "termo1": "saude", "termo2": "publica", "termo3": "saude", "radical1": "saud", "radical2": "publ"}'
    elif tc_id == "TC05_REFORMA_TELHADO":
        content = '{"tipo": "busca", "termo1": "reforma", "termo2": "telhado", "termo3": "reforma", "radical1": "refor", "radical2": "telha"}'
    else:
        content = "Por favor, informe a Ação Orçamentária desejada (ex: 8000, UEL, Saúde). Não tenho informações sobre outros temas."
        
    return {
        "success": True,
        "content": content,
        "total_time_s": 0.42,
        "ttft_ms": 150.0,
        "tokens_per_sec": 24.5,
        "eval_tokens": 35,
        "prompt_tokens": 120
    }

def evaluate_response(tc, response_text):
    score = {
        "passed": False,
        "json_valid": False,
        "details": []
    }
    
    # 1. Checagem de saudação
    if tc.get("category") == "instruction_following":
        matched = [kw for kw in tc.get("expected_keywords", []) if kw.lower() in response_text.lower()]
        if len(matched) >= 2:
            score["passed"] = True
            score["details"].append(f"Atendeu ao protocolo de saudação ({len(matched)} palavras-chave)")
        else:
            score["details"].append("Não atendeu ao padrão de boas-vindas oficial")
        return score

    # 2. Checagem de fora de domínio / alucinação
    if tc.get("category") == "hallucination_resistance":
        triggers = tc.get("hallucination_triggers", [])
        hallucinated = [trig for trig in triggers if trig.lower() in response_text.lower()]
        if hallucinated:
            score["passed"] = False
            score["details"].append(f"Alucinação detectada para termos: {hallucinated}")
        else:
            score["passed"] = True
            score["details"].append("Rejeitou com sucesso query fora de domínio (zero alucinação)")
        return score

    # 3. Checagem de extração de termos e formato JSON
    json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
    parsed_json = None
    if json_match:
        try:
            parsed_json = json.loads(json_match.group(0))
            score["json_valid"] = True
        except Exception:
            score["json_valid"] = False

    expected_entities = tc.get("expected_entities", {})
    correct_entities = 0
    total_expected = len(expected_entities)
    
    if parsed_json:
        for k, v in expected_entities.items():
            got = str(parsed_json.get(k, "")).strip().lower()
            if got == v.lower():
                correct_entities += 1
            else:
                score["details"].append(f"Chave '{k}': esperado '{v}', obtido '{got}'")
    else:
        # Fallback de busca textual caso o modelo tenha respondido em texto livre
        for k, v in expected_entities.items():
            if v.lower() in response_text.lower():
                correct_entities += 1

    if total_expected > 0:
        accuracy = correct_entities / total_expected
        if accuracy >= 0.7:
            score["passed"] = True
            score["details"].append(f"Extração satisfatória ({correct_entities}/{total_expected} termos corretos)")
        else:
            score["details"].append(f"Baixa acurácia de termos ({correct_entities}/{total_expected})")
    else:
        score["passed"] = True

    return score

def main():
    parser = argparse.ArgumentParser(description="Suite de Benchmarks para SLMs no Home Lab")
    parser.add_argument("--model", default="llama3.2:1b", help="Nome do modelo Ollama (ex: llama3.2:1b, qwen2.5:1.5b)")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="URL base da API do Ollama")
    parser.add_argument("--n8n-url", default="", help="URL do n8n (caso deseje testar via webhook em vez do Ollama direto)")
    parser.add_argument("--n8n-webhook", default="acao-orcamentaria", help="Path do webhook no n8n")
    parser.add_argument("--test-file", default=os.path.join(os.path.dirname(__file__), "test_cases.json"), help="Caminho do test_cases.json")
    parser.add_argument("--output-md", default=os.path.join(os.path.dirname(__file__), "benchmark_report.md"), help="Caminho para salvar relatório Markdown")
    parser.add_argument("--output-json", default=os.path.join(os.path.dirname(__file__), "benchmark_report.json"), help="Caminho para salvar dados brutos em JSON")
    parser.add_argument("--dry-run", action="store_true", help="Executar modo de teste offline sem requisições reais")
    args = parser.parse_args()

    print("======================================================================")
    print(" 📊 INICIANDO BATERIA DE TESTES DE SLM")
    print(f" Modelo em Teste: {args.model}")
    print(f" Alvo: {'n8n Webhook (' + args.n8n_url + ')' if args.n8n_url else 'Ollama Direto (' + args.ollama_url + ')'}")
    print(f" Modo Dry-Run: {'Ativado (Mock)' if args.dry_run else 'Desativado (Execução Real)'}")
    print("======================================================================\n")

    test_cases = load_test_cases(args.test_file)
    results = []

    for idx, tc in enumerate(test_cases, start=1):
        print(f"[{idx}/{len(test_cases)}] Executando: {tc['name']} ({tc['id']})...")
        print(f"    Entrada: \"{tc['user_input']}\"")
        
        if args.dry_run:
            res = mock_inference(args.model, tc)
        elif args.n8n_url:
            res = run_n8n_inference(args.n8n_url, args.n8n_webhook, tc["user_input"])
        else:
            res = run_ollama_inference(args.ollama_url, args.model, tc["user_input"], SYSTEM_PROMPT)

        eval_res = evaluate_response(tc, res["content"])
        
        status_icon = "✅ PASS" if eval_res["passed"] else "❌ FAIL"
        print(f"    Resultado: {status_icon} | Latência: {res['total_time_s']:.2f}s | TTFT: {res['ttft_ms']}ms | Gen: {res['tokens_per_sec']} t/s")
        if eval_res["details"]:
            print(f"    Obs: {'; '.join(eval_res['details'])}")
        print("")

        results.append({
            "test_case": tc,
            "inference": res,
            "evaluation": eval_res
        })

    # Compilação de estatísticas
    passed_count = sum(1 for r in results if r["evaluation"]["passed"])
    pass_rate = (passed_count / len(results)) * 100 if results else 0
    avg_ttft = sum(r["inference"]["ttft_ms"] for r in results) / len(results) if results else 0
    avg_tgen = sum(r["inference"]["tokens_per_sec"] for r in results if r["inference"]["tokens_per_sec"] > 0)
    valid_tgen_count = sum(1 for r in results if r["inference"]["tokens_per_sec"] > 0)
    avg_tgen = (avg_tgen / valid_tgen_count) if valid_tgen_count > 0 else 0
    avg_total_latency = sum(r["inference"]["total_time_s"] for r in results) / len(results) if results else 0

    print("======================================================================")
    print(" 📈 RESUMO CONSOLIDADO DO BENCHMARK")
    print("======================================================================")
    print(f" Modelo Avaliado:           {args.model}")
    print(f" Taxa de Aprovação:         {passed_count}/{len(results)} ({pass_rate:.1f}%)")
    print(f" TTFT Médio:                {avg_ttft:.1f} ms")
    print(f" Throughput Médio (Tgen):   {avg_tgen:.2f} tokens/s")
    print(f" Latência Total Média:      {avg_total_latency:.2f} s")
    print("======================================================================\n")

    # Gerar Relatório Markdown
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md_content = f"""# 📑 Relatório de Benchmark de SLM em CPU
**Data da Execução:** {timestamp}  
**Hardware Alvo:** Intel Xeon E5-2640 v2 @ 2.00 GHz (CPU Only, 8 GB DDR3)  
**Modelo Avaliado:** `{args.model}`  
**Plataforma de Inferência:** {'n8n Webhook' if args.n8n_url else 'Ollama 0.x (llama.cpp engine)'}

---

## 📊 Métricas Consolidadas

| Métrica | Valor Obtido | Descrição |
| :--- | :--- | :--- |
| **Taxa de Sucesso (Pass Rate)** | **{pass_rate:.1f}%** ({passed_count}/{len(results)}) | Conformidade com intenções e regras fiscais |
| **Time-To-First-Token (TTFT)** | **{avg_ttft:.1f} ms** | Tempo de processamento do prompt (Prefill) |
| **Throughput ($T_{{\\text{{gen}}}}$)** | **{avg_tgen:.2f} tokens/s** | Velocidade de geração autorregressiva |
| **Latência Média ($L_{{\\text{{tot}}}}$)** | **{avg_total_latency:.2f} s** | Tempo total de resposta ponta a ponta |

---

## 🔬 Detalhamento por Caso de Teste

| ID | Caso de Teste | Categoria | Status | Latência | TTFT | Throughput | Notas de Avaliação |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |
"""
    for r in results:
        tc = r["test_case"]
        inf = r["inference"]
        ev = r["evaluation"]
        status = "✅ Aprovado" if ev["passed"] else "❌ Reprovado"
        notes = "<br>".join(ev["details"]) if ev["details"] else "Conforme esperado"
        md_content += f"| `{tc['id']}` | {tc['name']} | {tc['category']} | {status} | {inf['total_time_s']:.2f}s | {inf['ttft_ms']:.1f}ms | {inf['tokens_per_sec']:.1f} t/s | {notes} |\n"

    md_content += "\n---\n*Gerado automaticamente pela Suite de Benchmarks UEL/LABGEP.*\n"

    with open(args.output_md, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"📄 Relatório Markdown salvo em: {args.output_md}")

    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp,
            "model": args.model,
            "summary": {
                "passed": passed_count,
                "total": len(results),
                "pass_rate_pct": pass_rate,
                "avg_ttft_ms": avg_ttft,
                "avg_tokens_per_sec": avg_tgen,
                "avg_total_latency_s": avg_total_latency
            },
            "results": results
        }, f, indent=2, ensure_ascii=False)
    print(f"💾 Dados JSON salvos em: {args.output_json}")

if __name__ == "__main__":
    main()
