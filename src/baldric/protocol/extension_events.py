"""Extension event and hook payload shapes.

Pure dataclasses describing the payloads handed to extension hook handlers
(lifecycle events, provider seams, tool hooks, user-bash). Split out of
``baldric.protocol.extension`` to keep each protocol module under the 400-line
budget (the structural plan's ``protocol/`` shape rule). Like its sibling, this
module imports nothing from the runtime, agent, ai, or frontend layers.

``baldric.protocol.extension`` re-exports these names for the existing import
surface; the single source of truth for the classes is here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from baldric.protocol.messages import AgentMessage, ToolResultMessage
from baldric.protocol.tools import AgentTool, AgentToolResult
from baldric.protocol.types import JSONValue

SessionLifecycleReason = Literal["startup", "reload", "new", "resume", "branch", "quit"]
DeliverAs = Literal["steer", "follow_up"]
NotifyLevel = Literal["info", "warning", "error"]


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
    "CompactionSummaryResult",
    "DeliverAs",
    "InputEvent",
    "InputHookResult",
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
    "ToolResultHookEvent",
    "ToolResultHookResult",
    "TurnEndEvent",
    "TurnStartEvent",
    "UserBashEvent",
    "UserBashResult",
]
