"""Pi-compatible JSONL RPC frontend for a Baldric coding session."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal, Protocol

from baldric_agent.session.entries import SessionEntry
from baldric_coding.commands.registry import CommandRegistry
from baldric_coding.events import CodingSessionEvent
from baldric_coding.providers.config import (
    ProviderConfig,
)
from baldric_coding.session.manager import SessionManager
from baldric_coding.session.session import (
    ManualCompactionResult,
    ModelChoice,
    TerminalCommandResult,
)
from baldric_coding.session.stats import SessionStats


class RpcSession(Protocol):
    """Public CodingSession surface consumed by RPC mode."""

    @property
    def model(self) -> str: ...

    @property
    def provider_name(self) -> str: ...

    @property
    def thinking_level(self) -> str: ...

    @property
    def available_thinking_levels(self) -> tuple[str, ...]: ...

    @property
    def available_model_choices(self) -> tuple[ModelChoice, ...]: ...

    def provider_config(self, provider_name: str) -> ProviderConfig | None: ...

    @property
    def messages(self) -> tuple[object, ...]: ...

    @property
    def session_id(self) -> str | None: ...

    @property
    def session_title(self) -> str | None: ...

    @property
    def session_manager(self) -> SessionManager | None: ...

    @property
    def storage(self) -> object: ...

    @property
    def auto_compact_token_threshold(self) -> int | None: ...

    @property
    def auto_compaction_enabled(self) -> bool: ...

    @property
    def context_window_tokens(self) -> int: ...

    @property
    def context_token_estimate(self) -> int: ...

    @property
    def queued_message_count(self) -> int: ...

    @property
    def session_stats(self) -> SessionStats: ...

    @property
    def command_registry(self) -> CommandRegistry: ...

    @property
    def state(self) -> object: ...

    def prompt(
        self,
        content: str,
        *,
        streaming_behavior: Literal["steer", "follow_up"] | None = None,
    ) -> AsyncIterator[CodingSessionEvent]: ...

    def cancel(self) -> None: ...

    def set_model_choice(self, choice: ModelChoice) -> None: ...

    async def cycle_thinking_level(self) -> str: ...

    async def set_thinking_level(self, level: str) -> str: ...

    def set_auto_compaction_enabled(self, enabled: bool) -> None: ...

    async def compact_detailed(self, instructions: str | None = None) -> ManualCompactionResult: ...

    async def new_session(self) -> str: ...

    async def resume(self, session_id: str) -> str: ...

    async def session_entries(self) -> tuple[SessionEntry, ...]: ...

    async def tree_choices(self) -> tuple[object, ...]: ...

    async def branch_to_entry(self, entry_id: str) -> object: ...

    async def export(self, destination: Path | None = None, *, format: str | None = None) -> Path: ...

    async def run_terminal_command(self, command: str, *, add_to_context: bool) -> TerminalCommandResult: ...

    async def set_session_name(self, name: str) -> str: ...

    async def emit_pending_session_start(self) -> None: ...

    async def aclose(self) -> None: ...
