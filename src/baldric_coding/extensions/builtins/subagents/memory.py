"""Per-agent persistent memory for subagents.

Agent types opt in with frontmatter `memory: user|project|local`, mapping to:

    user      ~/.baldric/agent-memory/<name>/
    project   <cwd>/.baldric/agent-memory/<name>/
    local     <cwd>/.baldric/agent-memory-local/<name>/

The agent maintains its memory with the ordinary read/write/edit tools; a prompt
block injected at spawn describes the directory and shows the first
`MAX_MEMORY_LINES` lines of MEMORY.md. Agents whose toolset cannot write get a
read-only variant and no directory is created for them.

The `project` and `local` scopes resolve inside the working directory, so they
are available only when that directory's project inputs were approved: an
untrusted repository must not be able to steer an agent through a planted memory
index. `user` scope never depends on trust.

Producing no block is always explained. A silently missing memory is indistinguishable
from an agent that chose not to write one, which makes the trust gate and the
name guard impossible to diagnose from the outside.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

from baldric_coding.paths import BaldricPaths

MEMORY_SCOPES = ("user", "project", "local")
MAX_MEMORY_LINES = 200
MEMORY_TRUNCATION_SUFFIX = "\n... (truncated at 200 lines)"

MEMORY_INSTRUCTIONS = (
    "## Memory instructions\n"
    "- MEMORY.md is your index. Keep it under 200 lines.\n"
    "- Store detailed memories in separate files in the memory directory and"
    " link them from MEMORY.md.\n"
    "- Start each memory file with frontmatter: name, description, and type"
    " (user|feedback|project|reference).\n"
    "- Update or remove outdated memories when you encounter them.\n"
    "- Maintain these files with the read/write/edit tools."
)

_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


@dataclass(frozen=True, slots=True)
class MemoryPreparation:
    """The prompt block for one spawn, or the reason there is none."""

    block: str | None = None
    reason: str | None = None


def is_valid_agent_name(name: str) -> bool:
    """Return True when name is safe to use as a memory directory component."""
    return len(name) <= 128 and _NAME_PATTERN.match(name) is not None


def _scope_root(scope: str, paths: BaldricPaths, cwd: Path, *, project_trusted: bool) -> Path | None:
    """Return the memory root for one scope, or None when it is not usable."""
    if scope not in MEMORY_SCOPES:
        return None
    if scope != "user" and not project_trusted:
        return None
    if scope == "user":
        return paths.user_agent_memory_dir
    if scope == "project":
        return paths.project_agent_memory_dir(cwd)
    return paths.project_local_agent_memory_dir(cwd)


def resolve_memory_dir(
    scope: str,
    agent_name: str,
    paths: BaldricPaths,
    cwd: Path,
    *,
    project_trusted: bool,
) -> Path | None:
    """Map a memory scope to its directory.

    `project_trusted` is a required argument rather than a defaulted one: a
    default of True would fail open for any caller that forgot to pass it, and
    this gate decides whether an untrusted repository can steer an agent.

    Returns None for an unknown scope, an unusable name, a project scope in an
    untrusted directory, or a path that is already a symlink.
    """
    base = _scope_root(scope, paths, cwd, project_trusted=project_trusted)
    if base is None or not is_valid_agent_name(agent_name):
        return None
    memory_dir = base / agent_name
    if memory_dir.is_symlink():
        return None
    return memory_dir


def read_memory_file(memory_dir: Path) -> str | None:
    """Read MEMORY.md capped at MAX_MEMORY_LINES; None when absent or unreadable."""
    try:
        text = (memory_dir / "MEMORY.md").read_text(encoding="utf-8")
    except (OSError, ValueError):
        # ValueError covers UnicodeDecodeError: a non-UTF-8 index is unreadable
        # in the same practical sense as a missing one.
        return None
    lines = text.splitlines()
    if len(lines) > MAX_MEMORY_LINES:
        return "\n".join(lines[:MAX_MEMORY_LINES]) + MEMORY_TRUNCATION_SUFFIX
    return text


def build_memory_block(memory_dir: Path, scope: str, existing: str | None) -> str:
    """Build the read-write memory prompt block.

    Paths are joined as Path objects rather than with a literal "/": this text
    goes to the model, and a mixed `C:\\base\\mem/scout/MEMORY.md` is both odd to
    read and easy for the agent to copy into a tool call that then fails.
    """
    header = (
        "# Agent Memory\n\n"
        f"You have a persistent memory directory at: {memory_dir}\n"
        f"Memory scope: {scope}\n\n"
        "This memory persists across sessions. Use it to build up knowledge"
        " over time."
    )
    if existing:
        current = f"\n\n## Current MEMORY.md\n{existing}"
    else:
        current = (
            f"\n\nNo MEMORY.md exists yet. Create one at {memory_dir / 'MEMORY.md'}"
            " to start building persistent memory."
        )
    return f"{header}{current}\n\n{MEMORY_INSTRUCTIONS}"


def build_read_only_memory_block(memory_dir: Path, scope: str, existing: str | None) -> str:
    """Build the read-only memory prompt block."""
    header = (
        "# Agent Memory (read-only)\n\n"
        f"Memory directory: {memory_dir}\n"
        f"Memory scope: {scope}\n\n"
        "You have read-only access to this memory; do not modify it."
    )
    if existing:
        return f"{header}\n\n## Current MEMORY.md\n{existing}"
    return f"{header}\n\nNo memory is available yet."


async def prepare_memory(
    agent_name: str,
    scope: str | None,
    paths: BaldricPaths,
    cwd: Path,
    *,
    read_write: bool,
    project_trusted: bool,
) -> MemoryPreparation:
    """Resolve, optionally create, and render the memory block for one spawn."""
    if scope is None:
        return MemoryPreparation()
    if scope not in MEMORY_SCOPES:
        return MemoryPreparation(reason=f"memory scope {scope!r} must be one of {', '.join(MEMORY_SCOPES)}")
    if not is_valid_agent_name(agent_name):
        return MemoryPreparation(reason=f"agent name {agent_name!r} cannot be used as a memory directory")
    if scope != "user" and not project_trusted:
        return MemoryPreparation(reason=f"memory scope {scope!r} needs the project directory to be trusted")
    return await asyncio.to_thread(
        _prepare_memory_blocking,
        agent_name,
        scope,
        paths,
        cwd,
        read_write,
        project_trusted,
    )


def _prepare_memory_blocking(
    agent_name: str,
    scope: str,
    paths: BaldricPaths,
    cwd: Path,
    read_write: bool,
    project_trusted: bool,
) -> MemoryPreparation:
    base = _scope_root(scope, paths, cwd, project_trusted=project_trusted)
    if base is None:
        # The public entry point explains scope, trust, and name first, so this
        # only runs for a direct caller.
        return MemoryPreparation(reason=f"memory scope {scope!r} is not usable here")
    if not is_valid_agent_name(agent_name):
        # Checked here as well as in the entry point: this is the function that
        # builds a path, so it must not depend on its caller to have validated.
        return MemoryPreparation(reason=f"agent name {agent_name!r} cannot be used as a memory directory")
    memory_dir = base / agent_name
    if memory_dir.is_symlink():
        return MemoryPreparation(reason=f"refusing to use {memory_dir} because it is a symlink")
    if read_write:
        try:
            memory_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return MemoryPreparation(reason=f"could not create {memory_dir}: {exc}")
        return MemoryPreparation(block=build_memory_block(memory_dir, scope, read_memory_file(memory_dir)))
    return MemoryPreparation(
        block=build_read_only_memory_block(memory_dir, scope, read_memory_file(memory_dir))
    )
