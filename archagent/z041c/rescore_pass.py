"""Session 041C — re-score the ONE archived route PASS under the corrected
duplicate-title evaluator, inside the restricted execution tier.

The archived candidate (merged-model Track-B, radiostation:api-post-
validation) is re-evaluated byte-for-byte from the 041B evidence record.
The corrected evaluator adds the duplicate-title-other-parent probe
(201 expected on a same-title/other-parent submission). The 041B pass was
scored with a GLOBALLY scoped duplicate check, so the honest expectation is
a flip to BEHAVIOR_FAIL — reported as measured, whatever it is.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.s040 import route_eval_s039_compat as compat  # noqa: E402

CANDIDATE = (ROOT / "experiments/z041c-evaluator-correction/rescore/"
             "merged-trackB-api-post-validation")
OUT = (ROOT / "experiments/z041c-evaluator-correction/rescore/"
       "merged-trackB-api-post-validation-corrected-verdict.json")


def main() -> int:
    archived = json.loads(
        (ROOT / "experiments/z041-coding-finetune/eval/merged/track-B/"
         "radiostation__api-post-validation.json").read_text(encoding="utf-8"))
    staged = (CANDIDATE / "output.ts").read_text(encoding="utf-8")
    import hashlib
    assert hashlib.sha256(staged.encode()).hexdigest() == archived["candidate_final_sha256"], \
        "staged candidate drifted from the archived evidence"
    t0 = time.time()
    verdict = compat.evaluate_route(ROOT, "dev", "radiostation:api-post-validation",
                                    CANDIDATE, backend="unshare")
    record = {
        "rescore_session": "041C",
        "reason": "duplicate-title evaluator corrected (041C-duplicate-title-scope); "
                  "the only archived route PASS is re-scored under the corrected probe plan",
        "source_evidence": "experiments/z041-coding-finetune/eval/merged/track-B/"
                           "radiostation__api-post-validation.json",
        "candidate_final_sha256": archived["candidate_final_sha256"],
        "model_label": archived["model_label"],
        "original_verdict": {"passed": archived["verdict"]["passed"],
                             "status": archived["verdict"]["status"],
                             "case_count": archived["verdict"]["case_count"]},
        "elapsed_seconds": round(time.time() - t0, 1),
        **verdict,
    }
    OUT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    failed = [c["name"] for c in verdict.get("checks", []) if not c["passed"]]
    print(json.dumps({"status": verdict.get("status"), "passed": verdict.get("passed"),
                      "case_count": verdict.get("case_count"),
                      "case_amendment": verdict.get("case_amendment"),
                      "failed_probes": failed,
                      "elapsed_seconds": record["elapsed_seconds"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
