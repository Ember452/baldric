"""Agent type definitions for the subagents capability.

Agent types are markdown files with frontmatter:

    ~/.baldric/agents/<name>.md      user agent types
    <cwd>/.baldric/agents/<name>.md  project agent types (win on conflicts)

The filename is the type name, the body is the subagent's system prompt, and
frontmatter supports `description`, `tools` (comma-separated allow-list of
built-in tool names, or `*`), `model`, `thinking` (a Baldric thinking level),
`max_turns`, `skills`, `prompt_mode` (`replace` or `append`), `memory` (one of
the scopes in `memory.MEMORY_SCOPES`), and `isolation` (`worktree`).

Children discover skills natively through Baldric's own machinery by default.
`skills: <csv>` additionally preloads the named skills' bodies into the system
prompt; `skills: true`/`*`/`all` pins resource discovery (skills and project
context files) to the parent cwd, which only matters under worktree isolation;
`skills: none`/`false` disables skill discovery entirely.

Two deliberate differences from the capability this was ported from:

* The project directory is skipped unless its inputs were trusted. An agent
  file's body is the child's system prompt and `tools:` is its allow-list, so an
  untrusted repository would otherwise be able to author both. The session
  already reports the trust decision itself as a resource diagnostic, so the only
  note added here is the concrete consequence: a project agents directory that
  exists but was not read.
* Every rejected or dropped value produces a note. A file the user wrote that
  behaves differently from what it says - `max_turns: five` silently becoming
  "unlimited", `thinking: highish` becoming "inherit the parent" - is otherwise
  impossible to diagnose.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from baldric_coding.extensions.builtins.subagents.memory import MEMORY_SCOPES
from baldric_coding.paths import BaldricPaths
from baldric_coding.resources import parse_markdown_resource
from baldric_coding.thinking import THINKING_LEVELS

#: Agent types that exist without any file on disk.
BUILT_IN_AGENT_NAMES = ("general", "fork", "explore")


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """One spawnable subagent type."""

    name: str
    description: str
    system_prompt: str | None = None
    tools: tuple[str, ...] | None = None
    model: str | None = None
    thinking: str | None = None
    max_turns: int | None = None
    skills: tuple[str, ...] | bool | None = None
    prompt_mode: str = "replace"
    memory: str | None = None
    isolation: str | None = None
    inherit_context: bool | None = None
    # Built-in only (not parseable from frontmatter): fork-ness overrides
    # tools, model, thinking, and the whole prompt assembly, so a .md file
    # declaring it would have every other key silently ignored.
    fork: bool = False


DEFAULT_AGENT_TYPES: tuple[AgentDefinition, ...] = (
    AgentDefinition(
        name="general",
        description=("General-purpose agent with the full coding toolset for research and multi-step tasks."),
    ),
    AgentDefinition(
        name="fork",
        description=(
            "Continues this conversation: starts with its full message history"
            " (tool calls and results included), system prompt, tools, and"
            " model. Provider, model, thinking, and isolated are fixed to the"
            " parent's."
        ),
        fork=True,
    ),
    AgentDefinition(
        name="explore",
        description="Read-only agent for searching and summarizing code without editing.",
        tools=("read", "bash"),
        system_prompt=(
            "You are a read-only exploration agent. Investigate the codebase and"
            " report findings. Never modify files; use bash only for read-only"
            " commands such as ls, grep, find, and git log."
        ),
    ),
)


def load_agent_definitions(
    paths: BaldricPaths,
    cwd: Path,
    *,
    project_trusted: bool,
) -> tuple[dict[str, AgentDefinition], tuple[str, ...]]:
    """Load agent types: built-in defaults, then user files, then project files.

    Returns the definitions plus one note per file that was skipped and one per
    frontmatter value that was rejected.
    """
    definitions = {definition.name: definition for definition in DEFAULT_AGENT_TYPES}
    notes: list[str] = []
    user_dir = paths.user_subagent_types_dir
    project_dir = paths.project_subagent_types_dir(cwd)
    if not project_trusted and project_dir.is_dir():
        notes.append(f"{project_dir} was not read because the project is not trusted")
    for directory, enabled in ((user_dir, True), (project_dir, project_trusted)):
        if not enabled or not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            # "fork" is reserved: a user file would silently turn forks into
            # ordinary subagents (fork-ness is not a frontmatter feature).
            if path.stem == "fork":
                notes.append(f"{path} is ignored because the 'fork' agent type is built in")
                continue
            definition = _load_definition(path, notes)
            if definition is not None:
                definitions[definition.name] = definition
    return definitions, tuple(notes)


def format_agent_type_list(definitions: dict[str, AgentDefinition]) -> str:
    """Format agent types for tool descriptions and the /agents command."""
    return "\n".join(f"- {name}: {definitions[name].description}" for name in sorted(definitions))


def _load_definition(path: Path, notes: list[str]) -> AgentDefinition | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        # ValueError covers UnicodeDecodeError: the file is not readable text.
        notes.append(f"{path} could not be read and was skipped")
        return None
    metadata, body = parse_markdown_resource(raw)
    thinking = metadata.get("thinking")
    if thinking is not None and thinking not in THINKING_LEVELS:
        notes.append(
            f"{path}: thinking {thinking!r} is not one of {', '.join(THINKING_LEVELS)};"
            " the agent will inherit the parent's thinking level"
        )
        thinking = None
    memory = metadata.get("memory")
    if memory is not None and memory not in MEMORY_SCOPES:
        notes.append(
            f"{path}: memory {memory!r} is not one of {', '.join(MEMORY_SCOPES)}; the agent"
            " will have no memory"
        )
        memory = None
    raw_isolation = metadata.get("isolation")
    if raw_isolation is not None and raw_isolation != "worktree":
        notes.append(
            f"{path}: isolation {raw_isolation!r} is not supported; the agent will run in"
            " the parent directory"
        )
    prompt_mode = metadata.get("prompt_mode")
    if prompt_mode is not None and prompt_mode not in ("replace", "append"):
        notes.append(f"{path}: prompt_mode {prompt_mode!r} must be 'replace' or 'append'; using 'replace'")
        prompt_mode = None
    raw_inherit = metadata.get("inherit_context")
    inherit_context = _parse_bool(raw_inherit)
    if raw_inherit is not None and inherit_context is None:
        notes.append(f"{path}: inherit_context {raw_inherit!r} must be true or false; using the default")
    return AgentDefinition(
        name=path.stem,
        description=metadata.get("description") or f"Custom agent type from {path}",
        system_prompt=body.strip() or None,
        tools=_parse_tools(metadata.get("tools")),
        model=metadata.get("model") or None,
        thinking=thinking,
        max_turns=_parse_max_turns(metadata.get("max_turns"), path, notes),
        skills=_parse_skills(metadata.get("skills")),
        prompt_mode="append" if prompt_mode == "append" else "replace",
        memory=memory,
        isolation="worktree" if raw_isolation == "worktree" else None,
        inherit_context=inherit_context,
    )


def _parse_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    stripped = str(raw).strip().lower()
    if stripped in ("true", "yes", "1"):
        return True
    if stripped in ("false", "no", "0"):
        return False
    return None


def _parse_tools(raw: str | None) -> tuple[str, ...] | None:
    if raw is None or raw.strip() in ("", "*", "all"):
        return None
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _parse_skills(raw: str | None) -> tuple[str, ...] | bool | None:
    """Parse `skills:` into four states.

    None = omitted (Baldric's native discovery, default); tuple = named preload;
    True (`true`/`*`/`all`) = pin discovery to the parent cwd; False
    (`none`/`false`) = disable skill discovery.
    """
    if raw is None:
        return None
    stripped = raw.strip().lower()
    if stripped == "":
        return None
    if stripped in ("none", "false"):
        return False
    if stripped in ("*", "all", "true"):
        return True
    return tuple(part.strip() for part in raw.split(",") if part.strip()) or None


def _parse_max_turns(raw: str | None, path: Path, notes: list[str]) -> int | None:
    """Parse a non-negative int turn limit (0 = unlimited); invalid → unlimited, noted.

    The fallback is deliberately loud: an unparseable limit must not quietly
    remove the bound the user was asking for.
    """
    if raw is None:
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        notes.append(f"{path}: max_turns {raw!r} is not a number; the agent will run without a turn limit")
        return None
    if value < 0:
        notes.append(f"{path}: max_turns {value} is negative; the agent will run without a turn limit")
        return None
    return value
