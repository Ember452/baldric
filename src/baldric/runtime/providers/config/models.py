"""Durable provider configuration for Baldric coding sessions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from baldric.ai.env import (
    DEFAULT_ANTHROPIC_BASE_URL,
    DEFAULT_OPENAI_COMPATIBLE_BASE_URL,
    DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES,
    DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS,
    DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS,
)
from baldric.ai.openai_codex import DEFAULT_OPENAI_CODEX_BASE_URL
from baldric.runtime.context.thinking import (
    ThinkingLevel,
    ThinkingParameter,
    normalize_thinking_level,
    normalize_thinking_levels,
)
from baldric.runtime.providers.catalog import (
    BUILTIN_PROVIDER_CATALOG,
    ModelCatalogMetadata,
    ModelCostTier,
    ProviderApi,
    ProviderCatalogEntry,
    ProviderKind,
)

DEFAULT_PROVIDER_NAME = "openai"
DEFAULT_MODEL = "gpt-5.4"
PROVIDER_SETTINGS_SCHEMA_VERSION = 2
# Hugging Face choices default to a fixed OpenRouter route so a newly selected
# model does not silently fall back to automatic routing.
DEFAULT_HUGGINGFACE_INFERENCE_PROVIDER = "openrouter"


class ProviderConfigError(ValueError):
    """Raised when Baldric provider configuration is invalid."""


class CredentialReader(Protocol):
    """Credential lookup used while building runtime provider config."""

    def get(self, name: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class ProviderModelMetadata:
    """Runtime metadata for one configured model."""

    name: str | None = None
    api: ProviderApi | None = None
    base_url: str | None = None
    reasoning: bool | None = None
    input: tuple[str, ...] = ()
    cost: dict[str, float] = field(default_factory=dict)
    cost_tiers: tuple[ModelCostTier, ...] = ()
    context_window: int | None = None
    max_tokens: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    compat: dict[str, Any] = field(default_factory=dict)
    thinking_level_map: dict[ThinkingLevel, str | None] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        """Serialize this model metadata to JSON-compatible data."""
        return {
            "name": self.name,
            "api": self.api,
            "base_url": self.base_url,
            "reasoning": self.reasoning,
            "input": list(self.input),
            "cost": dict(self.cost),
            "cost_tiers": [
                {
                    **(
                        {"max_input_tokens": tier.max_input_tokens}
                        if tier.max_input_tokens is not None
                        else {}
                    ),
                    **tier.cost,
                }
                for tier in self.cost_tiers
            ],
            "context_window": self.context_window,
            "max_tokens": self.max_tokens,
            "headers": dict(self.headers),
            "compat": dict(self.compat),
            "thinking_level_map": dict(self.thinking_level_map),
        }


@dataclass(frozen=True, slots=True)
class OpenAICompatibleProviderConfig:
    """Durable settings for one OpenAI-compatible provider."""

    name: str
    base_url: str = DEFAULT_OPENAI_COMPATIBLE_BASE_URL
    api: ProviderApi = "openai-completions"
    api_key_env: str = "OPENAI_API_KEY"
    credential_name: str | None = None
    models: tuple[str, ...] = (DEFAULT_MODEL,)
    default_model: str = DEFAULT_MODEL
    context_windows: dict[str, int] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    compat: dict[str, Any] = field(default_factory=dict)
    model_metadata: dict[str, ProviderModelMetadata] = field(default_factory=dict)
    timeout_seconds: float = DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES
    max_retry_delay_seconds: float = DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS
    thinking_levels: tuple[ThinkingLevel, ...] | None = None
    thinking_models: tuple[str, ...] = ()
    thinking_default: ThinkingLevel | None = None
    thinking_parameter: ThinkingParameter | None = None
    thinking_defaults: dict[str, ThinkingLevel] = field(default_factory=dict)
    inference_providers: dict[str, str] = field(default_factory=dict)
    default_inference_provider: str | None = None

    def __post_init__(self) -> None:
        _validate_provider_numbers(
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
            max_retry_delay_seconds=self.max_retry_delay_seconds,
        )
        _validate_context_windows(self.context_windows)
        _validate_model_metadata(self.models, self.model_metadata)
        _validate_json_object(self.compat, "Provider compat")
        _validate_thinking_config(
            thinking_levels=self.thinking_levels,
            thinking_models=self.thinking_models,
            thinking_default=self.thinking_default,
            thinking_parameter=self.thinking_parameter,
        )
        _validate_thinking_defaults(self.thinking_defaults)
        _validate_inference_providers(self.name, self.models, self.inference_providers)
        _validate_default_inference_provider(self.name, self.default_inference_provider)

    def to_json(self) -> dict[str, Any]:
        """Serialize this provider config to JSON-compatible data."""
        return {
            "name": self.name,
            "type": "openai-compatible",
            "base_url": self.base_url,
            "api": self.api,
            "api_key_env": self.api_key_env,
            "credential_name": self.credential_name,
            "models": list(self.models),
            "default_model": self.default_model,
            "context_windows": dict(self.context_windows),
            "headers": dict(self.headers),
            "compat": dict(self.compat),
            "model_metadata": {model: metadata.to_json() for model, metadata in self.model_metadata.items()},
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "max_retry_delay_seconds": self.max_retry_delay_seconds,
            "thinking_levels": (list(self.thinking_levels) if self.thinking_levels is not None else None),
            "thinking_models": list(self.thinking_models),
            "thinking_default": self.thinking_default,
            "thinking_parameter": self.thinking_parameter,
            "thinking_defaults": dict(self.thinking_defaults),
            "inference_providers": dict(self.inference_providers),
            "default_inference_provider": self.default_inference_provider,
        }


@dataclass(frozen=True, slots=True)
class AnthropicProviderConfig:
    """Durable settings for Anthropic's Messages API."""

    name: str = "anthropic"
    base_url: str = DEFAULT_ANTHROPIC_BASE_URL
    api: ProviderApi = "anthropic-messages"
    api_key_env: str = "ANTHROPIC_API_KEY"
    credential_name: str | None = "anthropic"
    models: tuple[str, ...] = ("claude-sonnet-4-6",)
    default_model: str = "claude-sonnet-4-6"
    context_windows: dict[str, int] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    compat: dict[str, Any] = field(default_factory=dict)
    model_metadata: dict[str, ProviderModelMetadata] = field(default_factory=dict)
    timeout_seconds: float = DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES
    max_retry_delay_seconds: float = DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS
    thinking_levels: tuple[ThinkingLevel, ...] | None = None
    thinking_models: tuple[str, ...] = ()
    thinking_default: ThinkingLevel | None = None
    thinking_parameter: ThinkingParameter | None = None
    thinking_defaults: dict[str, ThinkingLevel] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_provider_numbers(
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
            max_retry_delay_seconds=self.max_retry_delay_seconds,
        )
        _validate_context_windows(self.context_windows)
        _validate_model_metadata(self.models, self.model_metadata)
        _validate_json_object(self.compat, "Provider compat")
        _validate_thinking_config(
            thinking_levels=self.thinking_levels,
            thinking_models=self.thinking_models,
            thinking_default=self.thinking_default,
            thinking_parameter=self.thinking_parameter,
        )
        _validate_thinking_defaults(self.thinking_defaults)

    def to_json(self) -> dict[str, Any]:
        """Serialize this provider config to JSON-compatible data."""
        return {
            "name": self.name,
            "type": "anthropic",
            "base_url": self.base_url,
            "api": self.api,
            "api_key_env": self.api_key_env,
            "credential_name": self.credential_name,
            "models": list(self.models),
            "default_model": self.default_model,
            "context_windows": dict(self.context_windows),
            "headers": dict(self.headers),
            "compat": dict(self.compat),
            "model_metadata": {model: metadata.to_json() for model, metadata in self.model_metadata.items()},
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "max_retry_delay_seconds": self.max_retry_delay_seconds,
            "thinking_levels": (list(self.thinking_levels) if self.thinking_levels is not None else None),
            "thinking_models": list(self.thinking_models),
            "thinking_default": self.thinking_default,
            "thinking_parameter": self.thinking_parameter,
            "thinking_defaults": dict(self.thinking_defaults),
        }


@dataclass(frozen=True, slots=True)
class OpenAICodexProviderConfig:
    """Durable settings for OpenAI Codex subscription OAuth."""

    name: str = "openai-codex"
    base_url: str = DEFAULT_OPENAI_CODEX_BASE_URL
    api_key_env: str = "OPENAI_CODEX_ACCESS_TOKEN"
    credential_name: str | None = "openai-codex"
    models: tuple[str, ...] = (
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.3-codex",
        "gpt-5.3-codex-spark",
        "gpt-5.2",
    )
    default_model: str = "gpt-5.5"
    context_windows: dict[str, int] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    model_metadata: dict[str, ProviderModelMetadata] = field(default_factory=dict)
    timeout_seconds: float = DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES
    max_retry_delay_seconds: float = DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS
    thinking_levels: tuple[ThinkingLevel, ...] | None = None
    thinking_models: tuple[str, ...] = ()
    thinking_default: ThinkingLevel | None = None
    thinking_parameter: ThinkingParameter | None = None
    thinking_defaults: dict[str, ThinkingLevel] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_provider_numbers(
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
            max_retry_delay_seconds=self.max_retry_delay_seconds,
        )
        _validate_context_windows(self.context_windows)
        _validate_model_metadata(self.models, self.model_metadata)
        _validate_thinking_config(
            thinking_levels=self.thinking_levels,
            thinking_models=self.thinking_models,
            thinking_default=self.thinking_default,
            thinking_parameter=self.thinking_parameter,
        )
        _validate_thinking_defaults(self.thinking_defaults)

    def to_json(self) -> dict[str, Any]:
        """Serialize this provider config to JSON-compatible data."""
        return {
            "name": self.name,
            "type": "openai-codex",
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "credential_name": self.credential_name,
            "models": list(self.models),
            "default_model": self.default_model,
            "context_windows": dict(self.context_windows),
            "headers": dict(self.headers),
            "model_metadata": {model: metadata.to_json() for model, metadata in self.model_metadata.items()},
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "max_retry_delay_seconds": self.max_retry_delay_seconds,
            "thinking_levels": (list(self.thinking_levels) if self.thinking_levels is not None else None),
            "thinking_models": list(self.thinking_models),
            "thinking_default": self.thinking_default,
            "thinking_parameter": self.thinking_parameter,
            "thinking_defaults": dict(self.thinking_defaults),
        }


type ProviderConfig = OpenAICompatibleProviderConfig | AnthropicProviderConfig | OpenAICodexProviderConfig


@dataclass(frozen=True, slots=True)
class ScopedModelConfig:
    """A provider/model pair enabled for quick model cycling."""

    provider: str
    model: str

    def to_json(self) -> dict[str, str]:
        """Serialize this scoped model reference."""
        return {"provider": self.provider, "model": self.model}


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    """Baldric provider settings loaded from Baldric home."""

    default_provider: str = DEFAULT_PROVIDER_NAME
    providers: tuple[ProviderConfig, ...] = field(default_factory=lambda: builtin_provider_configs())
    scoped_models: tuple[ScopedModelConfig, ...] = ()

    def get_provider(self, name: str | None = None) -> ProviderConfig:
        """Return a configured provider by name."""
        target = name or self.default_provider
        for provider in self.providers:
            if provider.name == target:
                return provider
        raise ProviderConfigError(f"Unknown provider: {target}")

    def to_json(self) -> dict[str, Any]:
        """Serialize runtime preferences to JSON-compatible data."""
        return {
            "schema_version": PROVIDER_SETTINGS_SCHEMA_VERSION,
            "default_provider": self.default_provider,
            "provider_preferences": {
                provider.name: _provider_preference_to_json(provider) for provider in self.providers
            },
            "scoped_models": [model.to_json() for model in self.scoped_models],
        }


@dataclass(frozen=True, slots=True)
class ProviderSelection:
    """Resolved provider/model selection for a Baldric run."""

    provider: ProviderConfig
    model: str


def builtin_provider_configs() -> tuple[ProviderConfig, ...]:
    """Return Baldric's built-in provider configs."""
    return tuple(provider_config_from_catalog_entry(entry.name) for entry in BUILTIN_PROVIDER_CATALOG)


def provider_config_from_catalog_entry(name: str) -> ProviderConfig:
    """Create a durable provider config from a built-in catalog entry."""
    for entry in BUILTIN_PROVIDER_CATALOG:
        if entry.name == name:
            return provider_config_from_entry(entry)
    raise ProviderConfigError(f"Unknown built-in provider: {name}")


def provider_config_from_entry(entry: ProviderCatalogEntry) -> ProviderConfig:
    """Create a durable provider config from a catalog entry."""
    context_windows = dict(entry.context_windows or {})
    model_metadata = _provider_model_metadata_from_catalog(entry.model_metadata)
    if entry.kind == "anthropic":
        return AnthropicProviderConfig(
            name=entry.name,
            base_url=entry.base_url,
            api=_default_api_for_kind(entry.kind),
            api_key_env=entry.api_key_env,
            credential_name=entry.credential_name,
            models=entry.models,
            default_model=entry.default_model,
            context_windows=context_windows,
            headers=dict(entry.headers),
            compat=dict(entry.compat),
            model_metadata=model_metadata,
            thinking_levels=entry.thinking_levels,
            thinking_models=entry.thinking_models,
            thinking_default=entry.thinking_default,
            thinking_parameter=entry.thinking_parameter,
            thinking_defaults={},
        )
    if entry.kind == "openai-codex":
        return OpenAICodexProviderConfig(
            name=entry.name,
            base_url=entry.base_url,
            api_key_env=entry.api_key_env,
            credential_name=entry.credential_name,
            models=entry.models,
            default_model=entry.default_model,
            context_windows=context_windows,
            headers=dict(entry.headers),
            model_metadata=model_metadata,
            thinking_levels=entry.thinking_levels,
            thinking_models=entry.thinking_models,
            thinking_default=entry.thinking_default,
            thinking_parameter=entry.thinking_parameter,
            thinking_defaults={},
        )
    return OpenAICompatibleProviderConfig(
        name=entry.name,
        base_url=entry.base_url,
        api=entry.api or _default_api_for_kind(entry.kind),
        api_key_env=entry.api_key_env,
        credential_name=entry.credential_name,
        models=entry.models,
        default_model=entry.default_model,
        context_windows=context_windows,
        headers=dict(entry.headers),
        compat=dict(entry.compat),
        model_metadata=model_metadata,
        thinking_levels=entry.thinking_levels,
        thinking_models=entry.thinking_models,
        thinking_default=entry.thinking_default,
        thinking_parameter=entry.thinking_parameter,
        thinking_defaults={},
        default_inference_provider=(
            DEFAULT_HUGGINGFACE_INFERENCE_PROVIDER if entry.name == "huggingface" else None
        ),
    )


def _default_api_for_kind(kind: str) -> ProviderApi:
    if kind == "anthropic":
        return "anthropic-messages"
    if kind == "openai-codex":
        return "openai-codex-responses"
    if kind == "google-generative-ai":
        return "google-generative-ai"
    if kind == "mistral-conversations":
        return "mistral-conversations"
    return "openai-completions"


def _provider_model_metadata_from_catalog(
    model_metadata: dict[str, ModelCatalogMetadata],
) -> dict[str, ProviderModelMetadata]:
    return {
        model: ProviderModelMetadata(
            name=metadata.name,
            api=metadata.api,
            base_url=metadata.base_url,
            reasoning=metadata.reasoning,
            input=tuple(metadata.input),
            cost=dict(metadata.cost or {}),
            cost_tiers=metadata.cost_tiers,
            context_window=metadata.context_window,
            max_tokens=metadata.max_tokens,
            headers=dict(metadata.headers),
            compat=dict(metadata.compat),
            thinking_level_map=dict(metadata.thinking_level_map),
        )
        for model, metadata in model_metadata.items()
    }


def default_openai_provider_config() -> OpenAICompatibleProviderConfig:
    """Return Baldric's default OpenAI-compatible provider entry."""
    provider = provider_config_from_catalog_entry(DEFAULT_PROVIDER_NAME)
    if not isinstance(provider, OpenAICompatibleProviderConfig):
        raise AssertionError("default OpenAI provider must be OpenAI-compatible")
    return provider


def _provider_preference_to_json(provider: ProviderConfig) -> dict[str, Any]:
    """Serialize only runtime preferences for one provider."""
    preference = {
        "default_model": provider.default_model,
        "headers": dict(provider.headers),
        "timeout_seconds": provider.timeout_seconds,
        "max_retries": provider.max_retries,
        "max_retry_delay_seconds": provider.max_retry_delay_seconds,
        "thinking_defaults": dict(provider.thinking_defaults),
    }
    if isinstance(provider, OpenAICompatibleProviderConfig) and provider.inference_providers:
        preference["inference_providers"] = dict(provider.inference_providers)
    if (
        isinstance(provider, OpenAICompatibleProviderConfig)
        and provider.default_inference_provider is not None
    ):
        preference["default_inference_provider"] = provider.default_inference_provider
    return preference


def provider_kind(provider: ProviderConfig) -> ProviderKind:
    """Return the durable provider kind."""
    if isinstance(provider, AnthropicProviderConfig):
        return "anthropic"
    if isinstance(provider, OpenAICodexProviderConfig):
        return "openai-codex"
    if isinstance(provider, OpenAICompatibleProviderConfig):
        if provider.api == "google-generative-ai":
            return "google-generative-ai"
        if provider.api == "mistral-conversations":
            return "mistral-conversations"
    return "openai-compatible"


def _validate_provider_numbers(
    *,
    timeout_seconds: float,
    max_retries: int,
    max_retry_delay_seconds: float,
) -> None:
    if isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
        raise ProviderConfigError("Provider timeout_seconds must be greater than 0")
    if not isinstance(max_retries, int) or isinstance(max_retries, bool) or max_retries < 0:
        raise ProviderConfigError("Provider max_retries must be 0 or greater")
    if (
        not isinstance(max_retry_delay_seconds, int | float)
        or isinstance(max_retry_delay_seconds, bool)
        or max_retry_delay_seconds < 0
    ):
        raise ProviderConfigError("Provider max_retry_delay_seconds must be 0 or greater")


def _validate_context_windows(context_windows: dict[str, int]) -> None:
    for model, context_window in context_windows.items():
        if not isinstance(model, str) or not model.strip():
            raise ProviderConfigError("Provider context_windows keys must be non-empty strings")
        if not isinstance(context_window, int) or isinstance(context_window, bool) or context_window <= 0:
            raise ProviderConfigError("Provider context_windows values must be positive integers")


def _validate_model_metadata(
    models: tuple[str, ...],
    model_metadata: dict[str, ProviderModelMetadata],
) -> None:
    model_names = set(models)
    for model, metadata in model_metadata.items():
        if model not in model_names:
            raise ProviderConfigError(f"Provider model_metadata key is not in models: {model}")
        if metadata.context_window is not None and metadata.context_window <= 0:
            raise ProviderConfigError("Provider model_metadata context_window must be positive")
        if metadata.max_tokens is not None and metadata.max_tokens <= 0:
            raise ProviderConfigError("Provider model_metadata max_tokens must be positive")
        if any(item not in {"text", "image"} for item in metadata.input):
            raise ProviderConfigError("Provider model_metadata input must contain text or image")
        if any(value < 0 for value in metadata.cost.values()):
            raise ProviderConfigError("Provider model_metadata cost values must be non-negative")
        _validate_runtime_cost_tiers(metadata.cost_tiers)
        _validate_json_object(metadata.compat, "Provider model_metadata compat")
        _validate_string_dict(metadata.headers, "Provider model_metadata headers")
        for level, value in metadata.thinking_level_map.items():
            normalize_thinking_level(level)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ProviderConfigError(
                    "Provider model_metadata thinking_level_map values must be strings or null"
                )


def _validate_runtime_cost_tiers(tiers: tuple[ModelCostTier, ...]) -> None:
    if tiers and tiers[-1].max_input_tokens is not None:
        raise ProviderConfigError("Provider model_metadata final cost tier must omit max_input_tokens")
    previous_limit = 0
    for tier in tiers:
        if any(value < 0 for value in tier.cost.values()):
            raise ProviderConfigError("Provider model_metadata cost tier values must be non-negative")
        if tier.max_input_tokens is None:
            continue
        if tier.max_input_tokens <= previous_limit:
            raise ProviderConfigError("Provider model_metadata cost tier limits must be strictly increasing")
        previous_limit = tier.max_input_tokens


def _validate_string_dict(value: dict[str, str], field_name: str) -> None:
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ProviderConfigError(f"{field_name} keys must be non-empty strings")
        if not isinstance(item, str) or not item.strip():
            raise ProviderConfigError(f"{field_name} values must be non-empty strings")


def _validate_json_object(value: dict[str, Any], field_name: str) -> None:
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ProviderConfigError(f"{field_name} keys must be non-empty strings")
        _validate_json_value(item, f"{field_name}.{key}")


def _validate_json_value(value: object, field_name: str) -> None:
    if value is None or isinstance(value, str | int | float | bool):
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, field_name)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProviderConfigError(f"{field_name} object keys must be strings")
            _validate_json_value(item, f"{field_name}.{key}")
        return
    raise ProviderConfigError(f"{field_name} must be JSON-compatible")


def _reject_codex_legacy_compat(compat: dict[str, Any]) -> None:
    if compat:
        raise ProviderConfigError("OpenAI Codex legacy provider compat is not supported")


_HF_INFERENCE_PROVIDER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_huggingface_inference_provider(value: str) -> str:
    """Return a normalized explicit Hugging Face provider suffix."""
    normalized = value.strip()
    if not _HF_INFERENCE_PROVIDER_PATTERN.fullmatch(normalized):
        raise ProviderConfigError(
            "Hugging Face inference provider must contain only letters, numbers, '.', '_', or '-'"
        )
    if normalized in {"fastest", "cheapest", "preferred"}:
        raise ProviderConfigError(
            f"Hugging Face inference provider must be explicit, not routing policy: {normalized}"
        )
    return normalized


def _validate_inference_providers(
    provider_name: str,
    models: tuple[str, ...],
    inference_providers: dict[str, str],
) -> None:
    if inference_providers and provider_name != "huggingface":
        raise ProviderConfigError(
            "inference_providers preferences are only supported for the huggingface provider"
        )
    for model, route in inference_providers.items():
        if model not in models:
            raise ProviderConfigError(f"Inference-provider preference references unknown model: {model}")
        validate_huggingface_inference_provider(route)


def _validate_default_inference_provider(provider_name: str, default: str | None) -> None:
    if default is None:
        return
    if provider_name != "huggingface":
        raise ProviderConfigError("default_inference_provider is only supported for the huggingface provider")
    validate_huggingface_inference_provider(default)


def _validate_thinking_defaults(thinking_defaults: dict[str, ThinkingLevel]) -> None:
    for model, thinking_level in thinking_defaults.items():
        if not isinstance(model, str) or not model.strip():
            raise ProviderConfigError("Provider thinking_defaults keys must be non-empty strings")
        try:
            normalize_thinking_level(thinking_level)
        except ValueError as exc:
            raise ProviderConfigError(str(exc)) from exc


def _validate_thinking_config(
    *,
    thinking_levels: tuple[ThinkingLevel, ...] | None,
    thinking_models: tuple[str, ...],
    thinking_default: ThinkingLevel | None,
    thinking_parameter: ThinkingParameter | None,
) -> None:
    if thinking_levels is None:
        if thinking_models or thinking_default is not None or thinking_parameter is not None:
            raise ProviderConfigError("Provider thinking_levels must be set before thinking metadata")
        return
    try:
        normalized = normalize_thinking_levels(thinking_levels)
    except ValueError as exc:
        raise ProviderConfigError(str(exc)) from exc
    if normalized != thinking_levels:
        raise ProviderConfigError("Provider thinking_levels must be normalized")
    if any(not isinstance(model, str) or not model.strip() for model in thinking_models):
        raise ProviderConfigError("Provider thinking_models must contain non-empty strings")
    if thinking_default is not None and thinking_default not in thinking_levels:
        raise ProviderConfigError("Provider thinking_default must be in thinking_levels")
    if thinking_parameter not in {
        None,
        "reasoning_effort",
        "reasoning.effort",
        "anthropic.thinking",
    }:
        raise ProviderConfigError(
            "Provider thinking_parameter must be reasoning_effort, reasoning.effort, or anthropic.thinking"
        )


def _reject_unimplemented_thinking_config(
    *,
    provider_type: str,
    thinking_levels: tuple[ThinkingLevel, ...] | None,
) -> None:
    if thinking_levels is not None:
        raise ProviderConfigError(f"{provider_type} thinking controls are not implemented yet")
