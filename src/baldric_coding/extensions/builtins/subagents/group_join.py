"""Group-join batching for background subagent notifications.

Background runs spawned close together are registered as a group; their
completion notifications are consolidated into one message. If some members are
still running when the group timeout fires, a partial notification is delivered
and the remaining members become a straggler group with a shorter timeout,
repeating until the group drains.

The timeout starts when the first member completes, not when the group is
registered: an empty batch would otherwise burn its whole window before any
result exists to consolidate.

Runs are typed through a local protocol rather than importing the host's run
record, so this module stays testable and importable on its own; anything with
an `agent_id` and a `result_consumed` flag can be joined.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Literal, Protocol

DEFAULT_TIMEOUT = 30.0
STRAGGLER_TIMEOUT = 15.0

#: "pass" - not grouped, the caller notifies individually.
#: "held" - waiting for the rest of the group.
#: "delivered" - this completion triggered the group notification.
GroupOutcome = Literal["pass", "held", "delivered"]


class JoinableRun(Protocol):
    """The slice of a subagent run record that group accounting needs."""

    agent_id: str
    result_consumed: bool


DeliverCallback = Callable[[list[JoinableRun], bool], None]


@dataclass(slots=True)
class _Group:
    agent_ids: set[str]
    completed: dict[str, JoinableRun] = field(default_factory=dict)
    timer: asyncio.TimerHandle | None = None
    is_straggler: bool = False


class GroupJoinManager:
    """Tracks agent groups and consolidates their completion notifications."""

    def __init__(
        self,
        deliver: DeliverCallback,
        *,
        group_timeout: float = DEFAULT_TIMEOUT,
        straggler_timeout: float = STRAGGLER_TIMEOUT,
    ) -> None:
        self._deliver = deliver
        self._group_timeout = group_timeout
        self._straggler_timeout = straggler_timeout
        self._groups: dict[str, _Group] = {}
        self._agent_to_group: dict[str, str] = {}

    def register_group(self, group_id: str, agent_ids: Iterable[str]) -> None:
        """Register a batch of agent ids as one notification group."""
        ids = set(agent_ids)
        self._groups[group_id] = _Group(agent_ids=ids)
        for agent_id in ids:
            self._agent_to_group[agent_id] = group_id

    def on_agent_complete(self, run: JoinableRun) -> GroupOutcome:
        """Feed a terminal run into group accounting and report what happened."""
        group_id = self._agent_to_group.get(run.agent_id)
        if group_id is None:
            return "pass"
        group = self._groups.get(group_id)
        if group is None:
            return "pass"
        group.completed[run.agent_id] = run
        if set(group.completed) >= group.agent_ids:
            self._deliver_group(group_id, group)
            return "delivered"
        if len(group.completed) == 1:
            timeout = self._straggler_timeout if group.is_straggler else self._group_timeout
            group.timer = asyncio.get_running_loop().call_later(timeout, self._on_timeout, group_id)
        return "held"

    def cancel_all(self) -> None:
        """Cancel all pending group timers and forget every group."""
        for group in self._groups.values():
            if group.timer is not None:
                group.timer.cancel()
        self._groups.clear()
        self._agent_to_group.clear()

    def _deliver_group(self, group_id: str, group: _Group) -> None:
        if group.timer is not None:
            group.timer.cancel()
            group.timer = None
        records = list(group.completed.values())
        self._remove_group(group_id, group)
        self._fire(records, partial=False)

    def _on_timeout(self, group_id: str) -> None:
        group = self._groups.get(group_id)
        if group is None:
            return
        group.timer = None
        records = list(group.completed.values())
        remaining = group.agent_ids - set(group.completed)
        for agent_id in group.completed:
            self._agent_to_group.pop(agent_id, None)
        if remaining:
            group.completed = {}
            group.agent_ids = remaining
            group.is_straggler = True
        else:
            self._remove_group(group_id, group)
        self._fire(records, partial=bool(remaining))

    def _remove_group(self, group_id: str, group: _Group) -> None:
        self._groups.pop(group_id, None)
        for agent_id in group.agent_ids:
            self._agent_to_group.pop(agent_id, None)

    def _fire(self, records: list[JoinableRun], *, partial: bool) -> None:
        unconsumed = [run for run in records if not run.result_consumed]
        if not unconsumed:
            return
        self._deliver(unconsumed, partial)
