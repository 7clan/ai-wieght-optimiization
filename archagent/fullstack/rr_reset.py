"""SESSION 036 — workspace reset between RoomReserve tracks (mechanical).

Removes the previous application surface (StockPilot leftovers or a
prior track's candidates) so each track starts from the identical
TRUSTED-SCAFFOLD baseline.  No application bytes are added.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

WS = Path("/home/z/my-project")

REMOVE = [
    "src/app/page.tsx",
    "src/app/api/items",
    "src/app/api/rooms",
    "src/app/api/reservations",
    "src/lib/inventory",
    "src/lib/roomreserve",
    "src/components/stockpilot",
    "src/components/roomreserve",
    "scripts/wipe-inventory.ts",
]

SCAFFOLD_SCHEMA = """generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  url      = env("DATABASE_URL")
}

model User {
  id        String   @id @default(cuid())
  email     String   @unique
  name      String?
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}

model Post {
  id        String   @id @default(cuid())
  title     String
  content   String?
  published Boolean  @default(false)
  authorId  String
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}
"""


def main() -> None:
    for rel in REMOVE:
        p = WS / rel
        if p.is_dir():
            subprocess.run(["rm", "-rf", str(p)])
        elif p.exists():
            p.unlink()
    (WS / "prisma/schema.prisma").write_text(SCAFFOLD_SCHEMA)
    r = subprocess.run(["bun", "run", "db:push"], cwd=str(WS),
                       capture_output=True, text=True, timeout=240)
    ok = r.returncode == 0
    print("db:push", "OK" if ok else r.stderr[-200:])
    print("workspace reset to RoomReserve scaffold baseline")


if __name__ == "__main__":
    sys.exit(main())
