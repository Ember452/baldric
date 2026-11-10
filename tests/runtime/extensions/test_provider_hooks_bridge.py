"""Extension provider-seam bridge (plan Task A2).

Proves the bridge from extension events (on("before_provider_headers") etc.)
onto the AI-layer seams: ExtensionRuntime.build_provider_hooks() adapts
registered handlers so a HookableProvider applies them to a real provider call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baldric.ai.events import AssistantDoneEvent, AssistantStartEvent
from baldric.ai.fake import FakeProvider
from baldric.ai.hooks import HookableProvider
from baldric.protocol.messages import AssistantMessage, TextContent, UserMessage
from baldric.runtime.extensions.api import ExtensionAPI
from baldric.runtime.extensions.builtin_registry import BuiltInExtension
from baldric.runtime.extensions.runtime import ExtensionRuntime
from tests.runtime.extensions.test_extensions import _paths

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _stream():
    return [
        AssistantStartEvent(partial=AssistantMessage(model="m")),
        AssistantDoneEvent(
            reason="stop",
            message=AssistantMessage(model="m", content=[TextContent(text="hi")], stop_reason="stop"),
        ),
    ]


def _runtime(tmp_path: Path, setup) -> ExtensionRuntime:
    runtime = ExtensionRuntime(built_in_extensions=(BuiltInExtension(name="ext", setup=setup),))
    runtime.load(_paths(tmp_path), include_resource_dirs=False)
    return runtime


def test_no_provider_handlers_means_no_hooks(tmp_path: Path) -> None:
    def setup(api: ExtensionAPI) -> None:
        api.on("input", lambda event, ctx: None)

    runtime = _runtime(tmp_path, setup)
    assert runtime.has_provider_hooks() is False
    assert runtime.build_provider_hooks().is_empty() is True


async def test_before_provider_headers_is_applied_to_real_call(tmp_path: Path) -> None:
    def setup(api: ExtensionAPI) -> None:
        def add(event, ctx):
            event.headers["X-From-Extension"] = "yes"

        api.on("before_provider_headers", add)

    runtime = _runtime(tmp_path, setup)
    assert runtime.has_provider_hooks() is True

    # Drive the headers seam the way an adapter would.
    from baldric.ai.hooks import apply_headers

    headers: dict[str, str] = {"content-type": "application/json"}
    await apply_headers(runtime.build_provider_hooks().request_hooks("m", None), headers)
    assert headers["X-From-Extension"] == "yes"

    # And a plain stream still works through the wrapper.
    inner = FakeProvider([_stream()])
    wrapped = HookableProvider(inner, runtime.build_provider_hooks())
    events = []
    async for event in wrapped.stream_response(
        model="m", system="s", messages=[UserMessage(content="q")], tools=[]
    ):
        events.append(event)
    assert len(events) == 2


async def test_before_provider_request_transforms_payload(tmp_path: Path) -> None:
    def setup(api: ExtensionAPI) -> None:
        def tag(event, ctx):
            return {**event.payload, "tagged": True}

        api.on("before_provider_request", tag)

    runtime = _runtime(tmp_path, setup)
    from baldric.ai.hooks import apply_payload

    payload = await apply_payload(runtime.build_provider_hooks().request_hooks("m", None), {"model": "m"})
    assert payload["tagged"] is True


async def test_context_hook_transforms_messages(tmp_path: Path) -> None:

    from baldric.runtime.extensions.api import ProviderContextEvent

    def setup(api: ExtensionAPI) -> None:
        def add_system(event, ctx):
            assert isinstance(event, ProviderContextEvent)
            return ProviderContextEvent(
                model=event.model, system=event.system + "+ext", messages=event.messages, tools=event.tools
            )

        api.on("context", add_system)

    runtime = _runtime(tmp_path, setup)
    hooks = runtime.build_provider_hooks()
    from baldric.ai.hooks import HookContext, ProviderContext

    req = ProviderContext(model="m", system="base", messages=[], tools=[])
    out = await hooks.context[0](req, HookContext(model="m"))
    assert out is not None and out.system == "base+ext"
