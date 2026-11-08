"""``refresh_system_prompt`` rebuilds the prompt from current registries."""

from __future__ import annotations

from pathlib import Path

import pytest

from baldric_agent import AssistantMessage
from baldric_ai import FakeProvider
from baldric_coding import CodingSession, CodingSessionConfig
from baldric_coding.session import JsonlSessionStorage
from tests.helpers.pi_event_helpers import assistant_done, assistant_start

pytestmark = pytest.mark.anyio


def anyio_backend() -> str:
    return "asyncio"


async def _run(session: CodingSession, text: str) -> None:
    _ = [event async for event in session.prompt(text)]


async def test_refresh_rebuilds_the_prompt_with_new_sections(tmp_path: Path) -> None:
    assistant = AssistantMessage(content="ok")
    provider = FakeProvider(
        [
            [assistant_start(), assistant_done(assistant)],
            [assistant_start(), assistant_done(assistant)],
        ]
    )
    session = await CodingSession.load(
        CodingSessionConfig(
            provider=provider,
            model="fake",
            storage=JsonlSessionStorage(tmp_path / "session.jsonl"),
            cwd=tmp_path,
        )
    )
    api = session._extension_runtime._extensions[-1].api  # noqa: SLF001 - test reaches the loaded API

    await _run(session, "Hi")

    api.add_prompt_section("MCP servers", "MCP-TEST-SECTION-BODY")
    session.refresh_system_prompt()

    await _run(session, "Again")

    assert "MCP-TEST-SECTION-BODY" not in provider.calls[0][1]
    assert "MCP-TEST-SECTION-BODY" in provider.calls[1][1]


async def test_refresh_is_a_no_op_for_explicit_system_prompts(tmp_path: Path) -> None:
    provider = FakeProvider([])
    session = await CodingSession.load(
        CodingSessionConfig(
            provider=provider,
            model="fake",
            system="EXPLICIT",
            storage=JsonlSessionStorage(tmp_path / "session.jsonl"),
            cwd=tmp_path,
        )
    )

    session.refresh_system_prompt()

    assert session._harness.config.system == "EXPLICIT"  # noqa: SLF001 - asserting the untouched prompt
