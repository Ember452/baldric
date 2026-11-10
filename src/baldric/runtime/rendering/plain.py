"""Pi-style final text renderer for print mode."""

import typer

from baldric.agent.events import MessageEndEvent
from baldric.protocol.messages import AssistantMessage
from baldric.runtime.events import AutoRetryEndEvent, CodingSessionEvent
from baldric.runtime.rendering.base import is_failed_stop_reason


class FinalTextRenderer:
    def __init__(self) -> None:
        self._last_assistant_text = ""
        self._failed = False
        self._error_messages: list[str] = []

    def render(self, event: CodingSessionEvent) -> None:
        if isinstance(event, AutoRetryEndEvent) and event.success:
            self._failed = False
            self._error_messages.clear()
            return
        if not isinstance(event, MessageEndEvent) or not isinstance(event.message, AssistantMessage):
            return
        if event.message.is_tool_result_recovery:
            return
        self._last_assistant_text = event.message.text
        if is_failed_stop_reason(event.message.stop_reason):
            self._failed = True
            if event.message.stop_reason == "length" and not event.message.error_message:
                self._error_messages.append(
                    "Response was truncated: the model reached its output token limit."
                )
            elif event.message.error_message:
                self._error_messages.append(event.message.error_message)

    def finish(self) -> bool:
        if self._failed:
            for message in self._error_messages:
                typer.echo(f"Error: {message}", err=True)
            return False
        if self._last_assistant_text:
            typer.echo(self._last_assistant_text)
        return True
