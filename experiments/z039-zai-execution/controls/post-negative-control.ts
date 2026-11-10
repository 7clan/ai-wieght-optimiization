// TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE — Session 039B oracle validation only.
// KNOWN-BAD control: it writes a demo row BEFORE validating anything and
// always answers 400. The evaluator MUST fail this control on the
// no-write-on-error cases (persist deltas on 400 must be 0) and on every
// 201 case; if it passes, the persistence probes are broken and must be
// fixed before any model output is scored.
import { db } from "@/lib/db";

export async function POST(request: Request): Promise<Response> {
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  await db.broadcast.create({
    data: {
      title: typeof body.title === "string" && body.title.trim() ? body.title.trim() : "demo row",
      airtimeMin: 1,
      transmitterId: "parent-a",
      status: "drafted",
    },
  });
  return Response.json({ error: "demo always writes before validating" }, { status: 400 });
}
