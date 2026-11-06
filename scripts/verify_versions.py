#!/usr/bin/env python3
"""Verify that the project version is consistent everywhere it is recorded.

Usage:
    uv run python scripts/verify_versions.py
    uv run python scripts/verify_versions.py --tag v0.2.2

``pyproject.toml`` and the ``baldric`` entry in ``uv.lock`` must agree. When
``--tag`` is passed (or ``GITHUB_REF_TYPE=tag`` is set in CI), the release tag
must match as well: a tag pointing at a different version ships a mislabeled
artifact.
"""

from __future__ import annotations

import argparse
import os
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        raise SystemExit("pyproject.toml has no project.version")
    return version


def _lock_version() -> str | None:
    text = (ROOT / "uv.lock").read_text(encoding="utf-8")
    match = re.search(r'\[\[package\]\]\nname = "baldric"\nversion = "([^"]+)"', text)
    return match.group(1) if match else None


def _check(version: str, tag: str | None) -> list[str]:
    violations: list[str] = []
    lock = _lock_version()
    if lock is None:
        violations.append("uv.lock has no baldric package entry")
    elif lock != version:
        violations.append(f"uv.lock records baldric {lock} but pyproject.toml records {version}")
    if tag is not None:
        expected = f"v{version}"
        if tag != expected:
            violations.append(f"release tag {tag} does not match version {version} (expected {expected})")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="release tag to verify, e.g. v0.2.2")
    args = parser.parse_args()

    tag = args.tag
    if tag is None and os.environ.get("GITHUB_REF_TYPE") == "tag":
        tag = os.environ.get("GITHUB_REF_NAME")

    version = _project_version()
    violations = _check(version, tag)
    if violations:
        print("version mismatches:")
        for violation in violations:
            print(f"  {violation}")
        return 1
    suffix = f" (tag {tag})" if tag else ""
    print(f"versions: OK ({version}{suffix})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
