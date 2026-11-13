from pathlib import Path

import pytest

from baldric.runtime.config.paths import BaldricPaths
from baldric.runtime.config.shell_config import (
    ShellConfigError,
    ShellSettings,
    load_shell_settings,
    shell_settings_from_json,
    shell_settings_path,
)


def test_load_shell_settings_missing_file_uses_defaults(tmp_path: Path) -> None:
    paths = BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents")

    assert load_shell_settings(paths) == ShellSettings()


def test_load_shell_settings_accepts_pi_style_shell_command_prefix(tmp_path: Path) -> None:
    paths = BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents")
    path = shell_settings_path(paths)
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"shellCommandPrefix": "shopt -s expand_aliases\\nalias gs=\\"git status\\""}',
        encoding="utf-8",
    )

    settings = load_shell_settings(paths)

    assert settings.shell_command_prefix == 'shopt -s expand_aliases\nalias gs="git status"'
    assert settings.to_json() == {"shellCommandPrefix": 'shopt -s expand_aliases\nalias gs="git status"'}


def test_shell_settings_accepts_baldric_style_shell_command_prefix() -> None:
    settings = shell_settings_from_json({"shell_command_prefix": " alias ll='ls -la' "})

    assert settings.shell_command_prefix == "alias ll='ls -la'"


def test_shell_settings_ignore_unknown_fields() -> None:
    settings = shell_settings_from_json(
        {
            "shellCommandPrefix": "source ~/.baldric/aliases.bash",
            "future_shell_option": True,
        }
    )

    assert settings.shell_command_prefix == "source ~/.baldric/aliases.bash"


def test_shell_preference_defaults_to_auto_and_is_not_serialized() -> None:
    settings = shell_settings_from_json({})

    assert settings.shell == "auto"
    assert "shell" not in settings.to_json()


def test_shell_preference_round_trips() -> None:
    settings = shell_settings_from_json({"shell": "bash"})

    assert settings.shell == "bash"
    assert settings.to_json() == {"shell": "bash"}


def test_unknown_shell_preference_is_rejected() -> None:
    with pytest.raises(ShellConfigError, match="shell must be one of"):
        shell_settings_from_json({"shell": "zsh"})
