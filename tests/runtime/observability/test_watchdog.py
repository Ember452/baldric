"""Tests for the UI-loop watchdog."""

import time

from baldric.runtime.observability.watchdog import WATCHDOG_EXIT_CODE, LoopWatchdog


def _wait_for_exits(exits: list[int], timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if exits:
            return True
        time.sleep(0.005)
    return False


def test_watchdog_exits_with_stacks_when_the_heartbeat_stalls() -> None:
    import io

    stream = io.StringIO()
    exits: list[int] = []
    # A frozen heartbeat means every poll is a full stall.
    watchdog = LoopWatchdog(
        lambda: 0.0,
        stall_limit_seconds=0.05,
        poll_seconds=0.01,
        stream=stream,
        exit_fn=exits.append,
    )

    watchdog.start()
    assert _wait_for_exits(exits)
    watchdog.stop()

    assert exits == [WATCHDOG_EXIT_CODE]
    output = stream.getvalue()
    assert "stalled" in output
    # faulthandler's dump names the calling thread stacks, so a hang leaves
    # evidence of where the loop was stuck.
    assert "Thread" in output


def test_watchdog_stays_silent_while_the_heartbeat_advances() -> None:
    exits: list[int] = []
    watchdog = LoopWatchdog(
        time.monotonic,
        stall_limit_seconds=0.5,
        poll_seconds=0.01,
        exit_fn=exits.append,
    )

    watchdog.start()
    time.sleep(0.15)
    watchdog.stop()

    assert exits == []


def test_watchdog_honors_baldric_watchdog_opt_out(monkeypatch) -> None:
    monkeypatch.setenv("BALDRIC_WATCHDOG", "0")
    exits: list[int] = []
    watchdog = LoopWatchdog(
        lambda: 0.0,
        stall_limit_seconds=0.01,
        poll_seconds=0.01,
        exit_fn=exits.append,
    )

    watchdog.start()
    time.sleep(0.05)
    watchdog.stop()

    assert exits == []
