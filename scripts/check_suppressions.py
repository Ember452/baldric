#!/usr/bin/env python3
"""Suppression ratchet: ``# type: ignore`` and ``# noqa`` may only shrink.

Usage:
    uv run python scripts/check_suppressions.py            # check against baseline
    uv run python scripts/check_suppressions.py --init     # rewrite the baseline
    uv run python scripts/check_suppressions.py --report   # print the current distribution

Why this exists
---------------
``mypy --strict`` and ``ruff`` can be kept green by sprinkling suppression
comments. Without a counter, every new suppression is invisible: the checks
still pass, so nothing reports that the codebase is losing type/lint coverage.
This ratchet records the current count per file and per suppression kind and
fails when any count grows. Counts that shrink are reported as a hint to rerun
``--init``; the baseline is committed and only ever tightens.

Comment scanning uses ``tokenize`` rather than a regexp so the literal text
``noqa`` inside a string or docstring is never counted. The scanner also
asserts a non-empty corpus, so a wrong path can never make the gate vacuously
green.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "suppressions-baseline.json"
SCAN_ROOT = ROOT / "src"
MINIMUM_CORPUS = 100

TYPE_IGNORE_RE = re.compile(r"#\s*type:\s*ignore(?:\[([^\]]*)\])?")
NOQA_RE = re.compile(r"#\s*noqa(?::\s*([A-Z][A-Z0-9]*(?:[,\s]+[A-Z][A-Z0-9]*)*))?")


def _suppression_kind(comment: str) -> list[str]:
    """Return the suppression keys contributed by one comment token."""
    kinds: list[str] = []
    type_ignore = TYPE_IGNORE_RE.search(comment)
    if type_ignore is not None:
        codes = (type_ignore.group(1) or "").strip()
        if codes:
            kinds.extend(f"type-ignore:{code.strip()}" for code in codes.split(",") if code.strip())
        else:
            kinds.append("type-ignore")
    noqa = NOQA_RE.search(comment)
    if noqa is not None:
        codes = noqa.group(1) or ""
        if codes.strip():
            kinds.extend(
                f"noqa:{code.strip()}" for code in re.split(r"[,\s]+", codes.strip()) if code.strip()
            )
        else:
            kinds.append("noqa")
    return kinds


def _file_suppressions(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    source = path.read_text(encoding="utf-8")
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        for kind in _suppression_kind(token.string):
            counts[kind] = counts.get(kind, 0) + 1
    return counts


def build_report() -> dict[str, dict[str, int]]:
    """Return ``{relative_path: {suppression_kind: count}}`` for ``src/``."""
    report: dict[str, dict[str, int]] = {}
    scanned = 0
    for path in sorted(SCAN_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        scanned += 1
        counts = _file_suppressions(path)
        if counts:
            report[path.relative_to(ROOT).as_posix()] = counts
    if scanned < MINIMUM_CORPUS:
        raise SystemExit(
            f"suppression scan found only {scanned} Python files under {SCAN_ROOT}; "
            f"expected at least {MINIMUM_CORPUS}. The corpus must not silently shrink."
        )
    return report


def _check(report: dict[str, dict[str, int]], baseline: dict[str, dict[str, int]]) -> list[str]:
    violations: list[str] = []
    improvements: list[str] = []
    for path, counts in sorted(report.items()):
        allowed = baseline.get(path, {})
        for kind, count in sorted(counts.items()):
            limit = allowed.get(kind, 0)
            if count > limit:
                violations.append(f"{path}: {kind} grew to {count} (baseline {limit})")
            elif count < limit:
                improvements.append(f"{path}: {kind} shrank to {count} (baseline {limit})")
    for path, kinds in sorted(baseline.items()):
        actual = report.get(path)
        if actual is None:
            improvements.append(f"{path}: no suppressions left")
            continue
        for kind, limit in sorted(kinds.items()):
            if kind not in actual:
                improvements.append(f"{path}: {kind} shrank to 0 (baseline {limit})")
    if improvements:
        print("suppression improvements available (rerun with --init to tighten):")
        for item in improvements:
            print(f"  {item}")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init", action="store_true", help="write the current distribution as the baseline")
    parser.add_argument("--report", action="store_true", help="print the current suppression distribution")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help=f"baseline file (default: {DEFAULT_BASELINE.name})",
    )
    args = parser.parse_args()

    report = build_report()
    if args.report:
        total = sum(sum(counts.values()) for counts in report.values())
        print(f"{total} suppressions across {len(report)} files")
        for path, counts in sorted(report.items()):
            print(f"  {path}: " + ", ".join(f"{kind}={count}" for kind, count in sorted(counts.items())))
        return 0
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
        print("suppression ratchet violations:")
        for violation in violations:
            print(f"  {violation}")
        print("Fix the underlying finding instead of adding a suppression comment.")
        return 1
    print("suppression ratchet: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
