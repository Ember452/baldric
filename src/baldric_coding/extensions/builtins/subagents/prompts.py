"""Child system prompt assembly for subagents.

Two modes, selected by agent frontmatter `prompt_mode`:

- `replace` (default): the agent body becomes the child's base prompt
  (`custom_system_prompt`), with any preloaded skill sections appended.
- `append`: the parent session's full system prompt is kept verbatim as a
  byte-identical prefix, followed by the sub-agent bridge, an `<active_agent/>`
  tag, an environment block, the agent body wrapped in `<agent_instructions>`,
  and skill sections. The result is a full system prompt override.

The parent prompt is never edited, only prefixed to: appending to it would break
the shared prompt cache for the parent conversation.

Skill discovery follows the session's project-trust decision. A child that
inherits skills natively would otherwise read `<cwd>/.baldric/skills` from a
repository the user never approved, which is a second route to the same
project-authored-prompt problem the agent-type directory already gates.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from baldric_agent.messages import AgentMessage
from baldric_coding.paths import BaldricPaths
from baldric_coding.resources import BaldricResourcePaths
from baldric_coding.skills import format_skill_invocation, load_skills

if TYPE_CHECKING:
    from .agents import AgentDefinition

GIT_TIMEOUT_SECONDS = 5

SUB_AGENT_BRIDGE = """<sub_agent_context>
You are operating as a sub-agent invoked to handle a specific task.
- Use the read tool instead of cat/head/tail
- Use the edit tool instead of sed/awk
- Use the write tool instead of echo/heredoc
- Use the find tool instead of bash find/ls for file search
- Use the grep tool instead of bash grep/rg for content search
- Make independent tool calls in parallel
- Use absolute file paths
- Do not use emojis
- Be concise but complete
</sub_agent_context>"""


PARENT_CONTEXT_HEADER = """# Parent Conversation Context
The following is the conversation history from the parent session that spawned you.
Use this context to understand what has been discussed and decided so far.

"""

PARENT_CONTEXT_FOOTER = """

---
# Your Task (below)
"""


def build_parent_context(transcript: Sequence[AgentMessage]) -> str:
    """Text digest of the parent conversation.

    Keeps user and assistant text turns and drops tool results, which are too
    verbose to be useful as context. Baldric folds compaction and branch
    summaries into user messages during replay, so they appear as `[User]`
    turns. Returns "" when there is nothing to inherit.
    """
    parts: list[str] = []
    for message in transcript:
        if message.role not in ("user", "assistant"):
            continue
        text = message.text.strip()
        if text:
            label = "User" if message.role == "user" else "Assistant"
            parts.append(f"[{label}]: {text}")
    if not parts:
        return ""
    return PARENT_CONTEXT_HEADER + "\n\n".join(parts) + PARENT_CONTEXT_FOOTER


def inherited_resource_paths(
    paths: BaldricPaths,
    cwd: Path,
    *,
    project_trusted: bool,
) -> BaldricResourcePaths:
    """Resource paths for a child that inherits skills natively (`skills: true`)."""
    return BaldricResourcePaths(
        root=paths.home,
        cwd=cwd,
        agents_root=paths.agents_home,
        paths=paths,
        project_resources_enabled=project_trusted,
    )


def resolve_skill_blocks(
    names: Sequence[str] | None,
    paths: BaldricPaths,
    cwd: Path,
    *,
    project_trusted: bool,
) -> list[tuple[str, str]]:
    """Resolve named skills to (name, block) pairs; missing → placeholder."""
    if not names:
        return []
    try:
        available = {
            skill.name: skill
            for skill in load_skills(inherited_resource_paths(paths, cwd, project_trusted=project_trusted))
        }
    except Exception:  # noqa: BLE001 - unreadable skill dirs degrade to placeholders
        available = {}
    blocks: list[tuple[str, str]] = []
    for name in names:
        skill = available.get(name)
        if skill is None:
            blocks.append((name, f'(Skill "{name}" not found)'))
        else:
            blocks.append((name, format_skill_invocation(skill)))
    return blocks


def build_child_system_prompt(
    definition: AgentDefinition,
    *,
    parent_prompt: str | None,
    environment: str,
    skill_blocks: Sequence[tuple[str, str]],
    memory_block: str | None = None,
) -> str | None:
    """Assemble the child system prompt for one agent definition.

    Append mode (with a parent prompt available) returns a full system prompt
    override incorporating `environment` (from `detect_environment`). Otherwise
    returns a base prompt for `custom_system_prompt`, or None to keep the
    default coding prompt. Extras follow a fixed order: memory block first, then
    skill sections.
    """
    if definition.prompt_mode == "append" and parent_prompt:
        custom_section = ""
        if definition.system_prompt:
            custom_section = f"\n\n<agent_instructions>\n{definition.system_prompt}\n</agent_instructions>"
        extras: list[str] = []
        if memory_block:
            extras.append(memory_block)
        extras.extend(f"\n# Preloaded Skill: {name}\n{block}" for name, block in skill_blocks)
        extras_suffix = "\n\n" + "\n".join(extras) if extras else ""
        return (
            f"{parent_prompt}\n\n{SUB_AGENT_BRIDGE}\n\n"
            f'<active_agent name="{definition.name}"/>\n\n'
            f"{environment}{custom_section}{extras_suffix}"
        )
    parts: list[str] = []
    if definition.system_prompt:
        parts.append(definition.system_prompt)
    if memory_block:
        parts.append(memory_block)
    parts.extend(f"# Preloaded Skill: {name}\n{block}" for name, block in skill_blocks)
    return "\n\n".join(parts) if parts else None


async def detect_environment(cwd: Path) -> str:
    """Build the append-mode environment block for cwd without blocking the loop."""
    return await asyncio.to_thread(_detect_environment_blocking, cwd)


def _detect_environment_blocking(cwd: Path) -> str:
    return f"# Environment\nWorking directory: {cwd}\n{_git_status_line(cwd)}\nPlatform: {sys.platform}"


def _git_status_line(cwd: Path) -> str:
    """Describe cwd's git state, degrading to "not a repository" on any failure.

    Every path here - git missing, a cwd that no longer exists, a timeout, a
    detached HEAD with no branch name - means "no branch to report", not an
    error worth raising while assembling a prompt.
    """
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return "Not a git repository"
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return "Not a git repository"
    name = branch.stdout.strip() if branch.returncode == 0 else ""
    if name:
        return f"Git repository: yes\nBranch: {name}"
    return "Git repository: yes"
