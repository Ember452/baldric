"""Contract tests for the public API surface of ``baldric_ai`` and ``baldric_agent``.

Public API policy: the package-root ``__all__`` list is the supported surface;
submodule objects are implementation details and must not appear in ``__all__``.
The definitions must stay static list literals so an internal reorganisation
cannot silently change the exported names.

See ``dev-notes/architecture/public-api-policy.md``.
"""

from __future__ import annotations

import ast
import types
from pathlib import Path

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
    "openai_compatible_config_from_env",
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
    "message_text",
    "run_agent_loop",
)


def _assert_public_surface(package: types.ModuleType, expected: tuple[str, ...]) -> None:
    assert tuple(sorted(package.__all__)) == expected, f"{package.__name__}.__all__ changed"
    module_names = sorted(
        name for name in package.__all__ if isinstance(getattr(package, name), types.ModuleType)
    )
    assert module_names == [], f"{package.__name__} exports module objects: {module_names}"


def _assert_static_all_literal(relative_path: str) -> None:
    """Reject a regression back to a ``globals()``-derived ``__all__``."""
    path = Path(__file__).resolve().parents[1] / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and getattr(node.targets[0], "id", None) == "__all__"
    ]
    assert len(assignments) == 1, f"{relative_path}: expected exactly one __all__ assignment"
    value = assignments[0].value
    assert isinstance(value, ast.List), f"{relative_path}: __all__ must be a list literal"
    assert all(
        isinstance(element, ast.Constant) and isinstance(element.value, str) for element in value.elts
    ), f"{relative_path}: __all__ must contain only string literals"


def test_baldric_ai_public_api_is_frozen() -> None:
    """Pin the supported ``baldric_ai`` public symbols."""
    _assert_public_surface(baldric_ai, EXPECTED_BALDRIC_AI)
    _assert_static_all_literal("src/baldric_ai/__init__.py")


def test_baldric_agent_public_api_is_frozen() -> None:
    """Pin the supported ``baldric_agent`` public symbols."""
    _assert_public_surface(baldric_agent, EXPECTED_BALDRIC_AGENT)
    _assert_static_all_literal("src/baldric_agent/__init__.py")
