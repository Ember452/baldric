"""Formatting helpers shared by slash-command handlers."""

from __future__ import annotations

from collections.abc import Sequence

from baldric.runtime.context.resources import ResourceDiagnostic
from baldric.runtime.session.manager import CodingSessionRecord
from baldric.runtime.update.reload import CodingReloadSummary, ReloadCategorySummary


def _format_session_record(record: CodingSessionRecord) -> str:
    title = record.title or "Untitled"
    return f"- {record.id}: {title} ({record.model}) {record.cwd}"


def _format_diagnostics(diagnostics: Sequence[ResourceDiagnostic], *, kind: str | None = None) -> list[str]:
    filtered = [diagnostic for diagnostic in diagnostics if kind is None or diagnostic.kind == kind]
    if not filtered:
        return ["Resource diagnostics: none"]
    lines = ["Resource diagnostics:"]
    lines.extend(f"- {diagnostic.format()}" for diagnostic in filtered)
    return lines


def format_resource_diagnostics(diagnostics: Sequence[ResourceDiagnostic]) -> str:
    """Render complete resource diagnostics for command output."""
    if not diagnostics:
        return "No resource diagnostics."

    lines = [f"Resource diagnostics ({len(diagnostics)}):"]
    for index, diagnostic in enumerate(diagnostics, start=1):
        lines.extend(
            [
                "",
                f"{index}. {diagnostic.severity.upper()}",
                f"Kind: {diagnostic.kind}",
            ]
        )
        if diagnostic.name is not None:
            lines.append(f"Name: {diagnostic.name}")
        if diagnostic.path is not None:
            lines.append(f"Path: {diagnostic.path}")
        lines.append(f"Message: {diagnostic.message}")
    return "\n".join(lines)


def format_reload_summary(summary: CodingReloadSummary) -> str:
    lines = [
        "Reloaded local coding resources and project context.",
        "Resources:",
        f"- Skills: {_format_reload_category(summary.skills)}",
        f"- Prompt templates: {_format_reload_category(summary.prompt_templates)}",
        f"- Extensions: {_format_reload_category(summary.extensions)}",
        "Context:",
        f"- Project context files: {_format_reload_category(summary.context_files)}",
        "- Next-turn system prompt: " + ("rebuilt" if summary.system_prompt_rebuilt else "unchanged"),
        "Diagnostics:",
        f"- Resource diagnostics: {_format_reload_category(summary.diagnostics)}",
        "Provider config:",
        "- Not refreshed by /reload; use /login or /model for provider/model settings.",
    ]
    return "\n".join(lines)


def _format_reload_category(summary: ReloadCategorySummary) -> str:
    status = "changed" if summary.changed else "unchanged"
    delta = _format_count_delta(summary.delta)
    suffix = f", {delta}" if delta is not None else ""
    return f"{summary.after} total ({status}{suffix})"


def _format_count_delta(delta: int) -> str | None:
    if delta == 0:
        return None
    return f"{delta:+d}"
