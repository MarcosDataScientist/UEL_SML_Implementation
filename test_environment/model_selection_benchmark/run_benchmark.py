#!/usr/bin/env python3
# ==============================================================================
# Academic Benchmark Suite for CPU-Bound SLMs (Intel Xeon E5-2640 v2 / 8 GB RAM)
# Project: UEL / LABGEP - Public Budget Automation with n8n and SLMs
# Evaluation of Three Pillars:
#   1. Computational Efficiency (TTFT, Throughput Tgen, Total Latency)
#   2. Tool Calling Decision (Prompt trigger accuracy: TP/TN/FP/FN)
#   3. Search Term Accuracy (Lexical normalization, stems, and SQL parameters)
# ==============================================================================

import argparse
import datetime
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request

SYSTEM_PROMPT_JSON = """Você é o assistente oficial do Ministério da Fazenda do Paraná, especialista em Ações Orçamentárias.

Se o usuário enviar saudação ("oi", "olá", "bom dia", etc.) ou pedir ajuda geral, responda EXATAMENTE:
"Qual a Ação Orçamentária? Digite o código, nome ou palavra-chave para localizar:"

Se o usuário fizer uma pergunta normativa sobre procedimentos (DAD, fontes de recursos, créditos), responda explicando o conceito formal do MTO-PR sem inventar dados fiscais.

Se o usuário enviar código numérico, nome ou palavra-chave de Ação Orçamentária, extraia os parâmetros estruturados:
termo1: palavra principal sem acento no singular (ou código numérico)
termo2: segunda palavra relevante (ou repita termo1)
termo3: terceira palavra ou sigla
radical1: primeiros 4 ou 5 caracteres de termo1
radical2: primeiros 4 ou 5 caracteres de termo2

Responda sempre em formato JSON válido contendo:
{"tipo": "saudacao" | "normativo" | "busca", "termo1": "...", "termo2": "...", "termo3": "...", "radical1": "...", "radical2": "...", "mensagem": "..."}
"""

SYSTEM_PROMPT_TOOLS = """Você é o assistente oficial do Ministério da Fazenda do Paraná, especialista em Ações Orçamentárias.
Quando o usuário solicitar informações, consultar códigos ou termos de Ações Orçamentárias, chame OBRIGATORIAMENTE a ferramenta 'search_budget_action'.
Se o usuário apenas saudar ou perguntar sobre procedimentos normativos gerais, responda diretamente em texto em português brasileiro sem acionar ferramentas."""

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_budget_action",
        "description": "Busca Ações Orçamentárias no banco de dados PostgreSQL do Estado do Paraná via pg_trgm e unaccent.",
        "parameters": {
            "type": "object",
            "properties": {
                "termo1": {
                    "type": "string",
                    "description": "Palavra principal da busca: substantivo no singular, sem acento, ou código numérico"
                },
                "termo2": {
                    "type": "string",
                    "description": "Segunda palavra relevante da busca ou repetição de termo1"
                },
                "termo3": {
                    "type": "string",
                    "description": "Terceira palavra, sigla institucional (ex: UEL, SEFA) ou código"
                },
                "radical1": {
                    "type": "string",
                    "description": "Radical de termo1 com 4 a 5 caracteres para busca parcial"
                },
                "radical2": {
                    "type": "string",
                    "description": "Radical de termo2 com 4 a 5 caracteres"
                }
            },
            "required": ["termo1", "termo2", "termo3", "radical1", "radical2"]
        }
    }
}

def remove_accents(input_str: str) -> str:
    nfkd = unicodedata.normalize('NFKD', str(input_str))
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower().strip()

def load_test_cases(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_ollama_inference(ollama_url, model, user_input, mode="tools", timeout=120):
    endpoint = f"{ollama_url.rstrip('/')}/api/chat"
    
    if mode == "tools":
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_TOOLS},
                {"role": "user", "content": user_input}
            ],
            "tools": [TOOL_SCHEMA],
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 256}
        }
    else:  # structured json
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_JSON},
                {"role": "user", "content": user_input}
            ],
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 256}
        }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"})
    
    start_time = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed_time = time.perf_counter() - start_time
            result = json.loads(resp.read().decode("utf-8"))
            
            message = result.get("message", {})
            content = message.get("content", "")
            tool_calls = message.get("tool_calls", [])
            
            eval_count = result.get("eval_count", 0)
            eval_duration_ns = result.get("eval_duration", 0)
            prompt_eval_count = result.get("prompt_eval_count", 0)
            prompt_eval_duration_ns = result.get("prompt_eval_duration", 0)
            
            tokens_per_sec = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns > 0 else 0.0
            ttft_ms = (prompt_eval_duration_ns / 1e6) if prompt_eval_duration_ns > 0 else (elapsed_time * 1000)
            
            return {
                "success": True,
                "content": content,
                "tool_calls": tool_calls,
                "total_time_s": elapsed_time,
                "ttft_ms": round(ttft_ms, 2),
                "tokens_per_sec": round(tokens_per_sec, 2),
                "eval_tokens": eval_count,
                "prompt_tokens": prompt_eval_count,
                "mode": mode,
                "raw": result
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "content": "",
            "tool_calls": [],
            "total_time_s": time.perf_counter() - start_time,
            "ttft_ms": 0.0,
            "tokens_per_sec": 0.0,
            "eval_tokens": 0,
            "prompt_tokens": 0,
            "mode": mode
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
                "tool_calls": [],
                "total_time_s": elapsed_time,
                "ttft_ms": round(elapsed_time * 1000, 2),
                "tokens_per_sec": 0.0,
                "eval_tokens": len(response_text.split()),
                "prompt_tokens": len(user_input.split()),
                "mode": "n8n"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "content": "",
            "tool_calls": [],
            "total_time_s": time.perf_counter() - start_time,
            "ttft_ms": 0.0,
            "tokens_per_sec": 0.0,
            "eval_tokens": 0,
            "prompt_tokens": 0,
            "mode": "n8n"
        }

def mock_inference(model, tc, mode="tools"):
    time.sleep(0.04)
    tc_id = tc["id"]
    requires_tool = tc.get("requires_tool_call", False)
    
    if mode == "tools":
        if requires_tool:
            args = {}
            for k, v in tc.get("expected_entities", {}).items():
                args[k] = v
            for k, v in tc.get("expected_radicals", {}).items():
                args[k] = v
            return {
                "success": True,
                "content": "",
                "tool_calls": [{"function": {"name": "search_budget_action", "arguments": args}}],
                "total_time_s": 0.45,
                "ttft_ms": 120.0,
                "tokens_per_sec": 26.5,
                "eval_tokens": 28,
                "prompt_tokens": 140,
                "mode": mode
            }
        else:
            return {
                "success": True,
                "content": "Qual a Ação Orçamentária? Digite o código, nome ou palavra-chave para localizar:",
                "tool_calls": [],
                "total_time_s": 0.35,
                "ttft_ms": 110.0,
                "tokens_per_sec": 25.0,
                "eval_tokens": 20,
                "prompt_tokens": 90,
                "mode": mode
            }
    else:  # json mode
        if requires_tool:
            resp_dict = {"tipo": "busca"}
            resp_dict.update(tc.get("expected_entities", {}))
            resp_dict.update(tc.get("expected_radicals", {}))
            content = json.dumps(resp_dict)
        else:
            content = json.dumps({"tipo": "saudacao", "mensagem": "Qual a Ação Orçamentária? Digite o código, nome ou palavra-chave para localizar:"})
        return {
            "success": True,
            "content": content,
            "tool_calls": [],
            "total_time_s": 0.40,
            "ttft_ms": 115.0,
            "tokens_per_sec": 24.0,
            "eval_tokens": 30,
            "prompt_tokens": 120,
            "mode": mode
        }

def evaluate_test_case(tc, inference_res):
    """
    Evaluates the model response across 3 fundamental pillars:
    1. Tool Calling Decision (triggered at the correct moment)
    2. Search Term Accuracy (parameters aligned with database rules)
    3. Conformity & Hallucination Resistance
    """
    requires_tool = tc.get("requires_tool_call", False)
    content = inference_res.get("content", "")
    tool_calls = inference_res.get("tool_calls", [])
    mode = inference_res.get("mode", "tools")
    
    # 1. Determine whether the model TRIGGERED search / tool
    called_tool = False
    extracted_params = {}

    if mode == "tools":
        if tool_calls:
            called_tool = True
            for call in tool_calls:
                fn = call.get("function", {})
                if fn.get("name") == "search_budget_action":
                    raw_args = fn.get("arguments", {})
                    if isinstance(raw_args, str):
                        try:
                            extracted_params = json.loads(raw_args)
                        except Exception:
                            extracted_params = {}
                    elif isinstance(raw_args, dict):
                        extracted_params = raw_args
    elif mode == "json":
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                if parsed.get("tipo") == "busca" or any(k in parsed for k in ["termo1", "radical1"]):
                    called_tool = True
                    extracted_params = parsed
            except Exception:
                called_tool = False
    elif mode == "n8n":
        # In n8n, if response contains table or SQL results, tool was executed
        if any(marker in content.lower() for marker in ["encontrei as seguintes", "| código |", "ações orçamentárias para"]):
            called_tool = True
        elif "qual a ação orçamentária" in content.lower() or "não tenho permissão" in content.lower():
            called_tool = False

    # 2. Evaluation of Tool Calling Decision (Confusion Matrix: TP, TN, FP, FN)
    tool_decision_correct = (called_tool == requires_tool)
    if requires_tool and called_tool:
        classification = "TP"  # True Positive: Search required and triggered
    elif not requires_tool and not called_tool:
        classification = "TN"  # True Negative: Greeting/normative handled without unnecessary query
    elif not requires_tool and called_tool:
        classification = "FP"  # False Positive: Unnecessary search triggered
    else:
        classification = "FN"  # False Negative: Search required, but model failed to call tool

    # 3. Evaluation of Search Term Accuracy (if search was called)
    expected_entities = tc.get("expected_entities", {})
    expected_radicals = tc.get("expected_radicals", {})
    all_expected = {**expected_entities, **expected_radicals}
    
    correct_terms_count = 0
    total_expected_terms = len(all_expected)
    term_details = []

    if requires_tool:
        if called_tool:
            for k, expected_v in all_expected.items():
                actual_v = extracted_params.get(k, "")
                exp_norm = remove_accents(str(expected_v))
                act_norm = remove_accents(str(actual_v))
                
                # Supports exact match or containment for stems/radicals
                if k.startswith("radical"):
                    if exp_norm and act_norm and (act_norm.startswith(exp_norm[:4]) or exp_norm.startswith(act_norm[:4])):
                        correct_terms_count += 1
                    else:
                        term_details.append(f"{k}: expected '{expected_v}', got '{actual_v}'")
                else:
                    if exp_norm == act_norm:
                        correct_terms_count += 1
                    else:
                        term_details.append(f"{k}: expected '{expected_v}', got '{actual_v}'")
        else:
            term_details.append("Search tool was NOT triggered by model.")
    
    term_accuracy = (correct_terms_count / total_expected_terms) if total_expected_terms > 0 else 1.0

    # 4. Anti-Hallucination Evaluation (H_rate) and Instruction Following
    hallucination_detected = False
    hallucination_details = []
    
    if tc.get("category") == "hallucination_resistance":
        triggers = tc.get("hallucination_triggers", [])
        for trig in triggers:
            if trig.lower() in content.lower():
                hallucination_detected = True
                hallucination_details.append(f"Hallucinated about '{trig}'")
    
    instruction_followed = True
    if tc.get("category") == "instruction_following":
        matched_kw = [kw for kw in tc.get("expected_keywords", []) if kw.lower() in content.lower()]
        if len(matched_kw) < 2:
            instruction_followed = False

    # 5. Overall Test Case Status
    overall_passed = False
    if requires_tool:
        overall_passed = called_tool and (term_accuracy >= 0.70)
    else:
        overall_passed = (not called_tool) and (not hallucination_detected) and instruction_followed

    return {
        "passed": overall_passed,
        "tool_decision": {
            "correct": tool_decision_correct,
            "requires_tool": requires_tool,
            "called_tool": called_tool,
            "classification": classification
        },
        "term_extraction": {
            "accuracy": round(term_accuracy * 100, 1),
            "correct_count": correct_terms_count,
            "total_count": total_expected_terms,
            "extracted_params": extracted_params,
            "details": term_details
        },
        "hallucination": {
            "detected": hallucination_detected,
            "details": hallucination_details
        }
    }

def run_benchmark_for_model(model_name, test_cases, args):
    print(f"\n======================================================================")
    print(f" 🤖 STARTING EVALUATION FOR MODEL: {model_name}")
    print(f" Inference Mode: {args.mode.upper()}")
    print(f" Target: {'n8n Webhook (' + args.n8n_url + ')' if args.mode == 'n8n' else 'Ollama (' + args.ollama_url + ')'}")
    print(f"======================================================================\n")

    results = []
    # Warmup model in host RAM
    if not args.dry_run and args.mode != "n8n":
        print(f"🔥 Warming up model '{model_name}' in RAM...")
        _ = run_ollama_inference(args.ollama_url, model_name, "Olá", mode=args.mode, timeout=60)
        print("✅ Model loaded!\n")

    for idx, tc in enumerate(test_cases, start=1):
        print(f"[{idx:02d}/{len(test_cases):02d}] Test: {tc['name']} ({tc['id']})")
        print(f"    Input: \"{tc['user_input']}\" | Requires Tool: {tc.get('requires_tool_call')}")

        if args.dry_run:
            inf = mock_inference(model_name, tc, mode=args.mode)
        elif args.mode == "n8n":
            inf = run_n8n_inference(args.n8n_url, args.n8n_webhook, tc["user_input"])
        else:
            inf = run_ollama_inference(args.ollama_url, model_name, tc["user_input"], mode=args.mode)

        ev = evaluate_test_case(tc, inf)

        status_icon = "✅ PASS" if ev["passed"] else "❌ FAIL"
        tool_icon = "🛠️ TOOL-OK" if ev["tool_decision"]["correct"] else "⚠️ TOOL-MISMATCH"
        print(f"    {status_icon} | {tool_icon} [{ev['tool_decision']['classification']}] | Latency: {inf['total_time_s']:.2f}s | TTFT: {inf['ttft_ms']:.1f}ms | Gen: {inf['tokens_per_sec']:.1f} t/s")
        
        if tc.get("requires_tool_call"):
            print(f"    Terms: {ev['term_extraction']['accuracy']}% ({ev['term_extraction']['correct_count']}/{ev['term_extraction']['total_count']})")
            if ev["term_extraction"]["details"]:
                print(f"    Term failures: {'; '.join(ev['term_extraction']['details'])}")
        elif ev["hallucination"]["detected"]:
            print(f"    ⚠️ Hallucination: {'; '.join(ev['hallucination']['details'])}")
        print("")

        results.append({
            "test_case": tc,
            "inference": inf,
            "evaluation": ev
        })

    # Aggregated Statistics
    total_tests = len(results)
    passed_count = sum(1 for r in results if r["evaluation"]["passed"])
    pass_rate = (passed_count / total_tests) * 100 if total_tests else 0.0

    # Tool Calling Metrics
    tp = sum(1 for r in results if r["evaluation"]["tool_decision"]["classification"] == "TP")
    tn = sum(1 for r in results if r["evaluation"]["tool_decision"]["classification"] == "TN")
    fp = sum(1 for r in results if r["evaluation"]["tool_decision"]["classification"] == "FP")
    fn = sum(1 for r in results if r["evaluation"]["tool_decision"]["classification"] == "FN")

    tool_accuracy = ((tp + tn) / total_tests) * 100 if total_tests else 0.0
    tool_precision = (tp / (tp + fp)) * 100 if (tp + fp) > 0 else 0.0
    tool_recall = (tp / (tp + fn)) * 100 if (tp + fn) > 0 else 0.0
    tool_f1 = (2 * tool_precision * tool_recall / (tool_precision + tool_recall)) if (tool_precision + tool_recall) > 0 else 0.0

    # Term Metrics
    tool_tests = [r for r in results if r["test_case"].get("requires_tool_call")]
    avg_term_acc = sum(r["evaluation"]["term_extraction"]["accuracy"] for r in tool_tests) / len(tool_tests) if tool_tests else 0.0

    # Computational / Reasoning Performance Metrics
    avg_ttft = sum(r["inference"]["ttft_ms"] for r in results) / total_tests if total_tests else 0.0
    valid_tgen = [r["inference"]["tokens_per_sec"] for r in results if r["inference"]["tokens_per_sec"] > 0]
    avg_tgen = (sum(valid_tgen) / len(valid_tgen)) if valid_tgen else 0.0
    avg_latency = sum(r["inference"]["total_time_s"] for r in results) / total_tests if total_tests else 0.0

    summary = {
        "model": model_name,
        "mode": args.mode,
        "pass_rate_pct": round(pass_rate, 1),
        "passed_count": passed_count,
        "total_tests": total_tests,
        "tool_calling": {
            "accuracy_pct": round(tool_accuracy, 1),
            "precision_pct": round(tool_precision, 1),
            "recall_pct": round(tool_recall, 1),
            "f1_pct": round(tool_f1, 1),
            "confusion_matrix": {"TP": tp, "TN": tn, "FP": fp, "FN": fn}
        },
        "term_extraction": {
            "avg_accuracy_pct": round(avg_term_acc, 1)
        },
        "performance": {
            "avg_ttft_ms": round(avg_ttft, 1),
            "avg_tokens_per_sec": round(avg_tgen, 2),
            "avg_total_latency_s": round(avg_latency, 2)
        }
    }

    return {"summary": summary, "results": results}

def main():
    parser = argparse.ArgumentParser(description="Academic Benchmark Suite for CPU-Bound SLMs - UEL / LABGEP")
    parser.add_argument("--model", default="qwen2.5:1.5b", help="Ollama model to evaluate")
    parser.add_argument("--models", default="", help="Comma-separated list of multiple models for comparative benchmarking")
    parser.add_argument("--mode", choices=["tools", "json", "n8n"], default="tools", help="Inference mode: 'tools' (native function calling), 'json' (structured ChatML), or 'n8n' (webhook)")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Base URL for Ollama API")
    parser.add_argument("--n8n-url", default="http://localhost:5678", help="Base URL for n8n orchestrator")
    parser.add_argument("--n8n-webhook", default="acao-orcamentaria", help="Webhook path in n8n")
    parser.add_argument("--test-file", default=os.path.join(os.path.dirname(__file__), "test_cases.json"), help="Path to test cases JSON file")
    parser.add_argument("--output-md", default=os.path.join(os.path.dirname(__file__), "benchmark_report.md"), help="Path to save Markdown report")
    parser.add_argument("--output-json", default=os.path.join(os.path.dirname(__file__), "benchmark_report.json"), help="Path to save consolidated JSON report")
    parser.add_argument("--dry-run", action="store_true", help="Run offline validation test mode without actual HTTP requests")
    args = parser.parse_args()

    models_to_test = [m.strip() for m in args.models.split(",") if m.strip()] if args.models else [args.model]
    test_cases = load_test_cases(args.test_file)

    all_models_data = []

    for model in models_to_test:
        data = run_benchmark_for_model(model, test_cases, args)
        all_models_data.append(data)

    # Print Consolidated Comparative Summary
    print("======================================================================")
    print(" 📊 CONSOLIDATED COMPARATIVE BENCHMARK SUMMARY")
    print("======================================================================")
    print(f"{'Model':<18} | {'Mode':<6} | {'Pass%':<6} | {'Tool Acc':<8} | {'Term Acc':<8} | {'TTFT':<9} | {'Tgen':<10} | {'Latency':<8}")
    print("-" * 88)
    for entry in all_models_data:
        s = entry["summary"]
        p = s["performance"]
        tc = s["tool_calling"]
        te = s["term_extraction"]
        print(f"{s['model']:<18} | {s['mode']:<6} | {s['pass_rate_pct']:>5.1f}% | {tc['accuracy_pct']:>7.1f}% | {te['avg_accuracy_pct']:>7.1f}% | {p['avg_ttft_ms']:>7.1f}ms | {p['avg_tokens_per_sec']:>7.2f} t/s | {p['avg_total_latency_s']:>6.2f}s")
    print("======================================================================\n")

    # Generate Full Markdown Report
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md_content = f"""# 📑 Comparative Benchmark Report: CPU-Bound SLMs
**Execution Date:** {timestamp}  
**Target Hardware:** Intel Xeon E5-2640 v2 @ 2.00 GHz (CPU Only, 8 GB DDR3, AVX Vectorization)  
**Execution Environment:** Home Lab Server (UEL / LABGEP)  
**Evaluation Mode:** `{args.mode.upper()}` ({'Native Tool Calling' if args.mode == 'tools' else 'Structured ChatML' if args.mode == 'json' else 'n8n Webhook'})

---

## 🏆 Performance Pillars Comparative Table

| Model | Mode | Global Accuracy | Tool Calling Accuracy | Term Accuracy | Avg TTFT | Throughput ($T_{{\\text{{gen}}}}$) | Total Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
"""
    for entry in all_models_data:
        s = entry["summary"]
        p = s["performance"]
        tc = s["tool_calling"]
        te = s["term_extraction"]
        md_content += f"| **`{s['model']}`** | `{s['mode']}` | **{s['pass_rate_pct']:.1f}%** ({s['passed_count']}/{s['total_tests']}) | **{tc['accuracy_pct']:.1f}%** (F1: {tc['f1_pct']:.1f}%) | **{te['avg_accuracy_pct']:.1f}%** | {p['avg_ttft_ms']:.1f} ms | {p['avg_tokens_per_sec']:.2f} t/s | {p['avg_total_latency_s']:.2f} s |\n"

    md_content += r"""
---

## 🔍 Detailed Analysis of the 3 Pillars

### 1. Computational Efficiency (Reasoning Latency)
- **Time-To-First-Token (TTFT):** Measures initial prompt prefill duration. On our Xeon CPU, 1B–1.5B models achieve fast prefill (<400ms on warm cache), while 3B models put heavier pressure on L2/L3 caches.
- **Throughput ($T_{\text{gen}}$):** Autoregressive token generation rate. Rates $\ge 12$ tokens/s ensure responsive and fluid user interaction in n8n.

### 2. Tool Calling Trigger Decision (Confusion Matrix)
The assistant must cleanly discriminate greetings and legal explanations (no tool) from budget search requests (tool call):

"""
    for entry in all_models_data:
        s = entry["summary"]
        cm = s["tool_calling"]["confusion_matrix"]
        md_content += f"""#### Model: `{s['model']}`
- **True Positives (TP):** {cm['TP']} (Budget query correctly recognized and tool triggered)
- **True Negatives (TN):** {cm['TN']} (Greeting/out-of-scope query handled without calling database)
- **False Positives (FP):** {cm['FP']} (Unwarranted database query triggered for greetings or general questions)
- **False Negatives (FN):** {cm['FN']} (Critical failure: user provided budget term/code, but tool was not called)
- **Precision:** {s['tool_calling']['precision_pct']:.1f}% | **Recall:** {s['tool_calling']['recall_pct']:.1f}% | **F1-Score:** {s['tool_calling']['f1_pct']:.1f}%

"""

    md_content += """### 3. Search Term Accuracy
Evaluates whether extracted parameters passed to PostgreSQL fuzzy search (`similarity()` and `unaccent()`) obey domain rules:
1. `termo1`: singular noun, diacritic-free, or raw budget numeric code.
2. `termo2`: second relevant keyword.
3. `termo3`: third keyword or institutional acronym (e.g., UEL, SEFA).
4. `radical1` and `radical2`: 4- to 5-character lexical roots for trigram matching.

---

## 🔬 Test Case Details
"""
    for entry in all_models_data:
        md_content += f"\n### Detailed Results: `{entry['summary']['model']}`\n\n"
        md_content += "| ID | Test Case | Requires Tool? | Called Tool? | Matrix | Latency | TTFT | Throughput | Terms (%) | Status |\n"
        md_content += "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n"
        for r in entry["results"]:
            tc = r["test_case"]
            inf = r["inference"]
            ev = r["evaluation"]
            td = ev["tool_decision"]
            te = ev["term_extraction"]
            status_badge = "✅ PASS" if ev["passed"] else "❌ FAIL"
            md_content += f"| `{tc['id']}` | {tc['name']} | {'Yes' if td['requires_tool'] else 'No'} | {'Yes' if td['called_tool'] else 'No'} | `{td['classification']}` | {inf['total_time_s']:.2f}s | {inf['ttft_ms']:.1f}ms | {inf['tokens_per_sec']:.1f} t/s | {te['accuracy']}% | {status_badge} |\n"

    md_content += "\n---\n*Generated automatically by the UEL / LABGEP Academic Benchmark Suite.*\n"

    with open(args.output_md, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"📄 Markdown report saved to: {args.output_md}")

    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp,
            "mode": args.mode,
            "hardware": "Intel Xeon E5-2640 v2 (8C/16T, 8GB DDR3)",
            "models": all_models_data
        }, f, indent=2, ensure_ascii=False)
    print(f"💾 Consolidated JSON data saved to: {args.output_json}")

if __name__ == "__main__":
    main()
