"""Provider and Pi-compatible model streaming layer for Baldric."""

# ruff: noqa: F401 - this module intentionally defines the public facade

from baldric_ai.anthropic import AnthropicProvider
from baldric_ai.env import (
    DEFAULT_ANTHROPIC_BASE_URL,
    DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES,
    DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS,
    DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS,
    AnthropicConfig,
    OpenAICompatibleConfig,
    RuntimeProviderAuth,
    openai_compatible_config_from_env,
)
from baldric_ai.events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantMessageEvent,
    AssistantStartEvent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
    ThinkingDeltaEvent,
    ThinkingEndEvent,
    ThinkingStartEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from baldric_ai.fake import FakeProvider
from baldric_ai.google import GoogleGenerativeAIProvider
from baldric_ai.mistral import MistralConversationsProvider
from baldric_ai.model_catalog import ModelCatalogProvider, RuntimeModel, RuntimeModelCatalog
from baldric_ai.model_limits import ModelLimitsProvider, RuntimeModelLimits
from baldric_ai.openai_codex import (
    DEFAULT_OPENAI_CODEX_BASE_URL,
    OpenAICodexConfig,
    OpenAICodexCredentials,
    OpenAICodexProvider,
)
from baldric_ai.openai_compatible import OpenAICompatibleProvider
from baldric_ai.provider import CancellationToken, ModelProvider

__all__ = [
    "content",
    "env",
    "events",
    "http",
    "http_errors",
    "provider",
    "retry",
    "stream",
    "tool_call_ids",
    "anthropic",
    "AnthropicProvider",
    "DEFAULT_ANTHROPIC_BASE_URL",
    "DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES",
    "DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS",
    "DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS",
    "AnthropicConfig",
    "OpenAICompatibleConfig",
    "RuntimeProviderAuth",
    "openai_compatible_config_from_env",
    "AssistantDoneEvent",
    "AssistantErrorEvent",
    "AssistantMessageEvent",
    "AssistantStartEvent",
    "TextDeltaEvent",
    "TextEndEvent",
    "TextStartEvent",
    "ThinkingDeltaEvent",
    "ThinkingEndEvent",
    "ThinkingStartEvent",
    "ToolCallDeltaEvent",
    "ToolCallEndEvent",
    "ToolCallStartEvent",
    "fake",
    "FakeProvider",
    "google",
    "GoogleGenerativeAIProvider",
    "mistral",
    "MistralConversationsProvider",
    "model_limits",
    "model_catalog",
    "ModelCatalogProvider",
    "RuntimeModel",
    "RuntimeModelCatalog",
    "ModelLimitsProvider",
    "RuntimeModelLimits",
    "openai_cache",
    "openai_codex",
    "DEFAULT_OPENAI_CODEX_BASE_URL",
    "OpenAICodexConfig",
    "OpenAICodexCredentials",
    "OpenAICodexProvider",
    "openai_compatible",
    "OpenAICompatibleProvider",
    "CancellationToken",
    "ModelProvider",
]
