"""Guard: the TUI must forward the configured shell preference to the session.

Regression guard for #53. The ``shell`` preference (auto/bash/pwsh/cmd) is
loaded from ``~/.baldric/settings.json`` into ``ShellSettings`` and must reach
``CodingSessionConfig``. Print and RPC modes pass ``shell=shell_settings.shell``;
the TUI builds its own ``CodingSessionConfig`` in ``run_tui_app`` and previously
omitted ``shell``, so a user's explicit ``shell`` was silently ignored in the
interactive app while honoured in every other mode.

A pure unit test cannot observe this because the omission is in one call site of
a 5,800-line module. Assert it at the source, mirroring the other guard tests,
so the omission cannot reappear unnoticed.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PY = REPO_ROOT / "src" / "baldric_coding" / "tui" / "app.py"


def _tui_session_config_block() -> str:
    source = APP_PY.read_text(encoding="utf-8")
    anchor = source.index("shell_command_prefix=shell_settings.shell_command_prefix")
    # The whole CodingSessionConfig(...) call sits within a few dozen lines of
    # the shell_command_prefix argument; bound the window to avoid matching a
    # different call site far away.
    return source[max(0, anchor - 1200) : anchor + 1200]


def test_tui_forwards_shell_preference_to_session_config() -> None:
    block = _tui_session_config_block()
    assert "shell_command_prefix=shell_settings.shell_command_prefix" in block
    assert re.search(r"shell=shell_settings\.shell\b", block), (
        "run_tui_app must pass shell=shell_settings.shell to CodingSessionConfig; "
        "otherwise the configured shell preference is ignored in the TUI."
    )


def test_all_session_config_builders_forward_shell() -> None:
    """Every place that forwards shell_command_prefix must also forward shell."""
    source = APP_PY.read_text(encoding="utf-8")
    prefix_sites = source.count("shell_command_prefix=shell_settings.shell_command_prefix")
    shell_sites = len(re.findall(r"shell=shell_settings\.shell\b", source))
    assert prefix_sites == shell_sites >= 1, (
        f"found {prefix_sites} shell_command_prefix forwards but {shell_sites} shell "
        "forwards; they must be passed together"
    )
