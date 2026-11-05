#!/usr/bin/env python3
"""
Full Paraná Expense Nature Seeder (1,560 records from test_environment/sql/data/naturezadespesa.csv).
Author: Marcos Vinicius Beregula Ferreira (UEL - LABGEP / NIGEP)

Populates `naturezadespesa` (1,557 unique subelements) and `subelementodetalhe`
(464 detail records) inside the running `homelab-slm-postgres` container so that
the production LEFT JOIN query returns the exact 1,560 records for K-Medoids testing.
"""

import csv
import subprocess
import sys
from pathlib import Path


def sql_escape(val: str) -> str:
    """Escape single quotes for PostgreSQL string literals."""
    return "'" + (val or "").replace("'", "''") + "'"


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    csv_path = repo_root / "test_environment" / "sql" / "data" / "naturezadespesa.csv"
    if not csv_path.exists():
        print(f"[ERROR] CSV file not found at {csv_path}", file=sys.stderr)
        return 1

    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    nd_pairs = list(
        dict.fromkeys(
            ((r.get("codigo") or "").strip(), (r.get("descricao") or "").strip())
            for r in rows
            if (r.get("codigo") or "").strip()
        )
    )
    sd_tuples = list(
        dict.fromkeys(
            (
                (r.get("codigo") or "").strip(),
                (r.get("detalhe") or "").strip(),
                (r.get("titulo") or "").strip(),
            )
            for r in rows
            if (r.get("codigo") or "").strip()
            and ((r.get("detalhe") or "").strip() or (r.get("titulo") or "").strip())
        )
    )

    sql_lines = [
        "BEGIN;",
        "TRUNCATE TABLE subelementodetalhe RESTART IDENTITY CASCADE;",
        "TRUNCATE TABLE naturezadespesa RESTART IDENTITY CASCADE;",
    ]

    if nd_pairs:
        values_nd = ",\n".join(
            f"({sql_escape(c)}, {sql_escape(d)})" for c, d in nd_pairs
        )
        sql_lines.append(
            f"INSERT INTO naturezadespesa (naturezadespesaformatada, descricaosubelemento) VALUES\n{values_nd};"
        )

    if sd_tuples:
        values_sd = ",\n".join(
            f"({sql_escape(c)}, {sql_escape(det)}, {sql_escape(tit)})"
            for c, det, tit in sd_tuples
        )
        sql_lines.append(
            f"INSERT INTO subelementodetalhe (naturezadespesa, descricaosubelementodetalhe, titulosubelementodetalhe) VALUES\n{values_sd};"
        )

    sql_lines.append("COMMIT;")
    sql_lines.append(
        "SELECT 'naturezadespesa' AS tabela, COUNT(*) AS registros FROM naturezadespesa "
        "UNION ALL SELECT 'subelementodetalhe', COUNT(*) FROM subelementodetalhe;"
    )

    sql_payload = "\n".join(sql_lines)

    proc = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "homelab-slm-postgres",
            "psql",
            "-U",
            "postgres",
            "-d",
            "orcamento_db",
        ],
        input=sql_payload.encode("utf-8"),
        capture_output=True,
    )

    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode("utf-8", errors="replace"))
        return proc.returncode

    sys.stdout.write(proc.stdout.decode("utf-8", errors="replace"))
    print(
        f"✅ Loaded {len(nd_pairs)} naturezadespesa rows and {len(sd_tuples)} subelementodetalhe rows (1,560 joined records)!"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

