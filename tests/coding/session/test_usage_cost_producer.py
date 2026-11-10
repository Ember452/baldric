"""`Usage.cost` gets a producer at the persistence boundary.

The field was declared, summed by `sum_usage`, and read by the stats and export
paths, but no adapter ever filled it: every response reported zero and every
consumer that trusted it saw zero. Pi fills it inside the adapter because its
model objects carry the rates; this project keeps pricing in the provider
catalog, so the durable message is the first place where response and rates meet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baldric.ai import FakeProvider
from baldric.coding.providers.config import (
    OpenAICompatibleProviderConfig,
    ProviderModelMetadata,
    ProviderSettings,
)
from baldric.coding.session import InMemorySessionStorage
from baldric.coding.session.session import CodingSession, CodingSessionConfig
from baldric.protocol.messages import AssistantMessage, Usage, UsageCost
from baldric.protocol.session import MessageEntry
from tests.helpers.pi_event_helpers import assistant_done, assistant_start


class _ClosableProvider(FakeProvider):
    async def aclose(self) -> None:
        return None


def _settings(**metadata: object) -> ProviderSettings:
    return ProviderSettings(
        default_provider="priced",
        providers=(
            OpenAICompatibleProviderConfig(
                name="priced",
                models=("m",),
                default_model="m",
                model_metadata={"m": ProviderModelMetadata(**metadata)},  # type: ignore[arg-type]
            ),
        ),
    )


async def _run(tmp_path: Path, settings: ProviderSettings, message: AssistantMessage) -> list[MessageEntry]:
    storage = InMemorySessionStorage()
    session = await CodingSession.load(
        CodingSessionConfig(
            provider=_ClosableProvider([[assistant_start(), assistant_done(message)]]),
            owns_initial_provider=True,
            model="m",
            system="You are Baldric.",
            storage=storage,
            cwd=tmp_path,
            provider_name="priced",
            provider_settings=settings,
            runtime_provider_config=settings.get_provider("priced"),
            extensions_enabled=False,
        )
    )
    try:
        _ = [event async for event in session.prompt("go")]
    finally:
        await session.aclose()
    return [entry for entry in storage.entries if isinstance(entry, MessageEntry)][-1:]


@pytest.mark.anyio
async def test_a_response_without_a_reported_cost_is_priced(tmp_path: Path) -> None:
    settings = _settings(cost={"input": 1.0, "output": 2.0})
    message = AssistantMessage(
        content="hi", model="m", provider="priced", usage=Usage(input=1_000, output=500)
    )

    entries = await _run(tmp_path, settings, message)

    usage = entries[0].message.usage  # type: ignore[attr-defined]
    assert usage.cost.total == pytest.approx(0.002)
    assert usage.cost.input == pytest.approx(0.001)
    assert usage.cost.output == pytest.approx(0.001)


@pytest.mark.anyio
async def test_a_provider_reported_cost_wins(tmp_path: Path) -> None:
    settings = _settings(cost={"input": 1.0, "output": 2.0})
    reported = UsageCost(input=9.0, output=9.0, total=18.0)
    message = AssistantMessage(
        content="hi",
        model="m",
        provider="priced",
        usage=Usage(input=1_000, output=500, cost=reported),
    )

    entries = await _run(tmp_path, settings, message)

    assert entries[0].message.usage.cost.total == pytest.approx(18.0)  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_an_unpriced_model_stays_unpriced(tmp_path: Path) -> None:
    settings = ProviderSettings(
        default_provider="priced",
        providers=(OpenAICompatibleProviderConfig(name="priced", models=("m",), default_model="m"),),
    )
    message = AssistantMessage(
        content="hi", model="m", provider="priced", usage=Usage(input=1_000, output=500)
    )

    entries = await _run(tmp_path, settings, message)

    assert entries[0].message.usage.cost.total == 0.0  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_a_response_without_usage_is_left_alone(tmp_path: Path) -> None:
    settings = _settings(cost={"input": 1.0, "output": 2.0})
    message = AssistantMessage(content="hi", model="m", provider="priced")

    entries = await _run(tmp_path, settings, message)

    assert entries[0].message.usage.cost.total == 0.0  # type: ignore[attr-defined]
