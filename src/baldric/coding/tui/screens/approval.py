"""The in-terminal approval card screen for the opt-in tool approval mode."""

from __future__ import annotations

from contextlib import suppress
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from baldric.coding.rendering.approval_card import render_approval_card
from baldric.coding.rendering.themes import TuiTheme
from baldric.coding.trust.approvals import (
    DEFAULT_REJECT_REASON,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalRule,
)

_REASON_INPUT_ID = "approval-reason"


class ApprovalScreen(ModalScreen[ApprovalDecision | None]):
    """Ask the user to allow, always-allow, or reject one mutating tool call.

    Dismisses with an :class:`ApprovalDecision`; ``None`` means the user
    dismissed the card without choosing, which the gate treats as a rejection.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "reject_default", "Reject", show=False),
        Binding("y", "allow_once", "Allow once", show=False),
        Binding("a", "allow_always", "Always allow", show=False),
        Binding("n", "start_reject_reason", "Reject with reason", show=False),
    ]

    def __init__(
        self,
        request: ApprovalRequest,
        *,
        theme: TuiTheme,
        always_rule: ApprovalRule,
    ) -> None:
        super().__init__()
        self.request = request
        self.card_theme = theme
        self.always_rule = always_rule

    def compose(self) -> ComposeResult:
        yield Static(
            render_approval_card(
                self.request,
                theme=self.card_theme,
                always_rule=self.always_rule,
            ),
            id="approval-card",
            markup=False,
        )

    def on_mount(self) -> None:
        # The card is the whole surface; the reason input mounts on demand so
        # the decision keys are never competing with a focused text field.
        with suppress(NoMatches):
            self.query_one("#approval-card", Static).focus()

    def action_allow_once(self) -> None:
        self.dismiss(ApprovalDecision(approved=True, remember=False))

    def action_allow_always(self) -> None:
        self.dismiss(ApprovalDecision(approved=True, remember=True))

    def action_start_reject_reason(self) -> None:
        if self._reason_input() is not None:
            return
        reason_input = Input(
            placeholder="Reason for rejecting (sent back to the model)",
            id=_REASON_INPUT_ID,
        )
        self.mount(reason_input, after=self.query_one("#approval-card"))
        reason_input.focus()

    def action_reject_default(self) -> None:
        reason_input = self._reason_input()
        reason = reason_input.value.strip() if reason_input is not None else ""
        self.dismiss(ApprovalDecision(approved=False, reason=reason or DEFAULT_REJECT_REASON))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != _REASON_INPUT_ID:
            return
        event.stop()
        reason = event.input.value.strip() or DEFAULT_REJECT_REASON
        self.dismiss(ApprovalDecision(approved=False, reason=reason))

    def _reason_input(self) -> Input | None:
        with suppress(NoMatches):
            return self.query_one(f"#{_REASON_INPUT_ID}", Input)
        return None
