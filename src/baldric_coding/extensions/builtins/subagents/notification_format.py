"""Pure formatting of subagent runs for model text and TUI cards.

These are the notification/rendering helpers split out of ``extension.py`` so the
712-line ``SubagentManager`` and 625-line ``setup`` in that module are not also
where the string formatting lives. Every function here is pure: it takes an
``AgentRun`` (or arguments mapping) and returns a string or dict, touching no
manager state. ``AgentRun`` is imported for typing only, so this module has no
runtime dependency on ``extension.py`` (no import cycle).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from baldric_coding.extensions import CustomMessageView, MessageRenderOptions
from baldric_protocol.types import JSONValue

from .notification_render import render_notification, stat_parts

if TYPE_CHECKING:
    from .extension import AgentRun

INDIVIDUAL_RESULT_CHARS = 500
GROUP_RESULT_CHARS = 300
STEER_CALL_PREVIEW_CHARS = 60
COMPLETION_NOTICE = (
    "This is an automated subagent completion notice, not a user message. "
    "Use the result to continue the original task."
)


def format_background_spawn(run: AgentRun, max_concurrent: int) -> str:
    """Format the tool result for a background spawn (started or queued)."""
    started = run.status != "queued"
    lines = [
        "Agent started in background." if started else "Agent queued in background.",
        f"Agent ID: {run.agent_id}",
        f"Type: {run.agent_type}",
        f"Description: {run.description}",
    ]
    if run.output_file:
        lines.append(f"Output file: {run.output_file}")
    if not started:
        lines.append(f"Position: queued (max {max_concurrent} concurrent)")
    lines.extend(
        [
            "",
            "You will be notified when this agent completes.",
            "Use get_subagent_result to retrieve full results, or steer_subagent to send it messages.",
            "Do not duplicate this agent's work.",
        ]
    )
    return "\n".join(lines)


def format_task_notification(run: AgentRun, max_result_chars: int = INDIVIDUAL_RESULT_CHARS) -> str:
    """Format one run's completion as a minimal <task-notification> block.

    Deliberately minimal: turns and usage stats are omitted (the
    get_subagent_result header repeats them, and the TUI card renders them
    from `details`, outside the model's context). The result is fit-or-fetch:
    included whole when it fits `max_result_chars`, otherwise replaced by a
    pointer to get_subagent_result — never truncated.
    """
    body = run.error if run.status == "error" else run.result_text
    body = body or "(no output)"
    if len(body) <= max_result_chars:
        result_line = f"<result>{body}</result>\n"
    else:
        result_line = (
            f"<result-pending>Result is {len(body)} chars. Call "
            f'get_subagent_result("{run.agent_id}") to read it before acting.'
            "</result-pending>\n"
        )
    output_line = f"<output-file>{run.output_file}</output-file>\n" if run.output_file else ""
    return (
        "<task-notification>\n"
        f"<agent-id>{run.agent_id}</agent-id>\n"
        f"<description>{run.description}</description>\n"
        f"{output_line}"
        f"<status>{run.status}</status>\n"
        f"{result_line}"
        "</task-notification>"
    )


def build_notification_details(
    run: AgentRun, result_max_chars: int = INDIVIDUAL_RESULT_CHARS
) -> dict[str, JSONValue]:
    """Structured details for the custom renderer (pi's buildNotificationDetails)."""
    body = run.error if run.status == "error" else run.result_text
    preview = body or "No output."
    if len(preview) > result_max_chars:
        preview = preview[:result_max_chars] + "…"
    return {
        "description": run.description,
        "status": run.status,
        "turn_count": run.turns,
        "max_turns": run.max_turns,
        "tool_uses": run.tool_calls,
        "total_tokens": lifetime_tokens(run) if run.has_usage else 0,
        "duration_ms": _duration_ms(run) or 0,
        "output_file": run.output_file,
        "error": run.error,
        "result_preview": preview,
    }


def format_group_notification(records: list[AgentRun], *, partial: bool) -> str:
    """Format a consolidated completion notice for a group of runs."""
    label = f"{len(records)} agent(s) finished"
    if partial:
        label += " (partial — others still running)"
    blocks = "\n\n".join(format_task_notification(run, GROUP_RESULT_CHARS) for run in records)
    return (
        f"Background agent group completed: {label}\n\n{blocks}\n\nUse get_subagent_result for full output."
    )


def format_run_summary(run: AgentRun) -> str:
    """Format one run for /agents and get_subagent_result output."""
    return (
        f"{run.agent_id} [{run.status}] type={run.agent_type}"
        f" turns={run.turns} tools={run.tool_calls} — {run.description}"
    )


def lifetime_tokens(run: AgentRun) -> int:
    """Lifetime billed tokens: input + output + cache_write (pi semantics)."""
    return run.tokens_input + run.tokens_output + run.tokens_cache_write


def format_live_stats(run: AgentRun) -> str:
    """Cumulative running-stats line in the completion card's vocabulary."""
    return " · ".join(
        stat_parts(
            {
                "turn_count": run.turns,
                "max_turns": run.max_turns,
                "tool_uses": run.tool_calls,
                "total_tokens": lifetime_tokens(run) if run.has_usage else 0,
            }
        )
    )


def format_usage_parts(run: AgentRun) -> str:
    """Format pi-style usage parts joined by middle dots."""
    parts = []
    if run.has_usage:
        parts.append(f"{lifetime_tokens(run)} tokens")
    parts.append(f"{run.tool_calls} tool uses")
    if run.context_tokens:
        parts.append(f"~{run.context_tokens} context tokens")
    duration = _duration_ms(run)
    if duration is not None:
        parts.append(f"{duration / 1000:.1f}s")
    return " · ".join(parts)


def _duration_ms(run: AgentRun) -> int | None:
    if run.started_at is None or run.completed_at is None:
        return None
    return max(0, int((run.completed_at - run.started_at) * 1000))


def render_agent_call(arguments: Mapping[str, object]) -> str:
    """Friendly invocation line for the agent tool (pi's renderCall port)."""
    agent_type = str(arguments.get("subagent_type") or "general")
    description = str(arguments.get("description") or "").strip()
    line = f"▸ {agent_type} agent"
    schedule = arguments.get("schedule")
    if schedule:
        line += f" (scheduled {schedule})"
    return f"{line} · {description}" if description else line


def render_get_result_call(arguments: Mapping[str, object]) -> str:
    """Friendly invocation line for get_subagent_result."""
    line = f"▸ get result · {arguments.get('agent_id') or '?'}"
    if arguments.get("wait"):
        line += " (wait)"
    return line


def render_steer_call(arguments: Mapping[str, object]) -> str:
    """Friendly invocation line for steer_subagent."""
    message = " ".join(str(arguments.get("message") or "").split())
    if len(message) > STEER_CALL_PREVIEW_CHARS:
        message = message[:STEER_CALL_PREVIEW_CHARS].rstrip() + "…"
    line = f"▸ steer {arguments.get('agent_id') or '?'}"
    return f"{line} · {message}" if message else line


def _notification_renderer(view: CustomMessageView, options: MessageRenderOptions) -> str:
    """Adapt the declining renderer to the host contract, which has no decline.

    The renderer returns None when it has nothing structured to draw. The host
    renders the message's own content in that case, so do the same here rather
    than pretend to render something.
    """
    return render_notification(view, options) or view.content
