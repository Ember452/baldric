"""Agent-type parsing branches the end-to-end suite leaves out.

The frontmatter cases that suite asserts are `memory` and `isolation`. What is
covered only here is the rest of the file format: the four `skills` states, tool
wildcards, precedence between the two directories, the reserved ``fork`` name, an
unreadable file, quoting and CRLF input, and the project-trust gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baldric_coding.config.paths import BaldricPaths
from baldric_coding.extensions.builtins.subagents.agents import (
    DEFAULT_AGENT_TYPES,
    format_agent_type_list,
    load_agent_definitions,
)


@pytest.fixture
def paths(tmp_path: Path) -> BaldricPaths:
    return BaldricPaths(home=tmp_path / "home" / ".baldric", agents_home=tmp_path / "agents")


@pytest.fixture
def cwd(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    return project


def _write(directory: Path, name: str, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.md"
    path.write_bytes(text.encode("utf-8"))
    return path


def test_the_three_built_in_types_need_no_files(paths: BaldricPaths, cwd: Path) -> None:
    definitions = load_agent_definitions(paths, cwd, project_trusted=True)

    assert sorted(definitions) == ["explore", "fork", "general"]
    assert [definition.name for definition in DEFAULT_AGENT_TYPES] == ["general", "fork", "explore"]
    assert definitions["fork"].fork is True
    assert definitions["explore"].tools == ("read", "bash")
    assert format_agent_type_list(definitions).startswith("- explore: ")


def test_user_file_loads_and_project_file_wins_the_same_name(paths: BaldricPaths, cwd: Path) -> None:
    user = _write(paths.user_subagent_types_dir, "scribe", "---\ndescription: user\n---\nu body\n")
    _write(paths.project_subagent_types_dir(cwd), "scribe", "---\ndescription: project\n---\np\n")

    definitions = load_agent_definitions(paths, cwd, project_trusted=True)

    assert definitions["scribe"].description == "project"
    assert definitions["scribe"].system_prompt == "p"
    # A body with no frontmatter still loads, with a path-derived description.
    _write(paths.user_subagent_types_dir, "bare", "just a body\n")
    assert load_agent_definitions(paths, cwd, project_trusted=True)["bare"].description == (
        f"Custom agent type from {paths.user_subagent_types_dir / 'bare.md'}"
    )
    assert str(user).endswith("scribe.md")


def test_an_untrusted_project_directory_is_not_read(paths: BaldricPaths, cwd: Path) -> None:
    _write(paths.user_subagent_types_dir, "useronly", "u\n")
    _write(paths.project_subagent_types_dir(cwd), "sneaky", "---\ntools: bash\n---\nBody.")

    untrusted = load_agent_definitions(paths, cwd, project_trusted=False)

    assert "useronly" in untrusted
    assert "sneaky" not in untrusted


def test_the_reserved_fork_name_cannot_be_replaced(paths: BaldricPaths, cwd: Path) -> None:
    _write(paths.user_subagent_types_dir, "fork", "---\ntools: bash\n---\nnot a fork\n")
    _write(paths.project_subagent_types_dir(cwd), "fork", "---\ntools: bash\n---\nnot a fork\n")

    definition = load_agent_definitions(paths, cwd, project_trusted=True)["fork"]

    assert definition.fork is True
    assert definition.tools is None


def test_an_unreadable_file_is_skipped_without_losing_the_rest(paths: BaldricPaths, cwd: Path) -> None:
    directory = paths.user_subagent_types_dir
    _write(directory, "good", "body\n")
    _write_raw(directory, "binary", b"\xff\xfe not utf-8")

    definitions = load_agent_definitions(paths, cwd, project_trusted=True)

    assert "good" in definitions
    assert "binary" not in definitions


def _write_raw(directory: Path, name: str, payload: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.md"
    path.write_bytes(payload)
    return path


def test_every_frontmatter_key_parses(paths: BaldricPaths, cwd: Path) -> None:
    _write(
        paths.user_subagent_types_dir,
        "kitchen",
        "---\n"
        "description: All the keys\n"
        "tools: read, write, bash\n"
        "model: some-model\n"
        "thinking: high\n"
        "max_turns: 12\n"
        "skills: review, testing\n"
        "prompt_mode: append\n"
        "memory: project\n"
        "isolation: worktree\n"
        "inherit_context: true\n"
        "---\n"
        "system prompt body\n",
    )

    definition = load_agent_definitions(paths, cwd, project_trusted=True)["kitchen"]

    assert definition.description == "All the keys"
    assert definition.tools == ("read", "write", "bash")
    assert definition.model == "some-model"
    assert definition.thinking == "high"
    assert definition.max_turns == 12
    assert definition.skills == ("review", "testing")
    assert definition.prompt_mode == "append"
    assert definition.memory == "project"
    assert definition.isolation == "worktree"
    assert definition.inherit_context is True
    assert definition.system_prompt == "system prompt body"


@pytest.mark.parametrize(
    ("key", "value", "attribute"),
    [
        ("thinking", "highish", "thinking"),
        ("memory", "galactic", "memory"),
        ("isolation", "docker", "isolation"),
        ("prompt_mode", "merge", "prompt_mode"),
        ("max_turns", "five", "max_turns"),
        ("max_turns", "-3", "max_turns"),
        ("inherit_context", "maybe", "inherit_context"),
    ],
)
def test_unrecognised_values_fall_back(
    paths: BaldricPaths, cwd: Path, key: str, value: str, attribute: str
) -> None:
    _write(paths.user_subagent_types_dir, "broken", f"---\n{key}: {value}\n---\nbody\n")

    definition = load_agent_definitions(paths, cwd, project_trusted=True)["broken"]

    expected = "replace" if attribute == "prompt_mode" else None
    assert getattr(definition, attribute) is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('---\nskills: "a, b"\n---\n', ("a", "b")),
        ("---\nskills: a,b,\n---\n", ("a", "b")),
        ("---\nskills: none\n---\n", False),
        ("---\nskills: false\n---\n", False),
        ("---\nskills: true\n---\n", True),
        ("---\nskills: *\n---\n", True),
        ("---\nskills: all\n---\n", True),
        ("---\nskills:\n---\n", None),
        ("---\n---\n", None),
    ],
)
def test_skills_frontmatter_has_four_distinct_states(
    paths: BaldricPaths, cwd: Path, raw: str, expected: tuple[str, ...] | bool | None
) -> None:
    _write(paths.user_subagent_types_dir, "skillful", raw)

    assert load_agent_definitions(paths, cwd, project_trusted=True)["skillful"].skills == expected


@pytest.mark.parametrize("raw", ["---\ntools:\n---\n", "---\ntools: *\n---\n", "---\ntools: all\n---\n"])
def test_tools_omitted_or_wildcard_means_the_full_toolset(paths: BaldricPaths, cwd: Path, raw: str) -> None:
    _write(paths.user_subagent_types_dir, "wide", raw)

    assert load_agent_definitions(paths, cwd, project_trusted=True)["wide"].tools is None


def test_quoting_blank_bodies_and_crlf_are_handled(paths: BaldricPaths, cwd: Path) -> None:
    _write(
        paths.user_subagent_types_dir,
        "quoted",
        '---\ndescription: "quoted text"\nmodel: ""\n# comment\n---\n   \n',
    )
    _write(
        paths.user_subagent_types_dir,
        "crlf",
        "---\r\ndescription: windows\r\nthinking: low\r\n---\r\nbody\r\n",
    )
    _write(
        paths.user_subagent_types_dir,
        "colon",
        "---\ndescription: use git: always stage first\n---\nb\n",
    )

    definitions = load_agent_definitions(paths, cwd, project_trusted=True)

    assert definitions["quoted"].description == "quoted text"
    assert definitions["quoted"].model is None
    assert definitions["quoted"].system_prompt is None
    assert definitions["crlf"].description == "windows"
    assert definitions["crlf"].thinking == "low"
    assert definitions["crlf"].system_prompt == "body"
    assert definitions["colon"].description == "use git: always stage first"
