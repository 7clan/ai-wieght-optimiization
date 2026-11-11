// TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE — Session 041C oracle validation only.
// KNOWN-BAD control for the corrected duplicate-title probe: byte-for-byte
// the spec-faithful positive control EXCEPT the duplicate check is GLOBALLY
// scoped by title (no transmitterId in the where clause) — the exact
// contract violation ("Reject duplicate title within one Transmitter")
// that the 039B probe plan could not detect and that produced the
// Session-041B merged-model Track-B false pass. The corrected evaluator
// MUST fail this control on duplicate-title-other-parent (a title used by
// another transmitter's row must be accepted with 201) and pass every
// other probe; if this control passes, the scope amendment is broken and
// no model output may be scored.
import { db } from "@/lib/db";

const MIN_AIRTIME = 1;
const MAX_AIRTIME = 360;

interface CreateBroadcastBody {
  title?: unknown;
  airtimeMin?: unknown;
  transmitterId?: unknown;
}

export async function POST(request: Request): Promise<Response> {
  let body: CreateBroadcastBody;
  try {
    body = (await request.json()) as CreateBroadcastBody;
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }
  const rawTitle = typeof body?.title === "string" ? body.title.trim() : "";
  if (!rawTitle) {
    return Response.json({ error: "title is required" }, { status: 400 });
  }
  const airtimeMin = body?.airtimeMin;
  if (typeof airtimeMin !== "number"
      || !Number.isInteger(airtimeMin)
      || airtimeMin < MIN_AIRTIME
      || airtimeMin > MAX_AIRTIME) {
    return Response.json({ error: "airtimeMin must be an integer within 1..360" }, { status: 400 });
  }
  const transmitterId = body?.transmitterId;
  let scope: string | null;
  if (transmitterId === null || transmitterId === undefined) {
    scope = null; // optional foreign key: null is allowed
  } else if (typeof transmitterId !== "string" || transmitterId === "") {
    return Response.json({ error: "transmitterId must be a string or null" }, { status: 400 });
  } else {
    const transmitter = await db.transmitter.findUnique({ where: { id: transmitterId } });
    if (!transmitter) {
      return Response.json({ error: "Unknown transmitter" }, { status: 404 });
    }
    scope = transmitterId;
  }
  // KNOWN-BAD: global title scope — the transmitterId is deliberately
  // missing from the where clause.
  const duplicate = await db.broadcast.findFirst({
    where: { title: rawTitle },
  });
  if (duplicate) {
    return Response.json({ error: "A broadcast with this title already exists for the transmitter" },
                         { status: 409 });
  }
  const created = await db.broadcast.create({
    data: { title: rawTitle, airtimeMin, transmitterId: scope, status: "drafted" },
  });
  return Response.json({ broadcast: created }, { status: 201 });
}
