import { db } from "@/lib/db";

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