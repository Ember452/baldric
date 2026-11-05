"""Contract tests for the public API surface of ``baldric_ai`` and ``baldric_agent``.

Both portable packages currently derive ``__all__`` from ``globals()``, which
silently turns every public name bound during package initialisation — including
submodule objects — into exported API. This test pins the *current* surface so
any future internal reorganisation that changes the exported name set is caught
immediately.

Scope note: this first step records content only. The AST assertion that the
definition must be a static list literal lands together with the Step 2 change
that replaces the ``globals()`` comprehensions, so each step keeps this test
green.
"""

from __future__ import annotations

import types

import baldric_agent
import baldric_ai

EXPECTED_BALDRIC_AI = (
    "AnthropicConfig",
    "AnthropicProvider",
    "AssistantDoneEvent",
    "AssistantErrorEvent",
    "AssistantMessageEvent",
    "AssistantStartEvent",
    "CancellationToken",
    "DEFAULT_ANTHROPIC_BASE_URL",
    "DEFAULT_OPENAI_CODEX_BASE_URL",
    "DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES",
    "DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS",
    "DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS",
    "FakeProvider",
    "GoogleGenerativeAIProvider",
    "MistralConversationsProvider",
    "ModelCatalogProvider",
    "ModelLimitsProvider",
    "ModelProvider",
    "OpenAICodexConfig",
    "OpenAICodexCredentials",
    "OpenAICodexProvider",
    "OpenAICompatibleConfig",
    "OpenAICompatibleProvider",
    "RuntimeModel",
    "RuntimeModelCatalog",
    "RuntimeModelLimits",
    "RuntimeProviderAuth",
    "TextDeltaEvent",
    "TextEndEvent",
    "TextStartEvent",
    "ThinkingDeltaEvent",
    "ThinkingEndEvent",
    "ThinkingStartEvent",
    "ToolCallDeltaEvent",
    "ToolCallEndEvent",
    "ToolCallStartEvent",
    "anthropic",
    "content",
    "env",
    "events",
    "fake",
    "google",
    "http",
    "http_errors",
    "mistral",
    "model_catalog",
    "model_limits",
    "openai_cache",
    "openai_codex",
    "openai_compatible",
    "openai_compatible_config_from_env",
    "provider",
    "retry",
    "stream",
    "tool_call_ids",
)

MODULE_EXPORTS_BALDRIC_AI = (
    "anthropic",
    "content",
    "env",
    "events",
    "fake",
    "google",
    "http",
    "http_errors",
    "mistral",
    "model_catalog",
    "model_limits",
    "openai_cache",
    "openai_codex",
    "openai_compatible",
    "provider",
    "retry",
    "stream",
    "tool_call_ids",
)

EXPECTED_BALDRIC_AGENT = (
    "AgentEndEvent",
    "AgentEvent",
    "AgentHarness",
    "AgentHarnessConfig",
    "AgentMessage",
    "AgentStartEvent",
    "AgentTool",
    "AgentToolResult",
    "AssistantMessage",
    "BashExecutionMessage",
    "BranchSummaryEntry",
    "BranchSummaryMessage",
    "CompactionEntry",
    "CompactionSummaryMessage",
    "CustomEntry",
    "CustomMessage",
    "CustomMessageEntry",
    "EventListener",
    "ImageContent",
    "JSONObject",
    "JSONPrimitive",
    "JSONValue",
    "JsonlSessionStorage",
    "LabelEntry",
    "LeafEntry",
    "MessageEndEvent",
    "MessageEntry",
    "MessageStartEvent",
    "MessageUpdateEvent",
    "ModelChangeEntry",
    "QueuedMessages",
    "ResponseTiming",
    "SessionEntry",
    "SessionInfoEntry",
    "SessionState",
    "SimpleCancellationToken",
    "TextContent",
    "ThinkingContent",
    "ThinkingLevelChangeEntry",
    "ToolCall",
    "ToolCancellationToken",
    "ToolExecutionEndEvent",
    "ToolExecutionMode",
    "ToolExecutionStartEvent",
    "ToolExecutionUpdateEvent",
    "ToolExecutor",
    "ToolResultMessage",
    "ToolUpdateCallback",
    "TurnEndEvent",
    "TurnStartEvent",
    "Usage",
    "UsageCost",
    "UserMessage",
    "content_text",
    "events",
    "harness",
    "loop",
    "message_text",
    "messages",
    "provider",
    "provider_events",
    "run_agent_loop",
    "session",
    "tool_arguments",
    "tool_history",
    "tools",
    "types",
)

MODULE_EXPORTS_BALDRIC_AGENT = (
    "events",
    "harness",
    "loop",
    "messages",
    "provider",
    "provider_events",
    "session",
    "tool_arguments",
    "tool_history",
    "tools",
    "types",
)


def _assert_public_surface(
    package: types.ModuleType,
    expected: tuple[str, ...],
    module_exports: tuple[str, ...],
) -> None:
    assert tuple(sorted(package.__all__)) == expected, f"{package.__name__}.__all__ changed"
    actual_modules = tuple(
        sorted(name for name in expected if isinstance(getattr(package, name), types.ModuleType))
    )
    assert actual_modules == module_exports, f"{package.__name__} module exports changed"


def test_baldric_ai_public_api_is_frozen() -> None:
    """Pin ``baldric_ai.__all__`` before any internal directory reorganisation."""
    _assert_public_surface(baldric_ai, EXPECTED_BALDRIC_AI, MODULE_EXPORTS_BALDRIC_AI)


def test_baldric_agent_public_api_is_frozen() -> None:
    """Pin ``baldric_agent.__all__`` before any internal directory reorganisation."""
    _assert_public_surface(baldric_agent, EXPECTED_BALDRIC_AGENT, MODULE_EXPORTS_BALDRIC_AGENT)
