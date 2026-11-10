"""The persist hot path must not re-read the transcript per message."""

from __future__ import annotations

from pathlib import Path

import pytest

from baldric.ai import FakeProvider
from baldric.coding.session import InMemorySessionStorage
from baldric.coding.session.session import CodingSession, CodingSessionConfig
from baldric.protocol.messages import AssistantMessage
from tests.helpers.pi_event_helpers import assistant_done, assistant_start


class _CountingStorage(InMemorySessionStorage):
    def __init__(self) -> None:
        super().__init__()
        self.reads = 0

    async def read_all(self) -> list[object]:  # type: ignore[override]
        self.reads += 1
        return await super().read_all()


class _ClosableProvider(FakeProvider):
    async def aclose(self) -> None:
        return None


def _one_turn() -> list[object]:
    return [assistant_start(), assistant_done(AssistantMessage(content="ok"))]


@pytest.mark.anyio
async def test_persisting_messages_does_not_reread_the_transcript(tmp_path: Path) -> None:
    storage = _CountingStorage()
    provider = _ClosableProvider([_one_turn(), _one_turn(), _one_turn()])
    session = await CodingSession.load(
        CodingSessionConfig(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            storage=storage,  # type: ignore[arg-type]
            cwd=tmp_path,
            provider_name="fake",
            resource_paths=None,
            extensions_enabled=False,
        )
    )
    try:
        after_load = storage.reads
        for index in range(3):
            _ = [event async for event in session.prompt(f"message {index}")]
        assert storage.reads == after_load + 1, (
            "persisting messages re-read the transcript; the hot path regressed to O(n^2). "
            "Exactly one read is expected: the first-append initialization check."
        )
        assert len(session.messages) == 6
    finally:
        await session.aclose()
