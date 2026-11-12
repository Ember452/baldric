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
    ("baldric.runtime.session", "baldric.runtime.tui"),
    ("baldric.runtime.tools", "baldric.runtime.tui"),
    ("baldric.runtime.backends", "baldric.runtime.tui"),
    ("baldric.runtime.trust", "baldric.runtime.tui"),
    ("baldric.runtime.context", "baldric.runtime.tui"),
    ("baldric.runtime.providers", "baldric.runtime.tui"),
    ("baldric.runtime.rendering", "baldric.runtime.tui"),
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


# --- S1a: core / platform / frontends must not import a feature *statically* ---
# A product feature (``baldric.runtime.features.<name>``) is loaded by the
# platform layer through a string path + importlib, never a static import, so the
# lower layers never depend on a feature implementation. This is acceptance S1a
# of the structural rearchitecture; the check walks every static import node
# (top-level AND function-body, because ``ast.walk`` sees both).
S1A_FORBIDDEN_IMPORTERS: tuple[str, ...] = (
    "baldric.runtime.core",
    "baldric.runtime.platform",
    "baldric.runtime.frontends",
    # ``runtime.extensions`` is the current home of the platform loader (it moves
    # to ``runtime.platform`` in stage E); the built-in registry lives here and
    # must resolve features by string path, not a static import.
    "baldric.runtime.extensions",
)
FEATURES_PREFIX = "baldric.runtime.features"


def scan_feature_isolation_violations(root: Path = ROOT) -> list[ImportViolation]:
    """Return static imports of a feature implementation from core/platform/frontends."""
    violations: list[ImportViolation] = []
    source_root = root / "src"
    if not source_root.exists():
        return violations
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts or "data" in path.parts:
            continue
        module = _module_name(path, root)
        if not any(_under(module, prefix) for prefix in S1A_FORBIDDEN_IMPORTERS):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, imported in _imports(tree):
            if _under(imported, FEATURES_PREFIX):
                violations.append(ImportViolation(module=module, lineno=lineno, imported=imported))
    return violations


# --- whitelist rules (structural rearchitecture stage A0) --------------------
# ``RULES`` above can only say "A may not import B". The rearchitecture needs the
# opposite shape too: "A may import B, but only these submodules of B" (e.g. a
# feature may reach another feature's ``port`` but never its ``service``). An
# ``AllowRule`` expresses that. The rules are data-led by ``LAYER_MATRIX`` below;
# the concrete source/target packages (``runtime.core`` / ``runtime.platform`` /
# ``runtime.features`` / ``runtime.frontends``) do not exist yet — they are
# created in later stages — so today the real tree yields no whitelist
# violations. This stage installs the checker and proves (in
# ``tests/guards/test_import_boundaries.py``) that it fires on synthetic input,
# which is the cheap moment to build a gate: once the directories exist, a new
# violation and a broken rule are indistinguishable without it.
@dataclass(frozen=True, slots=True)
class AllowRule:
    """Permit ``source`` to import only ``allow`` submodules of ``target``.

    ``target`` is a package prefix; a source module (``source`` or a descendant)
    importing ``target`` or any descendant must land under one of the ``allow``
    submodule names, or it is a violation. ``allow=()`` forbids importing the
    target entirely (equivalent to a ``RULES`` entry, kept here for symmetry).
    """

    source: str
    target: str
    allow: tuple[str, ...]


# The intended layer dependency matrix (rows = importer domain, cols = the set of
# domains it may reach). This is documentation-in-code for the target skeleton;
# ``ALLOW_RULES`` derives the machine-checkable whitelist edges from it. A cell
# absent from a row means "not permitted". Kept as data so later stages flip
# individual edges on as the packages appear, instead of editing scanner logic.
LAYER_MATRIX: dict[str, tuple[str, ...]] = {
    # A feature may only reach another feature's public ``port`` submodule.
    "features": ("protocol", "core", "providers", "platform", "features"),
    "platform": ("protocol", "config", "observability", "utils", "providers"),
    "frontends": ("protocol", "core", "providers", "platform"),
}


def _default_allow_rules() -> tuple[AllowRule, ...]:
    """Return the concrete whitelist edges implied by :data:`LAYER_MATRIX`.

    Only the cross-feature edge is a *narrowing* whitelist today (a feature may
    import a sibling feature's ``port`` only); the other matrix rows are
    expressed as ordinary forbidden edges once those packages exist. Returning
    them as ``AllowRule`` objects keeps the checker uniform.
    """
    return (
        # features.a may import features.b.port, never features.b.service/etc.
        AllowRule(source="baldric.runtime.features", target="baldric.runtime.features", allow=("port",)),
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


def scan_allow_violations(
    root: Path = ROOT,
    rules: tuple[AllowRule, ...] | None = None,
) -> list[ImportViolation]:
    """Return imports that breach an :class:`AllowRule` whitelist.

    For each source under ``rule.source`` that imports something under
    ``rule.target``, the import is permitted only if it resolves to one of the
    allowed submodules, **or** it stays within the source's own package namespace
    (a package importing its own siblings/descendants is always allowed). The
    special self-referential rule (``source == target``, e.g. cross-feature) uses
    the first path segment after the shared prefix as the "feature" identity and
    only flags imports that cross into a *different* feature namespace.
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
            for rule in active:
                if not _under(module, rule.source) or not _under(imported, rule.target):
                    continue
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
