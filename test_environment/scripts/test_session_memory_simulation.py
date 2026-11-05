#!/usr/bin/env python3
"""
Standalone Multi-Turn Verification Suite: n8n Session Mini-Memory + K-Medoids (PAM).
Author: Marcos Vinicius Beregula Ferreira (UEL - LABGEP / NIGEP)

Simulates the exact state machine and clustering logic implemented in:
  1. test_environment/n8n_workflows/proposed/n8n_session_memory_router.js (Pre-SLM Router & Cluster Expander)
  2. test_environment/n8n_workflows/proposed/n8n_kmedoids_node.js         (Post-Postgres K-Medoids + Memory Saver)

Zero external dependencies (Python 3 standard library only, per AGENTS.md Rule 5).
"""

import csv
import math
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


SESSION_TTL_SEC = 15 * 60
MAX_REFINEMENT_TURNS = 3


def normalize_text(text: str) -> str:
    """Lowercase and strip basic Portuguese diacritics for simulated unaccent search."""
    mapping = str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ",
        "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC",
    )
    return (text or "").translate(mapping).lower().strip()


def load_expense_nature_catalog(csv_path: Path) -> List[Dict[str, str]]:
    """Load real Paraná budget expense nature items from test_environment/sql/data/naturezadespesa.csv."""
    items: List[Dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items.append(
                {
                    "codigo": (row.get("codigo") or "").strip(),
                    "descricao": (row.get("descricao") or "").strip(),
                    "titulo": (row.get("titulo") or "").strip(),
                    "detalhe": (row.get("detalhe") or "").strip(),
                }
            )
    return items


def simulate_postgres_search(
    catalog: List[Dict[str, str]], search_term: str, limit: int = 60
) -> List[Dict[str, str]]:
    """Simulate the PostgreSQL unaccent/ILIKE + trigram priority query with LIMIT 60."""
    terms = [t for t in normalize_text(search_term).split() if len(t) >= 3]
    if not terms:
        terms = [normalize_text(search_term)]

    scored: List[Tuple[int, str, Dict[str, str]]] = []
    for item in catalog:
        cod_norm = item["codigo"].replace(".", "").replace("-", "")
        desc_norm = normalize_text(item["descricao"])
        tit_norm = normalize_text(item["titulo"])
        det_norm = normalize_text(item["detalhe"])
        combined = f"{cod_norm} {desc_norm} {tit_norm} {det_norm}"

        if all(t in combined for t in terms):
            t0 = terms[0]
            if cod_norm == t0.replace(".", "").replace("-", ""):
                priority = 0
            elif desc_norm.startswith(t0):
                priority = 1
            elif t0 in desc_norm:
                priority = 2
            elif t0 in tit_norm:
                priority = 3
            else:
                priority = 4
            scored.append((priority, item["codigo"], item))

    scored.sort(key=lambda x: (x[0], x[1]))
    return [x[2] for x in scored[:limit]]


def extract_tokens(item: Dict[str, str]) -> Set[str]:
    """Extract 3+ character lexical tokens matching n8n_kmedoids_node.js."""
    text = f"{item.get('codigo', '')} {item.get('descricao', '')} {item.get('titulo', '')} {item.get('detalhe', '')}".lower()
    return set(re.findall(r"[a-zà-ÿ0-9]{3,}", text))


def jaccard_distance(set_a: Set[str], set_b: Set[str]) -> float:
    """Compute Jaccard distance between two lexical token sets."""
    if not set_a and not set_b:
        return 0.0
    inter = len(set_a.intersection(set_b))
    union = len(set_a) + len(set_b) - inter
    return 0.0 if union == 0 else 1.0 - (inter / union)


def run_kmedoids_pam(
    items: List[Dict[str, str]], k: int = 4, max_iter: int = 25
) -> List[Dict[str, Any]]:
    """Execute Partitioning Around Medoids (PAM) returning medoids and full member lists."""
    n = len(items)
    if n <= k:
        return [
            {
                "grupo": idx + 1,
                "medoid": item,
                "totalItensNoGrupo": 1,
                "descricaoGrupo": f"[{item['codigo']}] {item['descricao']}"
                + (f" - {item['titulo']}" if item.get("titulo") else ""),
                "membros": [item],
            }
            for idx, item in enumerate(items)
        ]

    token_sets = [extract_tokens(it) for it in items]
    dist_matrix = [
        [
            0.0 if i == j else jaccard_distance(token_sets[i], token_sets[j])
            for j in range(n)
        ]
        for i in range(n)
    ]

    step = max(1, n // k)
    medoids = [min(i * step, n - 1) for i in range(k)]
    clusters: Dict[int, List[int]] = {}

    for _ in range(max_iter):
        clusters = {m: [] for m in medoids}
        for i in range(n):
            best_m = min(medoids, key=lambda m: dist_matrix[i][m])
            clusters[best_m].append(i)

        changed = False
        new_medoids: List[int] = []
        for m in medoids:
            members = clusters.get(m, [])
            if not members:
                new_medoids.append(m)
                continue
            best_cand = min(
                members,
                key=lambda cand: sum(dist_matrix[cand][other] for other in members),
            )
            if best_cand != m:
                changed = True
            new_medoids.append(best_cand)

        medoids = new_medoids
        if not changed:
            break

    result = []
    for idx, m in enumerate(medoids):
        member_indices = clusters.get(m, [m])
        member_items = [items[i] for i in member_indices]
        medoid_item = items[m]
        result.append(
            {
                "grupo": idx + 1,
                "medoid": medoid_item,
                "totalItensNoGrupo": len(member_items),
                "descricaoGrupo": f"[{medoid_item['codigo']}] {medoid_item['descricao']}"
                + (f" - {medoid_item['titulo']}" if medoid_item.get("titulo") else ""),
                "membros": member_items,
            }
        )
    return result


class N8nSessionMiniMemorySimulator:
    """Simulates n8n $getWorkflowStaticData('global') Session Mini-Memory workflow."""

    def __init__(self, catalog: List[Dict[str, str]]) -> None:
        self.catalog = catalog
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def process_turn(self, session_id: str, user_message: str) -> Dict[str, Any]:
        t_start = time.perf_counter()
        now = time.time()

        # 1. Garbage collection for expired sessions
        expired = [
            sid
            for sid, s in self.sessions.items()
            if (now - s.get("updatedAt", 0)) > SESSION_TTL_SEC
        ]
        for sid in expired:
            del self.sessions[sid]

        raw_msg = user_message.strip()
        norm_msg = raw_msg.lower()

        session = self.sessions.get(
            session_id,
            {
                "sessionId": session_id,
                "lastTerm": None,
                "turnCount": 0,
                "clusters": None,
                "updatedAt": now,
            },
        )

        # CASE 1: Explicit reset command
        if re.match(
            r"^(reiniciar|limpar|reset|nova busca|recomeçar|recomecar|cancelar|outro assunto)$",
            norm_msg,
            re.IGNORECASE,
        ):
            self.sessions.pop(session_id, None)
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            return {
                "route_to_slm": False,
                "acao_memoria": "contexto_reiniciado",
                "slm_tokens_used": 0,
                "latency_ms": round(elapsed_ms, 3),
                "output_preview": "Contexto da conversa reiniciado com sucesso.",
            }

        # CASE 2: User selects a K-Medoids cluster option ("1", "opção 2", "grupo 3")
        if session.get("clusters"):
            m_choice = re.match(
                r"^(?:op[cç][aã]o|grupo|item|topico|tópico|numero|número|quero o|quero a|ver o|ver a|abrir)?\s*([1-9])\b",
                norm_msg,
                re.IGNORECASE,
            )
            if m_choice:
                chosen_num = int(m_choice.group(1))
                chosen_cluster = next(
                    (c for c in session["clusters"] if c["grupo"] == chosen_num), None
                )
                if chosen_cluster:
                    members = chosen_cluster["membros"]
                    session["clusters"] = None
                    session["turnCount"] += 1
                    session["updatedAt"] = now
                    self.sessions[session_id] = session
                    elapsed_ms = (time.perf_counter() - t_start) * 1000.0
                    return {
                        "route_to_slm": False,
                        "acao_memoria": "expansao_cluster_direta",
                        "grupoEscolhido": chosen_num,
                        "totalItensGrupo": len(members),
                        "slm_tokens_used": 0,
                        "latency_ms": round(elapsed_ms, 3),
                        "output_preview": (
                            f"Exibindo itens do Grupo {chosen_num} "
                            f"({chosen_cluster['descricaoGrupo']}) -> {len(members)} registros listados sem acionar a SLM."
                        ),
                    }

        # CASE 3: Incremental refinement vs. Auto-Reset on Turn Limit / New Topic
        refinement_prefix = bool(
            re.match(
                r"^(mas\s+|só\s+|so\s+|apenas\s+|somente\s+|especificamente\s+|para\s+|de\s+|do\s+|da\s+|tipo\s+|exceto\s+)",
                norm_msg,
                re.IGNORECASE,
            )
        )
        is_short_refinement = (
            bool(session.get("lastTerm"))
            and session.get("turnCount", 0) < MAX_REFINEMENT_TURNS
            and (refinement_prefix or len(norm_msg.split()) <= 2)
            and not re.match(
                r"^(oi|olá|ola|bom dia|boa tarde|boa noite|ajuda|socorro)\b",
                norm_msg,
                re.IGNORECASE,
            )
            and not re.match(r"^\d", norm_msg)
        )

        last_term = session.get("lastTerm") or ""
        if is_short_refinement and last_term.lower() not in norm_msg:
            clean_mod = re.sub(
                r"^(?:(?:mas|só|so|apenas|somente|especificamente|para|de|do|da|tipo)\s+)+",
                "",
                raw_msg,
                flags=re.IGNORECASE,
            ).strip()
            message_for_slm = f"{last_term} {clean_mod}".strip()
            session["turnCount"] += 1
            memory_action = "refinamento_incremental"
        else:
            prev_turns = session.get("turnCount", 0)
            memory_action = (
                "auto_reset_limite_turnos"
                if prev_turns >= MAX_REFINEMENT_TURNS
                else "nova_busca_limpa"
            )
            session = {
                "sessionId": session_id,
                "lastTerm": None,
                "turnCount": 1,
                "clusters": None,
                "updatedAt": now,
            }
            message_for_slm = raw_msg

        # Simulate SLM single-turn keyword normalization (zero chat history injected!)
        # In production this calls Qwen 2.5 / Llama 3.2 with ~150 prompt tokens.
        normalized_query = re.sub(
            r"\b(quero|preciso|comprar|contratar|adquirir|de|para|do|da|em|no|na)\b",
            " ",
            message_for_slm,
            flags=re.IGNORECASE,
        )
        normalized_query = " ".join(normalized_query.split())
        slm_prompt_tokens = 145 + len(message_for_slm.split())

        # Execute simulated PostgreSQL search (LIMIT 60)
        db_rows = simulate_postgres_search(self.catalog, normalized_query, limit=60)
        session["lastTerm"] = normalized_query
        session["updatedAt"] = now

        if len(db_rows) <= 7:
            session["clusters"] = None
            self.sessions[session_id] = session
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            return {
                "route_to_slm": True,
                "acao_memoria": memory_action,
                "acao_pos_banco": "exibicao_direta",
                "effective_query": normalized_query,
                "db_rows_returned": len(db_rows),
                "slm_tokens_used": slm_prompt_tokens,
                "latency_ms": round(elapsed_ms, 3),
                "output_preview": f"Tabela direta formatada com {len(db_rows)} registros.",
            }
        else:
            k = 4
            clusters = run_kmedoids_pam(db_rows, k=k)
            session["clusters"] = clusters
            self.sessions[session_id] = session
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            return {
                "route_to_slm": True,
                "acao_memoria": memory_action,
                "acao_pos_banco": "desambiguacao_kmedoids_salva_em_memoria",
                "effective_query": normalized_query,
                "db_rows_returned": len(db_rows),
                "k_clusters": k,
                "slm_tokens_used": slm_prompt_tokens,
                "latency_ms": round(elapsed_ms, 3),
                "clusters_summary": [
                    f"Opção {c['grupo']} ({c['totalItensNoGrupo']} itens): {c['descricaoGrupo']}"
                    for c in clusters
                ],
                "output_preview": f"Agrupado em {k} medoids representativos e salvo na Mini-Memória da sessão.",
            }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    csv_path = repo_root / "test_environment" / "sql" / "data" / "naturezadespesa.csv"
    if not csv_path.exists():
        print(f"[ERROR] Dataset not found at {csv_path}", file=sys.stderr)
        return 1

    catalog = load_expense_nature_catalog(csv_path)
    sim = N8nSessionMiniMemorySimulator(catalog)
    session_id = "servidor-sefa-pr-sessao-01"

    print("=" * 82)
    print("  N8N SESSION MINI-MEMORY + K-MEDOIDS MULTI-TURN VERIFICATION SUITE")
    print(f"  Dataset loaded: {len(catalog)} records from test_environment/sql/data/naturezadespesa.csv")
    print("=" * 82)

    scenarios = [
        (
            "Turn 1 — Broad Query ('serviço') -> Triggers K-Medoids (k=4) & Saves to Session Memory",
            "serviço",
        ),
        (
            "Turn 2 — Cluster Option Selection ('opção 2') -> Direct Memory Expansion (0 SLM Tokens, <1 ms)",
            "opção 2",
        ),
        (
            "Turn 3 — Short Refinement ('mas apenas limpeza') -> Concatenates with lastTerm ('serviço limpeza')",
            "mas apenas limpeza",
        ),
        (
            "Turn 4 — Turn Limit Reached (turnCount=3 -> Auto-Reset) with New Query ('equipamento de informática')",
            "equipamento de informática",
        ),
        (
            "Turn 5 — Explicit Reset Command ('reiniciar') -> Purges Session State Immediately",
            "reiniciar",
        ),
    ]

    for title, user_input in scenarios:
        print(f"\n>>> {title}")
        print(f"    User Input : \"{user_input}\"")
        res = sim.process_turn(session_id, user_input)
        print(f"    Route SLM? : {res['route_to_slm']} (SLM Prompt Tokens: {res['slm_tokens_used']})")
        print(f"    Memory Act : {res['acao_memoria']}")
        if "acao_pos_banco" in res:
            print(f"    Post-DB Act: {res['acao_pos_banco']} (Query: '{res['effective_query']}', Rows: {res['db_rows_returned']})")
        if "clusters_summary" in res:
            for line in res["clusters_summary"]:
                print(f"      - {line}")
        print(f"    Latency    : {res['latency_ms']} ms (in-memory JS/Python processing)")
        print(f"    Result     : {res['output_preview']}")

        # Assertions for automated validation
        if user_input == "serviço":
            assert res["route_to_slm"] is True
            assert res["acao_pos_banco"] == "desambiguacao_kmedoids_salva_em_memoria"
            assert res["k_clusters"] == 4
        elif user_input == "opção 2":
            assert res["route_to_slm"] is False
            assert res["acao_memoria"] == "expansao_cluster_direta"
            assert res["slm_tokens_used"] == 0
            assert res["totalItensGrupo"] > 0
        elif user_input == "mas apenas limpeza":
            assert res["route_to_slm"] is True
            assert res["acao_memoria"] == "refinamento_incremental"
            assert "limpeza" in res["effective_query"]
        elif user_input == "equipamento de informática":
            assert res["route_to_slm"] is True
            assert res["acao_memoria"] == "auto_reset_limite_turnos"
        elif user_input == "reiniciar":
            assert res["route_to_slm"] is False
            assert res["acao_memoria"] == "contexto_reiniciado"

    print("\n" + "=" * 82)
    print("  [PASS] All 5 multi-turn Session Mini-Memory & K-Medoids assertions succeeded!")
    print("=" * 82)
    return 0


if __name__ == "__main__":
    sys.exit(main())
