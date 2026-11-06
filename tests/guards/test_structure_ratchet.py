"""Structure ratchet gate.

The real repository must satisfy the committed baseline, and the checker must
be proven to reject a regressed metric: a ratchet that no longer fires is worse
than no ratchet at all.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_structure import HARD_LIMITS, FileMetrics, Report, _check, build_report

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "structure-baseline.json"


def test_baseline_is_committed_and_complete() -> None:
    assert BASELINE.exists(), "structure-baseline.json must be committed"
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert baseline["files"], "baseline must record at least one file"
    assert set(baseline["global"]) == {"inheritance_depth", "module_fanout"}


def test_repository_satisfies_baseline() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    violations = _check(build_report(), baseline)

    assert violations == []


def test_checker_rejects_grown_file() -> None:
    report = Report(files={"src/example.py": FileMetrics(lines=2000, max_function_stmts=10)})
    baseline = {"files": {"src/example.py": {"lines": 100, "max_function_stmts": 10}}, "global": {}}

    violations = _check(report, baseline)

    assert any("grew to 2000 lines" in violation for violation in violations)


def test_checker_rejects_grown_function() -> None:
    report = Report(files={"src/example.py": FileMetrics(lines=10, max_function_stmts=400)})
    baseline = {"files": {"src/example.py": {"lines": 10, "max_function_stmts": 50}}, "global": {}}

    violations = _check(report, baseline)

    assert any("longest function grew to 400" in violation for violation in violations)


def test_checker_rejects_grown_global_metrics() -> None:
    report = Report(inheritance_depth=99, module_fanout=99)
    baseline = {"files": {}, "global": {"inheritance_depth": 1, "module_fanout": 10}}

    violations = _check(report, baseline)

    assert any("inheritance depth grew" in violation for violation in violations)
    assert any("module fan-out grew" in violation for violation in violations)


def test_new_file_uses_hard_limits() -> None:
    report = Report(files={"src/huge.py": FileMetrics(lines=HARD_LIMITS["lines"] + 1, max_function_stmts=1)})

    violations = _check(report, {"files": {}, "global": {}})

    assert any("hard limit" in violation for violation in violations)
