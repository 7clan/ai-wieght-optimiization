// TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE — Session 039B timeout control.
// KNOWN-BAD control: the GET handler never resolves (asynchronous hang).
// The per-probe timeout must fail every case within the bounded probe
// window and the overall verdict must be fail-closed, not an unbounded
// hang of the evaluator. (Synchronous infinite loops are instead bounded
// by the container-level timeout and equally fail closed.)
import { db } from "@/lib/db";

export async function GET(request: Request): Promise<Response> {
  void request;
  void db;
  await new Promise(() => {});
  return Response.json({ broadcasts: [], total: 0 });
}
