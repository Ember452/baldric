"""Durable shell execution settings for Baldric terminal commands."""

from __future__ import annotations

from dataclasses import dataclass
from json import JSONDecodeError, loads
from pathlib import Path
from typing import Any, Literal

from baldric.runtime.config.paths import BaldricPaths

# The default project-trust decision is a *durable settings value* (it is stored
# in shell settings and read by the trust coordinator), so the config layer owns
# the shape and the trust layer re-exports it. This keeps the config -> trust
# import edge nonexistent (the layer matrix forbids it; enforced by
# ``scripts/check_import_graph.py``).
TrustDefault = Literal["ask", "always", "never"]


class ShellConfigError(ValueError):
    """Raised when Baldric shell settings are invalid."""


SHELL_PREFERENCES = ("auto", "bash", "pwsh", "cmd")


@dataclass(frozen=True, slots=True)
class ShellSettings:
    """Shell execution settings loaded from Baldric home."""

    shell_command_prefix: str | None = None
    shell: str = "auto"
    default_project_trust: TrustDefault = "ask"

    def to_json(self) -> dict[str, str]:
        """Serialize these settings to JSON-compatible data."""
        result: dict[str, str] = {}
        if self.default_project_trust != "ask":
            result["defaultProjectTrust"] = self.default_project_trust
        if self.shell_command_prefix is not None:
            result["shellCommandPrefix"] = self.shell_command_prefix
        if self.shell != "auto":
            result["shell"] = self.shell
        return result


def shell_settings_path(paths: BaldricPaths | None = None) -> Path:
    """Return the durable shell settings path."""
    return (paths or BaldricPaths()).home / "settings.json"


def load_shell_settings(paths: BaldricPaths | None = None) -> ShellSettings:
    """Load durable shell settings, falling back to built-in defaults."""
    path = shell_settings_path(paths)
    if not path.exists():
        return ShellSettings()
    try:
        raw = loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise ShellConfigError(f"Shell settings are not valid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ShellConfigError("Shell settings must be a JSON object")
    return shell_settings_from_json(raw)


def shell_settings_from_json(data: dict[str, Any]) -> ShellSettings:
    """Parse shell settings from JSON-compatible data."""
    # Read only settings this version understands so fields written by a newer
    # Baldric installation cannot prevent an older installation from starting.
    if "shellCommandPrefix" in data and "shell_command_prefix" in data:
        raise ShellConfigError("Use only one of shellCommandPrefix or shell_command_prefix")

    raw_default = data.get("defaultProjectTrust", "ask")
    if raw_default not in {"ask", "always", "never"}:
        raise ShellConfigError("defaultProjectTrust must be ask, always, or never")

    raw_shell = data.get("shell", "auto")
    if raw_shell not in SHELL_PREFERENCES:
        raise ShellConfigError("shell must be one of " + ", ".join(SHELL_PREFERENCES))

    raw_prefix = data.get("shellCommandPrefix", data.get("shell_command_prefix"))
    if raw_prefix is None:
        return ShellSettings(shell=str(raw_shell), default_project_trust=raw_default)
    if not isinstance(raw_prefix, str):
        raise ShellConfigError("shellCommandPrefix must be a string")
    prefix = raw_prefix.strip()
    return ShellSettings(
        shell_command_prefix=prefix or None,
        shell=str(raw_shell),
        default_project_trust=raw_default,
    )
