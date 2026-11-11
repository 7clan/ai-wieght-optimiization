import { db } from "@/lib/db";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  if (!body || typeof body.title !== "string" || body.title.trim() === "") {
    return Response.json({ error: "title is required" }, { status: 400 });
  }
  const airtimeMin = Number(body.airtimeMin);
  if (!Number.isInteger(airtimeMin) || airtimeMin < 1 || airtimeMin > 360) {
    return Response.json({ error: "airtimeMin must be 1..360" }, { status: 400 });
  }
  if (body.transmitterId) {
    const transmitter = await db.transmitter.findUnique({ where: { id: body.transmitterId } });
    if (!transmitter) {
      return Response.json({ error: "transmitter not found" }, { status: 404 });
    }
  }
  const duplicate = await db.broadcast.findFirst({ where: { title: body.title.trim() } });
  if (duplicate) {
    return Response.json({ error: "title already exists" }, { status: 409 });
  }
  const broadcast = await db.broadcast.create({
    data: {
      title: body.title.trim(),
      airtimeMin,
      ...(body.transmitterId ? { transmitterId: body.transmitterId } : {}),
      status: "drafted",
    },
  });
  return Response.json(broadcast, { status: 201 });
}