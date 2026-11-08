"""Schema micro-patch repair — FIM-anchored (Session-032 method).

The schema stage failed 3 rounds x 4 samples on ONE property: the
model never writes the nullable marker on sku.  This script gives the
model the block with a gap exactly at the sku line and asks it to
make the field optional — the micro-patch regime Session 034 proved
(ONE rule, ONE property, measured facts only).

If a sample fills the gap with a nullable sku, the block is merged,
pushed, and recorded as QWEN-REPAIRED.  Otherwise the failure stands
and the integration decision is documented.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.fullstack import devserver, install  # noqa: E402
from archagent.model import FrozenModel  # noqa: E402

GEN = ROOT / "experiments/zai-fullstack/generations"
LEDGER = ROOT / "experiments/zai-fullstack/PROVENANCE.json"

BLOCK_HEAD = """model InventoryItem {
  id          String    @id @default(cuid())
  name        String
  category    String
"""
BLOCK_TAIL = """  quantity    Int
  minQuantity Int
  updatedAt   DateTime  @updatedAt
}"""

INSTRUCTIONS = ("Change the sku field so it is optional (nullable). "
                "Keep it unique.")


def main() -> None:
    devserver.stop_dev()
    time.sleep(1)
    model = FrozenModel(threads=2)
    accepted = None
    for k in range(4):
        seed = k * 1013 or 7
        stochastic = k != 0
        text, usage = model.fim(
            prefix=BLOCK_HEAD, suffix=BLOCK_TAIL,
            instructions=INSTRUCTIONS,
            max_tokens=40, seed=seed, stochastic=stochastic)
        line = text.strip().splitlines()[0] if text.strip() else ""
        nullable = "?" in line and "sku" in line
        print(f"[fim k{k}] seed={seed} fill={line!r} nullable={nullable}")
        (GEN / f"schema_fim_k{k}.json").write_text(json.dumps(dict(
            kind="schema-fim", k=k, seed=seed, usage=usage,
            prefix=BLOCK_HEAD, suffix=BLOCK_TAIL,
            instructions=INSTRUCTIONS, completion=text,
            nullable=nullable), ensure_ascii=False, indent=1))
        if nullable and accepted is None:
            accepted = (k, seed, line, usage)
    if accepted:
        k, seed, line, usage = accepted
        block = BLOCK_HEAD + "  " + line + "\n" + BLOCK_TAIL
        install.merge_schema_block(block)
        ok, out = install.db_push()
        print(f"accepted k{k}: line={line!r} db_push={ok}")
        if ok:
            data = json.loads(LEDGER.read_text()) if LEDGER.exists() \
                else {"files": {}, "stages": [],
                      "model_usage_cumulative": {}}
            data["files"]["prisma/schema.prisma"] = dict(
                contract="schema", round="fim", k=k, seed=seed,
                tokens=usage["tokens"], label="QWEN-REPAIRED",
                note=("schema stage failed 3x4 completion rounds on "
                      "sku nullability; repaired by first FIM "
                      "micro-patch sample"))
            data["stages"].append(dict(
                contract="schema:fim-repair", accepted=True,
                mode="fim", k=k, seed=seed))
            LEDGER.write_text(json.dumps(data, indent=1))
    else:
        print("FIM repair FAILED too — integration decision required")
    devserver.start_dev()


if __name__ == "__main__":
    main()
