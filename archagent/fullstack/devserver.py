"""Dev-server lifecycle helper (TRUSTED-SCAFFOLD).

The sandbox has 3.9GB RAM; the fp32 model + generation peaks near
3GB, which cannot coexist with the dev server (~0.9GB).  Generation
phases therefore stop the dev server and testing phases restart it.
"""
from __future__ import annotations

import subprocess
import time
import urllib.request
import urllib.error
from pathlib import Path

APP = Path("/home/z/my-project")


def dev_up() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:3000/",
                                    timeout=5) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def stop_dev() -> None:
    for _ in range(3):
        subprocess.run(["pkill", "-f", "next dev -p 3000"],
                       capture_output=True)
        subprocess.run(["pkill", "-f", "next-server"], capture_output=True)
        subprocess.run(["pkill", "-f", "bun run dev"], capture_output=True)
        subprocess.run(["pkill", "-f", "postcss.js"], capture_output=True)
        time.sleep(2)
        if not dev_up():
            break
    # wait for the port to actually free
    for _ in range(20):
        r = subprocess.run(["bash", "-c",
                            "ss -ltn 2>/dev/null | grep -c ':3000 ' || true"],
                           capture_output=True, text=True)
        if r.stdout.strip() in ("0", ""):
            break
        time.sleep(1)
    print(f"[devserver] stopped (up={dev_up()})")


def start_dev() -> None:
    if dev_up():
        print("[devserver] already up")
        return
    # Daemonized (double-fork) so the server survives the spawning
    # tool call's cleanup — plain nohup/setsid children do NOT.
    daemon = Path(__file__).parent / "daemonize.py"
    subprocess.run(
        ["/home/z/.venv/bin/python3", str(daemon),
         str(APP / "dev.log"), "--", "bash", "-c",
         f"cd {APP} && exec node_modules/.bin/next dev -p 3000 >> dev.log 2>&1"],
        check=True, capture_output=True)
    t0 = time.time()
    while time.time() - t0 < 120:
        if dev_up():
            print(f"[devserver] up after {time.time() - t0:.0f}s")
            time.sleep(3)  # settle
            return
        time.sleep(2)
    raise RuntimeError("dev server did not come up within 120s")


def restart_dev() -> None:
    stop_dev()
    start_dev()
