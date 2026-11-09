# SESSION 037 — PHASE 1: SESSION-036 ROOT-CAUSE REPORT

Everything below is derived from the archived Session-036 artifacts
(`experiments/z036-roomreserve/`, `experiments/z036/`) by the
reproducible script `taxonomy.py` (same directory; output
`taxonomy.json`). No model was run for this analysis.

## The nine investigation questions

### 1. Why did `exact_shape` dominate the fixed controller?

It was the **only strategy whose prompt was valid for generation
contracts**. `exact_shape` sent concept + demo + spec + anchor with the
contract's token budget (300–900). Every other armed strategy was
designed for *repair* (existing code + diagnosis + region) and was
degenerate when applied to *generation*:

- `ast_replace` / `minimal_diff` / `fim_micro`: FIM over an **empty
  region** (the target file does not exist yet), instruction
  "rewrite this one statement to satisfy: …" with no statement present;
- `contract_split`: emitted the literal placeholder
  `Piece: the required element.` — 20/20 archived prompts contain the
  unfilled placeholder;
- `compiler_guided`: no tsc in the generation phase → silently degraded
  to `fim_micro`;
- `doc_lookup`: valid spec but 88% parse-reject (framework prose pulls
  the 0.5B into documentation echo).

Parse-failure rates (Track C): exact_shape 33%, regen_whole 36%,
fim_micro 20% — versus ast_replace 73%, compiler_guided 64%,
minimal_diff 69%, doc_lookup 88%. `exact_shape` dominated because the
alternatives were broken for the job, not because whole-file generation
is intrinsically optimal.

### 2. Why did the bandit explore strategies that repeatedly failed?

Thompson sampling over 9 arms with 8 attempts per contract cannot
concentrate: each attempt moves one Beta posterior by one count. The
Session-035-mined priors covered only `body_completion` and `fim_micro`
arms; the other seven arms — including all five degenerate strategies —
started at Beta(1,1), i.e. **indistinguishable from the empirically
strongest strategy**. The final Track-C posteriors confirm the loss:
best `missing_literal` arm ended at 0.29.

There was also **no within-attempt credit**: a candidate that missed by
one clause (reservations-route #5) earned the same reward (0) as an
empty candidate, so the bandit could not see that `exact_shape` was
95% correct on that contract.

### 3. Were previous-task priors incorrectly transferred?

Partially. `body_completion|missing_call` [6,2] transferred correctly
(final posterior 0.56 — the bandit DID learn real within-category
structure). But `missing_literal`'s prior evidence
(`body_completion` [3,45], `fim_micro` [0,23]) described Session-035's
*whole-file* UI failures, not this task's demo-complete contracts — the
negative evidence pushed away from a family that had changed shape,
while the seven unprior-ed arms looked maximally attractive. Absence of
evidence was treated as equal attractiveness to the strong default.

### 4. Were attempts rewarded for syntactic validity rather than behavioral correctness?

Yes. The scored tracks ran with `probe=None` — acceptance was
structural-gates only. The POST-listing hook (passed every gate, fetched
the list via POST) is the documented consequence. Additionally the
binary reward ignored *closeness*, wasting the strongest learning
signal available (near-miss detection).

### 5. Did the model receive too much information in individual prompts?

Both tails failed:
- **Too much**: reservations-route = 198 words / 24 clauses in one shot
  (spec: 5 GET filters + 10 POST branches). rooms/page contracts failed
  on integration. But clause count alone is not destiny —
  reservation-id-route (135 words / 15 clauses) resolved in both tracks.
  The binding variable is *integration surface* (clauses × distinct
  cross-referenced identifiers).
- **Too little**: the degenerate micro strategies sent essentially zero
  context (empty FIM regions).

The sweet spot in the archived data: demo-complete whole-file contracts
of 46–100 words (all six Track-B UI/hook/component wins sit there).

### 6. Why did Prisma relations and time-window reasoning remain difficult?

**Relations — genuine model gap.** 0/16 attempts produced a valid
relation pair. Best case (`exact_shape-1`, Track B): both fragments
present but malformed — bare `@relation(...)` attribute lines with no
field name/type. Typical failure: self-relation hallucination
(`rooms [Room!] @relation(fields:[roomId])` *inside* model Room). The
schema demo (FitnessClass) contained **no relation at all**, so the
model had no in-context pattern to adapt. This is a curriculum+demo
failure layered on a real capability limit.

**Time-window — NOT intrinsically impossible.** Exhibit E1: Track-B
reservations-route attempt 5 contains a correctly *adapted* overlap
check —

```ts
const clash = await db.reservation.findFirst({
  where: { roomId, status: 'confirmed',
           start: { lt: body.end }, end: { gt: body.start } } })
if (clash) return NextResponse.json(
  { error: 'Time conflict with an existing reservation' }, { status: 409 })
```

— using **target** identifiers, right status code, right message. It
was rejected for exactly one missing clause (`db.room.findUnique` 404
check) plus demo remnants (`treatments`, `stylist ?? 'spa'`). **The
"zero-teacher overlap logic unsuccessful" verdict was a
contract-granularity failure, not an interval-reasoning failure.** The
spa demo contained the overlap pattern; when the target piece matched
the demo's shape, the 0.5B adapted it correctly.

### 7. Did the repair controller itself misclassify errors?

The *categorization* was sound (missing_export for routes,
missing_literal for UI, wrong_contract for schema/types). The failure
was downstream: (a) categories indexed arms that included the five
degenerate strategies; (b) `_token_from_failures` regexes
(`missing 'X'`, `'X' not found`) match neither the verify system's
`'GET' not exported` nor `Room.floor missing` formats, so micro
strategies were token-blind exactly where they were sampled; (c) no
behavioral channel existed at all (H4).

### 8. Was generating an entire function too difficult when a smaller expression would suffice?

The evidence is two-sided:
- For **initial generation**, whole-file `exact_shape` was the only
  working mode (the micro strategies' failure was harness-made).
- For **verified near-misses**, the opposite holds: reservations-route
  #5 needed one call + one branch — a bounded micro-repair would
  plausibly have completed it. The Session-036 controller never ran
  micro-repairs on structurally-verified near-misses because its
  generation loop only retried the same strategy family.

**Design consequence for Session 037:** whole-file generation to get a
verifiable base, then smallest-contract decomposition + micro-repair
driven by verified gate/behavior evidence.

## Failure taxonomy (three sources, reproducible counts)

| Source | Count | Items |
|---|---|---|
| Harness/strategy | 5 | H1 degenerate prompts (53/87 Track-C attempts used the five broken strategies); H2 token-extractor blind to verify formats; H3 micro token starvation (48–120 tokens); H4 no behavioral probe in-loop; H5 no early-EOS mitigation — **46/147 archived candidates (31%) were near-empty** (anchor echoed, then EOS) |
| Strategy/prompt | 4 | P1 contract granularity (overlap piece producible, 14-clause integration not); P2 demo-shape leakage (3-member demo interface → `floor` dropped in 8 types rejects; relation-free schema demo); P3 raw gate-failure text as feedback (regen_whole 1 win/14); P4 demo-verbatim copying on near-match specs |
| Model capability | 4 | M1 Prisma relation grammar 0/16; M2 member-typing discipline (`floor: string`, literal-union leaks); M3 cross-clause integration; M4 prose rambling after code |

## Consequences for the Session-037 design

1. **TaskIR pieces, not mega-contracts**: decompose routes into
   handler-level contracts with ≤6 clauses each; the overlap check
   becomes its own contract (proven producible, Exhibit E1).
2. **Anchor inside the construct** (e.g. the handler signature line),
   never the file's first import — early-EOS (H5) becomes mechanically
   detectable and retryable at near-zero cost.
3. **Near-empty detection + re-anchor retry** before scoring a strategy
   failure.
4. **Demo-completeness law, extended**: the demo must contain every
   construct shape the contract requires (relations for relation
   contracts, with different domain identifiers).
5. **Fix the token extractor** (H2): parse the verify system's actual
   message formats so micro-repairs anchor on the real gap.
6. **Behavioral probes in-loop** (H4): one cheap live check per route
   contract (dev-server + model coexistence is affordable).
7. **Near-miss-aware policy**: "1–2 failing clauses with the rest
   intact" switches to micro-repair instead of re-rolling whole files;
   repeated identical failure signatures stop early (budget-aware).
8. **Conservative exploration**: start every contract family on the
   empirically strongest strategy; explore only with justified expected
   benefit (Session-036 §14 recommendation, now evidence-backed).
