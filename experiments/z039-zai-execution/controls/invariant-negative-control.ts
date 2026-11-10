// TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE — Session 039B oracle validation only.
// KNOWN-BAD control: it copies the generic demo stage vocabulary ("raw" ->
// "edited" -> "reviewed") instead of the radiostation domain states
// (drafted -> cleared -> aired). The invariant evaluator MUST fail this
// control on the exact domain states; if it passes, the oracle is broken
// and no model output may be scored until the harness is fixed.
export function canAdvanceBroadcast(from: string, to: string): boolean {
  if (from === "raw" && to === "edited") {
    return true;
  }
  if (from === "edited" && to === "reviewed") {
    return true;
  }
  return false;
}
