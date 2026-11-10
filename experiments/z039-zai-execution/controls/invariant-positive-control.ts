// TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE — Session 039B oracle validation only.
// This file is never used as a model prompt, target solution or training
// example. It exists so the invariant evaluator can be proven to PASS a
// spec-faithful implementation before any model-generated candidate is
// scored. Task: radiostation:state-invariant (dev), workflow
// drafted -> cleared -> aired, export canAdvanceBroadcast.
export function canAdvanceBroadcast(from: string, to: string): boolean {
  if (typeof from !== "string" || typeof to !== "string") {
    return false;
  }
  if (from === to) {
    return false;
  }
  const order: Record<string, number> = { drafted: 0, cleared: 1, aired: 2 };
  const a = order[from];
  const b = order[to];
  return a !== undefined && b !== undefined && b === a + 1;
}
