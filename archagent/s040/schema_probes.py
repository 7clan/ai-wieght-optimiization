"""Trusted behavioral probe script staged for the schema runner (teacher-authored).

The runner imports this INSIDE the restricted tier and passes the contract
facts; the probes exercise the candidate-built database through the
candidate-generated Prisma client. Parameterized by contract facts only.
"""

from __future__ import annotations

PROBE_MJS = """// TRUSTED Session-040 fixture — AUTHORED_PROBE_NOT_QWEN_CODE
import prismaPkg from "/work/generated-client/index.js";
const { PrismaClient } = prismaPkg;
const db = new PrismaClient();

const isForeignKeyError = (error) =>
  Boolean(error && (error.code === "P2003" || /foreign key/i.test(String(error.message))));

export async function runProbes(cfg) {
  const probes = [];
  const report = (name, passed, detail = "") => probes.push({ name, passed, detail: String(detail).slice(0, 160) });

  let parentId = null;
  try {
    const parent = await db[cfg.parentClient].create({ data: { id: "parent-a" } });
    parentId = parent.id;
    report("parent-create", true);
  } catch (error) {
    report("parent-create", false, error.message);
    await db.$disconnect();
    return { probes };
  }

  // Required child fields accepted.
  try {
    const child = await db[cfg.childClient].create({
      data: { [cfg.label]: "Probe One", [cfg.amount]: cfg.lo, [cfg.fk]: parentId },
    });
    report("child-required-fields-present", Boolean(child && child.id));
  } catch (error) {
    report("child-required-fields-present", false, error.message);
  }

  // Valid-FK create.
  try {
    const child = await db[cfg.childClient].create({
      data: { [cfg.label]: "Probe Two", [cfg.amount]: cfg.lo, [cfg.fk]: parentId },
    });
    report("child-create-valid-fk", Boolean(child && child.id));
  } catch (error) {
    report("child-create-valid-fk", false, error.message);
  }

  // FK nullability must match the contract mode.
  try {
    await db[cfg.childClient].create({
      data: { [cfg.label]: "NullFk Probe", [cfg.amount]: cfg.lo, [cfg.fk]: null },
    });
    report("fk-nullability-matches-contract", cfg.fkOptional === true);
  } catch (error) {
    report("fk-nullability-matches-contract", cfg.fkOptional === false,
      cfg.fkOptional ? "contract says optional but null FK rejected: " + error.message : "");
  }

  // Bogus FK rejected (P2003).
  try {
    await db[cfg.childClient].create({
      data: { [cfg.label]: "Bogus Probe", [cfg.amount]: cfg.lo, [cfg.fk]: "no-such-parent" },
    });
    report("bogus-fk-rejected", false, "bogus FK accepted");
  } catch (error) {
    report("bogus-fk-rejected", isForeignKeyError(error), "err: " + error.code);
  }

  // onDelete semantics: optional -> SetNull (child survives, FK null);
  // required -> Restrict (parent delete refused while children exist).
  try {
    const own = await db[cfg.parentClient].create({ data: { id: "parent-probe" } });
    const row = await db[cfg.childClient].create({
      data: { [cfg.label]: "Delete Probe", [cfg.amount]: cfg.lo, [cfg.fk]: own.id },
    });
    try {
      await db[cfg.parentClient].delete({ where: { id: own.id } });
      if (cfg.fkOptional) {
        const survivor = await db[cfg.childClient].findUnique({ where: { id: row.id } });
        report("on-delete-semantics", Boolean(survivor && survivor[cfg.fk] === null),
          "survivor fk: " + (survivor ? survivor[cfg.fk] : "gone"));
      } else {
        report("on-delete-semantics", false, "required-FK parent delete allowed (Restrict missing)");
      }
    } catch (error) {
      if (cfg.fkOptional) {
        report("on-delete-semantics", false, "optional-FK delete failed: " + error.code);
      } else {
        report("on-delete-semantics", isForeignKeyError(error), "err: " + error.code);
      }
    }
  } catch (error) {
    report("on-delete-semantics", false, error.message);
  }

  // Persisted status default equals workflow[0].
  try {
    const fresh = await db[cfg.childClient].create({
      data: { [cfg.label]: "Status Probe", [cfg.amount]: cfg.lo, [cfg.fk]: parentId },
    });
    report("status-default", fresh.status === cfg.initialStatus,
      "got: " + JSON.stringify(fresh.status) + " want: " + JSON.stringify(cfg.initialStatus));
  } catch (error) {
    report("status-default", false, error.message);
  }

  await db.$disconnect();
  return { probes };
}
"""


def probe_mjs() -> str:
    return PROBE_MJS
