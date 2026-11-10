// TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE — Session 039B discrimination control.
// KNOWN-BAD (partial) control: filtering, case-insensitivity, envelope and
// totals are all correct, but the result is returned in fixture insertion
// order instead of title-ascending order. Exactly the list-all case (and
// any other order-sensitive case) must fail while the other cases pass;
// this proves the oracle checks ordering and does not pass "mostly right"
// implementations.
import { db } from "@/lib/db";

export async function GET(request: Request): Promise<Response> {
  const { searchParams } = new URL(request.url);
  const q = searchParams.get("q");
  const transmitterId = searchParams.get("transmitterId");
  const broadcasts = await db.broadcast.findMany({
    where: {
      ...(transmitterId ? { transmitterId } : {}),
    },
    include: { transmitter: true },
  });
  const needle = q ? q.toLowerCase() : null;
  const filtered = needle === null
    ? broadcasts
    : broadcasts.filter((row) => row.title.toLowerCase().includes(needle));
  return Response.json({ broadcasts: filtered, total: filtered.length });
}
