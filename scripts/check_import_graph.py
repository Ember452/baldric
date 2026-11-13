#!/usr/bin/env python3
"""Check import-direction invariants for the three Baldric packages.

Usage:
    uv run python scripts/check_import_graph.py

The script parses absolute imports with ast. It intentionally does not try to
resolve every runtime import; it is a guard for layer direction, not a complete
import checker. A violation prints the source file, line, and imported module.

The same rules are exercised by ``tests/guards/test_import_boundaries.py``
so an ordinary ``pytest`` run enforces the layers too; this script stays as the
fast standalone/CI entry point and the tests import :func:`scan_violations`.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (source prefix, forbidden imported prefix)
RULES: tuple[tuple[str, str], ...] = (
    # The protocol contract is the lowest layer: it may not depend on the agent
    # runtime, provider adapters, or coding app, and may not touch platform I/O.
    ("baldric.protocol", "baldric.agent"),
    ("baldric.protocol", "baldric.ai"),
    ("baldric.protocol", "baldric.runtime"),
    ("baldric.protocol", "textual"),
    ("baldric.protocol", "rich"),
    ("baldric.protocol", "fcntl"),
    ("baldric.protocol", "msvcrt"),
    ("baldric.protocol", "tempfile"),
    # The agent kernel must not depend on provider implementations (the reverse
    # direction of the provider surface below).
    ("baldric.agent", "baldric.ai"),
    ("baldric.agent", "baldric.runtime"),
    ("baldric.agent", "textual"),
    ("baldric.agent", "rich"),
    # The provider layer now depends on the protocol contract, not the harness.
    ("baldric.ai", "baldric.agent"),
    ("baldric.ai", "baldric.runtime"),
    # The MCP client core is an application-layer package beside the coding
    # app: it delegates protocol work to the official `mcp` SDK and must stay
    # importable without the harness, providers, or the TUI stack.
    ("baldric.mcp", "baldric.agent"),
    ("baldric.mcp", "baldric.ai"),
    ("baldric.mcp", "baldric.runtime"),
    ("baldric.mcp", "textual"),
    ("baldric.mcp", "rich"),
    # The harness and providers must not learn MCP exists; the coding app
    # reaches MCP only through its built-in extension.
    ("baldric.agent", "baldric.mcp"),
    ("baldric.ai", "baldric.mcp"),
    ("baldric.runtime.session", "baldric.runtime.frontends.tui"),
    ("baldric.runtime.tools", "baldric.runtime.frontends.tui"),
    ("baldric.runtime.trust", "baldric.runtime.frontends.tui"),
    ("baldric.runtime.context", "baldric.runtime.frontends.tui"),
    ("baldric.runtime.providers", "baldric.runtime.frontends.tui"),
    ("baldric.runtime.rendering", "baldric.runtime.frontends.tui"),
    # Cross-cutting settings must not reach the trust policy: the trust default
    # is a *durable settings value* owned by the config layer (shell_config
    # defines the Literal; trust/policy re-exports it).
    ("baldric.runtime.config", "baldric.runtime.trust"),
)

# The provider layer depends on the protocol contract only. It may not import the
# harness (``baldric.agent``) at all; that direction is now a plain RULES entry.
# This surface records the protocol modules an adapter is allowed to build on, so
# an adapter that reaches for a non-contract module is caught even inside protocol.
AI_PROTOCOL_SURFACE: tuple[str, ...] = (
    "baldric.protocol.messages",
    "baldric.protocol.provider",
    "baldric.protocol.provider_events",
    "baldric.protocol.tools",
    "baldric.protocol.types",
)

# Backwards-compatible alias for the previous name; the surface now points at the
# protocol package rather than the agent package.
AI_AGENT_SURFACE = AI_PROTOCOL_SURFACE


# --- S1a: no runtime module may statically import a feature implementation ---
# Product features (``baldric.runtime.features.<name>``) are loaded by the
# platform layer through a string path + importlib, never a static import, so no
# other module may depend on a feature implementation. The rule is expressed
# inversely on purpose: *every* ``baldric.runtime.*`` module except the features
# package itself is a forbidden importer, so a subpackage added tomorrow is
# covered without touching this file (the original allowlist of three prefixes
# silently missed session/tools/commands/context/rendering because those still
# live directly under ``runtime`` — see plan §0.2). Features importing features
# is governed separately by the AllowRule whitelist below. The check walks every
# static import node (top-level AND function-body, because ``ast.walk`` sees
# both); ``importlib.import_module`` string paths are not import nodes and stay
# legal.
RUNTIME_PREFIX = "baldric.runtime"
FEATURES_PREFIX = "baldric.runtime.features"


def scan_feature_isolation_violations(root: Path = ROOT) -> list[ImportViolation]:
    """Return static feature imports from any runtime module outside ``features``."""
    violations: list[ImportViolation] = []
    source_root = root / "src"
    if not source_root.exists():
        return violations
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts or "data" in path.parts:
            continue
        module = _module_name(path, root)
        if not _under(module, RUNTIME_PREFIX) or _under(module, FEATURES_PREFIX):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, imported in _imports(tree):
            if _under(imported, FEATURES_PREFIX):
                violations.append(ImportViolation(module=module, lineno=lineno, imported=imported))
    return violations


# --- whitelist rules (structural rearchitecture) -----------------------------
# ``RULES`` above can only say "A may not import B". The rearchitecture also
# needs "A may import B, but only these submodules of B": the subagents UI is
# the one documented features->frontends exception, and it may reach exactly the
# three TUI modules it mounts widgets with, never the rest of the frontend. An
# ``AllowRule`` expresses that. When several rules match one import, the MOST
# SPECIFIC one wins (longest source prefix, then longest target prefix), so the
# narrow ``subagents.ui`` exception is not swallowed by the blanket
# features->frontends ban. The full intended layer matrix lives in the
# structural plan §4.3; cells enforced elsewhere are the tui rules above and the
# feature-isolation scan. The checker is proven (in
# ``tests/guards/test_import_boundaries.py``) to fire on synthetic input, so a
# new violation and a broken rule are distinguishable.
@dataclass(frozen=True, slots=True)
class AllowRule:
    """Permit ``source`` to import only ``allow`` submodules of ``target``.

    ``target`` is a package prefix; a source module (``source`` or a descendant)
    importing ``target`` or any descendant must land under one of the ``allow``
    submodule names, or it is a violation. ``allow=()`` forbids importing the
    target entirely. A special case: when ``source == target`` (cross-feature
    discipline), the first path segment after the shared prefix identifies the
    feature, and intra-feature imports are always allowed.
    """

    source: str
    target: str
    allow: tuple[str, ...]


def _default_allow_rules() -> tuple[AllowRule, ...]:
    """Return the whitelist edges the structural plan §4.3 enforces today."""
    return (
        # features.a may import features.b.port, never features.b.service/etc.
        AllowRule(source="baldric.runtime.features", target="baldric.runtime.features", allow=("port",)),
        # The documented features->frontends exception: the subagents UI mounts
        # widgets built on exactly these three TUI modules (theme/keybindings,
        # transcript state, and the transcript widget). Anything else under
        # frontends.tui — and anything under frontends at all from any other
        # feature — is a violation.
        AllowRule(
            source="baldric.runtime.features.subagents.ui",
            target="baldric.runtime.frontends.tui",
            allow=("config", "state", "widgets"),
        ),
        # Blanket ban: a feature must not depend on a frontend surface. Matches
        # every features->frontends import; the more specific rule above exempts
        # the subagents.ui trio via most-specific-wins.
        AllowRule(source="baldric.runtime.features", target="baldric.runtime.frontends", allow=()),
    )


ALLOW_RULES: tuple[AllowRule, ...] = _default_allow_rules()


@dataclass(frozen=True, slots=True)
class ImportViolation:
    """One forbidden import plus where it was found."""

    module: str
    lineno: int
    imported: str


def _module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root / "src").with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.lineno, node.module))
    return found


def scan_violations(root: Path = ROOT) -> list[ImportViolation]:
    """Return every import that violates :data:`RULES` under ``root/src``."""
    violations: list[ImportViolation] = []
    source_root = root / "src"
    if not source_root.exists():
        return violations
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts or "data" in path.parts:
            continue
        module = _module_name(path, root)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, imported in _imports(tree):
            for source_prefix, forbidden in RULES:
                if (module == source_prefix or module.startswith(source_prefix + ".")) and (
                    imported == forbidden or imported.startswith(forbidden + ".")
                ):
                    violations.append(ImportViolation(module=module, lineno=lineno, imported=imported))
    return violations


def _is_on_surface(imported: str) -> bool:
    return any(imported == module or imported.startswith(module + ".") for module in AI_PROTOCOL_SURFACE)


def scan_surface_violations(root: Path = ROOT) -> list[ImportViolation]:
    """Return provider-layer imports outside the protocol contract surface.

    The provider layer may import the ``baldric.protocol`` contract and nothing
    else from the in-project packages. Importing ``baldric.agent`` (runtime or
    package root) ties the provider layer to the harness and is a violation.
    """
    violations: list[ImportViolation] = []
    source_root = root / "src"
    if not source_root.exists():
        return violations
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts or "data" in path.parts:
            continue
        module = _module_name(path, root)
        if not (module == "baldric.ai" or module.startswith("baldric.ai.")):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, imported in _imports(tree):
            if imported == "baldric.agent" or imported.startswith("baldric.agent."):
                violations.append(ImportViolation(module=module, lineno=lineno, imported=imported))
                continue
            if (
                imported == "baldric.protocol" or imported.startswith("baldric.protocol.")
            ) and not _is_on_surface(imported):
                violations.append(ImportViolation(module=module, lineno=lineno, imported=imported))
    return violations


def _under(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _most_specific_rule(matching: list[AllowRule]) -> AllowRule:
    """Pick the rule that governs an import: longest source, then longest target.

    Overlapping rules encode an exception inside a blanket ban (the subagents UI
    trio inside the features->frontends ban); applying every match would let the
    blanket rule condemn imports the exception deliberately permits.
    """
    return max(matching, key=lambda rule: (len(rule.source), len(rule.target)))


def scan_allow_violations(
    root: Path = ROOT,
    rules: tuple[AllowRule, ...] | None = None,
) -> list[ImportViolation]:
    """Return imports that breach an :class:`AllowRule` whitelist.

    For each import, the most specific matching rule (longest ``source``, then
    longest ``target``) decides. Under that rule, the import is permitted only if
    it resolves to one of the allowed submodules, **or** it stays within the
    source's own package namespace. The special self-referential rule
    (``source == target``, e.g. cross-feature) uses the first path segment after
    the shared prefix as the "feature" identity and only flags imports that cross
    into a *different* feature namespace.
    """
    active = rules if rules is not None else ALLOW_RULES
    violations: list[ImportViolation] = []
    source_root = root / "src"
    if not source_root.exists() or not active:
        return violations
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts or "data" in path.parts:
            continue
        module = _module_name(path, root)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, imported in _imports(tree):
            matching = [
                rule for rule in active if _under(module, rule.source) and _under(imported, rule.target)
            ]
            if not matching:
                continue
            rule = _most_specific_rule(matching)
            if rule.source == rule.target:
                # Same namespace: allow within the same feature, police
                # cross-feature imports to anything but the allowed submodule.
                source_rest = module[len(rule.source) :].lstrip(".")
                target_rest = imported[len(rule.target) :].lstrip(".")
                source_head = source_rest.split(".", 1)[0] if source_rest else ""
                if target_rest == source_head or target_rest.startswith(source_head + "."):
                    continue  # intra-feature
                remainder = target_rest.split(".", 1)[1] if "." in target_rest else ""
                head = remainder.split(".", 1)[0] if remainder else ""
                if head in rule.allow:
                    continue
                violations.append(ImportViolation(module=module, lineno=lineno, imported=imported))
                continue
            # Cross-package rule: the imported path relative to the target
            # must begin with an allowed submodule name.
            remainder = imported[len(rule.target) :].lstrip(".")
            head = remainder.split(".", 1)[0] if remainder else ""
            if head in rule.allow:
                continue
            violations.append(ImportViolation(module=module, lineno=lineno, imported=imported))
    return violations


def main() -> int:
    violations = (
        [(violation, "layer") for violation in scan_violations()]
        + [(violation, "surface") for violation in scan_surface_violations()]
        + [(violation, "allow") for violation in scan_allow_violations()]
        + [(violation, "s1a") for violation in scan_feature_isolation_violations()]
    )
    if violations:
        print("import-graph violations:")
        for violation, kind in violations:
            print(f"  [{kind}] {violation.module}:{violation.lineno} imports {violation.imported}")
        return 1
    print("import-graph: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
