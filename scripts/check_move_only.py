#!/usr/bin/env python3
"""Reject commits that change more than import blocks inside src/ and tests/.

Usage:
    uv run python scripts/check_move_only.py HEAD
    uv run python scripts/check_move_only.py <commit-ish> --allow PATH [--allow PATH ...]

The script diffs ``<commit-ish>^`` against ``<commit-ish>`` with rename
detection and zero context. A change is accepted when every added or removed
content line below ``src/`` or ``tests/`` belongs to one of:

* an import statement (single-line or parenthesised multi-line block);
* a docstring line or blank line in a newly created package ``__init__.py``
  (rule 2.1: new package inits carry a docstring only);
* a path declared with ``--allow`` -- used only for the documented, ledgered
  path-expression fixes that a move makes unavoidable (for example the theme
  JSON loader in ``rendering/themes/__init__.py``).

Everything else is printed as a violation and the process exits non-zero.

The script is intentionally narrow: it is a guard for the phase-1 move-only
refactor, not a general-purpose diff auditor.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath

_SCOPE_PREFIXES = ("src/", "tests/")

# Diff metadata lines. These describe the patch, not its content.
_METADATA_PREFIXES = (
    "diff --git ",
    "index ",
    "similarity index ",
    "dissimilarity index ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
    "new file mode ",
    "deleted file mode ",
    "old mode ",
    "new mode ",
    "--- ",
    "+++ ",
    "@@",
    "\\ No newline at end of file",
)

_DIFF_RE = re.compile(r"^diff --git a/(?P<old>.+) b/(?P<new>.+)$")
_HUNK_RE = re.compile(r"^@@ -(?P<old>\d+)(?:,(?P<old_count>\d+))? \+(?P<new>\d+)(?:,(?P<new_count>\d+))? @@")
_IMPORT_RE = re.compile(r"^(?:from\s+[.\w]+\s+import\b|import\s+)")
_DOCSTRING_PREFIX_RE = re.compile(r"^[rRuUbB]{0,2}")


@dataclass
class Violation:
    """One changed line that is not allowed by the move-only contract."""

    path: str
    line: int
    side: str
    text: str


class _ImportBlock:
    """Tracks whether one side of a hunk is inside an import statement."""

    def __init__(self) -> None:
        self._active = False
        self._depth = 0
        self._backslash = False

    def feed(self, text: str) -> bool:
        stripped = text.strip()
        if self._active:
            if self._backslash:
                self._backslash = text.rstrip().endswith("\\")
                return True
            self._depth += text.count("(") - text.count(")")
            if self._depth <= 0:
                self._active = False
                self._depth = 0
            return True
        if not _IMPORT_RE.match(stripped):
            return False
        depth = text.count("(") - text.count(")")
        if depth > 0:
            self._active = True
            self._depth = depth
        elif text.rstrip().endswith("\\"):
            self._active = True
            self._backslash = True
        return True


class _DocstringBlock:
    """Tracks whether a new file contains only blank lines and docstrings."""

    def __init__(self) -> None:
        self._delimiter: str | None = None

    def feed(self, text: str) -> bool:
        stripped = text.strip()
        if self._delimiter is not None:
            if self._delimiter in stripped:
                self._delimiter = None
            return True
        if not stripped:
            return True
        match = _DOCSTRING_PREFIX_RE.match(stripped)
        candidate = stripped[match.end() :] if match else stripped
        for delimiter in ('"""', "'''"):
            if candidate.startswith(delimiter):
                if delimiter not in candidate[len(delimiter) :]:
                    self._delimiter = delimiter
                return True
        return False


def _git_diff(commit: str) -> str:
    base = f"{commit}^"
    result = subprocess.run(
        [
            "git",
            "diff",
            "--find-renames",
            "-U0",
            "--no-color",
            "--no-ext-diff",
            base,
            commit,
        ],
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(f"check_move_only: cannot diff {base}..{commit}")
    return result.stdout


def check(commit: str, allowed_paths: set[str]) -> list[Violation]:
    """Return every non-import content change introduced by ``commit``."""

    violations: list[Violation] = []
    path = ""
    is_new_file = False
    old_line = 0
    new_line = 0
    in_hunk = False
    import_old = _ImportBlock()
    import_new = _ImportBlock()
    docstring = _DocstringBlock()

    for raw_line in _git_diff(commit).splitlines():
        diff_match = _DIFF_RE.match(raw_line)
        if diff_match is not None:
            path = diff_match.group("new")
            is_new_file = False
            in_hunk = False
            continue
        if raw_line.startswith("new file mode "):
            is_new_file = True
            continue
        hunk_match = _HUNK_RE.match(raw_line)
        if hunk_match is not None:
            old_line = int(hunk_match.group("old"))
            new_line = int(hunk_match.group("new"))
            in_hunk = True
            import_old = _ImportBlock()
            import_new = _ImportBlock()
            docstring = _DocstringBlock()
            continue
        if not in_hunk:
            if raw_line and not raw_line.startswith(_METADATA_PREFIXES):
                sys.stderr.write(f"check_move_only: unparsed diff line: {raw_line!r}\n")
                raise SystemExit(2)
            continue
        if not raw_line:
            continue
        if raw_line.startswith(_METADATA_PREFIXES):
            continue

        side = raw_line[0]
        text = raw_line[1:]
        if side == "-":
            line_no = old_line
            old_line += 1
            allowed = import_old.feed(text)
        elif side == "+":
            line_no = new_line
            new_line += 1
            if is_new_file and PurePosixPath(path).name == "__init__.py":
                allowed = docstring.feed(text)
            else:
                allowed = import_new.feed(text)
        elif side == " ":
            old_line += 1
            new_line += 1
            continue
        else:
            sys.stderr.write(f"check_move_only: unparsed hunk line: {raw_line!r}\n")
            raise SystemExit(2)

        if allowed:
            continue
        if path in allowed_paths:
            continue
        if not path.startswith(_SCOPE_PREFIXES) or not path.endswith(".py"):
            continue
        violations.append(Violation(path=path, line=line_no, side=side, text=text))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit", help="commit-ish to inspect (compared with its parent)")
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="PATH",
        help="repo-relative path whose non-import changes are declared in the migration ledger",
    )
    args = parser.parse_args(argv)

    allowed_paths = {path.replace("\\", "/") for path in args.allow}
    violations = check(args.commit, allowed_paths)
    if violations:
        print(f"check_move_only: {len(violations)} violation(s) in {args.commit}")
        for violation in violations:
            print(f"  {violation.path}:{violation.line} {violation.side} {violation.text.rstrip()}")
        return 1
    print(f"check_move_only: OK -- {args.commit} contains no non-import changes under src/ or tests/")
    if allowed_paths:
        print(f"check_move_only: declared exceptions: {', '.join(sorted(allowed_paths))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
