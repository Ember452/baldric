"""Terminal capability self-check printed by ``baldric --doctor``.

The report is environment-derived and never probes the TTY with timed
queries, so it is safe to run piped, over SSH, or from a broken terminal —
the situations where a doctor command is most needed.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
import unicodedata
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

from rich.console import Console
from rich.table import Table

from baldric_coding.version import current_version

_TRUECOLOR_TERMS = {"truecolor", "24bit"}
_KNOWN_OSC94_TERMINALS = {"Windows Terminal", "iTerm.app", "ghostty", "WezTerm", "kitty"}
_KNOWN_OSC_NOTIFY_TERMINALS = {"ghostty", "iTerm.app", "mintty", "kitty"}


def _terminal_name(env: dict[str, str]) -> str:
    if env.get("WT_SESSION"):
        return "Windows Terminal"
    for key in ("TERM_PROGRAM", "GHOSTTY_RESOURCES_DIR"):
        if env.get(key):
            return "ghostty" if key == "GHOSTTY_RESOURCES_DIR" else env[key]
    term = env.get("TERM", "")
    return term or "unknown"


def _truecolor_support(env: dict[str, str]) -> str:
    colorterm = env.get("COLORTERM", "").lower()
    if colorterm in _TRUECOLOR_TERMS or env.get("WT_SESSION"):
        return "yes"
    if env.get("TERM", "").endswith("256color"):
        return "256-color (no truecolor advertised)"
    return "unknown"


def _mouse_support(env: dict[str, str]) -> str:
    if env.get("SSH_CONNECTION"):
        return "likely (depends on the SSH client)"
    if env.get("WT_SESSION") or env.get("TERM_PROGRAM") or env.get("GHOSTTY_RESOURCES_DIR"):
        return "yes"
    return "unknown"


def _osc_progress_support(env: dict[str, str]) -> str:
    terminal = _terminal_name(env)
    return "yes" if terminal in _KNOWN_OSC94_TERMINALS else "no known support"


def _osc_notify_support(env: dict[str, str]) -> str:
    terminal = _terminal_name(env)
    return "yes" if terminal in _KNOWN_OSC_NOTIFY_TERMINALS else "no known support"


def _cjk_width_report() -> str:
    if unicodedata.east_asian_width("宽") != "W":
        return "unexpected: east_asian_width('宽') != W"
    return "double-width detected; alignment sample: 宽|en"


def _package_version(name: str) -> str:
    try:
        return package_version(name)
    except PackageNotFoundError:
        return "not installed"


def _session_storage_report() -> str:
    from baldric_coding.config.paths import BaldricPaths

    try:
        home = BaldricPaths().home
    except ValueError as exc:
        return f"unavailable: {exc}"
    if home.is_dir() and os.access(home, os.W_OK):
        return f"ok ({home})"
    return f"missing or not writable ({home})"


def build_doctor_report(env: dict[str, str] | None = None) -> Table:
    """Build the capability report table; ``env`` defaults to the process environment."""
    environment = os.environ if env is None else env
    table = Table(title="baldric --doctor", show_header=True, header_style="bold")
    table.add_column("check")
    table.add_column("result")
    table.add_row("baldric", current_version())
    table.add_row("python", sys.version.split()[0])
    table.add_row("platform", platform.platform())
    table.add_row("terminal", _terminal_name(environment))
    table.add_row("truecolor", _truecolor_support(environment))
    table.add_row("mouse", _mouse_support(environment))
    table.add_row("OSC 9;4 progress", _osc_progress_support(environment))
    table.add_row("OSC 9/99 notify", _osc_notify_support(environment))
    table.add_row("CJK width", _cjk_width_report())
    table.add_row("git", shutil.which("git") or "not found")
    table.add_row("textual", _package_version("textual"))
    table.add_row("rich", _package_version("rich"))
    table.add_row("session storage", _session_storage_report())
    return table


def render_doctor_report(console: Console | None = None) -> None:
    """Print the capability report to stdout."""
    (console or Console()).print(build_doctor_report())
