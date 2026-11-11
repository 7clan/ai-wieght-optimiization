// TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE — Session 039B oracle validation only.
// Spec-faithful POST implementation for radiostation:api-post-validation
// (dev): POST /api/radiostation-broadcasts with trimmed-title validation,
// finite-integer airtimeMin within 1..360, Transmitter existence check
// (404), duplicate title within one transmitter (409), create only after
// every check (201) and status created as "drafted". The evaluator MUST
// pass this control on all eleven cases (the 039B plan plus the 041C
// duplicate-title scope amendment).
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
  const duplicate = await db.broadcast.findFirst({
    where: { title: rawTitle, transmitterId: scope },
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
