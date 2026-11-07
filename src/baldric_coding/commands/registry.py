"""Slash command registry and built-in command registration."""

from __future__ import annotations

from baldric_coding.commands.base import (
    CommandContext,
    CommandHandler,
    CommandRegistry,
    CommandResult,
    CommandSession,
    SlashCommand,
)
from baldric_coding.commands.config import (
    LOGIN_PROVIDER_ALIASES,
    _approvals_command,
    _local_command,
    _login_command,
    _logout_command,
    _model_command,
    _scoped_models_command,
    _sidebar_command,
    _theme_command,
    _thinking_command,
)
from baldric_coding.commands.core import (
    _compact_command,
    _exit_command,
    _export_command,
    _help_command,
    _hotkeys_command,
    _new_command,
    _status_command,
    _tools_command,
)
from baldric_coding.commands.formatting import format_reload_summary, format_resource_diagnostics
from baldric_coding.commands.resources import (
    _context_command,
    _diagnostics_command,
    _extensions_command,
    _prompts_command,
    _reload_command,
    _skill_command,
    _skills_command,
    _system_command,
)
from baldric_coding.commands.session import _name_command, _resume_command, _tree_command

__all__ = [
    "CommandContext",
    "CommandHandler",
    "CommandRegistry",
    "CommandResult",
    "CommandSession",
    "LOGIN_PROVIDER_ALIASES",
    "SlashCommand",
    "create_default_command_registry",
    "format_reload_summary",
    "format_resource_diagnostics",
]


def create_default_command_registry() -> CommandRegistry:
    """Create Baldric's built-in slash command registry."""
    registry = CommandRegistry()
    registry.register(
        SlashCommand(
            name="quit",
            usage="/quit",
            description="Exit the current session.",
            handler=_exit_command,
            aliases=("exit",),
        )
    )
    registry.register(
        SlashCommand(
            name="new",
            usage="/new",
            description="Start a new session.",
            handler=_new_command,
            search_terms=("clear", "reset"),
        )
    )
    registry.register(
        SlashCommand(
            name="compact",
            usage="/compact [instructions]",
            description="Summarize and compact active context.",
            handler=_compact_command,
        )
    )
    registry.register(
        SlashCommand(
            name="diagnostics",
            usage="/diagnostics",
            description="Show resource loading diagnostics.",
            handler=_diagnostics_command,
            search_terms=("errors", "warnings", "loading"),
        )
    )
    registry.register(
        SlashCommand(
            name="extensions",
            usage="/extensions",
            description="Browse loaded extensions and diagnostics.",
            handler=_extensions_command,
            search_terms=("plugins", "addons"),
        )
    )
    registry.register(
        SlashCommand(
            name="export",
            usage="/export [--format html|jsonl] [destination]",
            description="Export the current session.",
            handler=_export_command,
        )
    )
    registry.register(
        SlashCommand(
            name="session",
            usage="/session",
            description="Show session info and stats.",
            handler=_status_command,
            search_terms=("info",),
        )
    )
    registry.register(
        SlashCommand(
            name="system",
            usage="/system",
            description="Show the active system prompt without saving it.",
            handler=_system_command,
            search_terms=("prompt", "instructions"),
        )
    )
    registry.register(
        SlashCommand(
            name="skill",
            usage="/skill:<name> [request]",
            description="Expand a loaded skill into your prompt.",
            handler=_skill_command,
            search_terms=("skills",),
        )
    )
    registry.register(
        SlashCommand(
            name="skills",
            usage="/skills",
            description="Browse and insert a loaded skill.",
            handler=_skills_command,
            search_terms=("skill", "picker", "search"),
        )
    )
    registry.register(
        SlashCommand(
            name="hotkeys",
            usage="/hotkeys",
            description="Show common keyboard shortcuts.",
            handler=_hotkeys_command,
            search_terms=("keys", "shortcuts", "bindings"),
        )
    )
    # Baldric-specific commands: implemented, tested, and now reachable. They are
    # not pi ports, and `test_non_pi_commands_are_not_registered` used to forbid
    # them; that test now pins the opposite decision.
    registry.register(
        SlashCommand(
            name="help",
            usage="/help",
            description="List the available slash commands.",
            handler=_help_command,
            search_terms=("commands", "usage"),
        )
    )
    registry.register(
        SlashCommand(
            name="context",
            usage="/context",
            description="Show the project context files loaded into this session.",
            handler=_context_command,
            search_terms=("instructions", "rules", "agents"),
        )
    )
    registry.register(
        SlashCommand(
            name="prompts",
            usage="/prompts",
            description="Choose a loaded prompt template.",
            handler=_prompts_command,
            search_terms=("templates", "picker"),
        )
    )
    registry.register(
        SlashCommand(
            name="reload",
            usage="/reload",
            description="Reload local resources and project context.",
            handler=_reload_command,
        )
    )
    registry.register(
        SlashCommand(
            name="resume",
            usage="/resume [session-id]",
            description="Resume a previous session.",
            handler=_resume_command,
            search_terms=("history", "previous"),
        )
    )
    registry.register(
        SlashCommand(
            name="tree",
            usage="/tree",
            description="Branch from a previous session entry.",
            handler=_tree_command,
            search_terms=("branch", "history", "fork"),
        )
    )
    registry.register(
        SlashCommand(
            name="name",
            usage="/name <new name>",
            description="Rename the current session.",
            handler=_name_command,
            search_terms=("rename", "title"),
        )
    )
    registry.register(
        SlashCommand(
            name="model",
            usage="/model",
            description="Choose the active model.",
            handler=_model_command,
        )
    )
    registry.register(
        SlashCommand(
            name="tools",
            usage="/tools",
            description="Browse tools available to the active session.",
            handler=_tools_command,
            search_terms=("capabilities", "reference"),
        )
    )
    registry.register(
        SlashCommand(
            name="scoped-models",
            usage="/scoped-models",
            description="Choose models available to quick-cycle with Ctrl+P.",
            handler=_scoped_models_command,
            search_terms=("scope", "quick", "cycle", "ctrl+p"),
        )
    )
    registry.register(
        SlashCommand(
            name="thinking",
            usage="/thinking [level]",
            description="Show or set the thinking mode.",
            handler=_thinking_command,
            search_terms=("reasoning", "effort"),
        )
    )
    registry.register(
        SlashCommand(
            name="theme",
            usage="/theme [name]",
            description="Show or set the TUI theme.",
            handler=_theme_command,
            search_terms=("light", "dark", "contrast"),
        )
    )
    registry.register(
        SlashCommand(
            name="local",
            usage="/local",
            description="Configure and manage local backends.",
            handler=_local_command,
            search_terms=("backends", "inference"),
        )
    )
    registry.register(
        SlashCommand(
            name="sidebar",
            usage="/sidebar",
            description="Show or hide the TUI sidebar for this session.",
            handler=_sidebar_command,
            search_terms=("toggle", "visibility", "panel"),
        )
    )
    registry.register(
        SlashCommand(
            name="approvals",
            usage="/approvals",
            description="Toggle approval prompts before edit/write/bash calls.",
            handler=_approvals_command,
            search_terms=("approval", "permission", "confirm", "gate"),
        )
    )
    registry.register(
        SlashCommand(
            name="login",
            usage="/login [provider]",
            description="Connect a provider with OAuth or an API key.",
            handler=_login_command,
        )
    )
    registry.register(
        SlashCommand(
            name="logout",
            usage="/logout [provider]",
            description="Remove saved credentials for a built-in provider.",
            handler=_logout_command,
        )
    )
    return registry
