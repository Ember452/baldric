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


def main() -> int:
    violations = [(violation, "layer") for violation in scan_violations()] + [
        (violation, "surface") for violation in scan_surface_violations()
    ]
    if violations:
        print("import-graph violations:")
        for violation, kind in violations:
            print(f"  [{kind}] {violation.module}:{violation.lineno} imports {violation.imported}")
        return 1
    print("import-graph: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
