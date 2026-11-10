#!/usr/bin/env python3
"""Render CHANGELOG.md from the packaged release notes.

`releases.json` is the single source of release facts: the CLI reads it at
startup and the website renders it. The changelog is generated from the same
file so the two cannot drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "baldric" / "runtime" / "data" / "release-notes" / "releases.json"
TARGET = ROOT / "CHANGELOG.md"
SECTION_ALIASES = {"New": "Added"}
HEADER = [
    "# Changelog",
    "",
    "All notable changes to this project are documented in this file.",
    "",
    "The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),",
    "and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).",
    "",
]


def render() -> str:
    """Return the full changelog for the current release notes."""
    releases = json.loads(SOURCE.read_text(encoding="utf-8"))
    lines = list(HEADER)
    for release in releases:
        heading = f"## [{release['version']}]"
        if release.get("date"):
            heading += f" - {release['date']}"
        lines.extend([heading, ""])
        for section, items in release["sections"].items():
            lines.extend([f"### {SECTION_ALIASES.get(section, section)}", ""])
            lines.extend(f"- {item}" for item in items)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    if "--check" in sys.argv[1:]:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != render():
            print("CHANGELOG.md is out of date; run `uv run python scripts/render_changelog.py`")
            return 1
        print("CHANGELOG.md is up to date")
        return 0
    TARGET.write_text(render(), encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
