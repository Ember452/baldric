"""Provider-level hook seams (plan Task A1): HookableProvider.

Locks the three A1 seams (context / provider_stream_event / after_provider_response),
the transparent-wrapper guarantee (no hooks == byte-identical forwarding), and the
hook-composition contract (order, per-handler isolation) at the provider layer.
"""

from __future__ import annotations

import pytest

from baldric.ai.events import (
    AssistantDoneEvent,
    AssistantStartEvent,
)
from baldric.ai.fake import FakeProvider
from baldric.ai.hooks import HookableProvider, HookContext, ProviderContext, ProviderHooks
from baldric.protocol.messages import AssistantMessage, TextContent, UserMessage

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _done() -> AssistantDoneEvent:
    return AssistantDoneEvent(
        reason="stop",
        message=AssistantMessage(model="m", content=[TextContent(text="hi")], stop_reason="stop"),
    )


def _stream() -> list:
    return [AssistantStartEvent(partial=AssistantMessage(model="m")), _done()]


async def _drain(provider, messages, tools=()):
    out = []
    async for event in provider.stream_response(
        model="m", system="sys", messages=list(messages), tools=list(tools)
    ):
        out.append(event)
    return out


async def test_no_hooks_is_transparent_forwarding() -> None:
    """Empty hook set forwards the request unchanged (transparency)."""
    user = UserMessage(content=[TextContent(text="q")])
    inner = FakeProvider([_stream()])
    wrapped = HookableProvider(inner)
    assert wrapped.hooks.is_empty()

    events = await _drain(wrapped, [user])

    assert len(events) == 2
    # inner saw exactly the request we sent
    model, system, messages, tools = inner.calls[0]
    assert (model, system) == ("m", "sys")
    assert messages == [user]
    assert tools == []


async def test_context_hook_transforms_outgoing_messages() -> None:
    """`context` seam: the handler's returned context is what the inner provider sees."""
    user = UserMessage(content=[TextContent(text="q")])

    def inject(request: ProviderContext, ctx: HookContext) -> ProviderContext:
        from dataclasses import replace

        extra = UserMessage(content=[TextContent(text="injected")])
        return replace(request, messages=[*request.messages, extra])

    hooks = ProviderHooks(context=[inject])
    inner = FakeProvider([_stream()])
    wrapped = HookableProvider(inner, hooks)

    await _drain(wrapped, [user])

    seen_messages = inner.calls[0][2]
    texts = [c.text for m in seen_messages for c in m.content if isinstance(c, TextContent)]
    assert texts == ["q", "injected"]


async def test_context_hooks_chain_in_order() -> None:
    """`context` is chained: each handler sees the previous handler's output."""
    user = UserMessage(content=[TextContent(text="a")])
    order: list[str] = []

    def first(request: ProviderContext, ctx: HookContext) -> ProviderContext:
        from dataclasses import replace

        order.append("first")
        return replace(request, system=request.system + "+first")

    def second(request: ProviderContext, ctx: HookContext) -> ProviderContext:
        order.append("second")
        assert request.system == "sys+first"  # sees first's output
        from dataclasses import replace

        return replace(request, system=request.system + "+second")

    wrapped = HookableProvider(FakeProvider([_stream()]), ProviderHooks(context=[first, second]))
    await _drain(wrapped, [user])

    assert order == ["first", "second"]
    assert wrapped._inner.calls[0][1] == "sys+first+second"


async def test_stream_event_and_response_start_seams_fire() -> None:
    """`provider_stream_event` fires per event; `after_provider_response` fires once on the first."""
    streamed: list[type] = []
    starts: list[type] = []
    hooks = ProviderHooks(
        stream_event=[lambda event, ctx: streamed.append(type(event))],
        response_start=[lambda event, ctx: starts.append(type(event))],
    )
    wrapped = HookableProvider(FakeProvider([_stream()]), hooks)

    await _drain(wrapped, [UserMessage(content=[TextContent(text="q")])])

    assert streamed == [AssistantStartEvent, AssistantDoneEvent]
    assert starts == [AssistantStartEvent]  # only the first event


async def test_a_raising_hook_is_isolated_and_others_still_run() -> None:
    """Fail-open isolation: a raising context hook is skipped, later hooks still run."""
    user = UserMessage(content=[TextContent(text="q")])
    ran: list[str] = []

    def boom(request: ProviderContext, ctx: HookContext):
        raise RuntimeError("kaboom")

    def after(request: ProviderContext, ctx: HookContext) -> ProviderContext:
        ran.append("after")
        return request

    wrapped = HookableProvider(FakeProvider([_stream()]), ProviderHooks(context=[boom, after]))
    # Must not raise out.
    await _drain(wrapped, [user])

    assert ran == ["after"]


async def test_aclose_forwards_to_inner() -> None:
    """The wrapper forwards aclose to a provider that supports it."""

    class ClosingProvider(FakeProvider):
        closed = False

        async def aclose(self) -> None:
            self.closed = True

    inner = ClosingProvider([_stream()])
    wrapped = HookableProvider(inner)
    await wrapped.aclose()

    assert inner.closed is True
