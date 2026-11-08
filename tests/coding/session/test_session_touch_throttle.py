"""Per-message index writes are throttled at the session layer, not in the manager.

`SessionManager.touch_session` always writes because `updated_at` is its ordering
contract (list order and "latest session" both depend on it). The per-message
caller is the one that must not pay a temp-file + fsync + replace for a timestamp
nobody asked about.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baldric_agent.session import InMemorySessionStorage
from baldric_ai import FakeProvider
from baldric_coding.config.paths import BaldricPaths
from baldric_coding.session import runtime as runtime_module
from baldric_coding.session.manager import CodingSessionRecord, SessionManager
from baldric_coding.session.session import CodingSession, CodingSessionConfig
from baldric_protocol.messages import AssistantMessage
from tests.helpers.pi_event_helpers import assistant_done, assistant_start


class _Provider(FakeProvider):
    async def aclose(self) -> None:
        return None


async def _session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CodingSession:
    manager = SessionManager(BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents"))
    record = manager.create_session(cwd=tmp_path, model="fake", provider_name="fake")
    session = await CodingSession.load(
        CodingSessionConfig(
            provider=_Provider([[assistant_start(), assistant_done(AssistantMessage(content="ok"))]]),
            model="fake",
            system="You are Baldric.",
            storage=InMemorySessionStorage(),
            cwd=tmp_path,
            provider_name="fake",
            session_id=record.id,
            session_manager=manager,
            extensions_enabled=False,
        )
    )
    return session


@pytest.mark.anyio
async def test_a_throttled_touch_writes_once_per_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = await _session(tmp_path, monkeypatch)
    calls: list[CodingSessionRecord | None] = []
    original = SessionManager.touch_session

    def counting(self: SessionManager, *args: object, **kwargs: object) -> CodingSessionRecord | None:
        calls.append(original(self, *args, **kwargs))  # type: ignore[arg-type]
        return calls[-1]

    monkeypatch.setattr(SessionManager, "touch_session", counting)
    try:
        for _ in range(3):
            runtime_module._touch_session_record(session, throttle=True)

        assert len(calls) == 1
    finally:
        await session.aclose()


@pytest.mark.anyio
async def test_a_metadata_change_is_written_immediately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = await _session(tmp_path, monkeypatch)
    calls: list[CodingSessionRecord | None] = []
    original = SessionManager.touch_session

    def counting(self: SessionManager, *args: object, **kwargs: object) -> CodingSessionRecord | None:
        calls.append(original(self, *args, **kwargs))  # type: ignore[arg-type]
        return calls[-1]

    monkeypatch.setattr(SessionManager, "touch_session", counting)
    try:
        runtime_module._touch_session_record(session, throttle=True)
        assert len(calls) == 1

        # The model setter writes the record itself, and the next throttled
        # touch sees a changed key, so neither waits for the interval.
        session.set_model("different-model")
        assert len(calls) == 2
        runtime_module._touch_session_record(session, throttle=True)
        assert len(calls) == 3

        assert session.session_manager is not None
        assert session.session_manager.get_session(session.session_id).model == "different-model"  # type: ignore[union-attr]
    finally:
        await session.aclose()


@pytest.mark.anyio
async def test_an_unthrottled_touch_always_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = await _session(tmp_path, monkeypatch)
    calls: list[CodingSessionRecord | None] = []
    original = SessionManager.touch_session

    def counting(self: SessionManager, *args: object, **kwargs: object) -> CodingSessionRecord | None:
        calls.append(original(self, *args, **kwargs))  # type: ignore[arg-type]
        return calls[-1]

    monkeypatch.setattr(SessionManager, "touch_session", counting)
    try:
        for _ in range(2):
            runtime_module._touch_session_record(session)

        assert len(calls) == 2
    finally:
        await session.aclose()
