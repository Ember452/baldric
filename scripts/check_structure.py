#!/usr/bin/env python3
"""Structure ratchet: file size, function length, inheritance, and coupling.

Usage:
    uv run python scripts/check_structure.py            # check against baseline
    uv run python scripts/check_structure.py --init     # (re)write the baseline

The script parses ``src/`` with ``ast`` and measures four structure metrics:

* per-file line count;
* per-file longest function body (direct statements, excluding nested defs);
* global deepest class-inheritance chain reachable inside the project;
* global widest module fan-out (distinct in-project modules imported).

A committed JSON baseline records the current values. Checking fails when any
metric regresses past its baseline, or when a file that has no baseline entry
exceeds the hard limits. Metrics that improved are reported as suggestions to
run ``--init`` again; the ratchet only ever tightens.

Line counts use ``splitlines()`` so they are independent of Windows/Unix
endings and of trailing newlines.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "structure-baseline.json"

HARD_LIMITS = {
    "lines": 1200,
    "max_function_stmts": 150,
    "inheritance_depth": 8,
    "module_fanout": 50,
}


@dataclass
class FileMetrics:
    lines: int
    max_function_stmts: int


@dataclass
class Report:
    files: dict[str, FileMetrics] = field(default_factory=dict)
    inheritance_depth: int = 0
    deepest_chain: str = ""
    module_fanout: int = 0
    widest_module: str = ""


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _file_metrics(path: Path) -> FileMetrics:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return FileMetrics(
        lines=len(path.read_text(encoding="utf-8").splitlines()),
        max_function_stmts=_longest_function_body(tree),
    )


def _longest_function_body(tree: ast.AST) -> int:
    longest = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            longest = max(longest, len(node.body))
    return longest


def _class_base_names(node: ast.ClassDef) -> list[str]:
    names: list[str] = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
    return names


def _inheritance_depth(trees: dict[str, ast.AST]) -> tuple[int, str]:
    """Deepest chain of project-defined bases, approximated across files."""
    bases_of: dict[str, list[str]] = {}
    for module, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in _class_base_names(node):
                    bases_of.setdefault(f"{module}.{node.name}", []).append(base)

    def depth(class_key: str, seen: frozenset[str]) -> tuple[int, str]:
        if class_key in seen or class_key not in bases_of:
            return 0, class_key
        best, chain = 0, class_key
        for base in bases_of[class_key]:
            # A base defined anywhere in the project under the same short name
            # continues the chain; unknown bases (stdlib/third-party) do not.
            candidates = [key for key in bases_of if key.rsplit(".", 1)[-1] == base]
            for candidate in candidates:
                sub_depth, sub_chain = depth(candidate, seen | {class_key})
                if sub_depth + 1 > best:
                    best, chain = sub_depth + 1, sub_chain
        return best, chain

    deepest, deepest_chain = 0, ""
    for class_key in bases_of:
        value, chain = depth(class_key, frozenset())
        if value > deepest:
            deepest, deepest_chain = value, chain
    return deepest, deepest_chain


def _module_fanout(trees: dict[str, ast.AST], project_roots: set[str]) -> tuple[int, str]:
    widest, widest_count = "", 0
    for module, tree in trees.items():
        imported: set[str] = set()
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                targets = [node.module]
            for target in targets:
                if target.split(".")[0] in project_roots:
                    imported.add(target)
        if len(imported) > widest_count:
            widest, widest_count = module, len(imported)
    return widest_count, widest


def build_report() -> Report:
    report = Report()
    trees: dict[str, ast.AST] = {}
    for path in sorted((ROOT / "src").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        module = path.relative_to(ROOT / "src").with_suffix("").as_posix()
        if module.endswith(".__init__"):
            module = module[: -len(".__init__")]
        trees[module] = ast.parse(path.read_text(encoding="utf-8"))
        report.files[_relative(path)] = _file_metrics(path)
    report.inheritance_depth, report.deepest_chain = _inheritance_depth(trees)
    report.module_fanout, report.widest_module = _module_fanout(
        trees, {"baldric_agent", "baldric_ai", "baldric_coding"}
    )
    return report


def _check(report: Report, baseline: dict[str, object]) -> list[str]:
    violations: list[str] = []
    improvements: list[str] = []
    baseline_files = baseline.get("files", {})
    for path, metrics in report.files.items():
        entry = baseline_files.get(path) if isinstance(baseline_files, dict) else None
        if entry is None:
            if metrics.lines > HARD_LIMITS["lines"]:
                violations.append(
                    f"{path}: {metrics.lines} lines exceeds the {HARD_LIMITS['lines']}-line hard limit"
                )
            if metrics.max_function_stmts > HARD_LIMITS["max_function_stmts"]:
                violations.append(
                    f"{path}: longest function has {metrics.max_function_stmts} statements "
                    f"(hard limit {HARD_LIMITS['max_function_stmts']})"
                )
            continue
        if metrics.lines > entry.get("lines", 0):
            violations.append(f"{path}: grew to {metrics.lines} lines (baseline {entry.get('lines')})")
        if metrics.max_function_stmts > entry.get("max_function_stmts", 0):
            violations.append(
                f"{path}: longest function grew to {metrics.max_function_stmts} statements "
                f"(baseline {entry.get('max_function_stmts')})"
            )
        if metrics.lines < entry.get("lines", 0) or metrics.max_function_stmts < entry.get(
            "max_function_stmts", 0
        ):
            improvements.append(path)

    baseline_global = baseline.get("global", {})
    if report.inheritance_depth > baseline_global.get("inheritance_depth", 0):
        violations.append(
            f"inheritance depth grew to {report.inheritance_depth} "
            f"(baseline {baseline_global.get('inheritance_depth')}, chain: {report.deepest_chain})"
        )
    if report.module_fanout > baseline_global.get("module_fanout", 0):
        violations.append(
            f"module fan-out grew to {report.module_fanout} "
            f"(baseline {baseline_global.get('module_fanout')}, widest: {report.widest_module})"
        )
    for name, value in (
        ("inheritance_depth", report.inheritance_depth),
        ("module_fanout", report.module_fanout),
    ):
        if value < baseline_global.get(name, 0):
            improvements.append(f"global {name}")

    if improvements:
        print("structure improvements available (rerun with --init to tighten):")
        for item in improvements:
            print(f"  {item}")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--init",
        action="store_true",
        help="write the current metrics as the new baseline (the ratchet tightens)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help=f"baseline file (default: {DEFAULT_BASELINE.name})",
    )
    args = parser.parse_args()

    report = build_report()
    if args.init:
        baseline = {
            "files": {
                path: {"lines": metrics.lines, "max_function_stmts": metrics.max_function_stmts}
                for path, metrics in sorted(report.files.items())
            },
            "global": {
                "inheritance_depth": report.inheritance_depth,
                "module_fanout": report.module_fanout,
            },
        }
        args.baseline.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"baseline written to {args.baseline}")
        return 0

    if not args.baseline.exists():
        print(f"baseline {args.baseline} is missing; run with --init to create it", file=sys.stderr)
        return 1
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    violations = _check(report, baseline)
    if violations:
        print("structure ratchet violations:")
        for violation in violations:
            print(f"  {violation}")
        return 1
    print("structure ratchet: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
