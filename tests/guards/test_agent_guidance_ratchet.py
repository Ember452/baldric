"""Agent-guidance byte ratchet.

Instruction files must not silently grow; the shim must stay a thin import.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_agent_guidance import _check, _normalized_bytes, build_report

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "agent-guidance-baseline.json"


def test_baseline_is_committed_and_readable() -> None:
    assert BASELINE.exists(), "agent-guidance-baseline.json must be committed"
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert "AGENTS.md" in baseline["files"]
    assert "docs/AGENTS.md" in baseline["files"]
    assert baseline["chain_bytes"] > 0
    assert baseline["shims"] == ["CLAUDE.md"]


def test_repository_satisfies_baseline() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    violations = _check(build_report(), baseline)

    assert violations == []


def test_grown_instruction_file_is_rejected() -> None:
    report = {"files": {"AGENTS.md": 9999}, "shims": [], "chain_bytes": 0}
    baseline = {"files": {"AGENTS.md": 1000}, "shims": [], "chain_bytes": 0}

    violations = _check(report, baseline)

    assert any("grew to 9999 bytes" in violation for violation in violations)


def test_grown_chain_is_rejected() -> None:
    report = {"files": {}, "shims": [], "chain_bytes": 20000}
    baseline = {"files": {}, "shims": [], "chain_bytes": 10000}

    violations = _check(report, baseline)

    assert any("instruction chain grew to 20000" in violation for violation in violations)


def test_shrunken_instruction_is_reported_as_improvement(capsys) -> None:
    report = {"files": {"AGENTS.md": 500}, "shims": [], "chain_bytes": 0}
    baseline = {"files": {"AGENTS.md": 1000}, "shims": [], "chain_bytes": 0}

    violations = _check(report, baseline)

    assert violations == []
    assert "shrank to 500 bytes" in capsys.readouterr().out


def test_oversized_shim_is_rejected() -> None:
    report = {"files": {"CLAUDE.md": 5000}, "shims": [], "chain_bytes": 0}
    baseline = {"files": {}, "shims": [], "chain_bytes": 0}

    violations = _check(report, baseline)

    assert any("shim limit" in violation for violation in violations)


def test_measurement_ignores_checkout_line_endings(tmp_path: Path) -> None:
    """An LF baseline must not fail on a CRLF checkout (Windows CI)."""
    lf = tmp_path / "lf.md"
    crlf = tmp_path / "crlf.md"
    lf.write_bytes(b"# Title\n\nTwo lines.\n")
    crlf.write_bytes(b"# Title\r\n\r\nTwo lines.\r\n")

    assert _normalized_bytes(crlf) == _normalized_bytes(lf)
