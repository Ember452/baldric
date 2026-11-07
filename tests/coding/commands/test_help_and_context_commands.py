"""`/help` and `/context` are Baldric commands and must be reachable.

Both were implemented and unit-tested but never registered, so no frontend could
run them. They are not pi ports; the project now owns the decision to expose
them, and `test_non_pi_commands_are_not_registered` pins the remaining ones.
"""

from __future__ import annotations

from baldric_coding.commands.base import CommandContext, CommandKind, CommandRegistry
from baldric_coding.commands.registry import create_default_command_registry


class _Session:
    context_files: tuple[object, ...] = ()
    resource_diagnostics: tuple[object, ...] = ()


def _context(registry: CommandRegistry, text: str) -> CommandContext:
    name, _, args = text.partition(" ")
    return CommandContext(
        session=_Session(),  # type: ignore[arg-type]
        registry=registry,
        text=text,
        name=name.lstrip("/"),
        args=args,
    )


def _handler(registry: CommandRegistry, name: str):  # type: ignore[no-untyped-def]
    return next(command for command in registry.list_commands() if command.name == name).handler


def test_help_is_registered_and_lists_commands() -> None:
    registry = create_default_command_registry()

    result = _handler(registry, "help")(_context(registry, "/help"))

    assert result.outcome.kind is CommandKind.MESSAGE
    assert "/context" in (result.outcome.message or "")
    assert "/help" in (result.outcome.message or "")


def test_context_is_registered_and_reports_loaded_files() -> None:
    registry = create_default_command_registry()

    result = _handler(registry, "context")(_context(registry, "/context"))

    assert result.outcome.kind is CommandKind.MESSAGE
    assert "No project context files" in (result.outcome.message or "")
