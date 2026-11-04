"""Tests for the subagent scheduler, cron matcher, and schedule store.

Ported verbatim from the upstream suite's portable sections (cron matcher,
``detect_schedule``, store round-trip and stale lock). Adaptations are only
where this host differs: the extension is an importable package here, so the
upstream's ``_load_runtime``/``_submodule`` dynamic loading is replaced by plain
imports, and ``resolve_store_path`` takes Baldric paths because schedules live
under the Baldric home.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from baldric_coding.extensions.builtins.subagents.cron import CronExpression, validate_cron
from baldric_coding.extensions.builtins.subagents.schedule import SubagentScheduler
from baldric_coding.extensions.builtins.subagents.schedule_store import (
    ScheduledSubagent,
    ScheduleStore,
    resolve_store_path,
)
from baldric_coding.paths import BaldricPaths

pytestmark = pytest.mark.anyio


def _store_path(tmp_path: Path, session_id: str) -> Path:
    """Upstream: ``resolve_store_path(tmp_path, "session-x")``."""
    paths = BaldricPaths(home=tmp_path / "home", agents_home=tmp_path / "agents")
    cwd = tmp_path / "project"
    cwd.mkdir(exist_ok=True)
    return resolve_store_path(paths, cwd, session_id)


def _make_job(**overrides: object) -> ScheduledSubagent:
    defaults = {
        "id": "job-1",
        "name": "nightly",
        "description": "nightly",
        "schedule": "0 9 * * 1",
        "schedule_type": "cron",
        "subagent_type": "general",
        "prompt": "do the thing",
        "enabled": True,
        "created_at": datetime.now().isoformat(),
        "run_count": 0,
    }
    defaults.update(overrides)
    return ScheduledSubagent(**defaults)  # type: ignore[arg-type]


# ── cron matcher ─────────────────────────────────────────────────────────


def test_cron_star_matches_every_minute() -> None:
    expr = CronExpression("* * * * *")
    assert expr.matches(datetime(2026, 7, 4, 13, 37))


def test_cron_specific_minute_hour() -> None:
    expr = CronExpression("30 14 * * *")
    assert expr.matches(datetime(2026, 7, 4, 14, 30))
    assert not expr.matches(datetime(2026, 7, 4, 14, 31))
    assert not expr.matches(datetime(2026, 7, 4, 15, 30))


def test_cron_step_and_range_and_list() -> None:
    step = CronExpression("*/15 * * * *")
    assert {m for m in range(60) if step.matches(datetime(2026, 1, 1, 0, m))} == {
        0,
        15,
        30,
        45,
    }
    rng = CronExpression("0 9-11 * * *")
    assert rng.matches(datetime(2026, 1, 1, 10, 0))
    assert not rng.matches(datetime(2026, 1, 1, 12, 0))
    lst = CronExpression("0,20,40 * * * *")
    assert lst.matches(datetime(2026, 1, 1, 5, 20))
    assert not lst.matches(datetime(2026, 1, 1, 5, 21))
    ranged_step = CronExpression("0-30/10 * * * *")
    assert {m for m in range(60) if ranged_step.matches(datetime(2026, 1, 1, 0, m))} == {
        0,
        10,
        20,
        30,
    }


def test_cron_day_of_week() -> None:
    # 2026-07-06 is a Monday. dow 1 = Monday.
    monday = CronExpression("0 0 * * 1")
    assert monday.matches(datetime(2026, 7, 6, 0, 0))
    assert not monday.matches(datetime(2026, 7, 7, 0, 0))
    # Sunday accepts both 0 and 7.
    sunday_zero = CronExpression("0 0 * * 0")
    sunday_seven = CronExpression("0 0 * * 7")
    assert sunday_zero.matches(datetime(2026, 7, 5, 0, 0))
    assert sunday_seven.matches(datetime(2026, 7, 5, 0, 0))


def test_cron_dom_dow_or_semantics() -> None:
    # Both restricted: matches on the 1st OR on Mondays.
    expr = CronExpression("0 0 1 * 1")
    assert expr.matches(datetime(2026, 7, 1, 0, 0))  # 1st (a Wednesday)
    assert expr.matches(datetime(2026, 7, 6, 0, 0))  # a Monday
    assert not expr.matches(datetime(2026, 7, 7, 0, 0))  # neither


def test_cron_next_after() -> None:
    expr = CronExpression("0 9 * * 1")  # 09:00 every Monday
    nxt = expr.next_after(datetime(2026, 7, 4, 12, 0))  # Sat
    assert nxt == datetime(2026, 7, 6, 9, 0)  # following Monday
    # Strictly after: a matching instant returns the next occurrence.
    after_match = expr.next_after(datetime(2026, 7, 6, 9, 0))
    assert after_match == datetime(2026, 7, 13, 9, 0)


def test_cron_validation() -> None:
    assert validate_cron("*/5 * * * *")
    assert not validate_cron("* * * *")  # 4 fields
    assert not validate_cron("* * * * * *")  # 6 fields
    assert not validate_cron("99 * * * *")  # out of range
    assert not validate_cron("abc * * * *")


# ── cron branches the upstream suite leaves unexercised ───────────────────


def test_cron_step_from_a_single_value_runs_to_the_field_maximum() -> None:
    """`N/M` is documented in cron.py but tested by neither suite upstream."""
    expression = CronExpression("5/15 * * * *")

    assert {m for m in range(60) if expression.matches(datetime(2026, 1, 1, 0, m))} == {
        5,
        20,
        35,
        50,
    }
    single = CronExpression("5 * * * *")
    assert {m for m in range(60) if single.matches(datetime(2026, 1, 1, 0, m))} == {5}


def test_cron_next_after_gives_up_instead_of_searching_forever() -> None:
    """The bounded forward search is the only guard against a hot loop."""
    assert CronExpression("0 0 30 2 *").next_after(datetime(2026, 1, 1, 0, 0)) is None


def test_cron_errors_are_value_errors_because_validation_catches_them() -> None:
    """`validate_cron` only swallows (ValueError, TypeError)."""
    with pytest.raises(ValueError, match="5 fields"):
        CronExpression("* * * *")
    with pytest.raises(ValueError, match="out of range"):
        CronExpression("99 * * * *")
    with pytest.raises(ValueError, match="matches nothing"):
        CronExpression("30-10 * * * *")


# ── detect_schedule ──────────────────────────────────────────────────────


def test_detect_schedule_forms() -> None:
    sched = SubagentScheduler
    assert sched.detect_schedule("5m")[0] == "interval"
    assert sched.detect_schedule("5m")[1] == 300_000
    assert sched.detect_schedule("+10m")[0] == "once"
    assert sched.detect_schedule("0 9 * * 1")[0] == "cron"
    future = (datetime.now() + timedelta(days=1)).replace(microsecond=0).isoformat()
    assert sched.detect_schedule(future)[0] == "once"
    with pytest.raises(ValueError, match="in the past"):
        sched.detect_schedule("2000-01-01T00:00:00")
    with pytest.raises(ValueError, match="Invalid schedule"):
        sched.detect_schedule("not a schedule")
    # Sub-minimum intervals are rejected: a zero interval would re-arm with
    # delay 0 and spawn agents in a tight loop.
    with pytest.raises(ValueError, match="too short"):
        sched.detect_schedule("0s")
    with pytest.raises(ValueError, match="too short"):
        sched.detect_schedule("4s")
    assert sched.detect_schedule("5s")[0] == "interval"


# ── store round-trip + stale lock ────────────────────────────────────────


def test_store_round_trip(tmp_path: Path) -> None:
    path = _store_path(tmp_path, "session-x")
    store = ScheduleStore(path)
    job = _make_job(provider="openai-codex", model="gpt-5.6-sol", max_turns=7)
    store.add(job)
    assert path.exists()

    reloaded = ScheduleStore(path)
    got = reloaded.get("job-1")
    assert got is not None
    assert got.provider == "openai-codex"
    assert got.model == "gpt-5.6-sol"
    assert got.max_turns == 7
    assert got.schedule == "0 9 * * 1"

    updated = reloaded.update("job-1", run_count=3, last_status="success")
    assert updated is not None and updated.run_count == 3
    assert reloaded.remove("job-1") is True
    assert reloaded.get("job-1") is None
    assert reloaded.update("missing", run_count=1) is None


def test_store_takes_over_stale_lock(tmp_path: Path) -> None:
    path = _store_path(tmp_path, "session-y")
    store = ScheduleStore(path)
    store.add(_make_job())

    lock_path = path.with_name(path.name + ".lock")
    lock_path.write_text("999999")  # PID that is not alive → stale
    assert lock_path.exists()

    updated = store.update("job-1", run_count=9)
    assert updated is not None and updated.run_count == 9
    assert not lock_path.exists()  # stale lock taken over and released
