"""Shared helpers for subagents TUI/widget tests.

Owned by the subagents UI test set so ``test_subagents_integration_tui`` can
reuse them without importing a sibling test module.
"""

from __future__ import annotations

import time

from baldric.runtime.features.subagents.extension import AgentRun
from baldric.runtime.features.subagents.ui.strip import AgentStripWidget


def _run(
    agent_id: str = "agent-1",
    *,
    agent_type: str = "explore",
    description: str = "survey",
    status: str = "running",
    started: bool = True,
    finished: bool = False,
    session: object | None = None,
) -> AgentRun:
    run = AgentRun(
        agent_id=agent_id,
        agent_type=agent_type,
        description=description,
        prompt="child prompt",
        background=True,
        status=status,
    )
    if started:
        run.started_at = time.monotonic()
    if finished:
        run.completed_at = time.monotonic()
    run.session = session
    return run


def _strip_text(strip: AgentStripWidget) -> str:
    group = strip.render()
    return " ".join(getattr(part, "plain", "") for part in group.renderables)
