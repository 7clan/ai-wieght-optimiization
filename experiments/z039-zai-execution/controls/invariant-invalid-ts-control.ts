// TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE — Session 039B fail-closed control.
// KNOWN-BAD control: syntactically invalid TypeScript. The evaluator must
// produce a fail-closed verdict (candidate import failure), never a crash
// of the harness and never a pass.
export function canAdvanceBroadcast(from: string, to: string): boolean {
  this is not valid typescript @@
}
