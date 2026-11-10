"""Provider-level extension seams (plan Task A1).

Two layers, mirroring Pi's split between the AI package (native request hooks:
``onPayload`` / custom ``headers`` / ``onResponse``) and the coding-agent package
(the extension-facing event names bridged onto them):

- **Request seams (adapter layer).** :class:`baldric.protocol.provider.RequestHooks`
  carries ``payload`` (chained), ``headers`` (in-place), and ``response``
  (observe) handlers. An adapter invokes them via :func:`apply_payload` /
  :func:`apply_headers` / :func:`observe_response` at its real request points.
- **Provider-boundary seams (this module).** :class:`HookableProvider` wraps any
  :class:`ModelProvider` and exposes ``context`` (chained transform of the
  outgoing ``messages``/``system``), ``provider_stream_event`` (observe each
  streamed event), and ``response_start`` (observe the first event of a response).
  It forwards its ``payload``/``headers``/``response`` handlers down to the
  wrapped adapter as a :class:`RequestHooks`.

Composition follows dev-notes/architecture/hook-composition.md everywhere:
handlers run in registration order; a raising handler is isolated (fail-open —
every seam here is transform/observe); ``context`` and ``payload`` are chained;
``headers`` is in-place; the observe seams are read-only; no seam short-circuits.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from typing import cast

from baldric.protocol.messages import AgentMessage
from baldric.protocol.provider import (
    CancellationToken,
    HeadersHook,
    HookContext,
    ModelProvider,
    PayloadHook,
    RequestHooks,
    ResponseHook,
)
from baldric.protocol.provider_events import AssistantMessageEvent
from baldric.protocol.tools import AgentTool
from baldric.protocol.types import JSONValue

# Chained transform of the outgoing context; returns a new ProviderContext or None
# (sync or awaitable).
type ContextHook = Callable[
    [ProviderContext, HookContext], ProviderContext | None | Awaitable[ProviderContext | None]
]
# In-place observe of one streamed event. Return ignored (sync or awaitable).
type StreamEventHook = Callable[[AssistantMessageEvent, HookContext], Awaitable[None] | None]
# In-place observe of the first assistant event of a response (sync or awaitable).
type ResponseStartHook = Callable[[AssistantMessageEvent, HookContext], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class ProviderContext:
    """The outgoing request context a ``context`` hook may transform (immutable)."""

    model: str
    system: str
    messages: Sequence[AgentMessage]
    tools: Sequence[AgentTool]
    session_id: str | None = None


@dataclass(slots=True)
class ProviderHooks:
    """Registered provider-seam handlers, in registration order."""

    context: list[ContextHook] = field(default_factory=list)
    stream_event: list[StreamEventHook] = field(default_factory=list)
    response_start: list[ResponseStartHook] = field(default_factory=list)
    payload: list[PayloadHook] = field(default_factory=list)
    headers: list[HeadersHook] = field(default_factory=list)
    response: list[ResponseHook] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.context
            or self.stream_event
            or self.response_start
            or self.payload
            or self.headers
            or self.response
        )

    def request_hooks(self, model: str, session_id: str | None) -> RequestHooks | None:
        """Build the adapter-facing request seams, or ``None`` when none registered."""
        if not (self.payload or self.headers or self.response):
            return None
        return RequestHooks(
            model=model,
            session_id=session_id,
            payload=tuple(self.payload),
            headers=tuple(self.headers),
            response=tuple(self.response),
        )


# --- request seams (adapters call these at their real request points) ---------


async def apply_payload(hooks: RequestHooks | None, payload: dict[str, JSONValue]) -> dict[str, JSONValue]:
    """Return the payload after the chained payload seam (``None`` hooks = unchanged).

    Handlers may be sync or async (Pi's ``onPayload`` is awaited); a raising
    handler is skipped (fail-open). Called from the adapter's async request path.
    """
    if hooks is None or not hooks.payload:
        return payload
    current: dict[str, JSONValue] = payload
    ctx = HookContext(model=hooks.model, session_id=hooks.session_id)
    for hook in hooks.payload:
        outcome: list[dict[str, JSONValue] | None] = []
        with suppress(_HandlerFailure):
            outcome.append(cast("dict[str, JSONValue] | None", await _guarded(hook, current, ctx)))
        if outcome and outcome[0] is not None:
            current = outcome[0]
    return current


async def apply_headers(hooks: RequestHooks | None, headers: dict[str, str]) -> None:
    """Mutate ``headers`` in place through the headers seam (``None`` hooks = no-op)."""
    if hooks is None or not hooks.headers:
        return
    ctx = HookContext(model=hooks.model, session_id=hooks.session_id)
    for hook in hooks.headers:
        with suppress(_HandlerFailure):
            await _guarded(hook, headers, ctx)


async def observe_response(hooks: RequestHooks | None, status: int, headers: dict[str, str]) -> None:
    """Observe the HTTP response before consumption (``None`` hooks = no-op)."""
    if hooks is None or not hooks.response:
        return
    ctx = HookContext(model=hooks.model, session_id=hooks.session_id)
    for hook in hooks.response:
        with suppress(_HandlerFailure):
            await _guarded(hook, status, headers, ctx)


class _HandlerFailure(Exception):
    """Carries a hook handler's own exception out of ``_guarded``."""


async def _guarded(handler: Callable[..., object], *args: object) -> object:
    """Await one hook handler, converting its failure to ``_HandlerFailure``.

    The provider seam is an isolation boundary: a misbehaving (sync or async)
    extension handler must never abort the stream or the run. Converting here
    (rather than a bare ``except Exception`` at each call site) keeps the
    isolation in one place and lets call sites use ``contextlib.suppress``
    without a broad-except literal.
    """
    try:
        result = handler(*args)
        return await result if inspect.isawaitable(result) else result
    except Exception as exc:  # noqa: BLE001 - extension hooks are an isolation boundary
        raise _HandlerFailure from exc


class HookableProvider:
    """A ``ModelProvider`` that forwards to ``inner`` through the seams above."""

    def __init__(self, inner: ModelProvider, hooks: ProviderHooks | None = None) -> None:
        self._inner = inner
        self.hooks = hooks if hooks is not None else ProviderHooks()

    async def aclose(self) -> None:
        """Forward ``aclose`` to the wrapped provider when it supports it."""
        close = getattr(self._inner, "aclose", None)
        if close is not None:
            await close()

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
        del hooks  # a wrapper's own request seams come from its ProviderHooks, not the caller
        return self._run(
            ProviderContext(
                model=model, system=system, messages=messages, tools=tools, session_id=session_id
            ),
            signal,
        )

    async def _run(
        self,
        request: ProviderContext,
        signal: CancellationToken | None,
    ) -> AsyncIterator[AssistantMessageEvent]:
        request = await self._apply_context(request)
        inner_source = self._inner.stream_response(
            model=request.model,
            system=request.system,
            messages=list(request.messages),
            tools=list(request.tools),
            signal=signal,
            session_id=request.session_id,
            hooks=self.hooks.request_hooks(request.model, request.session_id),
        )
        hook_context = HookContext(model=request.model, session_id=request.session_id)
        response_started = False
        async for event in inner_source:
            if not response_started:
                response_started = True
                for handler in self.hooks.response_start:
                    with suppress(_HandlerFailure):
                        await _guarded(handler, event, hook_context)
            for handler in self.hooks.stream_event:
                with suppress(_HandlerFailure):
                    await _guarded(handler, event, hook_context)
            yield event

    async def _apply_context(self, request: ProviderContext) -> ProviderContext:
        """Run the chained ``context`` seam; a raising handler is skipped (fail-open)."""
        current = request
        hook_context = HookContext(model=request.model, session_id=request.session_id)
        for handler in self.hooks.context:
            outcome: list[ProviderContext | None] = []
            with suppress(_HandlerFailure):
                outcome.append(cast("ProviderContext | None", await _guarded(handler, current, hook_context)))
            if outcome and outcome[0] is not None:
                current = outcome[0]
        return current


__all__ = [
    "ContextHook",
    "HookableProvider",
    "ProviderContext",
    "ProviderHooks",
    "ResponseStartHook",
    "StreamEventHook",
    "apply_headers",
    "apply_payload",
    "observe_response",
]
