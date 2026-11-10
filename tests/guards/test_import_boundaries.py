"""Architecture layer-direction gate.

The real repository must have zero forbidden imports, and the scanner itself
must be proven to still detect violations: a gate that silently stops matching
is worse than no gate at all.
"""

from __future__ import annotations

import os
import subprocess
import sys
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
    assert ("baldric.agent", "baldric.runtime") in pairs
    assert ("baldric.agent", "textual") in pairs
    assert ("baldric.ai", "baldric.runtime") in pairs
    assert ("baldric.runtime.rendering", "baldric.runtime.tui") in pairs


def test_protocol_is_the_bottom_layer() -> None:
    """The protocol package must not depend on upper layers or platform I/O."""
    pairs = set(RULES)
    for forbidden in ("baldric.agent", "baldric.ai", "baldric.runtime", "textual", "rich", "fcntl", "msvcrt"):
        assert ("baldric.protocol", forbidden) in pairs, f"missing protocol rule: {forbidden}"


def test_kernel_cannot_depend_on_providers() -> None:
    """The reverse arrow: the agent kernel must not import provider adapters."""
    assert ("baldric.agent", "baldric.ai") in set(RULES)


def test_mcp_layer_direction_is_declared() -> None:
    """The MCP core sits beside the coding app; neither may know the other."""
    pairs = set(RULES)
    for forbidden in ("baldric.agent", "baldric.ai", "baldric.runtime", "textual", "rich"):
        assert ("baldric.mcp", forbidden) in pairs, f"missing mcp rule: {forbidden}"
    assert ("baldric.agent", "baldric.mcp") in pairs
    assert ("baldric.ai", "baldric.mcp") in pairs


def test_repository_has_no_layer_violations() -> None:
    violations = scan_violations(REPO_ROOT)

    assert violations == [], "\n".join(
        f"{violation.module}:{violation.lineno} imports {violation.imported}" for violation in violations
    )


def test_scanner_detects_synthetic_violation(tmp_path: Path) -> None:
    """A planted violation must be reported: this proves the gate has teeth."""
    package = tmp_path / "src" / "baldric" / "agent"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "leaky.py").write_text(
        "import baldric.runtime.tui.app  # noqa: F401\n",
        encoding="utf-8",
    )

    violations = scan_violations(tmp_path)

    assert violations == [
        ImportViolation(module="baldric.agent.leaky", lineno=1, imported="baldric.runtime.tui.app")
    ]


def test_scanner_ignores_allowed_directions(tmp_path: Path) -> None:
    package = tmp_path / "src" / "baldric" / "runtime"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "allowed.py").write_text(
        "from baldric.agent.loop import run_agent_loop\nfrom baldric.runtime.tui.app import BaldricTuiApp\n",
        encoding="utf-8",
    )

    assert scan_violations(tmp_path) == []


def test_scanner_detects_rendering_importing_the_frontend(tmp_path: Path) -> None:
    package = tmp_path / "src" / "baldric" / "runtime" / "rendering"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "leaky.py").write_text(
        "from baldric.runtime.tui.state import TuiState  # noqa: F401\n",
        encoding="utf-8",
    )

    violations = scan_violations(tmp_path)

    assert violations == [
        ImportViolation(
            module="baldric.runtime.rendering.leaky",
            lineno=1,
            imported="baldric.runtime.tui.state",
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
    """``baldric.ai`` may use the protocol contract and nothing else."""
    violations = scan_surface_violations(REPO_ROOT)

    assert violations == [], "\n".join(
        f"{violation.module}:{violation.lineno} imports {violation.imported}" for violation in violations
    )


def test_surface_scanner_detects_harness_import_from_provider(tmp_path: Path) -> None:
    """Importing the harness from the provider layer must be reported."""
    package = tmp_path / "src" / "baldric" / "ai"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "leaky.py").write_text(
        "from baldric.agent.loop import run_agent_loop  # noqa: F401\n",
        encoding="utf-8",
    )

    violations = scan_surface_violations(tmp_path)

    assert violations == [ImportViolation(module="baldric.ai.leaky", lineno=1, imported="baldric.agent.loop")]


def test_surface_scanner_rejects_agent_package_root_import(tmp_path: Path) -> None:
    """Importing the harness package root from the provider layer is a violation."""
    package = tmp_path / "src" / "baldric" / "ai"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "rooted.py").write_text(
        "from baldric.agent import AssistantMessage  # noqa: F401\n",
        encoding="utf-8",
    )

    violations = scan_surface_violations(tmp_path)

    assert violations == [ImportViolation(module="baldric.ai.rooted", lineno=1, imported="baldric.agent")]


def test_surface_scanner_allows_protocol_contract_modules(tmp_path: Path) -> None:
    package = tmp_path / "src" / "baldric" / "ai"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "allowed.py").write_text(
        "from baldric.protocol.messages import AssistantMessage\n"
        "from baldric.protocol.tools import AgentTool\n"
        "from baldric.protocol.provider_events import TextDeltaEvent\n",
        encoding="utf-8",
    )

    assert scan_surface_violations(tmp_path) == []


def _loaded_modules_after_import(module_name: str) -> set[str]:
    """Import ``module_name`` in a clean subprocess and return ``sys.modules``."""
    code = f"import {module_name}\nimport sys\nprint(chr(10).join(sys.modules))"
    env = {**os.environ, "PYTHONPATH": "src"}
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return set(result.stdout.split())


def _loads_only(module_name: str, forbidden: tuple[str, ...]) -> list[str]:
    loaded = _loaded_modules_after_import(module_name)
    leaked: list[str] = []
    for name in forbidden:
        leaked.extend(sorted(m for m in loaded if m == name or m.startswith(name + ".")))
    return leaked


def test_protocol_loads_no_upper_layer_at_runtime() -> None:
    """The contract package must not pull the runtime, adapters, or frontend.

    Static import checks miss coupling that flows through a package ``__init__``
    re-export; asserting on ``sys.modules`` after a bare import catches it.
    """
    leaked = _loads_only(
        "baldric.protocol",
        ("baldric.agent", "baldric.ai", "baldric.runtime", "textual", "rich"),
    )
    assert leaked == [], f"baldric.protocol pulled in: {leaked}"


def test_kernel_and_providers_do_not_load_each_other_at_runtime() -> None:
    """The agent kernel and the provider layer must stay decoupled at runtime."""
    assert _loads_only("baldric.agent", ("baldric.ai", "baldric.runtime")) == []
    assert _loads_only("baldric.ai", ("baldric.agent", "baldric.runtime")) == []


def test_mcp_package_loads_no_upper_layer_at_runtime() -> None:
    """``baldric.mcp`` must stay importable without the harness or frontend."""
    assert (
        _loads_only(
            "baldric.mcp",
            ("baldric.agent", "baldric.ai", "baldric.runtime", "textual", "rich"),
        )
        == []
    )
