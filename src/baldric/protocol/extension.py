"""Extension contract *shapes* — the parts every layer may depend on.

This module holds only pure shapes (dataclasses, Literal aliases, Callable type
aliases, and contract constants) that flow across the extension boundary. It
imports **nothing** from ``baldric.agent``, ``baldric.ai``, ``baldric.runtime``,
``textual``, or ``rich`` — enforcement lives in
``tests/guards/test_import_boundaries.py`` and a shape-only guard test. Keeping
the shapes here (instead of in the runtime extension package) means a feature,
frontend, or third-party extension can describe and receive these payloads
without pulling the runtime layer, and it prevents the protocol package from
silently growing behaviour as the project scales (see the structural plan,
``protocol/`` "shapes only" rule).

Behavioural classes — ``ExtensionAPI``, ``ExtensionContext``, ``ExtensionUi``,
``ExtensionSidebar``, ``ExtensionGeneration``, the UI bridges, and the
``UiBridge``/``ComponentBridge`` protocols that reference TUI types — stay in
``baldric.runtime.extensions.api``. Only what is pure shape lives here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from baldric.protocol.messages import AgentMessage, ToolResultMessage
from baldric.protocol.tools import AgentTool, AgentToolResult
from baldric.protocol.types import JSONValue

AGENT_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "agent_start",
        "agent_end",
        "agent_settled",
        "turn_start",
        "turn_end",
        "queue_update",
        "message_start",
        "message_update",
        "message_end",
        "tool_execution_start",
        "tool_execution_update",
        "tool_execution_end",
        "compaction_start",
        "compaction_end",
        "session_info_changed",
        "thinking_level_changed",
        "auto_retry_start",
        "auto_retry_end",
    }
)
AGENT_EVENT_WILDCARD = "agent_event"

# Version of the extension-facing contract. Baldric documents a third-party
# extension ecosystem, so the public API is explicitly versioned: an extension
# declares ``API_VERSION = EXTENSION_API_VERSION`` at module level and the loader
# refuses any other version instead of letting the extension break later against
# a changed runtime. Pi deliberately keeps no backward compatibility and
# therefore has no constant; Baldric's ecosystem promise is why this one exists.
#
# v2 added the provider seams, the entry/tool/markdown renderers, the dynamic
# tool handles (set_active_tools / execute_tool), and the lifecycle events
# (user_bash, model_select, thinking_level_select, session_before_compact).
EXTENSION_API_VERSION = 2

LIFECYCLE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "session_start",
        "session_shutdown",
        "input",
        "tool_call",
        "tool_result",
        "project_trust",
        "user_bash",
        "model_select",
        "thinking_level_select",
        "session_before_compact",
    }
)

# Extension-facing event names that map onto an existing canonical event type.
# Pi calls the thinking-level notification `thinking_level_select`; Baldric's
# canonical frontend event is `thinking_level_changed`, so subscribing with
# either name delivers the same event (no duplicate emission).
EVENT_NAME_ALIASES: Mapping[str, str] = {
    "thinking_level_select": "thinking_level_changed",
}

# Provider-level seams (plan Task A2). These mirror Pi's provider events and are
# bridged onto the AI-layer request hooks (RequestHooks / HookableProvider). They
# do NOT go through emit_event; ExtensionRuntime.build_provider_hooks() wires the
# registered handlers onto the provider during session creation.
# - context / context_with_system: chained transform of the outgoing messages/system.
# - before_provider_headers: in-place mutate of the outgoing HTTP headers.
# - before_provider_request: chained transform of the outgoing payload.
# - after_provider_response: read-only observe of status + headers.
# - provider_stream_event: read-only observe of each parsed stream event.
PROVIDER_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "context",
        "context_with_system",
        "before_provider_headers",
        "before_provider_request",
        "after_provider_response",
        "provider_stream_event",
    }
)

SessionLifecycleReason = Literal["startup", "reload", "new", "resume", "branch", "quit"]
DeliverAs = Literal["steer", "follow_up"]
NotifyLevel = Literal["info", "warning", "error"]


@dataclass(frozen=True, slots=True)
class ExtensionCapabilities:
    """Optional host surfaces an extension declares in its extension module.

    An extension declares ``CAPABILITIES = ExtensionCapabilities(...)`` next to
    its ``API_VERSION``. These are contract metadata (which surfaces the
    extension relies on), not a runtime permission system: the host uses them to
    describe compatibility and reviewers use them to see where an extension is
    coupled to the frontend. A missing declaration means
    :meth:`minimal` (nothing declared).

    ``components`` is the capability that makes Textual part of the extension's
    public contract: slot widgets, main views, and key interceptors carry
    ``textual.widget.Widget``/Textual event values. Extensions that only
    register tools, hooks, commands, providers, or plain-text UI never need
    Textual.

    v2 adds two domains for the new surfaces: ``provider_hooks`` (the
    provider-level seams) and ``renderers`` (entry/tool/markdown renderers).
    Like the other fields these describe reliance, not permission: the host
    never refuses a surface because a domain was not declared, because the
    contract promises an ecosystem, not a sandbox (see the note on
    ``EXTENSION_API_VERSION``).
    """

    ui: bool = False
    components: bool = False
    providers: bool = False
    tools: bool = False
    hooks: bool = False
    provider_hooks: bool = False
    renderers: bool = False

    def __post_init__(self) -> None:
        for name in (
            "ui",
            "components",
            "providers",
            "tools",
            "hooks",
            "provider_hooks",
            "renderers",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"Extension capability `{name}` must be a boolean")

    @classmethod
    def minimal(cls) -> ExtensionCapabilities:
        """Return the all-off declaration used when an extension omits it."""
        return cls()

    @property
    def requires_textual(self) -> bool:
        """Return whether this declaration pulls Textual into the contract."""
        return self.components


@dataclass(frozen=True, slots=True)
class CustomMessageView:
    """Read-only view of a custom message handed to a message renderer.

    Ports Pi's ``CustomMessage``: ``custom_type`` selects the renderer,
    ``content`` is the LLM-context text, and ``details`` carries arbitrary
    structured data the renderer formats.
    """

    custom_type: str
    content: str
    details: Mapping[str, JSONValue] | None = None


@dataclass(frozen=True, slots=True)
class MessageRenderOptions:
    """Options passed to a message renderer (ports Pi's ``MessageRenderOptions``)."""

    expanded: bool = False


# A message renderer returns a Rich-markup (or plain) string, NOT a Textual
# widget: message rendering stays frontend-data-only (deviation from Pi's
# ``Component`` return; see the phase-21 custom-renderer Ruling). Textual's
# ``Widget`` enters an extension's contract only through the ``components``
# capability (``ExtensionCapabilities.components``), never through renderers.
MessageRenderer = Callable[[CustomMessageView, MessageRenderOptions], str]

# Host-side resolver installed into render paths: given a custom message's
# fields and whether it is expanded, return rendered markup or ``None`` to fall
# back to the raw content. Errors are swallowed by the resolver, never raised
# into the frontend.
CustomMessageMarkup = Callable[[str, str, "Mapping[str, JSONValue] | None", bool], "str | None"]

# Host-side resolver installed into render paths: given a tool call's name and
# arguments, return the friendly invocation line from the tool's `render_call`
# or ``None`` to fall back to generic formatting. Errors are swallowed by the
# resolver, never raised into the frontend.
ToolCallMarkup = Callable[[str, "Mapping[str, JSONValue]"], "str | None"]

# Host-side resolver installed into render paths: given the tool name, its
# result, and whether the row is expanded, return the display markup from the tool's
# `render_result` or ``None`` to fall back to the generic result block. Errors
# are swallowed by the resolver, never raised into the frontend.
ToolResultMarkup = Callable[[str, AgentToolResult, bool], "str | None"]

# --- extension renderers (plan Task D) ---------------------------------------


@dataclass(frozen=True, slots=True)
class CustomEntryView:
    """Read-only view of a custom entry handed to an entry renderer.

    Ports Pi's ``registerEntryRenderer``: the entry was created with
    ``append_entry(namespace, data)``; ``namespace`` selects the renderer and
    ``data`` is the stored payload. Rendered to Rich-markup text, never a Textual
    widget (same deviation as message renderers — keeps extensions TUI-free).
    """

    namespace: str
    data: Mapping[str, JSONValue]


# An entry renderer returns Rich-markup (or plain) text for one custom entry.
type EntryRenderer = Callable[[CustomEntryView, MessageRenderOptions], str]

# A tool-call render resolver: Pi's ``registerToolRenderer`` shape. Receives the
# tool name and ``next_call`` — which returns whatever lower-priority resolvers
# and the tool's own ``render_call`` would produce (or None). Return None to
# defer to ``next_call``; return a string to take over. Errors are swallowed.
type ToolCallResolver = Callable[[str, "Callable[[], str | None]"], "str | None"]
# A tool-result render resolver: same shape for the result end of the row.
type ToolResultResolver = Callable[[str, AgentToolResult, bool, "Callable[[], str | None]"], "str | None"]

# A markdown transformer: chained, display-only, runs on ``message_type`` surfaces.
# Receives the markdown and the surface it is rendering for; returns the
# (possibly rewritten) markdown. Pi's ``registerMarkdownTransformer``.
type MarkdownTransformer = Callable[[str, "MarkdownRenderContext"], str]


@dataclass(frozen=True, slots=True)
class MarkdownRenderContext:
    """Context handed to a markdown transformer (ports Pi's transformer context)."""

    message_type: str
    is_streaming: bool = False
    available_width: int | None = None


@dataclass(frozen=True, slots=True)
class TurnStartEvent:
    """Pi-shaped extension event fired at the start of a turn.

    The portable agent event intentionally has no session metadata. The coding
    session adapter adds the zero-based turn index and millisecond timestamp
    before dispatching the event to extensions.
    """

    turn_index: int
    timestamp: int
    type: Literal["turn_start"] = field(default="turn_start", init=False)


@dataclass(frozen=True, slots=True)
class TurnEndEvent:
    """Pi-shaped extension event fired after one assistant/tool turn."""

    turn_index: int
    message: AgentMessage
    tool_results: list[ToolResultMessage]
    type: Literal["turn_end"] = field(default="turn_end", init=False)


@dataclass(frozen=True, slots=True)
class SessionStartEvent:
    """Payload for the `session_start` lifecycle event."""

    reason: SessionLifecycleReason


@dataclass(frozen=True, slots=True)
class SessionShutdownEvent:
    """Payload for the `session_shutdown` lifecycle event."""

    reason: SessionLifecycleReason


@dataclass(frozen=True, slots=True)
class InputEvent:
    """Payload for the `input` hook: raw user prompt text, before expansion.

    Mirrors Pi's `InputEvent`. `source` says where the input came from:
    ``"interactive"`` for TUI/print-mode user input, ``"extension"`` for a turn
    an extension started via ``send_user_message``/``send_custom_message``.
    `streaming_behavior` says how the input will be queued when the agent is
    mid-run (``"steer"``/``"follow_up"``), and is ``None`` on the idle prompt
    path.

    Pi's `images` field is omitted (Baldric has no image input yet) and Pi's
    ``"rpc"`` source is omitted (Baldric has no RPC mode). Both defaults keep
    existing handlers that read only ``.text`` working unchanged.
    """

    text: str
    source: Literal["interactive", "extension"] = "interactive"
    streaming_behavior: Literal["steer", "follow_up"] | None = None


@dataclass(frozen=True, slots=True)
class InputHookResult:
    """Result of an `input` hook handler.

    `action="continue"` leaves the text unchanged, `"transform"` replaces it
    with `text` (transforms chain across handlers), and `"handled"` consumes
    the input entirely, optionally showing `message` to the user.
    """

    action: Literal["continue", "transform", "handled"] = "continue"
    text: str | None = None
    message: str | None = None


# --- provider seam events (plan Task A2) --------------------------------------
# Payloads handed to handlers registered via ``on("<provider_event>")``. Each is
# bridged onto the AI-layer RequestHooks by ExtensionRuntime.build_provider_hooks.


@dataclass(frozen=True, slots=True)
class ProviderContextEvent:
    """Payload for ``context`` / ``context_with_system`` (chained transform).

    Return a replacement :class:`ProviderContextEvent` to change the outgoing
    request; return ``None`` to keep the previous handler's value.
    """

    model: str
    system: str
    messages: tuple[AgentMessage, ...]
    tools: tuple[AgentTool, ...]


@dataclass(frozen=True, slots=True)
class ProviderHeadersEvent:
    """Payload for ``before_provider_headers`` (in-place mutate).

    ``headers`` is the live dict the adapter is about to send; mutate it in place.
    """

    model: str
    headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class ProviderRequestEvent:
    """Payload for ``before_provider_request`` (chained payload transform).

    ``payload`` is the live request body dict; return a replacement dict to
    swap it (Pi's ``onPayload``), or ``None`` to keep it.
    """

    model: str
    payload: dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class ProviderResponseEvent:
    """Payload for ``after_provider_response`` (read-only observe)."""

    model: str
    status: int
    headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class ProviderStreamEvent:
    """Payload for ``provider_stream_event`` (read-only observe of one event)."""

    model: str
    event: object


@dataclass(frozen=True, slots=True)
class UserBashEvent:
    """Payload for the ``user_bash`` hook (a ``!``/``!!`` command, ports Pi).

    ``exclude_from_context`` is True for ``!!`` (output is not added to the
    model context). A handler may return a :class:`UserBashResult` to answer the
    command itself; returning ``None`` continues to the next handler, then the
    local shell.
    """

    command: str
    cwd: Path
    exclude_from_context: bool = False


@dataclass(frozen=True, slots=True)
class UserBashResult:
    """A completed ``user_bash`` command supplied by an extension.

    Returning this records the command as if it had run (no local execution).
    ``cancelled`` lets an extension report an aborted remote run.
    """

    output: str = ""
    exit_code: int | None = None
    cancelled: bool = False


@dataclass(frozen=True, slots=True)
class SessionBeforeCompactEvent:
    """Payload for ``session_before_compact`` (Pi's event, summary half only).

    Baldric does not expose veto power here: a handler may return a
    :class:`CompactionSummaryResult` to supply the summary, and returning
    ``None`` keeps the built-in summarizer. Compaction must always succeed, so a
    ``block``-style result is not part of this contract (see hook-composition.md).
    """

    reason: str
    messages: tuple[AgentMessage, ...]


@dataclass(frozen=True, slots=True)
class CompactionSummaryResult:
    """A replacement compaction summary produced by an extension."""

    summary: str


@dataclass(frozen=True, slots=True)
class ToolCallHookEvent:
    """Payload for the `tool_call` hook, before a tool executes.

    Carries no tool-call id: the hook runs inside the tool executor seam,
    which the agent loop invokes without the id. Use the observation events
    (`tool_execution_start`/`tool_execution_end`) for id correlation.
    """

    tool_name: str
    arguments: Mapping[str, JSONValue]


@dataclass(frozen=True, slots=True)
class ToolCallHookResult:
    """Result of a `tool_call` hook handler.

    Set `block=True` (with an optional `reason`) to prevent execution, or
    return replacement `arguments` to rewrite the call. Blocking wins over
    argument rewrites and short-circuits remaining handlers.
    """

    block: bool = False
    reason: str | None = None
    arguments: Mapping[str, JSONValue] | None = None


@dataclass(frozen=True, slots=True)
class ToolResultHookEvent:
    """Payload for the `tool_result` hook, after a tool executes."""

    tool_name: str
    arguments: Mapping[str, JSONValue]
    result: AgentToolResult


@dataclass(frozen=True, slots=True)
class ToolResultHookResult:
    """Result of a `tool_result` hook handler; set fields to override."""

    content: str | None = None
    details: dict[str, JSONValue] | None = None


__all__ = [
    "AGENT_EVENT_TYPES",
    "AGENT_EVENT_WILDCARD",
    "EXTENSION_API_VERSION",
    "EVENT_NAME_ALIASES",
    "LIFECYCLE_EVENT_TYPES",
    "PROVIDER_EVENT_TYPES",
    "CompactionSummaryResult",
    "CustomEntryView",
    "CustomMessageMarkup",
    "CustomMessageView",
    "DeliverAs",
    "EntryRenderer",
    "ExtensionCapabilities",
    "InputEvent",
    "InputHookResult",
    "MarkdownRenderContext",
    "MarkdownTransformer",
    "MessageRenderOptions",
    "MessageRenderer",
    "NotifyLevel",
    "ProviderContextEvent",
    "ProviderHeadersEvent",
    "ProviderRequestEvent",
    "ProviderResponseEvent",
    "ProviderStreamEvent",
    "SessionBeforeCompactEvent",
    "SessionLifecycleReason",
    "SessionShutdownEvent",
    "SessionStartEvent",
    "ToolCallHookEvent",
    "ToolCallHookResult",
    "ToolCallMarkup",
    "ToolCallResolver",
    "ToolResultHookEvent",
    "ToolResultHookResult",
    "ToolResultMarkup",
    "ToolResultResolver",
    "TurnEndEvent",
    "TurnStartEvent",
    "UserBashEvent",
    "UserBashResult",
]
