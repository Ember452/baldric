from pathlib import Path

import pytest

from baldric.runtime.config.paths import BaldricPaths


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


def test_subagent_type_directories_are_baldric_native(tmp_path: Path) -> None:
    """Subagent types live beside skills/prompts, not in the `.agents` ecosystem dir."""
    paths = BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents")
    cwd = tmp_path / "project"

    assert paths.user_subagent_types_dir == tmp_path / ".baldric" / "agents"
    assert paths.project_subagent_types_dir(cwd) == cwd / ".baldric" / "agents"
    assert paths.project_subagent_types_dir(cwd) != paths.project_agents_dir(cwd) / "agents"


def test_subagent_settings_files_live_next_to_the_other_settings_files(
    tmp_path: Path,
) -> None:
    paths = BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents")
    cwd = tmp_path / "project"

    assert paths.user_subagent_settings_path == tmp_path / ".baldric" / "subagents.json"
    assert paths.project_subagent_settings_path(cwd) == cwd / ".baldric" / "subagents.json"


def test_subagent_transcripts_are_kept_outside_the_session_directory(
    tmp_path: Path,
) -> None:
    """Durable child transcripts are separate from resumable parent sessions."""
    paths = BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents")

    assert paths.subagent_transcripts_dir == tmp_path / ".baldric" / "subagents"
    assert paths.subagent_transcripts_dir != paths.sessions_dir


def test_agent_memory_scopes_are_three_distinct_roots(tmp_path: Path) -> None:
    """`user`, `project` and `local` memory must never resolve to the same dir."""
    paths = BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents")
    cwd = tmp_path / "project"

    user = paths.user_agent_memory_dir
    project = paths.project_agent_memory_dir(cwd)
    local = paths.project_local_agent_memory_dir(cwd)

    assert user == tmp_path / ".baldric" / "agent-memory"
    assert project == cwd / ".baldric" / "agent-memory"
    assert local == cwd / ".baldric" / "agent-memory-local"
    assert len({user, project, local}) == 3


def test_schedules_are_stored_under_the_home_not_in_the_project(tmp_path: Path) -> None:
    """A scheduled job is a stored prompt: it must not land in a repository."""
    paths = BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents")
    cwd = tmp_path / "repos" / "app"
    cwd.mkdir(parents=True)

    schedules = paths.project_schedules_dir(cwd)

    assert schedules.parent == tmp_path / ".baldric" / "schedules"
    assert schedules.name == paths.project_session_dir(cwd).name
    assert not str(schedules).startswith(str(cwd))
    # Two projects with the same directory name still get separate stores.
    other = tmp_path / "other" / "app"
    other.mkdir(parents=True)
    assert paths.project_schedules_dir(other) != schedules


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
