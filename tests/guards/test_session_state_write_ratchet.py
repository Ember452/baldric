"""Ratchet: writes to `CodingSession` private state may only shrink.

`CodingSession` keeps ~33 mutable fields, and 46 of them are written from other
modules in the session package. That is what let `resume()` silently drop a
field: the state has no single owner, so every caller has to know the whole
shape.

The hottest four (`_thinking_level`, `_last_parent_id`, `_preview_model`,
`_preview_thinking`) now have semantic writers on the class and the call sites
use them. The rest is recorded here: a new `session._field = ...` outside
`session.py` fails, and fixing one only ever tightens the baseline.

Regenerate with the same scan and pass `--init`-style intent: a smaller number is
always accepted, a larger one needs a review.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).with_name("session_state_write_baseline.json")
SCANNED_PACKAGE = ROOT / "src" / "baldric_coding"
OWNER_MODULE = Path("src/baldric_coding/session/session.py")

# The guard must never pass because it looked at the wrong tree.
MINIMUM_FILES = 3
MINIMUM_WRITE_SITES = 80


def _write_sites() -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for path in sorted(SCANNED_PACKAGE.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if "__pycache__" in path.parts or relative == OWNER_MODULE.as_posix():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AugAssign):
                targets = [node.target]
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "session"
                    and target.attr.startswith("_")
                ):
                    counts.setdefault(relative, {})
                    counts[relative][target.attr] = counts[relative].get(target.attr, 0) + 1
    return counts


def _baseline() -> dict[str, dict[str, int]]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))["files"]


def test_the_scan_sees_the_expected_corpus() -> None:
    sites = _write_sites()

    assert len(sites) >= MINIMUM_FILES, "the scanner is not looking at the session package"
    assert sum(sum(fields.values()) for fields in sites.values()) >= MINIMUM_WRITE_SITES


def test_no_new_private_state_writes_outside_the_owner() -> None:
    sites = _write_sites()
    baseline = _baseline()

    growth: list[str] = []
    for path, fields in sites.items():
        allowed = baseline.get(path, {})
        for field, count in fields.items():
            limit = allowed.get(field, 0)
            if count > limit:
                growth.append(f"{path}: session.{field} written {count} times (baseline {limit})")

    assert growth == [], "new writes to CodingSession state outside session.py:\n" + "\n".join(growth)


def test_a_cleanup_is_recorded_by_tightening_the_baseline() -> None:
    sites = _write_sites()
    baseline = _baseline()

    improved = [
        f"{path}: {field} {baseline[path][field]} -> {sites.get(path, {}).get(field, 0)}"
        for path in baseline
        for field in baseline[path]
        if sites.get(path, {}).get(field, 0) < baseline[path][field]
    ]

    assert improved == [], (
        "private-state writes shrank; regenerate session_state_write_baseline.json:\n" + "\n".join(improved)
    )
