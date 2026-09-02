"""Standalone verification of parser + hash-embedding + vector-search math.

Runs WITHOUT Postgres/Redis. Confirms:
  1. CSV BOM parsing extracts the expected line items.
  2. Hash-fallback embeddings are 384-dim and L2-normalized.
  3. Cosine similarity ranks a near-duplicate description above an unrelated one.
"""
import sys
from pathlib import Path

# Make `app` importable
sys.path.insert(0, str(Path(__file__).parent))

results = []


def check(name, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, extra))


# 1) Parser
from app.docai.parser import parse_bom_file  # noqa: E402

sample = Path(__file__).parents[2] / "samples" / "sample_bom.csv"
rows = parse_bom_file(sample)
mpns = {r["mpn"] for r in rows}
check("csv parse row count == 9", len(rows) == 9, f"got {len(rows)}")
check("parsed STM32F411CEU6", "STM32F411CEU6" in mpns)
check("parsed AP2112K-3.3TRG1", "AP2112K-3.3TRG1" in mpns)
first = next(r for r in rows if r["mpn"] == "STM32F411CEU6")
check("qty parsed for STM32", first["quantity"] == 2, f"qty={first['quantity']}")
check("refdes parsed for STM32", first["reference_designator"].upper() == "U1",
      f"ref={first['reference_designator']}")

# 2) Embeddings (force hash fallback by disabling model load)
import app.embeddings as emb  # noqa: E402

emb._load_failed = True  # skip sentence-transformers download
v = emb.embed("STM32F411 Cortex-M4 MCU UFQFPN48 3.3V")
check("embedding dim == 384", len(v) == 384, f"dim={len(v)}")
norm = sum(x * x for x in v) ** 0.5
check("embedding L2-normalized ~1.0", abs(norm - 1.0) < 1e-6, f"norm={norm:.6f}")


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))


base = emb.embed("3.3V 600mA LDO voltage regulator SOT-23")
near = emb.embed("3.3V LDO voltage regulator low dropout SOT-23")
far = emb.embed("8MHz quartz crystal resonator 18pF")
sim_near = cosine(base, near)
sim_far = cosine(base, far)
check("similar text ranks above unrelated", sim_near > sim_far,
      f"near={sim_near:.3f} far={sim_far:.3f}")

# 3) Graph builds (in-memory checkpointer) — validates LangGraph wiring
try:
    from app.agents.graph import build_graph  # noqa: E402
    g = build_graph()
    check("LangGraph compiles", g is not None)
except Exception as e:  # pragma: no cover
    check("LangGraph compiles", False, repr(e))

print("\n=== VERIFICATION RESULTS ===")
for status, name, extra in results:
    line = f"[{status}] {name}"
    if extra:
        line += f"  ({extra})"
    print(line)

fails = [r for r in results if r[0] == "FAIL"]
print(f"\n{len(results) - len(fails)}/{len(results)} checks passed.")
sys.exit(1 if fails else 0)
