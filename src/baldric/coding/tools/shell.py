"""Platform shell resolution and process-tree termination for the bash tool."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

# Mirrors Pi's PowerShell invocation: no profile, no interactive prompts, and a
# UTF-8 output encoding so non-ASCII command output is not mangled by the
# Windows console code page.
POWERSHELL_ARGS = ("-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command")
POWERSHELL_UTF8_PREFIX = "try { [Console]::OutputEncoding=[System.Text.Encoding]::UTF8 } catch {}\n"
TASKKILL_TIMEOUT_SECONDS = 5


class ShellUnavailable(RuntimeError):
    """Raised when the requested shell cannot be found on this host."""


@dataclass(frozen=True, slots=True)
class ShellSpec:
    """One resolved shell: what to run and how to hand it a command."""

    name: str
    executable: str
    args_prefix: tuple[str, ...]

    def command_line(self, command: str) -> tuple[str, ...]:
        """Return the argv that runs ``command`` in this shell."""
        if self.name in {"pwsh", "powershell"}:
            return (self.executable, *self.args_prefix, POWERSHELL_UTF8_PREFIX + command)
        return (self.executable, *self.args_prefix, command)

    @property
    def label(self) -> str:
        """Human-readable shell name used in tool descriptions."""
        return {
            "pwsh": "PowerShell (pwsh)",
            "powershell": "Windows PowerShell",
            "cmd": "cmd.exe",
        }.get(self.name, self.name)


def resolve_shell(preference: str | None = None) -> ShellSpec:
    """Resolve the shell to use, preferring one that accepts the tool's syntax.

    ``auto`` picks PowerShell on Windows (pwsh, then Windows PowerShell, then
    cmd.exe) and bash/sh on POSIX. Unlike Pi, Baldric keeps one shell tool, so
    the tool adapts instead of splitting into a separate ``powershell`` tool.
    """
    normalized = (preference or "auto").strip().lower()
    if normalized not in {"auto", "bash", "pwsh", "cmd"}:
        raise ShellUnavailable(f"Unknown shell preference: {preference}")
    if os.name == "nt":
        return _resolve_windows(normalized)
    return _resolve_posix(normalized)


def kill_process_tree(pid: int, *, platform: str | None = None) -> None:
    """Terminate a process and its descendants.

    Windows uses the trusted ``System32\\taskkill.exe`` so cleanup does not
    depend on ``PATH``; POSIX signals the whole process group started for the
    command.
    """
    target = platform or os.name
    if target == "nt":
        taskkill = os.path.join(_system_root(), "System32", "taskkill.exe")
        try:
            subprocess.run(
                [taskkill, "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=TASKKILL_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return
        return
    try:
        # The Windows stubs omit killpg/SIGKILL (see issue #513); this branch
        # only runs on POSIX.
        cast(Any, os).killpg(pid, cast(Any, signal).SIGKILL)
    except (ProcessLookupError, PermissionError):
        return


def _resolve_posix(preference: str) -> ShellSpec:
    if preference == "pwsh":
        pwsh = shutil.which("pwsh")
        if pwsh is None:
            raise ShellUnavailable(
                "No PowerShell executable found; install PowerShell 7 or use the default shell."
            )
        return ShellSpec("pwsh", pwsh, POWERSHELL_ARGS)
    if preference in {"auto", "bash"}:
        bash = _find_posix_bash()
        if bash is not None:
            return ShellSpec("bash", bash, ("-c",))
        if preference == "bash":
            raise ShellUnavailable("No bash executable found; install bash or use the default shell.")
    return ShellSpec("sh", "sh", ("-c",))


def _resolve_windows(preference: str) -> ShellSpec:
    if preference in {"auto", "pwsh"}:
        powershell = _find_windows_powershell()
        if powershell is not None:
            name = "pwsh" if Path(powershell).name.lower() == "pwsh.exe" else "powershell"
            return ShellSpec(name, powershell, POWERSHELL_ARGS)
        if preference == "pwsh":
            raise ShellUnavailable(
                "No PowerShell executable found; install PowerShell or add powershell.exe to PATH."
            )
    if preference == "bash":
        bash = _find_windows_bash()
        if bash is None:
            raise ShellUnavailable(
                "No bash found. Install Git for Windows (https://git-scm.com/download/win), "
                "add bash.exe to PATH, or use the default PowerShell shell."
            )
        return ShellSpec("bash", bash, ("-c",))
    return ShellSpec("cmd", os.path.join(_system_root(), "System32", "cmd.exe"), ("/d", "/s", "/c"))


def _find_posix_bash() -> str | None:
    if Path("/bin/bash").is_file():
        return "/bin/bash"
    return shutil.which("bash")


def _find_windows_bash() -> str | None:
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        root = os.environ.get(variable)
        if not root:
            continue
        candidate = Path(root) / "Git" / "bin" / "bash.exe"
        if candidate.is_file():
            return str(candidate)
    return shutil.which("bash.exe")


def _find_windows_powershell() -> str | None:
    pwsh = shutil.which("pwsh.exe") or shutil.which("pwsh")
    if pwsh is not None:
        return pwsh
    program_files = os.environ.get("PROGRAMFILES")
    if program_files:
        candidate = Path(program_files) / "PowerShell" / "7" / "pwsh.exe"
        if candidate.is_file():
            return str(candidate)
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is not None:
        return powershell
    candidate = Path(_system_root()) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if candidate.is_file():
        return str(candidate)
    return None


def _system_root() -> str:
    return os.environ.get("SYSTEMROOT") or r"C:\Windows"
