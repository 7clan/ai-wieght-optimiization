"""Build the joint multi-category (CON+XCOM) factor set at layer 16.

Candidate 3 of Phase C: a regularized multi-key update in which keys from two
behavior families (interface-contract compliance and cross-component binding)
carry different target directions, solved in one closed-form least-squares
step.  Uses only dev tasks; the norm cap is the repository limit (1.5%).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
torch.set_num_threads(2)

from archcircuits.benchmark import tasks_for, build_prompt  # noqa: E402
from archcircuits.runner import load_model  # noqa: E402
from archcircuits import edits  # noqa: E402

REPORTS = Path(__file__).resolve().parents[1] / "reports"
FACTORS = Path(__file__).resolve().parents[1] / "factors"
BASELINE = Path(__file__).resolve().parents[2] / "experiments" / "archcircuits" / "reports" / "baseline.json"


def main() -> None:
    model, tok, _ = load_model()
    base = json.loads(BASELINE.read_text())
    wrongs = {r["id"]: r["prediction_extracted"] for r in base["records"]}

    def distractor(task):
        w = (wrongs.get(task["id"]) or "").strip()
        if w and w.lower() != task["gold"].strip().lower():
            return w
        try:
            return str(int(task["gold"]) + 1)
        except ValueError:
            return "unknown"

    layer, matrix = 16, "mlp.down_proj"
    key_groups, dir_groups, cats = [], [], []
    for cat in ("CON", "XCOM"):
        pairs = []
        for t in tasks_for("dev", cat):
            pairs.append({"prompt": build_prompt(t["category"], t["question"]),
                          "gold": t["gold"], "wrong": distractor(t)})
        con = edits.collect_contrast(model, tok, pairs, layer=layer, matrix=matrix)
        print(f"{cat}: d_norm={con['d_norm']:.3f} cos={con['cos_gold_wrong']:.3f}")
        key_groups.append(con["keys_wrong"])
        dir_groups.append(con["d"])
        cats.append(cat)

    W = edits._resolve(model, layer, matrix).weight.detach().float()
    left, right, info = edits.joint_factors(W, key_groups, dir_groups, alphas=[1.0, 1.0])
    meta = {
        "category": "JOINT_CON_XCOM",
        "method": "joint-multi-key",
        "alpha": 1.0,
        "construction": {**info, "categories": cats,
                         "d_norms": [round(float(d.norm().item()), 3) for d in dir_groups]},
        "norm_limit": 0.015,
        "note": "multi-category joint subspace edit at L16; interference must be measured",
    }
    stats, left, right = edits.cap_and_apply(model, layer, matrix, left, right)
    meta["applied"] = stats
    out = FACTORS / "joint_L16"
    # Session 011 audit fix: persist the SCALED factors so reload == applied.
    edits.save_factors(str(out), layer, matrix, left, right, meta)
    verification = edits.verify_factor_set(model, str(out))
    meta["verification"] = verification
    edits.save_factors(str(out), layer, matrix, left, right, meta)
    print("saved", out, "stats:", stats, "verification:", verification)


if __name__ == "__main__":
    main()
