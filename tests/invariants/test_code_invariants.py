"""Code invariants that static review keeps missing.

Each check walks ``src/`` with ``ast`` (never regexps, which match docstrings
and miss aliases). Hard invariants must stay at zero; the encoding invariant is
a ratchet, because the existing 18 call sites predate the rule and only need to
stop growing.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "src"

# Ratchet: the count of IO calls without an explicit encoding may only shrink.
# Lower this number whenever a call site is fixed; never raise it.
ENCODING_BASELINE = 18

MINIMUM_CORPUS = 100


def _source_files() -> list[Path]:
    files = [path for path in SOURCE_ROOT.rglob("*.py") if "__pycache__" not in path.parts]
    assert len(files) >= MINIMUM_CORPUS, (
        f"invariant scan found only {len(files)} files under {SOURCE_ROOT}; "
        "the corpus must not silently shrink"
    )
    return files


def _iter_nodes() -> list[tuple[Path, ast.AST]]:
    nodes: list[tuple[Path, ast.AST]] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        nodes.extend((path, node) for node in ast.walk(tree))
    return nodes


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _io_without_encoding() -> list[str]:
    violations: list[str] = []
    for path, node in _iter_nodes():
        if not isinstance(node, ast.Call):
            continue
        keywords = {keyword.arg for keyword in node.keywords}
        name = _call_name(node)
        is_open = name == "open"
        is_path_io = name in {"read_text", "write_text"}
        if (is_open or is_path_io) and "encoding" not in keywords and "mode" not in keywords:
            violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} {name}()")
    return violations


def _subprocess_without_timeout() -> list[str]:
    violations: list[str] = []
    for path, node in _iter_nodes():
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
            continue
        if func.value.id != "subprocess" or func.attr not in {"run", "call", "check_call", "check_output"}:
            continue
        keywords = {keyword.arg for keyword in node.keywords}
        if "timeout" not in keywords:
            violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} subprocess.{func.attr}()")
    return violations


def _bare_except() -> list[str]:
    violations: list[str] = []
    for path, node in _iter_nodes():
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} bare except")
    return violations


def test_io_calls_declare_encoding() -> None:
    violations = _io_without_encoding()

    assert len(violations) <= ENCODING_BASELINE, (
        f"IO without an explicit encoding grew to {len(violations)} "
        f'(baseline {ENCODING_BASELINE}). Pass encoding="utf-8":\n' + "\n".join(violations)
    )


def test_subprocess_calls_set_a_timeout() -> None:
    violations = _subprocess_without_timeout()

    assert violations == [], "subprocess calls must pass an explicit timeout:\n" + "\n".join(violations)


def test_no_bare_except() -> None:
    violations = _bare_except()

    assert violations == [], "bare except hides KeyboardInterrupt and SystemExit:\n" + "\n".join(violations)
