"""Session replacement must carry every caller-supplied config field.

`resume()`/`new_session()` rebuild `CodingSessionConfig` by hand. A field that is
not copied is silently reset to its default, which is how a host that narrowed
the tool set through `tools=` got the full catalogue back after a resume.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import baldric_coding.session.session as coding_session_module
from baldric_agent.session import JsonlSessionStorage
from baldric_agent.tools import AgentTool
from baldric_coding.config.paths import BaldricPaths
from baldric_coding.providers.config import OpenAICompatibleProviderConfig, ProviderSettings
from baldric_coding.session.manager import SessionManager
from baldric_coding.session.session import CodingSession, CodingSessionConfig
from baldric_coding.tools.registry import create_coding_tools


class _Provider:
    """Minimal provider: resume only needs a closable object with a config."""

    def __init__(self, config: object) -> None:
        self.config = config

    async def aclose(self) -> None:
        return None


def _settings() -> ProviderSettings:
    return ProviderSettings(
        default_provider="openai",
        providers=(OpenAICompatibleProviderConfig(name="openai", models=("gpt-5",), default_model="gpt-5"),),
    )


async def _session_with_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, manager: SessionManager
) -> tuple[CodingSession, str, list[AgentTool]]:
    record = manager.create_session(cwd=tmp_path, model="gpt-5", provider_name="openai")
    settings = _settings()

    def create_provider(provider_config: object, **_kwargs: object) -> _Provider:
        return _Provider(provider_config)

    monkeypatch.setattr(coding_session_module, "create_model_provider", create_provider)
    tools = create_coding_tools(cwd=tmp_path)[:1]
    session = await CodingSession.load(
        CodingSessionConfig(
            provider=_Provider(settings.get_provider("openai")),
            owns_initial_provider=True,
            model="gpt-5",
            system="You are Baldric.",
            storage=JsonlSessionStorage(record.path),
            cwd=record.cwd,
            session_id=record.id,
            session_manager=manager,
            provider_name="openai",
            provider_settings=settings,
            runtime_provider_config=settings.get_provider("openai"),
            tools=tools,
        )
    )
    target = manager.create_session(cwd=tmp_path, model="gpt-5", provider_name="openai")
    return session, target.id, tools


@pytest.mark.anyio
async def test_resume_keeps_the_configured_tool_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = SessionManager(BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents"))
    session, target_id, tools = await _session_with_tools(tmp_path, monkeypatch, manager)
    try:
        await session.resume(target_id)

        assert session._config.tools is not None, "resume dropped the explicit tool set"
        assert [tool.name for tool in session._config.tools] == [tool.name for tool in tools]
        assert tools[0].name in [tool.name for tool in session.tools]
    finally:
        await session.aclose()


@pytest.mark.anyio
async def test_new_session_keeps_the_configured_tool_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = SessionManager(BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents"))
    session, _target_id, tools = await _session_with_tools(tmp_path, monkeypatch, manager)
    try:
        await session.new_session()

        assert session._config.tools is not None, "new_session dropped the explicit tool set"
        assert [tool.name for tool in session._config.tools] == [tool.name for tool in tools]
    finally:
        await session.aclose()
