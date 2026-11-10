"""Guard: session logic lives in focused modules; session.py stays a typed facade.

`CodingSession` is deliberately a wide, thin facade over module-level functions
(`session/runtime.py`, `session/model_runtime.py`, `session/branching.py`). That
keeps mypy --strict meaningful (each function is fully typed) instead of moving
bodies into mixins whose ``self`` would have to be ``Any``. These assertions keep
the layout and the re-export surface in place.
"""

from __future__ import annotations

from baldric.runtime.session import branching, model_runtime
from baldric.runtime.session import session as session_module
from baldric.runtime.session.session import (
    TREE_RUNNING_MESSAGE,
    CodingSession,
    SessionTreeBranchResult,
    SessionTreeChoice,
)


def test_session_is_a_plain_facade_not_a_mixin_stack() -> None:
    # Mixins would force `self: Any` and silently disable strict typing on the
    # moved bodies; logic belongs in module functions instead.
    assert CodingSession.__bases__ == (object,)


def test_branching_types_are_single_sourced_and_reexported() -> None:
    # Defined once in session.branching; re-exported so existing importers of
    # `baldric.runtime.session.session` keep working.
    assert session_module.TREE_RUNNING_MESSAGE is branching.TREE_RUNNING_MESSAGE
    assert TREE_RUNNING_MESSAGE == branching.TREE_RUNNING_MESSAGE
    assert SessionTreeChoice is branching.SessionTreeChoice
    assert SessionTreeBranchResult is branching.SessionTreeBranchResult


def test_model_runtime_functions_exist_and_delegate_targets_are_on_the_class() -> None:
    for name in (
        "run_huggingface_route_failover",
        "observe_response_headers",
        "refresh_runtime_model_limits",
        "pricing_for_response",
        "build_runtime_provider",
        "activate_runtime_provider",
        "should_auto_failover_huggingface_route",
        "will_auto_retry",
    ):
        assert callable(getattr(model_runtime, name)), f"model_runtime missing {name}"
    for name in (
        "_run_huggingface_route_failover",
        "_observe_response_headers",
        "_refresh_runtime_model_limits",
        "_pricing_for_response",
        "_build_runtime_provider",
        "_activate_runtime_provider",
        "will_auto_retry",
    ):
        assert callable(getattr(CodingSession, name)), f"CodingSession missing {name}"


def test_branching_functions_exist_and_are_exposed_on_the_class() -> None:
    for name in ("branch_to_entry", "tree_choices", "set_label", "session_entries"):
        assert callable(getattr(branching, name)), f"branching missing {name}"
        assert callable(getattr(CodingSession, name)), f"CodingSession missing {name}"
