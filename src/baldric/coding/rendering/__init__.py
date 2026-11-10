"""Event renderers for Baldric coding frontends and print modes."""

from __future__ import annotations

from pathlib import Path

from baldric.coding.extensions.api import CustomMessageMarkup
from baldric.coding.rendering.base import EventRenderer, PrintOutputMode
from baldric.coding.rendering.json import JsonEventRenderer
from baldric.coding.rendering.plain import FinalTextRenderer
from baldric.coding.rendering.transcript import TranscriptRenderer


def create_event_renderer(
    mode: PrintOutputMode,
    *,
    custom_message_renderer: CustomMessageMarkup | None = None,
    cwd: Path | None = None,
) -> EventRenderer:
    """Create a renderer for a print output mode."""
    if mode is PrintOutputMode.text:
        return FinalTextRenderer()
    if mode is PrintOutputMode.json:
        return JsonEventRenderer()
    return TranscriptRenderer(custom_message_renderer=custom_message_renderer, cwd=cwd)


__all__ = [
    "EventRenderer",
    "FinalTextRenderer",
    "JsonEventRenderer",
    "PrintOutputMode",
    "TranscriptRenderer",
    "create_event_renderer",
]
