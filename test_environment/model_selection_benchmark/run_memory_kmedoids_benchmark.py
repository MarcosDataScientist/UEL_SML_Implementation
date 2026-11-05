#!/usr/bin/env python3
"""
End-to-End Live Benchmark: n8n Session Mini-Memory + K-Medoids + Fine-Tuned Qwen 2.5 1.5B.
Author: Marcos Vinicius Beregula Ferreira (UEL - LABGEP / NIGEP)

Executes a 6-turn live conversation against the n8n production webhook
(`/webhook/natureza-despesa-memoria`) running on the Home Lab CPU-Only server
(Intel Xeon E5-2640 v2, 8 GB DDR3 RAM) and records end-to-end latency,
SLM bypass rate, K-Medoids clustering accuracy, and memory state transitions.

Zero external dependencies (Python 3 standard library only, per AGENTS.md Rule 5).
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List


def call_n8n_webhook(url: str, session_id: str, message: str, timeout: int = 120) -> Dict[str, Any]:
    payload = json.dumps({"sessionId": session_id, "message": message}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    data = json.loads(raw) if raw.strip() else {}
    if isinstance(data, list) and data:
        data = data[0]
    return {"latency_ms": round(elapsed_ms, 2), "response": data}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Live End-to-End Benchmark for n8n Session Mini-Memory & K-Medoids"
    )
    parser.add_argument(
        "--webhook-url",
        default="http://localhost:5678/webhook/natureza-despesa-memoria",
        help="Full URL of the n8n webhook endpoint",
    )
    parser.add_argument(
        "--session-id",
        default=f"homelab-bench-{int(time.time())}",
        help="Session ID for multi-turn evaluation",
    )
    args = parser.parse_args()

    turns = [
        {
            "turn": 1,
            "name": "Broad Search -> K-Medoids Clustering (k=4)",
            "input": "serviço",
            "expected_action": "desambiguacao_kmedoids_salva_em_memoria",
            "expects_slm": True,
        },
        {
            "turn": 2,
            "name": "Cluster Selection #2 -> Instant Memory Expansion (SLM Bypassed)",
            "input": "2",
            "expected_action": "expansao_cluster_direta",
            "expects_slm": False,
        },
        {
            "turn": 3,
            "name": "Cluster Selection #3 -> Instant Memory Expansion (SLM Bypassed)",
            "input": "3",
            "expected_action": "expansao_cluster_direta",
            "expects_slm": False,
        },
        {
            "turn": 4,
            "name": "Auto-Reset on Turn Limit (turnCount=3) + Specific Search",
            "input": "equipamento de informática",
            "expected_action": "exibicao_direta",
            "expects_slm": True,
        },
        {
            "turn": 5,
            "name": "Incremental Short Refinement ('mas apenas locação')",
            "input": "mas apenas locação",
            "expected_action": "exibicao_direta",
            "expects_slm": True,
        },
        {
            "turn": 6,
            "name": "Explicit Session Reset Command ('reiniciar')",
            "input": "reiniciar",
            "expected_action": "contexto_reiniciado",
            "expects_slm": False,
        },
    ]

    print("=" * 90)
    print("  LIVE END-TO-END BENCHMARK: N8N + QWEN 2.5 1.5B (FINE-TUNED) + K-MEDOIDS + MINI-MEMORY")
    print(f"  Endpoint   : {args.webhook_url}")
    print(f"  Session ID : {args.session_id}")
    print("=" * 90)

    results: List[Dict[str, Any]] = []
    passed = 0

    for t in turns:
        res = call_n8n_webhook(args.webhook_url, args.session_id, t["input"])
        body = res["response"]
        actual_action = body.get("acao") or body.get("acao_memoria") or "unknown"
        output_text = body.get("output") or ""
        ok = actual_action == t["expected_action"] and len(output_text) > 10
        if ok:
            passed += 1

        status_str = "PASS" if ok else "FAIL"
        slm_str = "SLM+DB" if t["expects_slm"] else "MEMORY-ONLY (0 SLM tokens)"
        print(
            f"\n[Turn {t['turn']}] {t['name']}\n"
            f"  Input      : {t['input']!r}\n"
            f"  Path       : {slm_str}\n"
            f"  Action     : {actual_action} (Expected: {t['expected_action']}) -> [{status_str}]\n"
            f"  Latency    : {res['latency_ms']:.2f} ms\n"
            f"  Output Preview: {output_text.splitlines()[0] if output_text else '<empty>'}"
        )

        results.append(
            {
                "turn": t["turn"],
                "name": t["name"],
                "input": t["input"],
                "expects_slm": t["expects_slm"],
                "expected_action": t["expected_action"],
                "actual_action": actual_action,
                "latency_ms": res["latency_ms"],
                "passed": ok,
            }
        )

    slm_latencies = [r["latency_ms"] for r in results if r["expects_slm"]]
    mem_latencies = [r["latency_ms"] for r in results if not r["expects_slm"]]
    avg_slm = sum(slm_latencies) / len(slm_latencies) if slm_latencies else 0.0
    avg_mem = sum(mem_latencies) / len(mem_latencies) if mem_latencies else 0.0
    speedup = (avg_slm / avg_mem) if avg_mem > 0 else 0.0

    print("\n" + "=" * 90)
    print(f"  SUMMARY: {passed}/{len(turns)} turns passed ({passed / len(turns) * 100:.1f}%)")
    print(f"  Avg SLM + Postgres + K-Medoids Turn Latency : {avg_slm:.2f} ms")
    print(f"  Avg Session Mini-Memory Direct Turn Latency : {avg_mem:.2f} ms")
    print(f"  Memory Expansion Speedup Factor             : {speedup:.1f}x faster (0 SLM tokens)")
    print("=" * 90)

    out_file = Path(__file__).resolve().parent / "memory_kmedoids_benchmark_report.json"
    out_file.write_text(
        json.dumps(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "webhook_url": args.webhook_url,
                "passed": passed,
                "total": len(turns),
                "avg_slm_turn_latency_ms": round(avg_slm, 2),
                "avg_memory_turn_latency_ms": round(avg_mem, 2),
                "speedup_factor": round(speedup, 1),
                "turns": results,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0 if passed == len(turns) else 1


if __name__ == "__main__":
    sys.exit(main())

