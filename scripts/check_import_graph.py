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
    ("baldric_agent", "baldric_coding"),
    ("baldric_agent", "textual"),
    ("baldric_agent", "rich"),
    ("baldric_ai", "baldric_coding"),
    ("baldric_coding.session", "baldric_coding.tui"),
    ("baldric_coding.tools", "baldric_coding.tui"),
    ("baldric_coding.backends", "baldric_coding.tui"),
    ("baldric_coding.trust", "baldric_coding.tui"),
    ("baldric_coding.context", "baldric_coding.tui"),
    ("baldric_coding.providers", "baldric_coding.tui"),
    ("baldric_coding.rendering", "baldric_coding.tui"),
)

# The provider layer may use the harness's provider-neutral wire contract and
# nothing else. This records today's surface so it cannot deepen while the
# contract's home is still being settled: an adapter that imports the loop, the
# harness, or the session would tie the provider layer to the harness runtime and
# make the declared direction of the two packages untrue in a second way.
AI_AGENT_SURFACE: tuple[str, ...] = (
    "baldric_agent.messages",
    "baldric_agent.provider",
    "baldric_agent.provider_events",
    "baldric_agent.tools",
    "baldric_agent.types",
)


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
    return any(imported == module or imported.startswith(module + ".") for module in AI_AGENT_SURFACE)


def scan_surface_violations(root: Path = ROOT) -> list[ImportViolation]:
    """Return provider-layer imports of the harness beyond :data:`AI_AGENT_SURFACE`.

    ``from baldric_agent import X`` counts as a violation: importing the package
    root executes ``baldric_agent/__init__.py``, which pulls the session, storage,
    and JSONL modules the provider layer must not depend on.
    """
    violations: list[ImportViolation] = []
    source_root = root / "src"
    if not source_root.exists():
        return violations
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts or "data" in path.parts:
            continue
        module = _module_name(path, root)
        if not (module == "baldric_ai" or module.startswith("baldric_ai.")):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, imported in _imports(tree):
            if not (imported == "baldric_agent" or imported.startswith("baldric_agent.")):
                continue
            if not _is_on_surface(imported):
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
