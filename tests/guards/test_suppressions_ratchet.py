"""Suppression ratchet gate.

Suppression comments keep ``mypy --strict`` and ``ruff`` green; this ratchet
must therefore be proven to (a) reject any new suppression and (b) ignore
suppression-looking text inside strings and docstrings.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_suppressions import _check, _file_suppressions, _suppression_kind, build_report

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "suppressions-baseline.json"


def test_baseline_is_committed_and_complete() -> None:
    assert BASELINE.exists(), "suppressions-baseline.json must be committed"
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert baseline, "baseline must record at least one suppression"
    assert any(kind.startswith("noqa") for kinds in baseline.values() for kind in kinds)


def test_repository_satisfies_baseline() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    violations = _check(build_report(), baseline)

    assert violations == []


def test_new_suppression_is_rejected() -> None:
    report = {"src/example.py": {"noqa:BLE001": 2}}
    baseline = {"src/example.py": {"noqa:BLE001": 1}}

    violations = _check(report, baseline)

    assert violations == ["src/example.py: noqa:BLE001 grew to 2 (baseline 1)"]


def test_reduced_suppression_is_reported_as_improvement(capsys) -> None:
    report = {"src/example.py": {"noqa:BLE001": 1}}
    baseline = {"src/example.py": {"noqa:BLE001": 2}}

    violations = _check(report, baseline)

    assert violations == []
    assert "shrank to 1" in capsys.readouterr().out


def test_kind_parsing_distinguishes_codes() -> None:
    assert _suppression_kind("# noqa") == ["noqa"]
    assert _suppression_kind("# noqa: BLE001") == ["noqa:BLE001"]
    assert _suppression_kind("# noqa: F401, BLE001") == ["noqa:F401", "noqa:BLE001"]
    assert _suppression_kind("# type: ignore") == ["type-ignore"]
    assert _suppression_kind("# type: ignore[attr-defined]") == ["type-ignore:attr-defined"]
    assert _suppression_kind("# type: ignore[arg-type, union-attr]") == [
        "type-ignore:arg-type",
        "type-ignore:union-attr",
    ]
    assert _suppression_kind("# ordinary comment") == []


def test_strings_are_not_counted_as_suppressions(tmp_path: Path) -> None:
    path = tmp_path / "example.py"
    path.write_text(
        'DOC = "use # noqa: BLE001 sparingly"\n'
        "value = 1  # noqa: BLE001\n"
        'other = """\n# type: ignore[attr-defined]\n"""\n',
        encoding="utf-8",
    )

    assert _file_suppressions(path) == {"noqa:BLE001": 1}
