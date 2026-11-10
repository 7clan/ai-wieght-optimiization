// SESSION040 GearHut — attribution: TEACHER-CORRECTED (frozen spec §route_contract
// teacher_extensions). The PATCH handler makes the QWEN-REPAIRED invariant
// (src/lib/gear-invariant.ts) load-bearing: an item may only advance one
// workflow stage (stashed -> inspected -> retired) when the invariant accepts
// the CURRENT record. DELETE removes the item.

import { db } from "@/lib/db";
import { canAdvanceGearItem } from "@/lib/gear-invariant";

const WORKFLOW = ["stashed", "inspected", "retired"] as const;

export async function PATCH(request: Request,
                            { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await request.json().catch(() => null);
  if (!body || typeof body.status !== "string") {
    return Response.json({ error: "status is required" }, { status: 400 });
  }
  const item = await db.gearItem.findUnique({ where: { id }, include: { locker: true } });
  if (!item) {
    return Response.json({ error: "item not found" }, { status: 404 });
  }
  const currentIndex = WORKFLOW.indexOf(item.status as typeof WORKFLOW[number]);
  const nextStage = currentIndex >= 0 && currentIndex < WORKFLOW.length - 1
    ? WORKFLOW[currentIndex + 1] : null;
  if (nextStage === null || body.status !== nextStage) {
    return Response.json(
      { error: `from "${item.status}" the only allowed next status is "${nextStage ?? "none"}"` },
      { status: 409 });
  }
  if (!canAdvanceGearItem(item, item.locker)) {
    return Response.json(
      { error: `invariant rejected the transition from "${item.status}"` },
      { status: 409 });
  }
  const updated = await db.gearItem.update({ where: { id }, data: { status: body.status } });
  return Response.json(updated);
}

export async function DELETE(_request: Request,
                             { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const item = await db.gearItem.findUnique({ where: { id } });
  if (!item) {
    return Response.json({ error: "item not found" }, { status: 404 });
  }
  await db.gearItem.delete({ where: { id } });
  return new Response(null, { status: 204 });
}
