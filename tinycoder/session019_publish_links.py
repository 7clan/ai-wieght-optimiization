"""Add immutable static preview URLs to the branch README after gallery commit.

raw.githack serves public GitHub HTML with the correct content type. Links are
commit-pinned so a later benchmark cannot silently change a visual preview.
GitHub Pages can replace this host after Pages is enabled in repo settings.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


REPO = "7clan/ai-wieght-optimiization"
BEGIN = "<!-- APP-PREVIEW-GALLERY-START -->"
END = "<!-- APP-PREVIEW-GALLERY-END -->"


def publish(readme: Path, manifest: Path, revision: str, directory: str):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Use a full immutable git commit SHA for preview links")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    apps = data["apps"]
    if len(apps) != 10 or len({item["slug"] for item in apps}) != 10:
        raise ValueError("Expected ten distinct rendered app destinations")
    for app in apps:
        if (not re.fullmatch(r"[a-z0-9-]+", app["slug"])
            or app["page"] != app["slug"] + ".html"
            or not (manifest.parent / app["page"]).is_file()):
            raise ValueError("Invalid or missing preview page")
    base = f"https://raw.githack.com/{REPO}/{revision}/{directory.strip('/')}"
    lines = [
        "## Visual application previews — Session 018",
        "",
        "Every generated application now has an actual React UI render you can open",
        "in a browser, even if it failed the execution tests. These are **static,",
        "sandbox-rendered visual snapshots** with public example data, not live",
        "Express/Python deployments. No generated JavaScript runs in your browser.",
        "",
        f"**[Open all ten applications in the visual gallery]({base}/index.html)**",
        "",
        "| Application | Preview | Full-stack holdout |",
        "| --- | --- | --- |",
    ]
    for app in apps:
        status = "Passed" if app["integrated_holdout_passed"] else "Failed"
        lines.append(f"| `{app['slug']}` | [View UI]({base}/{app['page']}) | {status} |")
    lines += ["", "Static pages are hosted via a third-party raw-file preview CDN",
              "from a public GitHub commit; use GitHub Pages if you prefer first-party",
              "hosting. Each page includes the generated Python, Express and React",
              "source and the verified test outcomes.", "", ""]
    text = readme.read_text(encoding="utf-8")
    block = "\n".join(lines)
    if BEGIN in text or END in text:
        if text.count(BEGIN) != 1 or text.count(END) != 1:
            raise ValueError("Malformed existing gallery markers")
        prefix, rest = text.split(BEGIN, 1)
        _, suffix = rest.split(END, 1)
        result = prefix + BEGIN + "\n" + block + END + suffix
    else:
        result = text.replace("# TinyCoder Weight Lab\n",
                              "# TinyCoder Weight Lab\n\n" + BEGIN + "\n" + block + END + "\n", 1)
    if result == text:
        raise ValueError("README title not found")
    readme.write_text(result, encoding="utf-8")
    print(json.dumps({"gallery_url": base + "/index.html", "apps": len(apps)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--manifest", type=Path,
                        default=Path("docs/previews/session018/manifest.json"))
    parser.add_argument("--directory", default="docs/previews/session018")
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    args = parser.parse_args()
    publish(args.readme, args.manifest, args.revision, args.directory)


if __name__ == "__main__":
    main()
