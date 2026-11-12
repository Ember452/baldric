"""Custom compaction summary hook (plan Task B, narrowed).

An extension may supply the compaction summary (Pi's session_before_compact,
summary half only). It cannot veto compaction: an empty/raising handler falls
back to the built-in summarizer, and the text is clamped so a runaway summary
cannot blow the budget it exists to protect.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baldric.ai.fake import FakeProvider
from baldric.protocol.messages import AssistantMessage, TextContent, UserMessage
from baldric.runtime.session.runtime import MAX_EXTENSION_COMPACTION_SUMMARY_CHARS
from baldric.runtime.session.session import CodingSession, CodingSessionConfig
from baldric.runtime.session.storage import JsonlSessionStorage
from tests.helpers.pi_event_helpers import assistant_done, assistant_start

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _write_extension(tmp_path: Path, body: str) -> Path:
    directory = tmp_path / "compaction-ext"
    directory.mkdir()
    (directory / "extension.py").write_text(body, encoding="utf-8")
    return directory


async def _open_session(tmp_path: Path, provider, *, extension_dir: Path | None = None) -> CodingSession:
    return await CodingSession.load(
        CodingSessionConfig(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            storage=JsonlSessionStorage(tmp_path / "session.jsonl"),
            cwd=tmp_path,
            extension_paths=(extension_dir,) if extension_dir is not None else (),
        )
    )


def _messages() -> tuple[UserMessage, ...]:
    return (UserMessage(content="old one"), UserMessage(content="old two"))


class _UnusedProvider:
    def stream_response(self, **kwargs):
        raise AssertionError("an extension summary must not call the provider")


async def test_extension_summary_is_used_without_calling_the_provider(tmp_path: Path) -> None:
    extension_dir = _write_extension(
        tmp_path,
        """
from baldric.runtime.platform import ExtensionAPI
from baldric.runtime.platform.api import CompactionSummaryResult, SessionBeforeCompactEvent


def setup(api: ExtensionAPI) -> None:
    def summarize(event, ctx):
        assert isinstance(event, SessionBeforeCompactEvent)
        return CompactionSummaryResult(summary="custom summary for " + event.reason)

    api.on("session_before_compact", summarize)
""",
    )
    session = await _open_session(tmp_path, _UnusedProvider(), extension_dir=extension_dir)
    try:
        generated = await session._generate_compaction_summary(_messages(), reason="threshold")

        assert generated.text == "custom summary for threshold"
        assert generated.usage is None
    finally:
        await session.aclose()


async def test_extension_summary_is_clamped(tmp_path: Path) -> None:
    extension_dir = _write_extension(
        tmp_path,
        """
from baldric.runtime.platform import ExtensionAPI
from baldric.runtime.platform.api import CompactionSummaryResult


def setup(api: ExtensionAPI) -> None:
    api.on("session_before_compact", lambda event, ctx: CompactionSummaryResult(summary="x" * 50_000))
""",
    )
    session = await _open_session(tmp_path, _UnusedProvider(), extension_dir=extension_dir)
    try:
        generated = await session._generate_compaction_summary(_messages())

        assert len(generated.text) == MAX_EXTENSION_COMPACTION_SUMMARY_CHARS
    finally:
        await session.aclose()


async def test_none_defers_to_the_builtin_summarizer(tmp_path: Path) -> None:
    extension_dir = _write_extension(
        tmp_path,
        """
from baldric.runtime.platform import ExtensionAPI


def setup(api: ExtensionAPI) -> None:
    api.on("session_before_compact", lambda event, ctx: None)
""",
    )
    provider = FakeProvider(
        [
            [
                assistant_start(),
                assistant_done(AssistantMessage(model="fake", content=[TextContent(text="builtin summary")])),
            ]
        ]
    )
    session = await _open_session(tmp_path, provider, extension_dir=extension_dir)
    try:
        generated = await session._generate_compaction_summary(_messages())

        assert generated.text == "builtin summary"
        assert provider.calls, "the built-in summarizer should have run"
    finally:
        await session.aclose()


async def test_empty_and_raising_handlers_fall_back(tmp_path: Path) -> None:
    extension_dir = _write_extension(
        tmp_path,
        """
from baldric.runtime.platform import ExtensionAPI
from baldric.runtime.platform.api import CompactionSummaryResult


def setup(api: ExtensionAPI) -> None:
    def empty(event, ctx):
        return CompactionSummaryResult(summary="   ")

    def boom(event, ctx):
        raise RuntimeError("kaboom")

    api.on("session_before_compact", empty)
    api.on("session_before_compact", boom)
""",
    )
    provider = FakeProvider(
        [
            [
                assistant_start(),
                assistant_done(AssistantMessage(model="fake", content=[TextContent(text="builtin summary")])),
            ]
        ]
    )
    session = await _open_session(tmp_path, provider, extension_dir=extension_dir)
    try:
        generated = await session._generate_compaction_summary(_messages())

        assert generated.text == "builtin summary"
        failures = [d for d in session.extension_runtime.diagnostics if "kaboom" in d.message]
        assert len(failures) == 1
    finally:
        await session.aclose()
