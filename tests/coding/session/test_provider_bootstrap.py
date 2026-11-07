"""Provider bootstrap and the response-headers observer.

The print and RPC frontends build a provider before the session exists, so they
cannot pass `response_headers_observer` (it is a session method). They get away
with it because `load()` rebuilds the provider through the observer path. The
TUI also builds its provider first - to show a login prompt - but marks it as
owned, which used to skip that rebuild entirely, so Hugging Face sticky routing
and automatic failover never engaged in the one frontend most people use.

These tests pin the rebuild decision for all three cases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baldric_agent.session import JsonlSessionStorage
from baldric_ai import FakeProvider
from baldric_coding.session.session import CodingSession, CodingSessionConfig


class _ClosableFakeProvider(FakeProvider):
    """A frontend-built provider owns its socket, so the session closes it."""

    async def aclose(self) -> None:
        return None


def _config(tmp_path: Path, *, provider_name: str, owns_initial_provider: bool) -> CodingSessionConfig:
    return CodingSessionConfig(
        provider=_ClosableFakeProvider([]),
        model="fake",
        system="You are Baldric.",
        storage=JsonlSessionStorage(tmp_path / "session.jsonl"),
        cwd=tmp_path,
        provider_name=provider_name,
        owns_initial_provider=owns_initial_provider,
    )


@pytest.mark.anyio
async def test_owned_huggingface_provider_is_rebuilt_to_attach_the_observer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuilds: list[str] = []
    monkeypatch.setattr(
        CodingSession,
        "_refresh_runtime_provider",
        lambda self: rebuilds.append(self.provider_name),
    )

    session = await CodingSession.load(
        _config(tmp_path, provider_name="huggingface", owns_initial_provider=True)
    )
    try:
        assert rebuilds == ["huggingface"]
    finally:
        await session.aclose()


@pytest.mark.anyio
async def test_owned_provider_of_another_provider_keeps_what_the_frontend_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuilds: list[str] = []
    monkeypatch.setattr(
        CodingSession,
        "_refresh_runtime_provider",
        lambda self: rebuilds.append(self.provider_name),
    )

    session = await CodingSession.load(
        _config(tmp_path, provider_name="anthropic", owns_initial_provider=True)
    )
    try:
        assert rebuilds == []
    finally:
        await session.aclose()


@pytest.mark.anyio
async def test_unowned_provider_is_still_rebuilt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The print/RPC path must not regress while fixing the TUI path."""
    rebuilds: list[str] = []
    monkeypatch.setattr(
        CodingSession,
        "_refresh_runtime_provider",
        lambda self: rebuilds.append(self.provider_name),
    )

    session = await CodingSession.load(
        _config(tmp_path, provider_name="anthropic", owns_initial_provider=False)
    )
    try:
        assert rebuilds == ["anthropic"]
    finally:
        await session.aclose()
