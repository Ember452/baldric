"""Durable provider configuration for Baldric coding sessions."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from baldric_ai.env import (
    CACHE_RETENTION_LONG,
    CACHE_RETENTION_NONE,
    CACHE_RETENTION_SHORT,
    DEFAULT_ANTHROPIC_BASE_URL,
    DEFAULT_OPENAI_COMPATIBLE_BASE_URL,
    AnthropicConfig,
    CacheRetention,
    OpenAICompatibleConfig,
)
from baldric_coding.context.thinking import (
    DEFAULT_THINKING_LEVEL,
    THINKING_LEVELS,
    ThinkingLevel,
    anthropic_thinking_budget_for_level,
    normalize_thinking_level,
    reasoning_effort_for_level,
)
from baldric_coding.providers.catalog import (
    ProviderApi,
)
from baldric_coding.providers.config.credentials import _api_key_from_provider
from baldric_coding.providers.config.models import (
    DEFAULT_PROVIDER_NAME,
    AnthropicProviderConfig,
    CredentialReader,
    OpenAICodexProviderConfig,
    OpenAICompatibleProviderConfig,
    ProviderConfig,
    ProviderConfigError,
    ProviderModelMetadata,
    ProviderSelection,
    ProviderSettings,
)


def _provider_config_module() -> Any:
    import baldric_coding.providers.config as provider_config

    return provider_config


def resolve_provider_selection(
    settings: ProviderSettings,
    *,
    provider_name: str | None = None,
    model: str | None = None,
) -> ProviderSelection:
    """Resolve the provider and model for a run."""
    provider = settings.get_provider(provider_name)
    selected_model = model or provider.default_model
    if not selected_model:
        raise ProviderConfigError(f"Provider {provider.name} does not define a default model")
    validate_provider_model(provider, selected_model)
    return ProviderSelection(provider=provider, model=selected_model)


def validate_provider_model(provider: ProviderConfig, model: str) -> None:
    """Raise when ``model`` is not declared by ``provider``."""
    if model in provider.models:
        return
    available = ", ".join(sorted(provider.models)) or "none"
    raise ProviderConfigError(
        f"Model is not configured for provider {provider.name}: {model}. Available models: {available}"
    )


def provider_thinking_levels(
    provider: ProviderConfig,
    *,
    model: str | None = None,
) -> tuple[ThinkingLevel, ...]:
    """Return thinking levels supported by a provider/model pair."""
    selected_model = model or provider.default_model
    metadata = _metadata_for_model(provider, selected_model)
    if metadata is not None and metadata.reasoning is False:
        return ()
    if provider.thinking_levels is None:
        if metadata is None or metadata.reasoning is not True:
            return ()
        return _levels_from_thinking_map(metadata.thinking_level_map)
    if provider.thinking_models and selected_model not in provider.thinking_models:
        return ()
    return tuple(
        level
        for level in THINKING_LEVELS
        if (
            level in provider.thinking_levels
            or metadata is not None
            and metadata.thinking_level_map.get(level) is not None
        )
        and (metadata is None or _metadata_supports_thinking_level(metadata, level))
    )


def provider_thinking_unavailable_reason(
    provider: ProviderConfig,
    *,
    model: str | None = None,
) -> str | None:
    """Explain why a provider/model pair has no configurable thinking modes."""
    selected_model = model or provider.default_model
    metadata = _metadata_for_model(provider, selected_model)
    if metadata is not None and metadata.reasoning is False:
        return f"{provider.name}:{selected_model} is not a reasoning model"
    if provider.thinking_levels is None:
        if metadata is not None and metadata.reasoning is True:
            return None
        if isinstance(provider, OpenAICodexProviderConfig):
            return (
                "OpenAI Codex subscription can stream reasoning output, but Baldric does "
                "not have a validated Codex transport mapping for changing reasoning "
                "effort yet"
            )
        return f"Provider {provider.name} does not declare thinking_levels"
    if provider.thinking_models and selected_model not in provider.thinking_models:
        return f"{provider.name}:{selected_model} is not declared in thinking_models"
    return None


def _levels_from_thinking_map(
    thinking_level_map: dict[ThinkingLevel, str | None],
) -> tuple[ThinkingLevel, ...]:
    return tuple(
        level for level in THINKING_LEVELS if _thinking_level_map_supports(thinking_level_map, level)
    )


def _metadata_supports_thinking_level(
    metadata: ProviderModelMetadata,
    level: ThinkingLevel,
) -> bool:
    if metadata.reasoning is None and not metadata.thinking_level_map:
        return True
    return _thinking_level_map_supports(metadata.thinking_level_map, level)


def _thinking_level_map_supports(
    thinking_level_map: dict[ThinkingLevel, str | None],
    level: ThinkingLevel,
) -> bool:
    if level in thinking_level_map:
        return thinking_level_map[level] is not None
    return level not in {"xhigh", "max"}


def _metadata_for_model(provider: ProviderConfig, model: str) -> ProviderModelMetadata | None:
    return getattr(provider, "model_metadata", {}).get(model)


def _provider_api(provider: ProviderConfig, model: str | None = None) -> ProviderApi | str:
    selected_model = model or provider.default_model
    metadata = _metadata_for_model(provider, selected_model)
    if metadata is not None and metadata.api is not None:
        return metadata.api
    if isinstance(provider, OpenAICodexProviderConfig):
        return "openai-codex-responses"
    return getattr(provider, "api", "openai-completions")


def _model_base_url(provider: ProviderConfig, model: str | None = None) -> str:
    selected_model = model or provider.default_model
    metadata = _metadata_for_model(provider, selected_model)
    return metadata.base_url if metadata is not None and metadata.base_url else provider.base_url


def _model_headers(provider: ProviderConfig, model: str | None = None) -> dict[str, str]:
    selected_model = model or provider.default_model
    metadata = _metadata_for_model(provider, selected_model)
    return {**provider.headers, **(metadata.headers if metadata is not None else {})}


def _model_compat(provider: ProviderConfig, model: str | None = None) -> dict[str, Any]:
    selected_model = model or provider.default_model
    metadata = _metadata_for_model(provider, selected_model)
    return {
        **_detected_compat(provider, selected_model),
        **getattr(provider, "compat", {}),
        **(metadata.compat if metadata is not None else {}),
    }


def _detected_compat(provider: ProviderConfig, model: str) -> dict[str, Any]:
    base_url = _model_base_url(provider, model)
    is_together = provider.name == "together" or "api.together.ai" in base_url
    is_zai = provider.name == "zai" or "api.z.ai" in base_url
    is_moonshot = provider.name in {"moonshotai", "moonshotai-cn"} or "moonshot." in base_url
    is_grok = provider.name == "xai" or "api.x.ai" in base_url
    is_deepseek = provider.name == "deepseek" or "deepseek.com" in base_url
    is_cerebras = provider.name == "cerebras" or "cerebras.ai" in base_url
    is_openrouter = provider.name == "openrouter" or "openrouter.ai" in base_url
    is_openai_api = urlsplit(base_url).hostname == urlsplit(DEFAULT_OPENAI_COMPATIBLE_BASE_URL).hostname
    is_openai_responses = _provider_api(provider, model) == "openai-responses"
    is_nonstandard = is_cerebras or is_grok or is_together or is_deepseek or is_zai or is_moonshot
    use_max_tokens = is_moonshot or is_together
    is_anthropic_api = urlsplit(base_url).hostname == urlsplit(DEFAULT_ANTHROPIC_BASE_URL).hostname
    return {
        "supportsStore": not is_nonstandard,
        "supportsReasoningEffort": not (is_grok or is_zai or is_moonshot or is_together),
        "supportsUsageInStreaming": True,
        "maxTokensField": "max_tokens" if use_max_tokens else "max_completion_tokens",
        "thinkingFormat": (
            "deepseek"
            if is_deepseek
            else "zai"
            if is_zai
            else "together"
            if is_together
            else "openrouter"
            if is_openrouter
            else "openai"
        ),
        "supportsStrictMode": not (is_moonshot or is_together),
        "supportsLongCacheRetention": not is_together,
        # OpenAI's prompt-cache fields and affinity headers are not universally
        # accepted by compatible gateways. Default them on only for the official
        # endpoint; provider/model compat can opt another route in explicitly.
        "supportsPromptCacheKey": is_openai_api,
        "sendSessionAffinityHeaders": is_openai_api and is_openai_responses,
        "sessionAffinityFormat": "openrouter" if is_openrouter else "openai",
        # Only first-party Anthropic is known to accept cache_control. Several
        # catalog providers speak the Anthropic protocol through a gateway, and one
        # proxies to non-Anthropic models, so they default to no breakpoints. This
        # is a detected default, overridable per provider or per model.
        "supportsCacheControl": is_anthropic_api,
        "supportsCacheControlOnTools": True,
    }


def provider_model_max_tokens(provider: ProviderConfig, model: str | None = None) -> int | None:
    """Return the catalog output token limit for a model, or None when it is unset."""
    selected_model = model or provider.default_model
    metadata = _metadata_for_model(provider, selected_model)
    return metadata.max_tokens if metadata is not None else None


def provider_model_supports_images(provider: ProviderConfig, model: str | None = None) -> bool:
    selected_model = model or provider.default_model
    metadata = _metadata_for_model(provider, selected_model)
    return metadata is not None and "image" in metadata.input


def provider_default_thinking_level(
    provider: ProviderConfig,
    *,
    model: str | None = None,
) -> ThinkingLevel | None:
    """Return the preferred thinking level for a provider/model pair."""
    levels = provider_thinking_levels(provider, model=model)
    if not levels:
        return None
    if provider.thinking_default in levels:
        return provider.thinking_default
    if DEFAULT_THINKING_LEVEL in levels:
        return DEFAULT_THINKING_LEVEL
    return levels[0]


def resolve_startup_thinking_level(
    provider: ProviderConfig,
    model: str,
    *,
    preferred: ThinkingLevel = DEFAULT_THINKING_LEVEL,
    cli_override: ThinkingLevel | None = None,
) -> ThinkingLevel | None:
    """Pick a valid startup thinking level for a provider/model pair.

    Startup (TUI and print mode) must never crash just because the remembered
    default model does not support the global default level. The level is
    resolved with the same precedence used when switching models mid-session:
    the remembered per-model preference wins, then the global ``preferred``
    level, then the provider/catalog default, then the first available level.

    An explicit ``cli_override`` (from ``--thinking``) takes precedence over
    everything, and unlike the fallback chain it is strict: requesting a level
    the model does not support raises :class:`ProviderConfigError` instead of
    silently falling back.

    Returns ``None`` when the model has no configurable thinking levels.
    """
    levels = provider_thinking_levels(provider, model=model)
    if cli_override is not None:
        if not levels:
            raise ProviderConfigError(f"Thinking modes are unavailable for {provider.name}:{model}")
        if cli_override not in levels:
            allowed = ", ".join(levels)
            raise ProviderConfigError(
                f'Thinking mode "{cli_override}" is not available for '
                f"{provider.name}:{model}. Available modes: {allowed}"
            )
        return cli_override
    if not levels:
        return None
    remembered = provider.thinking_defaults.get(model)
    if remembered in levels:
        return remembered
    if preferred in levels:
        return preferred
    return provider_default_thinking_level(provider, model=model) or levels[0]


def openai_compatible_config_from_provider(
    provider: OpenAICompatibleProviderConfig,
    *,
    credential_reader: CredentialReader | None = None,
    model: str | None = None,
    thinking_level: ThinkingLevel | None = None,
) -> OpenAICompatibleConfig:
    """Build OpenAI-compatible runtime config from durable settings."""
    api_key = _api_key_from_provider(provider, credential_reader=credential_reader)
    selected_model = model or provider.default_model
    base_url = _model_base_url(provider, selected_model)
    if provider.name == DEFAULT_PROVIDER_NAME and provider.api_key_env == "OPENAI_API_KEY":
        base_url = _provider_config_module().environ.get("OPENAI_BASE_URL", base_url)
    reasoning_effort = _reasoning_effort_from_provider(
        provider,
        model=selected_model,
        thinking_level=thinking_level,
    )
    compat = _model_compat(provider, selected_model)
    return OpenAICompatibleConfig(
        api_key=api_key,
        provider_name=provider.name,
        api=str(_provider_api(provider, selected_model)),
        base_url=base_url.rstrip("/"),
        headers=_model_headers(provider, selected_model),
        timeout_seconds=provider.timeout_seconds,
        max_retries=provider.max_retries,
        max_retry_delay_seconds=provider.max_retry_delay_seconds,
        supports_images=provider_model_supports_images(provider, selected_model),
        reasoning_effort=reasoning_effort,
        reasoning_effort_parameter=provider.thinking_parameter or "reasoning_effort",
        thinking_format=_thinking_format(provider, selected_model),
        compat=compat,
        response_provider_header=("x-inference-provider" if provider.name == "huggingface" else None),
        include_reasoning_effort_none=_include_reasoning_effort_none(
            provider,
            model=selected_model,
            thinking_level=thinking_level,
        ),
    )


def anthropic_config_from_provider(
    provider: AnthropicProviderConfig,
    *,
    credential_reader: CredentialReader | None = None,
    model: str | None = None,
    thinking_level: ThinkingLevel | None = None,
) -> AnthropicConfig:
    """Build Anthropic runtime config from durable settings."""
    api_key = _api_key_from_provider(provider, credential_reader=credential_reader)
    selected_model = model or provider.default_model
    thinking_budget_tokens = _anthropic_thinking_budget_from_provider(
        provider,
        model=selected_model,
        thinking_level=thinking_level,
    )
    base_url = _normalize_anthropic_base_url(_model_base_url(provider, selected_model))
    cache_retention, cache_control_on_tools = anthropic_cache_settings(provider, selected_model)
    return AnthropicConfig(
        api_key=api_key,
        provider_name=provider.name,
        base_url=base_url,
        cache_retention=cache_retention,
        cache_control_on_tools=cache_control_on_tools,
        headers=_model_headers(provider, selected_model),
        timeout_seconds=provider.timeout_seconds,
        max_retries=provider.max_retries,
        max_retry_delay_seconds=provider.max_retry_delay_seconds,
        max_tokens=provider_model_max_tokens(provider, selected_model),
        supports_images=provider_model_supports_images(provider, selected_model),
        thinking_budget_tokens=thinking_budget_tokens,
        thinking_effort=_reasoning_effort_from_anthropic_provider(
            provider,
            model=selected_model,
            thinking_level=thinking_level,
        ),
        thinking_mode=_anthropic_thinking_mode(provider, selected_model, thinking_level=thinking_level),
    )


def _reasoning_effort_from_provider(
    provider: OpenAICompatibleProviderConfig,
    *,
    model: str | None,
    thinking_level: ThinkingLevel | None,
) -> str | None:
    if thinking_level is None or provider.thinking_parameter not in {
        "reasoning_effort",
        "reasoning.effort",
    }:
        return None

    levels = provider_thinking_levels(provider, model=model)
    if not levels:
        return None

    selected_model = model or provider.default_model
    normalized = normalize_thinking_level(thinking_level)
    if normalized not in levels:
        available = ", ".join(levels)
        raise ProviderConfigError(
            f"Thinking mode {normalized} is not available for "
            f"{provider.name}:{selected_model}. Available modes: {available}"
        )
    mapped = _metadata_thinking_value(provider, selected_model, normalized)
    if mapped is not None:
        return mapped
    if provider.name == "huggingface" and normalized == "minimal":
        # Hugging Face's router currently accepts low/medium/high/xhigh/max/none
        # for reasoning_effort, but rejects Pi/Baldric's "minimal" label.
        return "low"
    return reasoning_effort_for_level(normalized)


def _anthropic_thinking_budget_from_provider(
    provider: AnthropicProviderConfig,
    *,
    model: str | None,
    thinking_level: ThinkingLevel | None,
) -> int | None:
    if thinking_level is None or provider.thinking_parameter != "anthropic.thinking":
        return None

    selected_model = model or provider.default_model
    if _anthropic_thinking_mode(provider, selected_model) == "adaptive":
        return None

    levels = provider_thinking_levels(provider, model=selected_model)
    if not levels:
        return None

    normalized = normalize_thinking_level(thinking_level)
    if normalized not in levels:
        available = ", ".join(levels)
        raise ProviderConfigError(
            f"Thinking mode {normalized} is not available for "
            f"{provider.name}:{selected_model}. Available modes: {available}"
        )
    return anthropic_thinking_budget_for_level(normalized)


def _metadata_thinking_value(
    provider: ProviderConfig,
    model: str,
    level: ThinkingLevel,
) -> str | None:
    metadata = _metadata_for_model(provider, model)
    if metadata is None:
        return None
    value = metadata.thinking_level_map.get(level)
    return value if isinstance(value, str) else None


def _thinking_format(provider: ProviderConfig, model: str) -> str:
    compat = _model_compat(provider, model)
    value = compat.get("thinkingFormat")
    if isinstance(value, str) and value:
        return value
    base_url = _model_base_url(provider, model)
    if provider.name == "deepseek" or "deepseek.com" in base_url:
        return "deepseek"
    if provider.name == "zai" or "api.z.ai" in base_url:
        return "zai"
    if provider.name == "together" or "api.together.ai" in base_url:
        return "together"
    if provider.name == "openrouter" or "openrouter.ai" in base_url:
        return "openrouter"
    return "openai"


def _include_reasoning_effort_none(
    provider: ProviderConfig,
    *,
    model: str,
    thinking_level: ThinkingLevel | None,
) -> bool:
    if thinking_level is None:
        return False
    try:
        normalized = normalize_thinking_level(thinking_level)
    except ValueError:
        return False
    if normalized != "off":
        return False
    return _metadata_thinking_value(provider, model, "off") == "none"


def _reasoning_effort_from_anthropic_provider(
    provider: AnthropicProviderConfig,
    *,
    model: str,
    thinking_level: ThinkingLevel | None,
) -> str | None:
    if thinking_level is None:
        return None
    selected_model = model
    normalized = normalize_thinking_level(thinking_level)
    if normalized == "off":
        return None
    mapped = _metadata_thinking_value(provider, selected_model, normalized)
    return mapped or normalized


def _anthropic_thinking_mode(
    provider: AnthropicProviderConfig,
    model: str,
    *,
    thinking_level: ThinkingLevel | None = None,
) -> str:
    compat = _model_compat(provider, model)
    if compat.get("forceAdaptiveThinking") is True:
        if thinking_level is not None and normalize_thinking_level(thinking_level) == "off":
            return "disabled"
        return "adaptive"
    return "budget"


def _normalize_anthropic_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"


def anthropic_cache_settings(
    provider: ProviderConfig,
    model: str | None = None,
    *,
    oauth: bool = False,
) -> tuple[CacheRetention, bool]:
    """Resolve prompt-cache settings for one Anthropic-protocol request.

    Capability comes from compat, which layers a detected default under the
    provider's own compat and then per-model compat. Intent comes from the auth
    mode: subscription OAuth is not billed per token, so it asks for the 1 hour
    TTL, while an API key keeps the shorter default. Capability only ever narrows
    intent, so the two compose without any precedence rule.
    """
    compat = _model_compat(provider, model)
    if compat.get("supportsCacheControl") is False:
        return CACHE_RETENTION_NONE, False
    retention = CACHE_RETENTION_LONG if oauth else CACHE_RETENTION_SHORT
    if retention == CACHE_RETENTION_LONG and compat.get("supportsLongCacheRetention") is False:
        retention = CACHE_RETENTION_SHORT
    return retention, compat.get("supportsCacheControlOnTools") is not False
