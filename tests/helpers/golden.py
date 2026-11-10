"""Golden-file assertions for behavior that users or other tools can observe.

The committed files under ``tests/expected/`` are the source of truth. Tests
only read them; rewriting requires an explicit environment flag so a passing
suite can never silently move the goalposts:

    UPDATE_EXPECTED=1 uv run pytest tests/runtime/test_expected_outputs.py

An update prints the unified diff it is about to accept so the change is
visible in CI logs even when nobody asks for it.
"""

from __future__ import annotations

import difflib
import os
from pathlib import Path

EXPECTED_DIR = Path(__file__).resolve().parents[1] / "expected"
UPDATE_ENV = "UPDATE_EXPECTED"


def assert_matches_expected(name: str, actual: str) -> None:
    """Compare ``actual`` with ``tests/expected/<name>``."""
    path = EXPECTED_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.environ.get(UPDATE_ENV) == "1":
        if path.exists():
            previous = path.read_text(encoding="utf-8")
            diff = "\n".join(
                difflib.unified_diff(
                    previous.splitlines(),
                    actual.splitlines(),
                    fromfile=f"{name} (head)",
                    tofile=f"{name} (new)",
                    lineterm="",
                )
            )
            if diff:
                print(f"updating {name}:\n{diff}")
        path.write_text(actual, encoding="utf-8")
        return
    assert path.exists(), (
        f"missing golden file tests/expected/{name}; create it with {UPDATE_ENV}=1 uv run pytest -k expected"
    )
    expected = path.read_text(encoding="utf-8")
    if actual == expected:
        return
    diff = "\n".join(
        difflib.unified_diff(
            expected.splitlines(),
            actual.splitlines(),
            fromfile=f"{name} (expected)",
            tofile=f"{name} (actual)",
            lineterm="",
        )
    )
    raise AssertionError(
        f"observable output changed for {name}.\n"
        f"If the change is intended, review this diff and rerun with {UPDATE_ENV}=1:\n{diff}"
    )
