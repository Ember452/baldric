"""Provider contract owned by the Baldric protocol layer."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from baldric.protocol.messages import AgentMessage
from baldric.protocol.provider_events import AssistantMessageEvent
from baldric.protocol.tools import AgentTool
from baldric.protocol.types import JSONValue


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
        hooks: RequestHooks | None = None,
    ) -> AsyncIterator[AssistantMessageEvent]:
        """Stream one model response as assistant message events.

        Providers may use ``session_id`` for request routing or prompt-cache
        affinity. Unsupported providers ignore it.

        ``hooks`` carries request-level extension seams (Pi's ``onPayload`` /
        custom ``headers`` / ``onResponse``). An adapter invokes them at its real
        payload/headers/response points. ``None`` means "no hooks" and the adapter
        behaves exactly as before (byte-identical request).
        """
        ...


class ClosableModelProvider(ModelProvider, Protocol):
    """Runtime provider object Baldric owns and can close.

    A provider that holds resources (HTTP clients, streams) implements this so
    the session can release them deterministically. It is a pure shape
    (``ModelProvider`` + ``aclose``) and lives in the contract layer so both the
    provider-config layer and the extension provider contracts can name it without
    importing each other.
    """

    async def aclose(self) -> None:
        """Close any provider-owned resources."""
        ...


# --- request-level hook contract (Pi onPayload / headers / onResponse) --------
# Shapes are pure data + pure dispatch so they belong to the contract layer:
# adapters and the adapter-hook helper both depend on protocol, never the reverse.

# Chained: receives the built payload dict, returns a replacement (or None to
# keep the current one). Pi's ``onPayload``: `nextPayload !== undefined` replaces.
# Handlers may be sync or async (Pi awaits ``onPayload``).
type PayloadHook = Callable[
    [dict[str, JSONValue], HookContext],
    dict[str, JSONValue] | None | Awaitable[dict[str, JSONValue] | None],
]
# In-place: mutate the headers mapping. Return ignored (sync or awaitable).
type HeadersHook = Callable[[dict[str, str], HookContext], Awaitable[None] | None]
# Read-only observe of the HTTP response (status + headers) before consumption.
type ResponseHook = Callable[[int, dict[str, str], HookContext], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class HookContext:
    """Read-only metadata handed to every provider seam handler."""

    model: str
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class RequestHooks:
    """Request-level seams an adapter threads through its own request build.

    Pure data: the adapter passes this to the adapter-hook helper (in
    ``baldric.ai.hooks``) which runs the handlers with isolation and the
    composition rules from dev-notes/architecture/hook-composition.md. Keeping
    the run logic out of the contract package keeps protocol dependency-free.
    """

    model: str
    session_id: str | None = None
    payload: Sequence[PayloadHook] = field(default_factory=tuple)
    headers: Sequence[HeadersHook] = field(default_factory=tuple)
    response: Sequence[ResponseHook] = field(default_factory=tuple)

    def is_empty(self) -> bool:
        return not (self.payload or self.headers or self.response)
