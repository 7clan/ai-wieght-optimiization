"""Mechanical installation of generated code into the live preview
workspace (/home/z/my-project) — TRUSTED-SCAFFOLD.

This module contains ZERO intelligence about the application: it
extracts files by their marker lines, writes them to disk, runs the
declared mechanical commands (prisma db push), backs up and restores
the workspace, and syncs the installed tree into the research repo
worktree.  Every action here is disclosed scaffolding and is never
counted as model capability.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

APP = Path("/home/z/my-project")
WORK = Path("/home/z/s035")
BACKUP = WORK / "experiments/zai-fullstack/workspace-backup"

# Files/dirs of the application surface (what generation may touch).
SURFACE = [
    "src/app/page.tsx",
    "src/app/api/items",
    "src/components/stockpilot",
    "src/lib/inventory",
    "prisma/schema.prisma",
]

MARKER = re.compile(
    r"^=== FILE: (.+?) ===\s*$", re.MULTILINE)


def extract_files(text: str) -> dict[str, str]:
    """Split a completion on '=== FILE: path ===' markers."""
    out: dict[str, str] = {}
    hits = list(MARKER.finditer(text))
    for i, m in enumerate(hits):
        path = m.group(1).strip()
        # strip the "(model block only)" style annotations
        path = re.sub(r"\s*\(.*\)\s*$", "", path).strip()
        start = m.end()
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        body = text[start:end].strip("\n")
        # drop trailing prose after the last balanced block
        out[path] = body
    return out


def backup_workspace() -> None:
    BACKUP.mkdir(parents=True, exist_ok=True)
    for rel in SURFACE:
        src = APP / rel
        dst = BACKUP / rel
        if dst.exists():
            shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst) if src.is_file() else shutil.copytree(src, dst)


def restore_workspace() -> None:
    """Restore the surface to the last backup (removes generated files)."""
    for rel in SURFACE:
        src = BACKUP / rel
        dst = APP / rel
        if dst.exists():
            shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst) if src.is_file() else shutil.copytree(src, dst)


def install_files(files: dict[str, str]) -> list[str]:
    """Write extracted files into the workspace. Returns paths written."""
    written = []
    for rel, body in files.items():
        # Safety: only allow paths inside the declared surface dirs.
        norm = re.sub(r"^\./", "", rel)
        if not any(norm == s or norm.startswith(s + "/") for s in SURFACE):
            continue
        target = APP / norm
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body + "\n")
        written.append(norm)
    return written


def merge_schema_block(model_block: str) -> bool:
    """Insert/replace the InventoryItem model in prisma/schema.prisma.
    Mechanical: keeps every other model untouched."""
    schema = APP / "prisma/schema.prisma"
    text = schema.read_text()
    block = model_block.strip()
    if "model InventoryItem" in text:
        text = re.sub(
            r"model InventoryItem \{.*?\n\}", block, text, flags=re.DOTALL)
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    schema.write_text(text)
    return True


def db_push() -> tuple[bool, str]:
    r = subprocess.run(["bun", "run", "db:push"], cwd=str(APP),
                       capture_output=True, text=True, timeout=180)
    return r.returncode == 0, (r.stdout + r.stderr)[-600:]


def run_cmd(cmd: list[str], cwd: Path, timeout: int = 240) -> dict:
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       timeout=timeout)
    return {"exit": r.returncode, "out": (r.stdout + r.stderr)[-4000:]}


def sync_to_worktree(origin: dict) -> None:
    """Copy the installed application surface into the research repo
    (apps/stockpilot) plus an ORIGIN.json provenance record."""
    dst_root = WORK / "apps/stockpilot"
    dst_root.mkdir(parents=True, exist_ok=True)
    for rel in SURFACE:
        src = APP / rel
        dst = dst_root / rel
        if dst.exists():
            shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst) if src.is_file() else shutil.copytree(src, dst)
    (dst_root / "ORIGIN.json").write_text(
        json.dumps(origin, indent=2, ensure_ascii=False) + "\n")


def sha256_of(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()
