import { db } from "@/lib/db";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const search = params.get("search") ?? "";
  const status = params.get("status") ?? "";
  const rows = await db.sensor.findMany({
    where: {
      ...(search ? { label: { contains: search } } : {}),
      ...(status ? { status } : {}),
    },
    orderBy: { reading: "asc" },
  });
  const filtered = rows.filter((row) =>
    (!search || row.label.toLowerCase().includes(search.toLowerCase()))
    && (!status || row.status === status));
  return Response.json({ sensors: filtered, total: filtered.length });
}