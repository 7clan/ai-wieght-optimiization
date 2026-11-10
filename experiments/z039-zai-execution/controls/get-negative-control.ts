// TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE — Session 039B oracle validation only.
// KNOWN-BAD control: it ignores the query entirely and returns a hardcoded
// copy of the demo fixture rows. The evaluator MUST fail this control on
// the filter cases (filter-one, case-insensitive, filter-by-parent,
// no-matches, combined-filter); if it passes, the oracle cannot
// discriminate real filtering from fixture copying and must be fixed
// before any model output is scored.
import { db } from "@/lib/db";

export async function GET(request: Request): Promise<Response> {
  void request;
  void db;
  return Response.json({
    broadcasts: [
      {
        id: "demo-a",
        title: "Amber",
        airtimeMin: 1,
        transmitterId: "parent-a",
        status: "drafted",
        transmitter: { id: "parent-a" },
      },
      {
        id: "demo-b",
        title: "Beacon",
        airtimeMin: 3,
        transmitterId: "parent-b",
        status: "aired",
        transmitter: { id: "parent-b" },
      },
      {
        id: "demo-c",
        title: "Cobalt",
        airtimeMin: 2,
        transmitterId: "parent-a",
        status: "cleared",
        transmitter: { id: "parent-a" },
      },
    ],
    total: 3,
  });
}
