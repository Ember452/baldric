"""Provider and Pi-compatible model streaming layer for Baldric."""

# this module intentionally defines the public facade

from baldric.ai.anthropic import AnthropicProvider
from baldric.ai.env import (
    DEFAULT_ANTHROPIC_BASE_URL,
    DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES,
    DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS,
    DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS,
    AnthropicConfig,
    OpenAICompatibleConfig,
    RuntimeProviderAuth,
    openai_compatible_config_from_env,
)
from baldric.ai.events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantMessageEvent,
    AssistantRetryEvent,
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
from baldric.ai.fake import FakeProvider
from baldric.ai.google import GoogleGenerativeAIProvider
from baldric.ai.mistral import MistralConversationsProvider
from baldric.ai.model_catalog import ModelCatalogProvider, RuntimeModel, RuntimeModelCatalog
from baldric.ai.model_limits import ModelLimitsProvider, RuntimeModelLimits
from baldric.ai.openai_codex import (
    DEFAULT_OPENAI_CODEX_BASE_URL,
    OpenAICodexConfig,
    OpenAICodexCredentials,
    OpenAICodexProvider,
)
from baldric.ai.openai_compatible import OpenAICompatibleProvider
from baldric.ai.provider import CancellationToken, ModelProvider

__all__ = [
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
    "AssistantRetryEvent",
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
    "FakeProvider",
    "GoogleGenerativeAIProvider",
    "MistralConversationsProvider",
    "ModelCatalogProvider",
    "RuntimeModel",
    "RuntimeModelCatalog",
    "ModelLimitsProvider",
    "RuntimeModelLimits",
    "DEFAULT_OPENAI_CODEX_BASE_URL",
    "OpenAICodexConfig",
    "OpenAICodexCredentials",
    "OpenAICodexProvider",
    "OpenAICompatibleProvider",
    "CancellationToken",
    "ModelProvider",
]
