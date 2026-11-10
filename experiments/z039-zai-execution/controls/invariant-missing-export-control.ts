// TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE — Session 039B fail-closed control.
// KNOWN-BAD control: exports the wrong name (canAdvanceShip instead of the
// required canAdvanceBroadcast). The evaluator must report
// export-present=false and fail closed.
export function canAdvanceShip(from: string, to: string): boolean {
  return from !== to;
}
