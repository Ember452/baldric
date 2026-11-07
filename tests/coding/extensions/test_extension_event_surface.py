"""The extension event whitelist must name events that actually exist.

`entry_appended` was advertised to extensions while nothing in the codebase ever
emitted it, and the rest of the whitelist was never checked against the event
union. Both failures are silent: an extension subscribes and never fires, with no
diagnostic anywhere.
"""

from __future__ import annotations

import inspect

import baldric_agent.events as agent_events
import baldric_coding.events as coding_events
from baldric_coding.extensions.api import AGENT_EVENT_TYPES


def _event_types() -> set[str]:
    """Every `type` discriminator declared by the two event modules."""
    found: set[str] = set()
    for module in (agent_events, coding_events):
        for _name, candidate in inspect.getmembers(module, inspect.isclass):
            field = getattr(candidate, "model_fields", {}).get("type")
            if field is not None and isinstance(field.default, str):
                found.add(field.default)
    return found


def test_every_whitelisted_event_is_a_real_coding_session_event() -> None:
    unknown = sorted(AGENT_EVENT_TYPES - _event_types())
    assert unknown == [], f"the extension whitelist names events nothing emits: {unknown}"


def test_the_dead_entry_appended_event_is_not_advertised() -> None:
    assert "entry_appended" not in AGENT_EVENT_TYPES
