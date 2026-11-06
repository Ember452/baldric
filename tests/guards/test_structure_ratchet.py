"""Structure ratchet gate.

The real repository must satisfy the committed baseline, and the checker must
be proven to reject a regressed metric: a ratchet that no longer fires is worse
than no ratchet at all.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_structure import (
    FUNCTION_GROWTH_FREE_LIMIT,
    GROWTH_FREE_LIMIT,
    HARD_LIMITS,
    FileMetrics,
    Report,
    _check,
    build_report,
)

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

    assert any("past the 400-line growth-free limit" in violation for violation in violations)


def test_small_file_may_grow_within_the_growth_free_limit() -> None:
    report = Report(files={"src/example.py": FileMetrics(lines=GROWTH_FREE_LIMIT, max_function_stmts=10)})
    baseline = {"files": {"src/example.py": {"lines": 100, "max_function_stmts": 10}}, "global": {}}

    assert _check(report, baseline) == []


def test_small_file_cannot_cross_the_growth_free_limit() -> None:
    report = Report(files={"src/example.py": FileMetrics(lines=GROWTH_FREE_LIMIT + 1, max_function_stmts=10)})
    baseline = {"files": {"src/example.py": {"lines": 100, "max_function_stmts": 10}}, "global": {}}

    violations = _check(report, baseline)

    assert any("split the file or record the growth" in violation for violation in violations)


def test_large_file_may_not_grow() -> None:
    report = Report(files={"src/big.py": FileMetrics(lines=501, max_function_stmts=10)})
    baseline = {"files": {"src/big.py": {"lines": 500, "max_function_stmts": 10}}, "global": {}}

    violations = _check(report, baseline)

    assert any("a file must split instead of growing" in violation for violation in violations)


def test_checker_rejects_grown_function() -> None:
    report = Report(files={"src/example.py": FileMetrics(lines=10, max_function_stmts=400)})
    baseline = {"files": {"src/example.py": {"lines": 10, "max_function_stmts": 50}}, "global": {}}

    violations = _check(report, baseline)

    assert any("a function must be split" in violation for violation in violations)


def test_small_function_may_grow_within_the_growth_free_limit() -> None:
    report = Report(
        files={"src/example.py": FileMetrics(lines=10, max_function_stmts=FUNCTION_GROWTH_FREE_LIMIT)}
    )
    baseline = {"files": {"src/example.py": {"lines": 10, "max_function_stmts": 10}}, "global": {}}

    assert _check(report, baseline) == []


def test_small_function_cannot_cross_the_growth_free_limit() -> None:
    report = Report(
        files={"src/example.py": FileMetrics(lines=10, max_function_stmts=FUNCTION_GROWTH_FREE_LIMIT + 1)}
    )
    baseline = {"files": {"src/example.py": {"lines": 10, "max_function_stmts": 10}}, "global": {}}

    violations = _check(report, baseline)

    assert any("extract a helper" in violation for violation in violations)


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
