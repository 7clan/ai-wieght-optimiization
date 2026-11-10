// SESSION040 GearHut — attribution:
//   POST: QWEN_GENERATED (frozen model, greedy; integrated verbatim from
//         app/evidence/gearhut__api-post-validation.json — passed its gate
//         at attempt 1 with zero repairs)
//   GET:  TEACHER-CORRECTED (the model's attempt was a near-verbatim copy of
//         the greenhouse demo: db.sensor / orderBy reading / { sensors }
//         envelope — the documented demo-vocabulary failure mode; corrected
//         to the frozen app contract: db.gearItem, orderBy label, { gear },
//         status=all handling, LOWER()-safe case-insensitive search)
//         Original archived in app/generated/route-get.ts.

import { db } from "@/lib/db";

// TEACHER-CORRECTED GET (vocabulary + contract corrections marked inline)
export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const search = params.get("search") ?? "";
  const status = params.get("status") ?? "";
  const rows = await db.gearItem.findMany({                       // was db.sensor
    where: {
      ...(search ? { label: { contains: search } } : {}),           // was label contains on Sensor
      ...(status && status !== "all" ? { status } : {}),            // added: all/empty = no filter
    },
    orderBy: { label: "asc" },                                      // was reading asc
  });
  const filtered = rows.filter((row) =>
    (!search || row.label.toLowerCase().includes(search.toLowerCase()))
    && (!status || status === "all" || row.status === status));
  return Response.json({ gear: filtered, total: filtered.length }); // was { sensors }
}

// QWEN_GENERATED POST (verbatim)
export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  if (!body || typeof body.label !== "string" || body.label.trim() === "") {
    return Response.json({ error: "label is required" }, { status: 400 });
  }
  const usageHours = Number(body.usageHours);
  if (!Number.isInteger(usageHours) || usageHours < 0 || usageHours > 2000) {
    return Response.json({ error: "usageHours must be 0..2000" }, { status: 400 });
  }
  const locker = await db.gearLocker.findUnique({ where: { id: body.lockerId } });
  if (!locker) {
    return Response.json({ error: "locker not found" }, { status: 404 });
  }
  const duplicate = await db.gearItem.findFirst({ where: { label: body.label.trim() } });
  if (duplicate) {
    return Response.json({ error: "label already exists" }, { status: 409 });
  }
  const item = await db.gearItem.create({
    data: {
      label: body.label.trim(),
      usageHours,
      lockerId: body.lockerId,
      status: "stashed",
    },
  });
  return Response.json(item, { status: 201 });
}
