"""Phase B: activation capture and causal counterfactual patching.

Causal protocol (value-swap patching): every dev task has a counterfactual
variant whose *critical span* changes the gold answer.  We patch activations
from the counterfactual run into the original run at the critical positions
and measure how much the next-token distribution at the answer position moves
toward the counterfactual gold.  A site (layer, component) that carries the
task-relevant information will show a large mediation score; sites that merely
correlate will not.

No gradients are used anywhere; all interventions are closed-form tensor
replacements inside forward hooks.
"""

from __future__ import annotations

import torch

from .benchmark import build_prompt


def tokenize(tokenizer, text: str):
    return tokenizer(text, return_tensors="pt", add_special_tokens=False)


def _offsets(tokenizer, text: str):
    """Per-token (start, end) char offsets, robust to BPE boundary merges."""
    enc = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    return enc["input_ids"], enc["offset_mapping"]


def span_positions(tokenizer, prompt: str, span: str) -> list[int]:
    """Token indices whose char ranges overlap the span's first occurrence."""
    char_start = prompt.find(span)
    if char_start < 0:
        return []
    char_end = char_start + len(span)
    ids, offsets = _offsets(tokenizer, prompt)
    out = []
    for i, (s, e) in enumerate(offsets):
        if e > char_start and s < char_end:
            out.append(i)
    return out


def aligned_span_positions(tokenizer, prompt: str, span: str,
                           other_prompt: str | None = None,
                           other_span: str | None = None) -> dict:
    """Session 011 audit fix: character-anchored span positions with alignment
    diagnostics.

    Token indices are computed independently per prompt via char offsets, so
    prompts with different tokenizations (different BPE merges, identifier
    lengths, whitespace) never share numerical indices by assumption.  When
    `other_prompt`/`other_span` are given, the returned dict also reports the
    other prompt's positions and the index shift, plus a decoded-text check of
    both position groups, so misalignment is observable instead of silent.
    """
    char_start = prompt.find(span)
    if char_start < 0:
        return {"positions": [], "error": "span not found in prompt"}
    ids, offsets = _offsets(tokenizer, prompt)
    positions = [i for i, (s, e) in enumerate(offsets)
                 if e > char_start and s < char_start + len(span)]
    out = {"positions": positions, "n_tokens": len(ids)}
    if positions:
        out["decoded"] = tokenizer.decode([ids[i] for i in positions])
    if other_prompt is not None and other_span is not None:
        other_char = other_prompt.find(other_span)
        if other_char < 0:
            out["other_error"] = "other span not found in other prompt"
        else:
            oids, ooffsets = _offsets(tokenizer, other_prompt)
            opos = [i for i, (s, e) in enumerate(ooffsets)
                    if e > other_char and s < other_char + len(other_span)]
            out["other_positions"] = opos
            out["other_n_tokens"] = len(oids)
            if opos:
                out["other_decoded"] = tokenizer.decode([oids[i] for i in opos])
            if positions and opos:
                out["index_shift"] = opos[0] - positions[0]
                out["tokenization_matches"] = (len(oids) == len(ids)
                                               and opos == positions)
    return out


def _block_output(out):
    """Normalize a block output to [T, H] (attn returns a tuple)."""
    v = out[0] if isinstance(out, tuple) else out
    return v[0]


class ActivationStore:
    """Capture per-layer attn-block and mlp-block outputs for all positions."""

    def __init__(self, model):
        self.model = model
        self.handles = []
        self.acts = {}  # (layer, "attn"|"mlp") -> tensor [T, H]

    def __enter__(self):
        for i, block in enumerate(self.model.model.layers):
            def hook_attn(_m, _inp, out, layer=i):
                self.acts[(layer, "attn")] = _block_output(out).detach()

            def hook_mlp(_m, _inp, out, layer=i):
                self.acts[(layer, "mlp")] = _block_output(out).detach()

            self.handles.append(block.self_attn.register_forward_hook(hook_attn))
            self.handles.append(block.mlp.register_forward_hook(hook_mlp))
        return self

    def __exit__(self, *exc):
        for h in self.handles:
            h.remove()
        return False


@torch.inference_mode()
def run_capture(model, tokenizer, prompt: str) -> tuple[dict, torch.Tensor]:
    """Forward pass capturing all block outputs and final logits."""
    with ActivationStore(model) as store:
        ids = tokenize(tokenizer, prompt)
        logits = model(**ids).logits[0].detach()
        return dict(store.acts), logits


@torch.inference_mode()
def patched_logits(model, tokenizer, ids, patches: list[dict]) -> torch.Tensor:
    """Forward pass where patches replace activations.

    patch = {"layer": int, "component": "attn"|"mlp", "positions": [int],
             "values": tensor [len(positions), H]}
    For per-head patches: {"layer": L, "head": h, ...} patches only the head's
    64-dim slice of the o_proj input at the given positions.
    """
    handles = []

    def make_pre_hook(patch):
        def hook(_m, args):
            inp = args[0]
            for j, pos in enumerate(patch["positions"]):
                s, e = patch["head"] * 64, (patch["head"] + 1) * 64
                inp[0, pos, s:e] = patch["values"][j].to(inp.dtype)
            return None
        return hook

    def make_hook(patch):
        def hook(_m, _inp, out):
            target = out[0] if isinstance(out, tuple) else out
            for j, pos in enumerate(patch["positions"]):
                target[0, pos, :] = patch["values"][j].to(target.dtype)
            return out
        return hook

    for patch in patches:
        block = model.model.layers[patch["layer"]]
        if "head" in patch:
            handles.append(block.self_attn.o_proj.register_forward_pre_hook(make_pre_hook(patch)))
        else:
            target = block.self_attn if patch["component"] == "attn" else block.mlp
            handles.append(target.register_forward_hook(make_hook(patch)))
    if torch.is_tensor(ids):
        ids = {"input_ids": ids, "attention_mask": torch.ones_like(ids)}
    try:
        logits = model(**ids).logits[0].detach()
    finally:
        for h in handles:
            h.remove()
    return logits


def answer_token_ids(tokenizer, answer: str) -> list[int]:
    """Token ids of ' ' + answer, generation-style."""
    return tokenizer(" " + answer, add_special_tokens=False)["input_ids"]


def divergence_index(ids_a: list[int], ids_b: list[int]) -> int:
    """First index where two token sequences differ (len if equal)."""
    n = min(len(ids_a), len(ids_b))
    for i in range(n):
        if ids_a[i] != ids_b[i]:
            return i
    return n


def first_answer_token_id(tokenizer, answer: str):
    """Token id of the first token of ' ' + answer (generation-style)."""
    return answer_token_ids(tokenizer, answer)[0]


@torch.inference_mode()
def token_logprob(logits: torch.Tensor, position: int, token_id: int) -> float:
    lp = torch.log_softmax(logits[position].float(), dim=-1)
    return float(lp[token_id].item())


def mediation_scan(model, tokenizer, task: dict, layers: list[int],
                   components: list[str] = ("attn", "mlp")) -> dict:
    """Counterfactual patching scan for one task.

    Metric: the answer's gold and counterfactual-gold token sequences share a
    common prefix and first diverge at token j.  The model commits to the
    discriminating token at position (prefix + j - 1).  We patch activations
    from the counterfactual run into the original run at the critical span
    positions and measure how much log p(cf token) - log p(orig token) at the
    commitment position moves toward the counterfactual.
    """
    cf = task["cf"]
    prompt_orig = build_prompt(task["category"], task["question"])
    prompt_cf = build_prompt(task["category"], cf["question"])

    gold_ids = answer_token_ids(tokenizer, task["gold"])
    cf_ids = answer_token_ids(tokenizer, cf["gold"])
    j = divergence_index(gold_ids, cf_ids)
    if j >= min(len(gold_ids), len(cf_ids)):
        return {"task": task["id"], "error": "gold and cf answers do not diverge", "scores": {}}
    tok_orig, tok_cf = gold_ids[j], cf_ids[j]
    shared = gold_ids[:j]  # identical prefix of both answers

    ids_orig = tokenize(tokenizer, prompt_orig)          # prompt only
    prefix_len = ids_orig.input_ids.shape[1]
    ids_commit = torch.cat([ids_orig.input_ids[0], torch.tensor(shared, dtype=torch.long)], 0).unsqueeze(0)
    pos_answer = prefix_len + j - 1                      # predicts token j

    with torch.inference_mode():
        logits_orig = model(ids_commit.clone(), attention_mask=torch.ones_like(ids_commit)).logits[0].detach()
    orig_gap = token_logprob(logits_orig, pos_answer, tok_cf) - token_logprob(logits_orig, pos_answer, tok_orig)

    # counterfactual run for patch source values (question side differs)
    ids_cf = tokenize(tokenizer, prompt_cf)
    ids_cf_commit = torch.cat([ids_cf.input_ids[0], torch.tensor(shared, dtype=torch.long)], 0).unsqueeze(0)

    pos_crit = [p for p in span_positions(tokenizer, prompt_orig, task["critical"]) if p < prefix_len]
    if not pos_crit:
        return {"task": task["id"], "error": "critical span not found", "scores": {}}

    # Session 011 audit fix: the counterfactual prompt can tokenize
    # differently (different identifiers, BPE merges, length).  Critical
    # positions for reading CF values are computed on the CF prompt itself
    # via char offsets; identical numerical indices are never assumed.
    cf_prefix_len = ids_cf.input_ids.shape[1]
    align = aligned_span_positions(tokenizer, prompt_orig, task["critical"],
                                   other_prompt=prompt_cf,
                                   other_span=cf["critical"])
    pos_crit_cf = [p for p in align.get("other_positions", []) if p < cf_prefix_len]
    if not pos_crit_cf:
        return {"task": task["id"], "error": "cf critical span not found",
                "alignment": align, "scores": {}}

    # capture cf activations at the cf critical positions (on the cf run)
    acts_cf = {}
    handles = []
    for L in layers:
        for comp in components:
            def hook(_m, _i, out, layer=L, c=comp):
                acts_cf[(layer, c)] = _block_output(out).detach()
            block = model.model.layers[L]
            target = block.self_attn if comp == "attn" else block.mlp
            handles.append(target.register_forward_hook(hook))
    try:
        with torch.inference_mode():
            model(ids_cf_commit.clone(), attention_mask=torch.ones_like(ids_cf_commit))
    finally:
        for h in handles:
            h.remove()

    results = {}
    for layer in layers:
        for comp in components:
            values = acts_cf[(layer, comp)][pos_crit_cf, :].clone()
            patched = patched_logits(
                model, tokenizer, ids_commit,
                [{"layer": layer, "component": comp, "positions": pos_crit, "values": values}],
            )
            gap = token_logprob(patched, pos_answer, tok_cf) - token_logprob(patched, pos_answer, tok_orig)
            results[f"L{layer}/{comp}"] = round(gap - orig_gap, 4)

    return {
        "task": task["id"],
        "orig_gap": round(orig_gap, 4),
        "divergence_index": j,
        "commit_position": pos_answer,
        "scores": results,
        "critical_positions": pos_crit,
        "cf_critical_positions": pos_crit_cf,
        "alignment": {k: v for k, v in align.items() if k in
                      ("index_shift", "tokenization_matches", "decoded", "other_decoded")},
    }


@torch.inference_mode()
def head_scan(model, tokenizer, task: dict, layer: int, n_heads: int = 14) -> dict:
    """Per-head patching within one attention layer (o_proj input slices).

    Uses the same divergence-commitment metric as mediation_scan: patch the
    head's 64-dim slice of the o_proj input at critical positions with the
    counterfactual run's values and measure the shift toward the cf token.
    """
    cf = task["cf"]
    prompt_orig = build_prompt(task["category"], task["question"])
    prompt_cf = build_prompt(task["category"], cf["question"])

    gold_ids = answer_token_ids(tokenizer, task["gold"])
    cf_ids = answer_token_ids(tokenizer, cf["gold"])
    j = divergence_index(gold_ids, cf_ids)
    if j >= min(len(gold_ids), len(cf_ids)):
        return {"task": task["id"], "layer": layer, "error": "no divergence", "scores": {}}
    tok_orig, tok_cf = gold_ids[j], cf_ids[j]
    shared = gold_ids[:j]

    head_inputs = {}

    def capture_hook(_m, inp, out):
        head_inputs["orig"] = inp[0].detach().clone()

    ids_orig = tokenize(tokenizer, prompt_orig)
    prefix_len = ids_orig.input_ids.shape[1]
    ids_commit = torch.cat([ids_orig.input_ids[0], torch.tensor(shared, dtype=torch.long)], 0).unsqueeze(0)
    pos_answer = prefix_len + j - 1

    handle = model.model.layers[layer].self_attn.o_proj.register_forward_hook(capture_hook)
    with torch.inference_mode():
        logits_orig = model(ids_commit.clone(), attention_mask=torch.ones_like(ids_commit)).logits[0].detach()
    handle.remove()

    def capture_cf(_m, inp, out):
        head_inputs["cf"] = inp[0].detach().clone()

    ids_cf = tokenize(tokenizer, prompt_cf)
    ids_cf_commit = torch.cat([ids_cf.input_ids[0], torch.tensor(shared, dtype=torch.long)], 0).unsqueeze(0)
    handle = model.model.layers[layer].self_attn.o_proj.register_forward_hook(capture_cf)
    with torch.inference_mode():
        model(ids_cf_commit.clone(), attention_mask=torch.ones_like(ids_cf_commit))
    handle.remove()

    orig_gap = token_logprob(logits_orig, pos_answer, tok_cf) - token_logprob(logits_orig, pos_answer, tok_orig)

    pos_crit = [p for p in span_positions(tokenizer, prompt_orig, task["critical"]) if p < prefix_len]
    if not pos_crit:
        return {"task": task["id"], "layer": layer, "error": "no critical positions", "scores": {}}

    # Session 011 audit fix: read CF head inputs at the CF prompt's own
    # critical positions (char-anchored), never at the original's indices.
    cf_prefix_len = ids_cf.input_ids.shape[1]
    align = aligned_span_positions(tokenizer, prompt_orig, task["critical"],
                                   other_prompt=prompt_cf,
                                   other_span=cf["critical"])
    pos_crit_cf = [p for p in align.get("other_positions", []) if p < cf_prefix_len]
    if not pos_crit_cf:
        return {"task": task["id"], "layer": layer, "error": "cf critical span not found",
                "alignment": align, "scores": {}}

    scores = {}
    for head in range(n_heads):
        s, e = head * 64, (head + 1) * 64
        values = head_inputs["cf"][0][pos_crit_cf, s:e].clone()
        patched = patched_logits(
            model, tokenizer, ids_commit,
            [{"layer": layer, "head": head, "positions": pos_crit, "values": values}],
        )
        gap = token_logprob(patched, pos_answer, tok_cf) - token_logprob(patched, pos_answer, tok_orig)
        scores[f"H{head}"] = round(gap - orig_gap, 4)
    return {"task": task["id"], "layer": layer, "orig_gap": round(orig_gap, 4),
            "scores": scores, "cf_critical_positions": pos_crit_cf,
            "alignment": {k: v for k, v in align.items() if k in
                          ("index_shift", "tokenization_matches")}}
