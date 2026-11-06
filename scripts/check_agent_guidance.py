#!/usr/bin/env python3
"""Agent-guidance ratchet: instruction files may only shrink or stay stable.

Usage:
    uv run python scripts/check_agent_guidance.py            # check the baseline
    uv run python scripts/check_agent_guidance.py --init     # rewrite the baseline

Why this exists
---------------
Agents tend to append "one more note" to instruction files. Left unchecked,
``AGENTS.md`` becomes a long document nobody reads and every session pays for
it in context. This ratchet records the current byte size of every managed
instruction file and the deepest root-to-module chain, then fails when either
grows. Raising a budget therefore requires an explicit ``--init`` run, which is
exactly the "explain why in the PR" moment the ratchet is meant to create.

Managed files are discovered by name, not by a single hard-coded path, so a
parallel copy (``CLAUDE.md`` and similar) cannot silently escape the budget.
``CLAUDE.md`` is additionally required to stay a thin import shim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "agent-guidance-baseline.json"

GUIDANCE_NAMES = ("AGENTS.md", "CLAUDE.md")
# Hard ceilings regardless of the baseline: a new instruction file cannot start
# life already huge.
ROOT_HARD_LIMIT = 20 * 1024
MODULE_HARD_LIMIT = 32 * 1024
CHAIN_HARD_LIMIT = 96 * 1024
SHIM_HARD_LIMIT = 1024
SHIM_REQUIRED_TEXT = "@AGENTS.md"


def _managed_files() -> list[Path]:
    """Return root-level and package-level guidance files, shallow to deep."""
    files: list[Path] = []
    for name in GUIDANCE_NAMES:
        candidate = ROOT / name
        if candidate.exists():
            files.append(candidate)
    for package_dir in sorted((ROOT / "src").glob("*")):
        if not package_dir.is_dir():
            continue
        for name in GUIDANCE_NAMES:
            candidate = package_dir / name
            if candidate.exists():
                files.append(candidate)
    return files


def _normalized_bytes(path: Path) -> int:
    """Byte size independent of the checkout's line endings.

    ``read_text`` uses universal newlines, so a CRLF checkout (git
    ``core.autocrlf=true`` on Windows CI) measures the same as the LF blob.
    Without this, every LF-recorded baseline fails on CRLF checkouts.
    """
    return len(path.read_text(encoding="utf-8").encode("utf-8"))


def _chain_bytes(module_file: Path) -> int:
    """Return the root instructions plus every ancestor scoped file."""
    total = 0
    for name in GUIDANCE_NAMES:
        root_file = ROOT / name
        if root_file.exists():
            total += _normalized_bytes(root_file)
            break
    package_dir = module_file.parent
    if package_dir != ROOT:
        candidate = package_dir / module_file.name
        if candidate.exists():
            total += _normalized_bytes(candidate)
    return total


def build_report() -> dict[str, object]:
    files: dict[str, int] = {}
    shims: list[str] = []
    deepest = 0
    for path in _managed_files():
        size = _normalized_bytes(path)
        relative = path.relative_to(ROOT).as_posix()
        files[relative] = size
        if path.name == "CLAUDE.md":
            shims.append(relative)
        if path.name == "AGENTS.md" and path.parent != ROOT:
            deepest = max(deepest, _chain_bytes(path))
    return {"files": files, "shims": shims, "chain_bytes": deepest}


def _check(report: dict[str, object], baseline: dict[str, object]) -> list[str]:
    violations: list[str] = []
    improvements: list[str] = []
    files = report["files"]
    baseline_files = baseline.get("files", {})
    assert isinstance(files, dict) and isinstance(baseline_files, dict)
    for path, size in sorted(files.items()):
        limit_kind = "root" if "/" not in path else "module"
        hard_limit = ROOT_HARD_LIMIT if limit_kind == "root" else MODULE_HARD_LIMIT
        if path.endswith("CLAUDE.md") and size > SHIM_HARD_LIMIT:
            violations.append(f"{path}: {size} bytes exceeds the {SHIM_HARD_LIMIT}-byte shim limit")
        if size > hard_limit:
            violations.append(f"{path}: {size} bytes exceeds the {hard_limit}-byte hard limit")
        previous = baseline_files.get(path)
        if previous is None:
            continue
        if size > previous:
            violations.append(f"{path}: grew to {size} bytes (baseline {previous})")
        elif size < previous:
            improvements.append(f"{path}: shrank to {size} bytes (baseline {previous})")
    chain_bytes = report["chain_bytes"]
    baseline_chain = baseline.get("chain_bytes", 0)
    assert isinstance(chain_bytes, int) and isinstance(baseline_chain, int)
    if chain_bytes > CHAIN_HARD_LIMIT:
        violations.append(f"deepest instruction chain is {chain_bytes} bytes (hard limit {CHAIN_HARD_LIMIT})")
    if chain_bytes > baseline_chain:
        violations.append(
            f"deepest instruction chain grew to {chain_bytes} bytes (baseline {baseline_chain})"
        )
    elif chain_bytes < baseline_chain:
        improvements.append(f"deepest instruction chain shrank to {chain_bytes} bytes")

    shims = report["shims"]
    assert isinstance(shims, list)
    for shim in shims:
        text = (ROOT / str(shim)).read_text(encoding="utf-8")
        if SHIM_REQUIRED_TEXT not in text:
            violations.append(f"{shim}: must import {SHIM_REQUIRED_TEXT} so instructions stay single-source")

    if improvements:
        print("agent-guidance improvements available (rerun with --init to tighten):")
        for item in improvements:
            print(f"  {item}")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init", action="store_true", help="write the current sizes as the baseline")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help=f"baseline file (default: {DEFAULT_BASELINE.name})",
    )
    args = parser.parse_args()

    report = build_report()
    if args.init:
        args.baseline.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"baseline written to {args.baseline}")
        return 0
    if not args.baseline.exists():
        print(f"baseline {args.baseline} is missing; run with --init to create it", file=sys.stderr)
        return 1
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    violations = _check(report, baseline)
    if violations:
        print("agent-guidance ratchet violations:")
        for violation in violations:
            print(f"  {violation}")
        print("Move detail into linked docs instead of growing the instruction file.")
        return 1
    print("agent-guidance ratchet: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
