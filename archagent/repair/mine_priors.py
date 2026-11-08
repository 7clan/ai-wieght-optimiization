"""SESSION 036 — PHASE 2 (TRUSTED-SCAFFOLD).

Mine GENERAL strategy-outcome priors from the Session-035 archive.

Reads every archived generation record, reconstructs (error_category,
strategy, outcome) from the recorded kind/round/reject/accept fields and
writes experiments/z036/prior-mining.json.  The priors feed the bandit's
Beta posteriors (discounted 50% so new-task evidence dominates quickly).

IMPORTANT: what is mined are STRATEGY-LEVEL outcomes (did micro-FIM tend
to fix missing-literal defects on schema files?), never task solutions.
"""
from __future__ import annotations

import glob
import json
import os
import re
from collections import defaultdict

ARCHIVE = os.path.join(os.path.dirname(__file__), "..", "..",
                       "experiments", "zai-fullstack", "generations")

# Map archived generation kinds to the strategies they instantiated.
KIND_TO_STRATEGY = {
    "whole": "exact_shape",        # whole-file contract w/ demo
    "body": "body_completion",     # handler-body contract w/ anchors
    "fim": "fim_micro",            # micro-FIM patch
    "fim-patch": "fim_micro",
    "schema-fim": "fim_micro",
    "ui-body": "body_completion",  # UI component contracts (body-shaped)
    "client": "exact_shape",
}

REJECT_TO_CATEGORY = [
    (re.compile(r"unbalanced brackets|brace imbalance|truncated", re.I),
     "syntax"),
    (re.compile(r"missing 'export |missing \"export |exports", re.I),
     "missing_export"),
    (re.compile(r"demo echo", re.I), "demo_contamination"),
    (re.compile(r"missing 'db\.|expect .*db\.", re.I), "missing_call"),
    (re.compile(r"missing 'Number\.isInteger|missing 'sku: sku|missing '300"
                r"|missing 'sku\.length|uiStrings|missing '", re.I),
     "missing_literal"),
    (re.compile(r"forbidden|where\.status|type|TS\d{4}", re.I),
     "wrong_contract"),
]


def reject_category(reject: str) -> str:
    for pat, cat in REJECT_TO_CATEGORY:
        if pat.search(reject):
            return cat
    return "wrong_contract"


def main() -> None:
    counts: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0]))
    n_records = 0
    unmatched_kinds = set()
    for f in sorted(glob.glob(os.path.join(ARCHIVE, "*.json"))):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        n_records += 1
        kind = d.get("kind", "")
        strat = KIND_TO_STRATEGY.get(kind)
        if not strat:
            unmatched_kinds.add(kind)
            continue
        reject = d.get("reject")
        accepted = not reject
        # the category is only meaningful for the OUTCOME side: an accepted
        # sample resolved whatever the contract gated; a rejected sample
        # failed for the reject reason.  For priors we need the category of
        # the DEFECT the attempt targeted.  Reconstruct from contract name +
        # reject prefix; for accepted attempts use the contract's own
        # expectation class.
        contract = str(d.get("contract", ""))
        if accepted:
            cat = _accept_category(contract, d)
        else:
            r = reject if isinstance(reject, str) else " | ".join(
                map(str, reject))
            cat = reject_category(r)
        counts[cat][strat][0 if accepted else 1] += 1

    priors = {c: {s: v for s, v in strs.items()}
              for c, strs in counts.items()}
    out = {
        "source": "Session-035 archived generations "
                  "(experiments/zai-fullstack/generations)",
        "n_records_read": n_records,
        "unmatched_kinds": sorted(unmatched_kinds),
        "priors": priors,
        "note": "priors[cat][strat] = [successes, failures]; strategy-level "
                "outcomes only, no task solutions; bandit discounts 50%.",
    }
    dest = os.path.join(os.path.dirname(ARCHIVE), "..", "z036",
                        "prior-mining.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"mined {n_records} records -> {dest}")
    for c in sorted(priors):
        row = ", ".join(f"{s}:{v[0]}/{sum(v)}"
                        for s, v in sorted(priors[c].items()))
        print(f"  {c:20s} {row}")


def _accept_category(contract: str, d: dict) -> str:
    """Category of the defect an ACCEPTED sample resolved."""
    if "schema" in contract:
        return "missing_literal"     # schema nullability one-literal gap
    if contract.startswith("types"):
        return "missing_export"
    if "route" in contract:
        return "missing_call"
    if contract.startswith(("ui-", "states", "stats", "client")):
        return "missing_literal"
    return "wrong_contract"


if __name__ == "__main__":
    main()
