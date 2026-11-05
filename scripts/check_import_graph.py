#!/usr/bin/env python3
"""Check import-direction invariants for the three Baldric packages.

Usage:
    uv run python scripts/check_import_graph.py

The script parses absolute imports with ast. It intentionally does not try to
resolve every runtime import; it is a guard for layer direction, not a complete
import checker. A violation prints the source file, line, and imported module.
"""

from __future__ import annotations

import ast
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
)


def _module_name(path: Path) -> str:
    relative = path.relative_to(ROOT / "src").with_suffix("")
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


def main() -> int:
    violations: list[tuple[str, int, str]] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        if "__pycache__" in path.parts or "data" in path.parts:
            continue
        module = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, imported in _imports(tree):
            for source_prefix, forbidden in RULES:
                if (module == source_prefix or module.startswith(source_prefix + ".")) and (
                    imported == forbidden or imported.startswith(forbidden + ".")
                ):
                    violations.append((module, lineno, imported))
    if violations:
        print("import-graph violations:")
        for module, lineno, imported in violations:
            print(f"  {module}:{lineno} imports {imported}")
        return 1
    print("import-graph: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
