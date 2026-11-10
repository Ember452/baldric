"""Hugging Face default inference-provider routing (provider-wide fallback)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from baldric.coding.config.paths import BaldricPaths
from baldric.coding.providers.config import (
    DEFAULT_HUGGINGFACE_INFERENCE_PROVIDER,
    OpenAICompatibleProviderConfig,
    ProviderConfigError,
    ProviderSettings,
    load_provider_settings,
    provider_settings_from_json,
    save_provider_settings,
)
from baldric.coding.session.provider_helpers import _configured_inference_provider


def _hf_provider(**overrides: object) -> OpenAICompatibleProviderConfig:
    defaults: dict[str, object] = {
        "name": "huggingface",
        "models": ("zai-org/GLM-5.2",),
        "default_model": "zai-org/GLM-5.2",
    }
    defaults.update(overrides)
    return OpenAICompatibleProviderConfig(**defaults)  # type: ignore[arg-type]


def _write_settings(
    home: Path,
    *,
    preference: dict[str, object] | None,
) -> None:
    baldric_home = home / ".baldric"
    baldric_home.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "schema_version": 2,
        "default_provider": "huggingface",
        "provider_preferences": {} if preference is None else {"huggingface": preference},
        "scoped_models": [],
    }
    (baldric_home / "providers.json").write_text(json.dumps(payload), encoding="utf-8")


def test_catalog_huggingface_defaults_to_fixed_openrouter_route() -> None:
    provider = load_provider_settings(BaldricPaths(home=Path("/nonexistent-baldric-home"))).get_provider(
        "huggingface"
    )
    assert isinstance(provider, OpenAICompatibleProviderConfig)
    assert provider.default_inference_provider == DEFAULT_HUGGINGFACE_INFERENCE_PROVIDER
    assert provider.inference_providers == {}


def test_non_huggingface_provider_cannot_set_default_route() -> None:
    with pytest.raises(ProviderConfigError, match="default_inference_provider is only supported"):
        OpenAICompatibleProviderConfig(
            name="openai",
            models=("gpt-5.4",),
            default_model="gpt-5.4",
            default_inference_provider="openrouter",
        )


def test_invalid_default_route_is_rejected() -> None:
    with pytest.raises(ProviderConfigError, match="must be explicit, not routing policy"):
        _hf_provider(default_inference_provider="fastest")
    with pytest.raises(ProviderConfigError, match="must contain only letters"):
        _hf_provider(default_inference_provider="not a provider")


def test_per_model_preference_wins_over_provider_default() -> None:
    provider = _hf_provider(
        inference_providers={"zai-org/GLM-5.2": "deepinfra"},
        default_inference_provider="openrouter",
    )
    assert _configured_inference_provider(provider, "zai-org/GLM-5.2") == "deepinfra"
    other = _hf_provider(
        models=("zai-org/GLM-5.2", "meta-llama/Llama-3"),
        default_model="zai-org/GLM-5.2",
        inference_providers={"zai-org/GLM-5.2": "deepinfra"},
        default_inference_provider="openrouter",
    )
    assert _configured_inference_provider(other, "meta-llama/Llama-3") == "openrouter"


def test_provider_default_used_without_per_model_preference() -> None:
    provider = _hf_provider(default_inference_provider="openrouter")
    assert _configured_inference_provider(provider, "zai-org/GLM-5.2") == "openrouter"


def test_explicit_null_preference_disables_default_route(tmp_path: Path) -> None:
    _write_settings(tmp_path, preference={"default_inference_provider": None})
    provider = load_provider_settings(BaldricPaths(home=tmp_path / ".baldric")).get_provider("huggingface")
    assert isinstance(provider, OpenAICompatibleProviderConfig)
    assert provider.default_inference_provider is None
    assert _configured_inference_provider(provider, "zai-org/GLM-5.2") is None


def test_preference_round_trips_and_survives_unrelated_save(tmp_path: Path) -> None:
    _write_settings(tmp_path, preference={"default_inference_provider": "openrouter"})
    home = BaldricPaths(home=tmp_path / ".baldric")
    loaded = load_provider_settings(home)
    provider = loaded.get_provider("huggingface")
    assert isinstance(provider, OpenAICompatibleProviderConfig)
    assert provider.default_inference_provider == "openrouter"

    saved = save_provider_settings(loaded, home)
    assert saved.exists()
    reloaded = load_provider_settings(home).get_provider("huggingface")
    assert isinstance(reloaded, OpenAICompatibleProviderConfig)
    assert reloaded.default_inference_provider == "openrouter"


def test_settings_without_key_keep_provider_default(tmp_path: Path) -> None:
    """A settings file that omits the key inherits the catalog default."""
    _write_settings(tmp_path, preference={"default_model": "zai-org/GLM-5.2"})
    provider = load_provider_settings(BaldricPaths(home=tmp_path / ".baldric")).get_provider("huggingface")
    assert isinstance(provider, OpenAICompatibleProviderConfig)
    assert provider.default_inference_provider == DEFAULT_HUGGINGFACE_INFERENCE_PROVIDER


def test_runtime_preference_parses_null_and_routes() -> None:
    settings = provider_settings_from_json(
        {
            "schema_version": 2,
            "default_provider": "huggingface",
            "provider_preferences": {
                "huggingface": {"default_inference_provider": None},
            },
            "scoped_models": [],
        }
    )
    hf = settings.get_provider("huggingface")
    assert isinstance(hf, OpenAICompatibleProviderConfig)
    assert hf.default_inference_provider is None

    settings = ProviderSettings(
        providers=(_hf_provider(default_inference_provider="openrouter"),),
        default_provider="huggingface",
    )
    hf = settings.get_provider("huggingface")
    assert isinstance(hf, OpenAICompatibleProviderConfig)
    assert _configured_inference_provider(hf, "zai-org/GLM-5.2") == "openrouter"
