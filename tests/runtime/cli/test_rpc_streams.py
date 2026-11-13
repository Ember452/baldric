"""RPC framing over real text streams rather than in-memory ``StringIO``.

``StringIO`` performs no newline translation and no code-page decoding, so the
regular RPC tests cannot see the two platform problems that matter for a byte
level peer: Windows text-mode stdout turns ``\\n`` into ``\\r\\n``, and Windows
stdin decodes through the system code page instead of UTF-8.

These tests wrap ``BytesIO`` in ``TextIOWrapper`` with the platform defaults
(``newline=None``, a non-UTF-8 encoding) to reproduce both behaviours.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from baldric.agent import AssistantMessage
from baldric.ai import FakeProvider
from baldric.runtime.frontends.rpc import RpcServer
from baldric.runtime.session import JsonlSessionStorage
from baldric.runtime.session.session import CodingSession, CodingSessionConfig
from tests.helpers.pi_event_helpers import assistant_done, assistant_start, text_delta


async def _session(tmp_path: Path, provider: FakeProvider) -> CodingSession:
    return await CodingSession.load(
        CodingSessionConfig(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            storage=JsonlSessionStorage(tmp_path / "session.jsonl"),
            cwd=tmp_path,
        )
    )


def _provider() -> FakeProvider:
    return FakeProvider(
        [
            [
                assistant_start(model="fake"),
                text_delta("ok"),
                assistant_done(AssistantMessage(content="ok", model="fake")),
            ]
        ]
    )


@pytest.mark.anyio
async def test_output_is_lf_framed_on_a_platform_translating_stream(tmp_path: Path) -> None:
    """stdout with newline=None would emit CRLF on Windows; RPC forces LF."""
    session = await _session(tmp_path, _provider())
    stdin = io.TextIOWrapper(
        io.BytesIO(b'{"id":"one","type":"prompt","message":"hi"}\n'),
        encoding="utf-8",
        newline=None,
    )
    raw = io.BytesIO()
    stdout = io.TextIOWrapper(raw, encoding="utf-8", newline=None)

    await RpcServer(session, stdin=stdin, stdout=stdout).run()
    stdout.flush()

    payload = raw.getvalue()
    assert b"\r" not in payload, "RPC records must be LF-delimited on every platform"
    records = [json.loads(line) for line in payload.decode("utf-8").split("\n") if line]
    assert records[0]["type"] == "response"
    assert records[0]["id"] == "one"


@pytest.mark.anyio
async def test_non_ascii_input_decodes_as_utf8_on_a_code_page_stream(tmp_path: Path) -> None:
    """A Windows stdin defaulting to a legacy code page must still read UTF-8."""
    session = await _session(tmp_path, _provider())
    request = json.dumps({"id": "one", "type": "prompt", "message": "你好"}, ensure_ascii=False)
    stdin = io.TextIOWrapper(
        io.BytesIO(request.encode("utf-8") + b"\n"),
        encoding="cp1252",
        newline=None,
    )
    stdout = io.StringIO()

    await RpcServer(session, stdin=stdin, stdout=stdout).run()

    records = [json.loads(line) for line in stdout.getvalue().split("\n") if line]
    assert records[0] == {"type": "response", "command": "prompt", "success": True, "id": "one"}


@pytest.mark.anyio
async def test_crlf_input_is_still_accepted(tmp_path: Path) -> None:
    """A CRLF peer must not produce an unparseable record."""
    session = await _session(tmp_path, _provider())
    stdin = io.TextIOWrapper(
        io.BytesIO(b'{"id":"one","type":"prompt","message":"hi"}\r\n'),
        encoding="utf-8",
        newline=None,
    )
    stdout = io.StringIO()

    await RpcServer(session, stdin=stdin, stdout=stdout).run()

    records = [json.loads(line) for line in stdout.getvalue().split("\n") if line]
    assert records[0]["id"] == "one"
    assert records[0]["success"] is True
