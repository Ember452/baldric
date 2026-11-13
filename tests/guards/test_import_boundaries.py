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
    ALLOW_RULES,
    RULES,
    AllowRule,
    ImportViolation,
    scan_allow_violations,
    scan_feature_isolation_violations,
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
    assert ("baldric.runtime.rendering", "baldric.runtime.frontends.tui") in pairs
    assert ("baldric.runtime.config", "baldric.runtime.trust") in pairs


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
        "import baldric.runtime.frontends.tui.app  # noqa: F401\n",
        encoding="utf-8",
    )

    violations = scan_violations(tmp_path)

    assert violations == [
        ImportViolation(module="baldric.agent.leaky", lineno=1, imported="baldric.runtime.frontends.tui.app")
    ]


def test_scanner_ignores_allowed_directions(tmp_path: Path) -> None:
    package = tmp_path / "src" / "baldric" / "runtime"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "allowed.py").write_text(
        "from baldric.agent.loop import run_agent_loop\n"
        "from baldric.runtime.frontends.tui.app import BaldricTuiApp\n",
        encoding="utf-8",
    )

    assert scan_violations(tmp_path) == []


def test_scanner_detects_rendering_importing_the_frontend(tmp_path: Path) -> None:
    package = tmp_path / "src" / "baldric" / "runtime" / "rendering"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "leaky.py").write_text(
        "from baldric.runtime.frontends.tui.state import TuiState  # noqa: F401\n",
        encoding="utf-8",
    )

    violations = scan_violations(tmp_path)

    assert violations == [
        ImportViolation(
            module="baldric.runtime.rendering.leaky",
            lineno=1,
            imported="baldric.runtime.frontends.tui.state",
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


# --- protocol shape-only wall (structural rearchitecture stage A0) -----------
# ``protocol/extension.py`` and ``protocol/ports.py`` hold the extension contract
# *shapes*. They must import nothing from an upper layer and must contain no
# behaviour (no function bodies except dataclass ``__post_init__``/validators,
# no I/O, no module-level singletons) so the protocol package cannot grow into a
# god module as the project scales. A gate that stops firing is worse than none,
# so the AST check is exercised directly below as well as over the real files.

_SHAPE_ONLY_MODULES = (
    "src/baldric/protocol/extension.py",
    "src/baldric/protocol/extension_events.py",
    "src/baldric/protocol/ports.py",
    "src/baldric/protocol/provider_events.py",
    "src/baldric/protocol/types.py",
)

# Protocol modules that still carry a few pre-existing helper methods/functions
# (text extraction, usage arithmetic, tree traversal, tool execution, hook-
# emptiness). The plan's "protocol holds only shapes" rule is future-facing:
# these are recorded debt to be migrated out in a later stage, and this ratchet
# forbids the *set* from growing. Every protocol module must be classified as
# either shape-only (enforced above) or legacy-behaviour (listed here); a new
# unclassified module fails.
_PROTOCOL_LEGACY_BEHAVIOUR = frozenset(
    {
        "src/baldric/protocol/messages.py",
        "src/baldric/protocol/provider.py",
        "src/baldric/protocol/tools.py",
        "src/baldric/protocol/session/entries.py",
        "src/baldric/protocol/session/tree.py",
    }
)

_PROTOCOL_LINE_BUDGET = 400


def _protocol_shape_violations(path: Path) -> list[str]:
    """Return reasons ``path`` is not shape-only (empty when it is).

    Permitted "methods" on a shape module are limited to the machinery that
    dataclasses and ``Protocol`` need, all of which are shape declarations, not
    logic: ``__post_init__``/``__init__``, ``@classmethod``/``@staticmethod``/
    ``@property`` members (contract metadata accessors), and ``Protocol`` stubs
    whose body is only a docstring / ``...`` / ``pass``. Anything else is
    behaviour and fails.
    """
    import ast

    def _decorated_as_machinery(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        for deco in fn.decorator_list:
            name = deco.id if isinstance(deco, ast.Name) else getattr(deco, "attr", "")
            if name in ("classmethod", "staticmethod", "property", "validator"):
                return True
        return False

    def _is_stub(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        for stmt in fn.body:
            if isinstance(stmt, ast.Pass):
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                continue  # docstring or ``...`` (Ellipsis)
            return False
        return True

    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            problems.append(f"{path.name}: top-level function {node.name!r} is behaviour")
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if child.name in ("__post_init__", "__init__"):
                    continue
                if _decorated_as_machinery(child) or _is_stub(child):
                    continue
                problems.append(f"{path.name}: {node.name}.{child.name} is a method body")
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.TypeAlias)):
            continue  # constants / type aliases are fine
    return problems


def test_protocol_extension_and_ports_pull_no_upper_layer() -> None:
    """The extension shape modules must not load the runtime/adapters/frontend."""
    for module_name in ("baldric.protocol.extension", "baldric.protocol.ports"):
        leaked = _loads_only(
            module_name,
            ("baldric.agent", "baldric.ai", "baldric.runtime", "textual", "rich"),
        )
        assert leaked == [], f"{module_name} pulled in: {leaked}"


def test_protocol_extension_and_ports_contain_only_shapes() -> None:
    """These modules must define only shapes, never behaviour."""
    problems: list[str] = []
    for rel in _SHAPE_ONLY_MODULES:
        problems.extend(_protocol_shape_violations(REPO_ROOT / rel))
    assert problems == [], "\n".join(problems)


def test_protocol_shape_guard_has_teeth(tmp_path: Path) -> None:
    """The shape-only check must reject a module that smuggles in behaviour."""
    bad = tmp_path / "bad.py"
    bad.write_text(
        "def helper() -> int:\n    return 1\n\n\nclass Shape:\n    def act(self) -> int:\n        return 2\n",
        encoding="utf-8",
    )
    problems = _protocol_shape_violations(bad)
    assert any("helper" in problem for problem in problems)
    assert any("act" in problem for problem in problems)


def _protocol_py_files() -> list[Path]:
    """Every non-package ``.py`` module under ``src/baldric/protocol``."""
    base = REPO_ROOT / "src" / "baldric" / "protocol"
    return [path for path in sorted(base.rglob("*.py")) if path.name != "__init__.py"]


def _relative_to_repo(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def test_every_protocol_module_is_classified() -> None:
    """Each protocol module is either shape-only or documented legacy debt.

    This is the ratchet that stops the protocol package from silently growing a
    new behaviour module: a new file must be consciously classified.
    """
    classified = {path for path in _SHAPE_ONLY_MODULES} | _PROTOCOL_LEGACY_BEHAVIOUR
    discovered = {_relative_to_repo(path) for path in _protocol_py_files()}
    unclassified = sorted(discovered - set(classified))
    assert unclassified == [], (
        "unclassified protocol module(s); add each to _SHAPE_ONLY_MODULES (must be "
        f"pure shapes) or _PROTOCOL_LEGACY_BEHAVIOUR (recorded debt): {unclassified}"
    )


def test_protocol_modules_stay_within_line_budget() -> None:
    """No protocol module may exceed the 400-line budget (split when it would)."""
    over = []
    for path in _protocol_py_files():
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > _PROTOCOL_LINE_BUDGET:
            over.append(f"{_relative_to_repo(path)}: {lines} > {_PROTOCOL_LINE_BUDGET}")
    assert over == [], "protocol module(s) over the line budget:\n" + "\n".join(over)


# --- allow-rule whitelist (cross-domain port discipline) ---------------------


def _write_feature(root: Path, name: str, files: dict[str, str]) -> None:
    package = root / "src" / "baldric" / "runtime" / "features" / name
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    for rel, text in files.items():
        target = package / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def _feature_rule() -> tuple[AllowRule, ...]:
    return (AllowRule(source="baldric.runtime.features", target="baldric.runtime.features", allow=("port",)),)


def test_allow_rules_declared_and_non_empty() -> None:
    assert ALLOW_RULES, "the whitelist must not be empty once features exist"
    assert any(rule.allow == ("port",) for rule in ALLOW_RULES)


def test_allow_rule_permits_a_sibling_features_port(tmp_path: Path) -> None:
    _write_feature(tmp_path, "a", {"svc.py": "import baldric.runtime.features.b.port\n"})
    _write_feature(tmp_path, "b", {"port.py": ""})
    assert scan_allow_violations(tmp_path, _feature_rule()) == []


def test_allow_rule_rejects_a_sibling_features_internals(tmp_path: Path) -> None:
    _write_feature(tmp_path, "a", {"svc.py": "import baldric.runtime.features.b.service\n"})
    _write_feature(tmp_path, "b", {"service.py": ""})
    violations = scan_allow_violations(tmp_path, _feature_rule())
    assert violations == [
        ImportViolation(
            module="baldric.runtime.features.a.svc",
            lineno=1,
            imported="baldric.runtime.features.b.service",
        )
    ]


def test_allow_rule_permits_intra_feature_imports(tmp_path: Path) -> None:
    _write_feature(
        tmp_path,
        "b",
        {"service.py": "", "port.py": "import baldric.runtime.features.b.service\n"},
    )
    assert scan_allow_violations(tmp_path, _feature_rule()) == []


def test_repository_has_no_allow_violations() -> None:
    """On the real tree the whitelist is quiet: the one live features->frontends
    edge (subagents/ui -> frontends.tui.{config,state,widgets}) is exactly the
    declared exception."""
    assert scan_allow_violations(REPO_ROOT) == []


def _features_frontends_rules() -> tuple[AllowRule, ...]:
    """The production pair: the subagents.ui exception inside the blanket ban."""
    return (
        AllowRule(
            source="baldric.runtime.features.subagents.ui",
            target="baldric.runtime.frontends.tui",
            allow=("config", "state", "widgets"),
        ),
        AllowRule(source="baldric.runtime.features", target="baldric.runtime.frontends", allow=()),
    )


def test_allow_rule_permits_the_declared_subagents_ui_exception(tmp_path: Path) -> None:
    """The subagents UI may import exactly its three declared TUI modules."""
    package = tmp_path / "src" / "baldric" / "runtime" / "features" / "subagents" / "ui"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "viewer.py").write_text(
        "from baldric.runtime.frontends.tui.config import TuiKeybindings\n"
        "from baldric.runtime.frontends.tui.state import TuiState\n"
        "from baldric.runtime.frontends.tui.widgets import TranscriptView\n",
        encoding="utf-8",
    )
    assert scan_allow_violations(tmp_path, _features_frontends_rules()) == []


def test_allow_rule_bans_feature_frontends_imports_outside_the_exception(tmp_path: Path) -> None:
    """Other frontends surfaces — and other TUI modules — stay banned for features."""
    ui = tmp_path / "src" / "baldric" / "runtime" / "features" / "subagents" / "ui"
    ui.mkdir(parents=True)
    (ui / "__init__.py").write_text("", encoding="utf-8")
    (ui / "viewer.py").write_text(
        "from baldric.runtime.frontends.tui.app import BaldricTuiApp\n", encoding="utf-8"
    )
    other = tmp_path / "src" / "baldric" / "runtime" / "features" / "other"
    other.mkdir(parents=True)
    (other / "__init__.py").write_text("", encoding="utf-8")
    (other / "svc.py").write_text("from baldric.runtime.frontends.rpc import RpcServer\n", encoding="utf-8")
    violations = scan_allow_violations(tmp_path, _features_frontends_rules())
    reported = {(v.module, v.imported) for v in violations}
    assert reported == {
        ("baldric.runtime.features.subagents.ui.viewer", "baldric.runtime.frontends.tui.app"),
        ("baldric.runtime.features.other.svc", "baldric.runtime.frontends.rpc"),
    }


# --- S1a: core/platform/frontends must not statically import a feature --------


def test_repository_has_no_feature_isolation_violations() -> None:
    """The real tree: no runtime module outside ``features`` statically imports a feature."""
    violations = scan_feature_isolation_violations(REPO_ROOT)
    assert violations == [], "\n".join(f"{v.module}:{v.lineno} imports {v.imported}" for v in violations)


def test_feature_isolation_scanner_detects_a_platform_import(tmp_path: Path) -> None:
    """A platform module importing a feature implementation must be reported."""
    package = tmp_path / "src" / "baldric" / "runtime" / "platform"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "loader.py").write_text(
        "from baldric.runtime.features.subagents.extension import setup\n", encoding="utf-8"
    )
    violations = scan_feature_isolation_violations(tmp_path)
    assert violations == [
        ImportViolation(
            module="baldric.runtime.platform.loader",
            lineno=1,
            imported="baldric.runtime.features.subagents.extension",
        )
    ]


def test_feature_isolation_scanner_detects_a_session_import(tmp_path: Path) -> None:
    """The historical blind spot: session lives directly under ``runtime``.

    The original allowlist of three prefixes (core/platform/frontends) missed it
    because the core merge never happened; the rule is now inverse — every
    runtime module outside ``features`` — so this case must be reported.
    """
    package = tmp_path / "src" / "baldric" / "runtime" / "session"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "leaky.py").write_text(
        "import baldric.runtime.features.subagents.extension\n", encoding="utf-8"
    )
    violations = scan_feature_isolation_violations(tmp_path)
    assert violations == [
        ImportViolation(
            module="baldric.runtime.session.leaky",
            lineno=1,
            imported="baldric.runtime.features.subagents.extension",
        )
    ]


def test_feature_isolation_scanner_ignores_in_body_importlib(tmp_path: Path) -> None:
    """String-path loading via importlib is allowed (not a static import node)."""
    package = tmp_path / "src" / "baldric" / "runtime" / "platform"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "loader.py").write_text(
        "from importlib import import_module\n\n"
        "def load() -> object:\n"
        "    return import_module('baldric.runtime.features.subagents.extension')\n",
        encoding="utf-8",
    )
    assert scan_feature_isolation_violations(tmp_path) == []


def test_feature_isolation_scanner_allows_features_importing_core(tmp_path: Path) -> None:
    """The forward direction (feature -> core) is allowed; S1a is one-way."""
    package = tmp_path / "src" / "baldric" / "runtime" / "features" / "x"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "svc.py").write_text("from baldric.runtime.core.session import x\n", encoding="utf-8")
    assert scan_feature_isolation_violations(tmp_path) == []


# --- FEATURES declaration completeness (S7) ----------------------------------


def test_every_feature_directory_is_declared_in_features() -> None:
    """Every ``runtime/features/<name>`` package has a matching FEATURES entry."""
    from baldric.runtime.platform.features import FEATURES

    declared = {spec.name for spec in FEATURES}
    features_dir = REPO_ROOT / "src" / "baldric" / "runtime" / "features"
    on_disk = {
        child.name for child in features_dir.iterdir() if child.is_dir() and child.name != "__pycache__"
    }
    assert on_disk <= declared, f"feature package(s) missing from FEATURES: {sorted(on_disk - declared)}"


def test_every_feature_setup_path_resolves() -> None:
    """Each FEATURES setup path names a real ``module:attr`` on disk."""
    from baldric.runtime.platform.features import FEATURES

    problems: list[str] = []
    for spec in FEATURES:
        module_path = spec.setup.split(":", 1)[0]
        rel = module_path.replace(".", "/")
        candidates = [REPO_ROOT / "src" / f"{rel}.py", REPO_ROOT / "src" / rel / "__init__.py"]
        if not any(path.exists() for path in candidates):
            problems.append(f"{spec.name}: {module_path} not found")
    assert problems == [], "\n".join(problems)


# --- public facade provenance (S4, partial) ----------------------------------


def test_api_facade_exports_protocol_shapes_by_identity() -> None:
    """Every protocol shape the ``baldric.api`` facade exports is the same object.

    The facade re-exports contract shapes straight from ``baldric.protocol`` so an
    extension that only needs shapes never pulls the platform runtime. This pins
    that provenance: if a shape is re-declared or imported from a different module,
    identity breaks and the test fails.
    """
    import baldric.api as api
    import baldric.protocol.extension as protocol_extension

    assert api.__all__, "the facade must export something"
    missing = [name for name in api.__all__ if not hasattr(api, name)]
    assert missing == [], f"__all__ names with no attribute: {missing}"

    shared = [name for name in protocol_extension.__all__ if hasattr(api, name)]
    assert shared, "the facade should re-export protocol shapes"
    mismatched = [name for name in shared if getattr(api, name) is not getattr(protocol_extension, name)]
    assert mismatched == [], f"facade shapes not identical to protocol: {mismatched}"


# --- platform root is not a second aggregate facade ---------------------------


def test_platform_root_reexports_only_platform_owned_names() -> None:
    """``runtime.platform``'s package root may only re-export its own modules.

    The root used to aggregate provider-domain contracts (34 ``LocalBackend*`` /
    ``LocalConfirmation*`` names from ``providers.backends.contracts``), which made
    it a second facade: consumers imported provider types from the extension
    framework package. Platform now re-exports only ``baldric.runtime.platform.*``
    modules; provider contracts are imported from their owning module. This pins
    that split so aggregation cannot creep back.
    """
    import ast

    init = REPO_ROOT / "src" / "baldric" / "runtime" / "platform" / "__init__.py"
    tree = ast.parse(init.read_text(encoding="utf-8"))
    foreign: list[tuple[str, list[str]]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and not node.module.startswith("baldric.runtime.platform")
        ):
            foreign.append((node.module, [alias.name for alias in node.names]))
    assert foreign == [], f"platform root re-exports non-platform modules: {foreign}"
