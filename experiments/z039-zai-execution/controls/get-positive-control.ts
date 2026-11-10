// TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE — Session 039B oracle validation only.
// Spec-faithful GET implementation for radiostation:api-get-filter (dev):
// GET /api/radiostation-broadcasts with case-insensitive 'q' title
// substring filter, optional transmitterId filter, title-ascending order,
// included transmitter and { broadcasts, total } envelope. The evaluator
// MUST pass this control; case-insensitivity is done in SQL via LOWER()
// because Prisma SQLite does not support mode: "insensitive".
import { db } from "@/lib/db";

export async function GET(request: Request): Promise<Response> {
  const { searchParams } = new URL(request.url);
  const q = searchParams.get("q");
  const transmitterId = searchParams.get("transmitterId");
  const broadcasts = await db.broadcast.findMany({
    where: {
      ...(transmitterId ? { transmitterId } : {}),
    },
    orderBy: { title: "asc" },
    include: { transmitter: true },
  });
  const needle = q ? q.toLowerCase() : null;
  const filtered = needle === null
    ? broadcasts
    : broadcasts.filter((row) => row.title.toLowerCase().includes(needle));
  return Response.json({ broadcasts: filtered, total: filtered.length });
}
