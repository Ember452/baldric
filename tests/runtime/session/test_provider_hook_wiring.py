"""End-to-end wiring test: extension provider hooks through a real CodingSession.

Proves plan Task A1/A2 beyond the unit level: a real extension (loaded from a
file) registers provider seams, the session wraps its provider in a
``HookableProvider``, and the hooks actually reach the provider's request path
when a prompt runs. This is the path ``_apply_provider_hooks`` owns; it had no
coverage before.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baldric.ai.fake import FakeProvider
from baldric.ai.hooks import HookableProvider, apply_headers, apply_payload, observe_response
from baldric.protocol.messages import AssistantMessage, TextContent, UserMessage
from baldric.runtime.session.session import CodingSession, CodingSessionConfig
from baldric.runtime.session.storage import JsonlSessionStorage
from tests.helpers.pi_event_helpers import assistant_done, assistant_start

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class HookApplyingProvider(FakeProvider):
    """A fake provider that applies the request seams like a real adapter would."""

    def __init__(self, streams, *, seen: dict[str, object]) -> None:
        super().__init__(streams)
        self._seen = seen

    def stream_response(
        self,
        *,
        model: str,
        system: str,
        messages,
        tools,
        signal=None,
        session_id=None,
        hooks=None,
    ):
        self.calls.append((model, system, list(messages), list(tools)))
        self.session_ids.append(session_id)
        stream = self._streams.pop(0) if self._streams else []

        async def iterator():
            headers: dict[str, str] = {"content-type": "application/json"}
            await apply_headers(hooks, headers)
            payload = await apply_payload(hooks, {"model": model, "stream": True})
            await observe_response(hooks, 200, {"request-id": "req-1"})
            self._seen["headers"] = dict(headers)
            self._seen["payload"] = dict(payload)
            for event in stream:
                yield event

        return iterator()


def _write_hook_extension(tmp_path: Path, seen_path: Path) -> Path:
    directory = tmp_path / "hook-ext"
    directory.mkdir()
    body = f"""
from baldric.protocol.messages import UserMessage
from baldric.runtime.extensions import ExtensionAPI
from baldric.runtime.extensions.api import ProviderContextEvent

SEEN = {str(seen_path)!r}


def setup(api: ExtensionAPI) -> None:
    def add_header(event, ctx):
        event.headers["X-From-Ext"] = "on"

    def add_context(event, ctx):
        marker = UserMessage(content="context-marker")
        return ProviderContextEvent(
            model=event.model,
            system=event.system,
            messages=(*event.messages, marker),
            tools=event.tools,
        )

    def note_stream(event, ctx):
        with open(SEEN, "a", encoding="utf-8") as handle:
            handle.write(event.event.type + "\\n")

    def tag_payload(event, ctx):
        payload = dict(event.payload)
        payload["x-extension"] = "on"
        return payload

    def note_response(event, ctx):
        with open(SEEN, "a", encoding="utf-8") as handle:
            handle.write("response:" + str(event.status) + ":" + event.headers.get("request-id", "") + "\\n")

    api.on("before_provider_headers", add_header)
    api.on("before_provider_request", tag_payload)
    api.on("after_provider_response", note_response)
    api.on("context", add_context)
    api.on("provider_stream_event", note_stream)
"""
    (directory / "extension.py").write_text(body, encoding="utf-8")
    return directory


def _stream():
    return [
        assistant_start(),
        assistant_done(AssistantMessage(model="fake", content=[TextContent(text="ok")])),
    ]


async def _collect(session_stream) -> list[object]:
    return [event async for event in session_stream]


async def test_extension_provider_hooks_reach_the_provider(tmp_path: Path) -> None:
    seen_path = tmp_path / "seen.txt"
    extension_dir = _write_hook_extension(tmp_path, seen_path)
    seen: dict[str, object] = {}
    provider = HookApplyingProvider([_stream()], seen=seen)

    session = await CodingSession.load(
        CodingSessionConfig(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            storage=JsonlSessionStorage(tmp_path / "session.jsonl"),
            cwd=tmp_path,
            extension_paths=(extension_dir,),
        )
    )
    try:
        # The session wrapped the provider because the extension registered seams.
        assert isinstance(session._harness.config.provider, HookableProvider)

        await _collect(session.prompt("hello"))

        # before_provider_headers reached the adapter's request path.
        headers = seen["headers"]
        assert isinstance(headers, dict) and headers["X-From-Ext"] == "on"

        # before_provider_request rewrote the outgoing payload.
        payload = seen["payload"]
        assert isinstance(payload, dict) and payload["x-extension"] == "on"

        # context seam added its marker to the outgoing provider messages.
        provider_messages = provider.calls[0][2]
        assert any(
            isinstance(message, UserMessage) and message.text == "context-marker"
            for message in provider_messages
        )

        # after_provider_response + provider_stream_event observed the exchange.
        observed = seen_path.read_text(encoding="utf-8").splitlines()
        assert "response:200:req-1" in observed
        assert "start" in observed
        assert "done" in observed
    finally:
        await session.aclose()


async def test_no_provider_hooks_leaves_the_provider_unwrapped(tmp_path: Path) -> None:
    provider = FakeProvider([_stream()])
    session = await CodingSession.load(
        CodingSessionConfig(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            storage=JsonlSessionStorage(tmp_path / "session.jsonl"),
            cwd=tmp_path,
        )
    )
    try:
        assert not isinstance(session._harness.config.provider, HookableProvider)
        assert session._harness.config.provider is provider
    finally:
        await session.aclose()
