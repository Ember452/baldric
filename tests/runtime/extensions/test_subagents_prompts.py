"""Tests for child prompt assembly, skill preloading, and the trust gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from baldric.protocol.messages import (
    AssistantMessage,
    CustomMessage,
    TextContent,
    ToolResultMessage,
    UserMessage,
)
from baldric.runtime.config.paths import BaldricPaths
from baldric.runtime.extensions.builtins.subagents import prompts as prompts_module
from baldric.runtime.extensions.builtins.subagents.agents import AgentDefinition
from baldric.runtime.extensions.builtins.subagents.prompts import (
    PARENT_CONTEXT_FOOTER,
    PARENT_CONTEXT_HEADER,
    SUB_AGENT_BRIDGE,
    build_child_system_prompt,
    build_parent_context,
    detect_environment,
    inherited_resource_paths,
    resolve_skill_blocks,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def paths(tmp_path: Path) -> BaldricPaths:
    return BaldricPaths(home=tmp_path / "home" / ".baldric", agents_home=tmp_path / "agents")


@pytest.fixture
def cwd(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    return project


def _skill(directory: Path, name: str, body: str) -> None:
    target = directory / name
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(f"---\ndescription: the {name} skill\n---\n{body}\n", encoding="utf-8")


def test_empty_or_absent_names_preload_nothing(paths: BaldricPaths, cwd: Path) -> None:
    assert resolve_skill_blocks(None, paths, cwd, project_trusted=True) == []
    assert resolve_skill_blocks((), paths, cwd, project_trusted=True) == []


def test_project_skills_are_invisible_until_the_project_is_trusted(paths: BaldricPaths, cwd: Path) -> None:
    _skill(paths.project_skills_dir(cwd), "review", "Review the diff.")

    untrusted = resolve_skill_blocks(("review",), paths, cwd, project_trusted=False)
    trusted = resolve_skill_blocks(("review",), paths, cwd, project_trusted=True)

    assert untrusted == [("review", '(Skill "review" not found)')]
    assert "Review the diff." in trusted[0][1]


def test_inherited_resource_paths_follow_home_agents_root_and_trust(
    tmp_path: Path, paths: BaldricPaths, cwd: Path
) -> None:
    resource_paths = inherited_resource_paths(paths, cwd, project_trusted=False)

    assert resource_paths.root == paths.home
    assert resource_paths.agents_root == paths.agents_home
    assert resource_paths.cwd == cwd
    assert resource_paths.project_resources_enabled is False
    assert paths.user_skills_dir in resource_paths.skills_dirs
    assert paths.project_skills_dir(cwd) not in resource_paths.skills_dirs

    trusted = inherited_resource_paths(paths, cwd, project_trusted=True)
    assert paths.project_skills_dir(cwd) in trusted.skills_dirs


def test_build_parent_context_keeps_text_turns_and_drops_tool_noise() -> None:
    transcript = [
        UserMessage(content="start the migration"),
        AssistantMessage(content=[TextContent(text="planning")]),
        ToolResultMessage(tool_call_id="c1", tool_name="bash", content="1200 lines of output"),
        CustomMessage(custom_type="note", content="injected"),
        UserMessage(content="   "),
        AssistantMessage(content="done"),
    ]

    text = build_parent_context(transcript)

    assert text.startswith(PARENT_CONTEXT_HEADER)
    assert text.endswith(PARENT_CONTEXT_FOOTER)
    assert "[User]: start the migration" in text
    assert "[Assistant]: planning" in text
    assert "[Assistant]: done" in text
    assert "1200 lines of output" not in text
    assert "injected" not in text
    assert text.count("[User]") == 1, "a blank turn is not context"


def test_build_parent_context_is_empty_when_there_is_nothing_to_inherit() -> None:
    assert build_parent_context([]) == ""
    assert build_parent_context([ToolResultMessage(tool_call_id="c", tool_name="t")]) == ""


def _definition(**overrides: object) -> AgentDefinition:
    base: dict[str, object] = {
        "name": "reviewer",
        "description": "reviews",
        "system_prompt": "Review carefully.",
    }
    base.update(overrides)
    return AgentDefinition(**base)  # type: ignore[arg-type]


def test_replace_mode_concatenates_memory_then_skills() -> None:
    prompt = build_child_system_prompt(
        _definition(),
        parent_prompt="PARENT",
        environment="# Environment\n",
        skill_blocks=[("testing", "SKILLBODY")],
        memory_block="MEMORYBLOCK",
    )

    assert prompt is not None
    assert "PARENT" not in prompt
    assert SUB_AGENT_BRIDGE not in prompt
    assert prompt == "Review carefully.\n\nMEMORYBLOCK\n\n# Preloaded Skill: testing\nSKILLBODY"


def test_replace_mode_without_anything_returns_none() -> None:
    definition = AgentDefinition(name="plain", description="no prompt")

    assert build_child_system_prompt(definition, parent_prompt=None, environment="", skill_blocks=[]) is None


def test_append_mode_keeps_the_parent_prompt_verbatim_as_a_prefix() -> None:
    parent = "You are Baldric.\nTool guidelines."

    prompt = build_child_system_prompt(
        _definition(prompt_mode="append"),
        parent_prompt=parent,
        environment="# Environment\nWorking directory: /tmp",
        skill_blocks=[("testing", "SKILLBODY")],
        memory_block="MEMORYBLOCK",
    )

    assert prompt is not None
    assert prompt.startswith(parent)
    assert prompt.index(parent) == 0, "no byte inserted before the parent prompt"
    assert SUB_AGENT_BRIDGE in prompt
    assert '<active_agent name="reviewer"/>' in prompt
    assert "<agent_instructions>\nReview carefully.\n</agent_instructions>" in prompt
    assert prompt.index("MEMORYBLOCK") < prompt.index("# Preloaded Skill: testing")
    assert "# Environment" in prompt


def test_append_mode_without_a_parent_prompt_falls_back_to_replace_behaviour() -> None:
    prompt = build_child_system_prompt(
        _definition(prompt_mode="append"),
        parent_prompt=None,
        environment="# Environment\n",
        skill_blocks=[],
    )

    assert prompt == "Review carefully."


def _patch_git(monkeypatch: pytest.MonkeyPatch, results: list[object]) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs: object) -> object:
        calls.append(args)
        outcome = results[len(calls) - 1] if len(calls) <= len(results) else results[-1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(
        prompts_module,
        "subprocess",
        SimpleNamespace(
            run=fake_run,
            SubprocessError=subprocess.SubprocessError,
            CompletedProcess=subprocess.CompletedProcess,
        ),
    )
    return calls


def _completed(*, returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["git"], returncode, stdout=stdout, stderr="")


async def test_environment_block_reports_branch_and_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_git(
        monkeypatch,
        [_completed(stdout="true\n"), _completed(stdout="feature/x\n")],
    )

    text = await detect_environment(tmp_path)

    assert f"Working directory: {tmp_path}" in text
    assert "Git repository: yes\nBranch: feature/x" in text
    assert f"Platform: {sys.platform}" in text
    assert [call[1:3] for call in calls] == [
        ["rev-parse", "--is-inside-work-tree"],
        ["branch", "--show-current"],
    ]


async def test_environment_block_reports_a_detached_head_without_a_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_git(monkeypatch, [_completed(stdout="true\n"), _completed(stdout="\n")])

    text = await detect_environment(tmp_path)

    assert "Git repository: yes" in text
    assert "Branch:" not in text


async def test_environment_block_degrades_when_git_is_unusable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases: list[list[object]] = [
        [_completed(returncode=128, stdout="")],
        [_completed(stdout="false\n")],
        [OSError("git not installed")],
        [subprocess.TimeoutExpired(["git"], 5)],
    ]
    for outcome in cases:
        _patch_git(monkeypatch, outcome)
        text = await detect_environment(tmp_path)
        assert "Not a git repository" in text, outcome
        assert "Branch:" not in text
