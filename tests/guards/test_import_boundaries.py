"""Architecture layer-direction gate.

The real repository must have zero forbidden imports, and the scanner itself
must be proven to still detect violations: a gate that silently stops matching
is worse than no gate at all.
"""

from __future__ import annotations

from pathlib import Path

from scripts.check_import_graph import RULES, ImportViolation, scan_violations

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_rules_declare_the_layer_direction() -> None:
    """The rule table must stay non-empty so the gate cannot become vacuous."""
    assert len(RULES) >= 8
    pairs = set(RULES)
    assert ("baldric_agent", "baldric_coding") in pairs
    assert ("baldric_agent", "textual") in pairs
    assert ("baldric_ai", "baldric_coding") in pairs


def test_repository_has_no_layer_violations() -> None:
    violations = scan_violations(REPO_ROOT)

    assert violations == [], "\n".join(
        f"{violation.module}:{violation.lineno} imports {violation.imported}" for violation in violations
    )


def test_scanner_detects_synthetic_violation(tmp_path: Path) -> None:
    """A planted violation must be reported: this proves the gate has teeth."""
    package = tmp_path / "src" / "baldric_agent"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "leaky.py").write_text(
        "import baldric_coding.tui.app  # noqa: F401\n",
        encoding="utf-8",
    )

    violations = scan_violations(tmp_path)

    assert violations == [
        ImportViolation(module="baldric_agent.leaky", lineno=1, imported="baldric_coding.tui.app")
    ]


def test_scanner_ignores_allowed_directions(tmp_path: Path) -> None:
    package = tmp_path / "src" / "baldric_coding"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "allowed.py").write_text(
        "from baldric_agent.loop import run_agent_loop\nfrom baldric_coding.tui.app import BaldricTuiApp\n",
        encoding="utf-8",
    )

    assert scan_violations(tmp_path) == []
