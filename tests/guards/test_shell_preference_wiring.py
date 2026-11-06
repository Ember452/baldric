"""Guard: every shell-tool construction forwards the ``shell`` preference.

Regression guard for the explicit-shell feature (#53). The ``shell`` preference
(auto/bash/pwsh/cmd) is resolved at *tool-construction* time, so wherever a
session builds its bash tool it must pass the same ``shell`` as the sibling
``shell_command_prefix``. The original PR wired only the primary call site, so a
resumed session (``session/lifecycle.py`` rebuild + staged reload) and the TUI
each rebuilt the bash tool with the default ``auto`` and silently dropped the
user's choice.

Rather than pin one file, scan every construction of ``create_coding_tools(`` and
``CodingSessionConfig(`` under ``src`` and require: if the call forwards
``shell_command_prefix=`` then it also forwards ``shell=``. A pure unit test
cannot see an omission at one call site in a large module; this catches the whole
class.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

# Call openers whose arguments may carry the shell settings.
OPENERS = ("create_coding_tools(", "CodingSessionConfig(")


def _iter_call_blocks(source: str):
    """Yield the argument text of each tracked call, balanced to its closing ')'.

    Naive but sufficient: the argument lists here never contain a ``)`` inside a
    string that would unbalance them (verified by the fact that every block ends
    at the first depth-0 ')'). We count parentheses/brackets/braces.
    """
    for opener in OPENERS:
        for match in re.finditer(re.escape(opener), source):
            i = match.end()
            depth = 1
            start = i
            while i < len(source) and depth > 0:
                ch = source[i]
                if ch in "([{":
                    depth += 1
                elif ch in ")]}":
                    depth -= 1
                i += 1
            yield source[start : i - 1]


def test_every_shell_call_site_forwards_shell_with_prefix() -> None:
    offenders: list[str] = []
    checked = 0
    for path in SRC.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for block in _iter_call_blocks(source):
            if not re.search(r"\bshell_command_prefix\s*=", block):
                continue
            checked += 1
            if not re.search(r"(?<![A-Za-z0-9_])shell\s*=", block):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert checked >= 3, f"expected several shell call sites, found {checked}"
    assert offenders == [], (
        "these call sites forward shell_command_prefix= but not shell=, so the "
        f"shell preference is silently downgraded to 'auto': {sorted(set(offenders))}"
    )
