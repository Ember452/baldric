"""Architecture layer-direction gate.

The real repository must have zero forbidden imports, and the scanner itself
must be proven to still detect violations: a gate that silently stops matching
is worse than no gate at all.
"""

from __future__ import annotations

from pathlib import Path

from scripts.check_import_graph import (
    AI_PROTOCOL_SURFACE,
    RULES,
    ImportViolation,
    scan_surface_violations,
    scan_violations,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_rules_declare_the_layer_direction() -> None:
    """The rule table must stay non-empty so the gate cannot become vacuous."""
    assert len(RULES) >= 8
    pairs = set(RULES)
    assert ("baldric_agent", "baldric_coding") in pairs
    assert ("baldric_agent", "textual") in pairs
    assert ("baldric_ai", "baldric_coding") in pairs
    assert ("baldric_coding.rendering", "baldric_coding.tui") in pairs


def test_protocol_is_the_bottom_layer() -> None:
    """The protocol package must not depend on upper layers or platform I/O."""
    pairs = set(RULES)
    for forbidden in ("baldric_agent", "baldric_ai", "baldric_coding", "textual", "rich", "fcntl", "msvcrt"):
        assert ("baldric_protocol", forbidden) in pairs, f"missing protocol rule: {forbidden}"


def test_kernel_cannot_depend_on_providers() -> None:
    """The reverse arrow: the agent kernel must not import provider adapters."""
    assert ("baldric_agent", "baldric_ai") in set(RULES)


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


def test_scanner_detects_rendering_importing_the_frontend(tmp_path: Path) -> None:
    package = tmp_path / "src" / "baldric_coding" / "rendering"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "leaky.py").write_text(
        "from baldric_coding.tui.state import TuiState  # noqa: F401\n",
        encoding="utf-8",
    )

    violations = scan_violations(tmp_path)

    assert violations == [
        ImportViolation(
            module="baldric_coding.rendering.leaky",
            lineno=1,
            imported="baldric_coding.tui.state",
        )
    ]


def test_ai_protocol_surface_is_declared_and_real() -> None:
    """The surface must stay non-empty and must point at modules that exist."""
    assert AI_PROTOCOL_SURFACE
    missing = [
        module
        for module in AI_PROTOCOL_SURFACE
        if not (REPO_ROOT / "src" / module.replace(".", "/")).with_suffix(".py").exists()
    ]

    assert missing == [], f"AI_PROTOCOL_SURFACE lists modules that no longer exist: {missing}"


def test_provider_layer_stays_on_the_protocol_contract_surface() -> None:
    """``baldric_ai`` may use the protocol contract and nothing else."""
    violations = scan_surface_violations(REPO_ROOT)

    assert violations == [], "\n".join(
        f"{violation.module}:{violation.lineno} imports {violation.imported}" for violation in violations
    )


def test_surface_scanner_detects_harness_import_from_provider(tmp_path: Path) -> None:
    """Importing the harness from the provider layer must be reported."""
    package = tmp_path / "src" / "baldric_ai"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "leaky.py").write_text(
        "from baldric_agent.loop import run_agent_loop  # noqa: F401\n",
        encoding="utf-8",
    )

    violations = scan_surface_violations(tmp_path)

    assert violations == [ImportViolation(module="baldric_ai.leaky", lineno=1, imported="baldric_agent.loop")]


def test_surface_scanner_rejects_agent_package_root_import(tmp_path: Path) -> None:
    """Importing the harness package root from the provider layer is a violation."""
    package = tmp_path / "src" / "baldric_ai"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "rooted.py").write_text(
        "from baldric_agent import AssistantMessage  # noqa: F401\n",
        encoding="utf-8",
    )

    violations = scan_surface_violations(tmp_path)

    assert violations == [ImportViolation(module="baldric_ai.rooted", lineno=1, imported="baldric_agent")]


def test_surface_scanner_allows_protocol_contract_modules(tmp_path: Path) -> None:
    package = tmp_path / "src" / "baldric_ai"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "allowed.py").write_text(
        "from baldric_protocol.messages import AssistantMessage\n"
        "from baldric_protocol.tools import AgentTool\n"
        "from baldric_protocol.provider_events import TextDeltaEvent\n",
        encoding="utf-8",
    )

    assert scan_surface_violations(tmp_path) == []
