"""Session 033 focused weight-space investigation (mission section 10).

Question: does any layer/site causally carry the distinction between the
CORRECT mutation-then-refetch pattern and the BUGGY parse-mutation-
response pattern that the real browser test caught in addProject?

Protocol (causal, no gradients):
- Build contrastive prompt pairs from the RECORDED TaskFlow repair: the
  same handler context, two continuations (repaired vs buggy), sharing a
  prefix and diverging at the first differing token.
- Value-swap mediation scan over all 24 layers (attn + mlp block
  outputs) at the handler-body positions: patch the counterfactual
  (buggy-context) activations into the original (repaired-context) run
  and measure the log-prob shift of the diverging token.
- Report per-layer mediation scores. A site with a large score is a
  localization CANDIDATE only — no edit is applied unless the evidence
  is strong AND a bounded reversible edit generalizes (per the corrected
  Session 010 finding, bounded edits have been behaviorally inert, so
  the bar for applying one is high).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
REPORTS = ROOT / "experiments" / "zai-taskflow" / "reports"

from archcircuits import tracing  # noqa: E402
from archcircuits.runner import resolve_model_path, repro_info  # noqa: E402

torch.set_num_threads(2)

# The repair contrast: same anchor + handler start, two continuations.
# Both are derived from the RECORDED TaskFlow bytes (the accepted repair
# and the recorded buggy attempt), shortened to the diverging region.
PREFIX = (
    "// TaskFlow App: the addProject submit handler.\n"
    "// After POSTing a new project, refresh the project list.\n"
    "  async function addProject(e) {\n"
    "    e.preventDefault();\n"
    "    if (!form.project) return;\n"
    "    if (offline) return;\n"
    "    try {\n"
    "      await api('/api/projects', { method: 'POST',\n"
    "        headers: { 'Content-Type': 'application/json' },\n"
    "        body: JSON.stringify({ name: form.project }) });\n"
)
REPAIRED_CONT = "      const data = await api('/api/projects');\n"
BUGGY_CONT = "      const data = await res.json();\n"

# counterfactual context: the buggy variant's surrounding comment
CF_PREFIX = (
    "// TaskFlow App: the addProject submit handler.\n"
    "// Parse the POST response and read the projects list from it.\n"
    "  async function addProject(e) {\n"
    "    e.preventDefault();\n"
    "    if (!form.project) return;\n"
    "    if (offline) return;\n"
    "    try {\n"
    "      await api('/api/projects', { method: 'POST',\n"
    "        headers: { 'Content-Type': 'application/json' },\n"
    "        body: JSON.stringify({ name: form.project }) });\n"
)


def run() -> dict:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    path = resolve_model_path()
    tok = AutoTokenizer.from_pretrained(path)
    model = AutoModelForCausalLM.from_pretrained(path, dtype=torch.float32)
    model.eval()
    n = sum(p.numel() for p in model.parameters())
    if n != 494_032_768:
        raise SystemExit(f"wrong architecture ({n} params)")

    # divergence token: first token where the two continuations differ
    rep_ids = tok(REPAIRED_CONT, add_special_tokens=False)["input_ids"]
    bug_ids = tok(BUGGY_CONT, add_special_tokens=False)["input_ids"]
    j = tracing.divergence_index(rep_ids, bug_ids)
    tok_rep, tok_bug = rep_ids[j], bug_ids[j]
    shared = rep_ids[:j]

    # commitment runs: prefix + shared continuation
    ids_prefix = tok(PREFIX, add_special_tokens=False)["input_ids"]
    cf_ids_prefix = tok(CF_PREFIX, add_special_tokens=False)["input_ids"]
    ids_orig = torch.tensor([ids_prefix + shared]).long()
    ids_cf = torch.tensor([cf_ids_prefix + shared]).long()
    pos_answer = len(ids_prefix) + j - 1
    # critical span: the instruction comment (differs between orig/cf)
    span = "refresh the project list"
    pos_crit = [p for p in tracing.span_positions(tok, PREFIX, span)
                if p < len(ids_prefix)]
    pos_crit_cf = [p for p in tracing.span_positions(tok, CF_PREFIX,
                                                     "Parse the POST response")
                   if p < len(cf_ids_prefix)]

    with torch.inference_mode():
        logits_orig = model(ids_orig.clone(),
                            attention_mask=torch.ones_like(ids_orig)).logits[0]
    orig_gap = tracing.token_logprob(logits_orig, pos_answer, tok_bug) - \
        tracing.token_logprob(logits_orig, pos_answer, tok_rep)

    # capture cf activations at the cf critical positions
    acts_cf = {}
    handles = []
    for L in range(24):
        for comp in ("attn", "mlp"):
            def hook(_m, _i, out, layer=L, c=comp):
                acts_cf[(layer, c)] = tracing._block_output(out).detach()
            block = model.model.layers[L]
            target = block.self_attn if comp == "attn" else block.mlp
            handles.append(target.register_forward_hook(hook))
    try:
        with torch.inference_mode():
            model(ids_cf.clone(), attention_mask=torch.ones_like(ids_cf))
    finally:
        for h in handles:
            h.remove()

    scores = {}
    t0 = time.time()
    for L in range(24):
        for comp in ("attn", "mlp"):
            values = acts_cf[(L, comp)][pos_crit_cf, :].clone()
            patched = tracing.patched_logits(
                model, tok, ids_orig,
                [{"layer": L, "component": comp, "positions": pos_crit,
                  "values": values}])
            gap = tracing.token_logprob(patched, pos_answer, tok_bug) - \
                tracing.token_logprob(patched, pos_answer, tok_rep)
            scores[f"L{L}/{comp}"] = round(gap - orig_gap, 4)
        print(f"  layer {L} done ({time.time()-t0:.0f}s)", flush=True)

    ranked = sorted(scores.items(), key=lambda kv: -abs(kv[1]))[:8]
    report = {
        "question": "which sites causally carry refetch-vs-parse?",
        "divergence_index": j,
        "orig_gap_bug_minus_rep": round(orig_gap, 4),
        "critical_positions": pos_crit,
        "cf_critical_positions": pos_crit_cf,
        "scores": scores,
        "top_by_absolute_mediation": ranked,
        "repro": repro_info(path),
        "interpretation_rule": "large |score| = mediation candidate only; "
                               "no weight edit is applied without "
                               "independent generalization evidence",
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / "weight_space_probe.json"
    out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf8")
    print(json.dumps(ranked, indent=1))
    print("saved", out)
    return report


if __name__ == "__main__":
    run()
