"""Command outcomes in print mode, and the exit code every print renderer shares.

Print mode used to consume a slash command's text message only: a command whose
outcome was a model/thinking change returned `handled=True` with no message, so
`/model gpt-5` printed nothing and exited 0 without changing anything. Commands
whose only outcome is a screen were equally silent. The renderers also disagreed
about what fails a run: `plain` reset on `aborted`, the other two ignored it, and
none of them failed a response truncated at the output-token limit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import baldric.runtime.session.session as coding_session_module
from baldric.agent.events import MessageEndEvent
from baldric.ai import FakeProvider
from baldric.protocol.messages import AssistantMessage
from baldric.runtime.cli import run_print_mode
from baldric.runtime.context.resources import BaldricResourcePaths
from baldric.runtime.providers.config import OpenAICompatibleProviderConfig, ProviderSettings
from baldric.runtime.rendering.json import JsonEventRenderer
from baldric.runtime.rendering.plain import FinalTextRenderer
from baldric.runtime.rendering.transcript import TranscriptRenderer


def _settings() -> ProviderSettings:
    return ProviderSettings(
        default_provider="fake-provider",
        providers=(
            OpenAICompatibleProviderConfig(
                name="fake-provider",
                models=("fake",),
                default_model="fake",
            ),
        ),
    )


class _ClosableProvider(FakeProvider):
    async def aclose(self) -> None:
        return None


async def _run(tmp_path: Path, prompt: str, monkeypatch: pytest.MonkeyPatch) -> tuple[bool, str]:
    settings = _settings()
    provider = _ClosableProvider([])
    rebuilt = _ClosableProvider([])

    def create_provider(provider_config: object, **_kwargs: object) -> _ClosableProvider:
        del provider_config
        return rebuilt

    monkeypatch.setattr(coding_session_module, "create_model_provider", create_provider)
    ok = await run_print_mode(
        prompt=prompt,
        model="fake",
        cwd=tmp_path,
        provider=provider,
        resource_paths=BaldricResourcePaths(root=tmp_path / "resources", agents_root=None),
        provider_name="fake-provider",
        provider_settings=settings,
        runtime_provider_config=settings.get_provider("fake-provider"),
    )
    return ok, ""


@pytest.mark.anyio
async def test_print_mode_applies_a_model_command_instead_of_exiting_silently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ok, _ = await _run(tmp_path, "/model fake", monkeypatch)

    captured = capsys.readouterr()
    assert ok is True
    assert "Current model: fake-provider:fake" in captured.out


@pytest.mark.anyio
async def test_print_mode_says_so_when_a_command_needs_the_tui(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ok, _ = await _run(tmp_path, "/tree", monkeypatch)

    captured = capsys.readouterr()
    assert ok is True
    assert "/tree is interactive-only in print mode." in captured.out


def _message_end(stop_reason: str) -> MessageEndEvent:
    return MessageEndEvent(
        message=AssistantMessage(content="partial", stop_reason=stop_reason)  # type: ignore[arg-type]
    )


@pytest.mark.parametrize("stop_reason", ["error", "aborted", "length"])
def test_every_print_renderer_fails_the_same_stop_reasons(stop_reason: str) -> None:
    renderers: list[object] = [FinalTextRenderer(), JsonEventRenderer(), TranscriptRenderer()]
    for renderer in renderers:
        renderer.render(_message_end(stop_reason))  # type: ignore[attr-defined]
        assert renderer.finish() is False, f"{type(renderer).__name__} did not fail on {stop_reason}"


def test_a_normal_stop_reason_passes_every_print_renderer() -> None:
    renderers: list[object] = [FinalTextRenderer(), JsonEventRenderer(), TranscriptRenderer()]
    for renderer in renderers:
        renderer.render(_message_end("stop"))  # type: ignore[attr-defined]
        assert renderer.finish() is True
