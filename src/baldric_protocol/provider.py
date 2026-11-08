"""Provider contract owned by the Baldric protocol layer."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from baldric_protocol.messages import AgentMessage
from baldric_protocol.provider_events import AssistantMessageEvent
from baldric_protocol.tools import AgentTool


class CancellationToken(Protocol):
    def is_cancelled(self) -> bool:
        """Return whether the current stream should stop."""
        ...

    async def wait_cancelled(self) -> None:
        """Resolve once the run is cancelled.

        Providers race this against a blocking read so a stalled response (a
        queued request, a silent upstream) stops promptly instead of waiting for
        the read timeout.
        """
        ...


class ModelProvider(Protocol):
    """Provider-neutral Pi-compatible model stream interface."""

    def stream_response(
        self,
        *,
        model: str,
        system: str,
        messages: list[AgentMessage],
        tools: list[AgentTool],
        signal: CancellationToken | None = None,
        session_id: str | None = None,
    ) -> AsyncIterator[AssistantMessageEvent]:
        """Stream one model response as assistant message events.

        Providers may use ``session_id`` for request routing or prompt-cache
        affinity. Unsupported providers ignore it.
        """
        ...
