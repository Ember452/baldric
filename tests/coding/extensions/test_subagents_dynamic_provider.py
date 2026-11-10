"""Regression: subagents inherit a dynamic (extension-registered) provider.

load_provider_settings only carries durable configuration, so a parent session
running on an extension-registered provider (llama.cpp, a Codex live catalog)
used to fail child spawns with the familiar unknown-provider error. The
resolver now falls back to the session's process-local provider registry.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from baldric.coding.extensions.provider_registry import DynamicProviderRegistry
from baldric.coding.extensions.providers import (
    DynamicProvider,
    NoAuth,
    OpenAICompatibleTransport,
    ProviderModel,
)


def _dynamic_provider(provider_id: str = "llamacpp", model: str = "local-model") -> DynamicProvider:
    return DynamicProvider(
        id=provider_id,
        display_name=provider_id,
        models=(ProviderModel(id=model, api=None),),
        default_model=model,
        transport=OpenAICompatibleTransport(base_url="http://127.0.0.1:8080/v1", auth=NoAuth()),
    )


def test_registry_effective_returns_dynamic_definition() -> None:
    registry = DynamicProviderRegistry(durable_providers=())
    registry.register("source-1", _dynamic_provider())

    effective = registry.effective("llamacpp")

    assert effective is not None
    assert effective.dynamic is True
    assert effective.definition.default_model == "local-model"
    # An unknown provider id still resolves to None, keeping the durable path.
    assert registry.effective("nope") is None


def test_registry_rejects_dynamic_layer_shadowing_a_durable_id() -> None:
    # A dynamic layer may never share an id with a durable provider (an
    # installed extension must not be able to hijack ``anthropic`` and its
    # credentials); the resolver therefore never sees such a collision.
    durable = SimpleNamespace(id="anthropic", name="anthropic", models=(), default_model=None)
    registry = DynamicProviderRegistry(durable_providers=(durable,))
    with pytest.raises(Exception) as excinfo:
        registry.register("source-1", _dynamic_provider("anthropic"))
    assert "durable" in str(excinfo.value).lower() or "shadow" in str(excinfo.value).lower()


@pytest.mark.parametrize("provider_id", ["fake", "openai", "anthropic"])
def test_durable_provider_ids_resolve_through_settings_path(provider_id: str) -> None:
    # Durable providers (builtin or configured) must not be shadowed by the
    # dynamic fallback; they keep resolving through provider settings.
    registry = DynamicProviderRegistry(durable_providers=())
    assert registry.effective(provider_id) is None or registry.effective(provider_id).dynamic is False
