"""Shell resolution and process-tree termination for the bash tool."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import baldric_coding.tools.shell as shell_module
from baldric_coding.tools.shell import (
    POWERSHELL_ARGS,
    POWERSHELL_UTF8_PREFIX,
    ShellSpec,
    ShellUnavailable,
    kill_process_tree,
    resolve_shell,
)


def test_shell_spec_builds_a_bash_command_line() -> None:
    spec = ShellSpec("bash", "/bin/bash", ("-c",))

    assert spec.command_line("ls -la") == ("/bin/bash", "-c", "ls -la")
    assert spec.label == "bash"


def test_shell_spec_prefixes_powershell_with_a_utf8_setup() -> None:
    spec = ShellSpec("pwsh", "pwsh", POWERSHELL_ARGS)

    assert spec.command_line("Get-ChildItem") == (
        "pwsh",
        *POWERSHELL_ARGS,
        POWERSHELL_UTF8_PREFIX + "Get-ChildItem",
    )
    assert "PowerShell" in spec.label


def test_unknown_shell_preference_is_rejected() -> None:
    with pytest.raises(ShellUnavailable, match="Unknown shell preference"):
        resolve_shell("zsh")


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell resolution")
def test_posix_auto_resolves_a_real_shell() -> None:
    spec = resolve_shell()

    assert spec.name in {"bash", "sh"}
    assert spec.command_line("echo hi")[-1] == "echo hi"


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell resolution")
def test_posix_explicit_bash_uses_the_found_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell_module, "_find_posix_bash", lambda: "/usr/bin/bash")

    spec = resolve_shell("bash")

    assert spec.name == "bash"
    assert spec.executable == "/usr/bin/bash"


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell resolution")
def test_posix_missing_bash_reports_an_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell_module, "_find_posix_bash", lambda: None)

    with pytest.raises(ShellUnavailable, match="No bash executable"):
        resolve_shell("bash")


def test_windows_taskkill_targets_the_system_binary_and_the_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        assert kwargs["timeout"] == shell_module.TASKKILL_TIMEOUT_SECONDS
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(shell_module.subprocess, "run", fake_run)
    monkeypatch.setattr(shell_module, "_system_root", lambda: r"C:\Windows")

    kill_process_tree(4321, platform="nt")

    taskkill = os.path.join(r"C:\Windows", "System32", "taskkill.exe")
    assert calls == [[taskkill, "/F", "/T", "/PID", "4321"]]


def test_posix_kill_signals_the_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    killed: list[tuple[int, int]] = []

    class FakeOs:
        @staticmethod
        def killpg(pid: int, sig: int) -> None:
            killed.append((pid, sig))

    class FakeSignal:
        SIGKILL = 9

    monkeypatch.setattr(shell_module, "os", FakeOs)
    monkeypatch.setattr(shell_module, "signal", FakeSignal)

    kill_process_tree(4321, platform="posix")

    assert killed == [(4321, 9)]


@pytest.mark.skipif(os.name != "nt", reason="Windows shell integration")
@pytest.mark.anyio
async def test_windows_auto_shell_runs_a_command(tmp_path: Path) -> None:
    from baldric_coding.tools.bash import create_bash_tool

    spec = resolve_shell()
    command = "echo hello" if spec.name == "cmd" else 'Write-Output "hello"'
    tool = create_bash_tool(cwd=tmp_path)

    result = await tool.execute("call-1", {"command": command})

    assert result.details["shell"] == spec.name
    assert result.details["exit_code"] == 0
    assert "hello" in result.text


@pytest.mark.skipif(os.name != "nt", reason="Windows shell integration")
def test_windows_auto_prefers_powershell_or_cmd() -> None:
    spec = resolve_shell()

    assert spec.name in {"pwsh", "powershell", "cmd"}
