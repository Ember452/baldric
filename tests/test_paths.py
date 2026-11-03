from pathlib import Path

import pytest

from baldric_coding.paths import BaldricPaths


def test_baldric_paths_user_locations(tmp_path: Path) -> None:
    paths = BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents")

    assert paths.sessions_dir == tmp_path / ".baldric" / "sessions"
    assert paths.user_skills_dir == tmp_path / ".baldric" / "skills"
    assert paths.user_prompts_dir == tmp_path / ".baldric" / "prompts"
    assert paths.user_agents_skills_dir == tmp_path / ".agents" / "skills"
    assert paths.user_agents_prompts_dir == tmp_path / ".agents" / "prompts"


def test_baldric_paths_project_locations(tmp_path: Path) -> None:
    paths = BaldricPaths(home=tmp_path / "home", agents_home=tmp_path / "agents")
    cwd = tmp_path / "project"

    assert paths.project_baldric_dir(cwd) == cwd / ".baldric"
    assert paths.project_agents_dir(cwd) == cwd / ".agents"
    assert paths.project_skills_dir(cwd) == cwd / ".baldric" / "skills"
    assert paths.project_prompts_dir(cwd) == cwd / ".baldric" / "prompts"
    assert paths.project_agents_skills_dir(cwd) == cwd / ".agents" / "skills"
    assert paths.project_agents_prompts_dir(cwd) == cwd / ".agents" / "prompts"


def test_default_session_path_uses_home_sessions_and_readable_project_path(
    tmp_path: Path,
) -> None:
    paths = BaldricPaths(home=tmp_path / "home", agents_home=tmp_path / "agents")
    cwd = tmp_path / "repos" / "exploration" / "baldric"
    cwd.mkdir(parents=True)

    session_path = paths.default_session_path(cwd)

    assert session_path.name == "default.jsonl"
    assert session_path.parent.parent == tmp_path / "home" / "sessions"
    assert "repos-exploration-baldric-" in session_path.parent.name
    assert len(session_path.parent.name.rsplit("-", maxsplit=1)[-1]) == 6
    assert session_path.parent.exists()


def test_baldric_home_defaults_to_dot_baldric(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BALDRIC_HOME", raising=False)

    assert BaldricPaths().home == Path.home() / ".baldric"


def test_empty_baldric_home_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BALDRIC_HOME", "")

    assert BaldricPaths().home == Path.home() / ".baldric"


def test_baldric_home_environment_override_is_read_for_each_instance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_home = tmp_path / "baldric-first"
    second_home = tmp_path / "baldric-second"

    monkeypatch.setenv("BALDRIC_HOME", str(first_home))
    first = BaldricPaths()
    monkeypatch.setenv("BALDRIC_HOME", str(second_home))
    second = BaldricPaths()

    assert first.home == first_home
    assert first.sessions_dir == first_home / "sessions"
    assert first.user_extensions_dir == first_home / "extensions"
    assert second.home == second_home
    assert second.models_store_path == second_home / "models-store.json"
    assert second.llama_cpp_state_path == second_home / "state" / "extensions" / "llama.cpp.json"
    assert first.agents_home == second.agents_home == Path.home() / ".agents"


def test_baldric_home_expands_current_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BALDRIC_HOME", "~/.baldric-personal")

    assert BaldricPaths().home == Path.home() / ".baldric-personal"


def test_baldric_home_must_be_absolute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BALDRIC_HOME", ".baldric-personal")

    with pytest.raises(ValueError, match="BALDRIC_HOME must be an absolute path"):
        BaldricPaths()


def test_explicit_baldric_home_ignores_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    explicit_home = tmp_path / "explicit"
    monkeypatch.setenv("BALDRIC_HOME", str(tmp_path / "environment"))

    assert BaldricPaths(home=explicit_home).home == explicit_home
