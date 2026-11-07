"""UI-loop watchdog: fail fast with thread stacks when the loop stops beating.

The interactive TUI owns the whole terminal, so a stalled event loop looks
like a frozen session with no diagnostics. A daemon thread watches a
heartbeat timestamp that the loop refreshes every second; when the heartbeat
stalls past the limit, the watchdog dumps all thread stacks and exits, so a
hang always leaves evidence instead of a silent freeze. Set
``BALDRIC_WATCHDOG=0`` to disable it (embedded hosts, debugging).
"""

from __future__ import annotations

import faulthandler
import os
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from typing import TextIO

DEFAULT_STALL_LIMIT_SECONDS = 30.0
WATCHDOG_POLL_SECONDS = 1.0
WATCHDOG_EXIT_CODE = 70


def watchdog_disabled() -> bool:
    """Return whether ``BALDRIC_WATCHDOG=0`` opted the watchdog out."""
    return os.environ.get("BALDRIC_WATCHDOG") == "0"


class LoopWatchdog:
    """Watch a heartbeat callable and fail the process when it stalls.

    ``heartbeat`` must return the ``time.monotonic()`` stamp of the last loop
    tick. Both sides use ``time.monotonic()``, so wall-clock changes cannot
    trigger a false stall.
    """

    def __init__(
        self,
        heartbeat: Callable[[], float],
        *,
        stall_limit_seconds: float = DEFAULT_STALL_LIMIT_SECONDS,
        poll_seconds: float = WATCHDOG_POLL_SECONDS,
        stream: TextIO | None = None,
        exit_fn: Callable[[int], None] = os._exit,
        enabled: bool | None = None,
    ) -> None:
        self._heartbeat = heartbeat
        self._stall_limit_seconds = stall_limit_seconds
        self._poll_seconds = poll_seconds
        self._stream = sys.stderr if stream is None else stream
        self._exit_fn = exit_fn
        self._enabled = (not watchdog_disabled()) if enabled is None else enabled
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the daemon watch thread; no-op when disabled or running."""
        if not self._enabled or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="baldric-loop-watchdog",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the watch thread and wait for it to exit."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _stalled(self, last_beat: float, now: float) -> bool:
        return now - last_beat >= self._stall_limit_seconds

    def _run(self) -> None:
        while not self._stop.wait(self._poll_seconds):
            last_beat = self._heartbeat()
            now = time.monotonic()
            if not self._stalled(last_beat, now):
                continue
            self._report_stall(now - last_beat)
            return

    def _report_stall(self, stall_seconds: float) -> None:
        try:
            print(
                f"baldric: UI loop stalled for {stall_seconds:.1f}s; dumping thread stacks and exiting.",
                file=self._stream,
            )
            self._dump_stacks()
        except (AttributeError, OSError, ValueError):
            # Diagnostics must never crash the watchdog itself: a broken
            # stream is still better than exiting without evidence.
            pass
        self._exit_fn(WATCHDOG_EXIT_CODE)

    def _dump_stacks(self) -> None:
        try:
            faulthandler.dump_traceback(file=self._stream)
            return
        except (AttributeError, OSError, ValueError):
            # fileno-less streams (embedded hosts, tests) cannot be handed to
            # faulthandler directly; stage the dump through a real temp file
            # so the C-level dump still reaches the stream.
            pass
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as staged:
            faulthandler.dump_traceback(file=staged)
            staged.seek(0)
            self._stream.write(staged.read())
