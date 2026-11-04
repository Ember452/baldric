"""Tests for the scheduled-subagent dispatcher.

Timers are never waited on: arming is asserted through the recorded handle and
firing is driven by calling the timer callback directly, then awaiting the job
task the scheduler created. The manager is a fake implementing the same narrow
protocol the scheduler depends on.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from baldric_coding.extensions.builtins.subagents.agents import AgentDefinition
from baldric_coding.extensions.builtins.subagents.schedule import (
    MIN_INTERVAL_MS,
    SubagentScheduler,
)
from baldric_coding.extensions.builtins.subagents.schedule_store import (
    ScheduledSubagent,
    ScheduleStore,
    resolve_store_path,
)
from baldric_coding.paths import BaldricPaths

pytestmark = pytest.mark.anyio

_DEFINITIONS = {"general": AgentDefinition(name="general", description="general")}


@dataclass
class FakeRun:
    agent_id: str
    status: str = "completed"
    task: asyncio.Task[None] | None = None


class FakeManager:
    """Implements SchedulingManager for these tests."""

    def __init__(self, *, spawn_raises: bool = False, final_status: str = "completed") -> None:
        self.spawn_raises = spawn_raises
        self.final_status = final_status
        self.runs = {}
        self.spawned: list[dict[str, object]] = []

    def definitions(self) -> dict[str, AgentDefinition]:
        return dict(_DEFINITIONS)

    def spawn(self, **kwargs: object) -> FakeRun:
        if self.spawn_raises:
            raise RuntimeError("no provider configured")
        self.spawned.append(kwargs)
        run = FakeRun(agent_id="agent-1", status=self.final_status)
        run.task = asyncio.ensure_future(self._finish(run))
        self.runs[run.agent_id] = run
        return run

    async def _finish(self, run: FakeRun) -> None:
        await asyncio.sleep(0)


@pytest.fixture
def store(tmp_path: Path) -> ScheduleStore:
    paths = BaldricPaths(home=tmp_path / "home", agents_home=tmp_path / "agents")
    cwd = tmp_path / "project"
    cwd.mkdir()
    return ScheduleStore(resolve_store_path(paths, cwd, "sess-1"))


@pytest.fixture
def scheduler(request: pytest.FixtureRequest) -> SubagentScheduler:
    manager = getattr(request, "param", None) or FakeManager()
    return SubagentScheduler(manager)  # type: ignore[arg-type]


def _job(**overrides: object) -> ScheduledSubagent:
    base: dict[str, object] = {
        "id": "job-1",
        "name": "nightly",
        "description": "suite",
        "schedule": "0 9 * * 1",
        "schedule_type": "cron",
        "subagent_type": "general",
        "prompt": "run it",
        "enabled": True,
        "created_at": datetime.now().isoformat(),
    }
    base.update(overrides)
    return ScheduledSubagent(**base)  # type: ignore[arg-type]


# -- format detection ---------------------------------------------------------


def test_detect_schedule_recognises_every_documented_form() -> None:
    assert SubagentScheduler.detect_schedule("0 9 * * 1") == ("cron", None, "0 9 * * 1")
    assert SubagentScheduler.detect_schedule("  5m  ") == ("interval", 300_000, "5m")
    assert SubagentScheduler.detect_schedule("+10m")[0] == "once"
    future = (datetime.now() + timedelta(days=1)).replace(microsecond=0).isoformat()
    assert SubagentScheduler.detect_schedule(future) == ("once", None, future)


def test_detect_schedule_rejects_the_ambiguous_and_the_impossible() -> None:
    with pytest.raises(ValueError, match="Invalid schedule"):
        SubagentScheduler.detect_schedule("not a schedule")
    with pytest.raises(ValueError, match="too short"):
        SubagentScheduler.detect_schedule("0s")
    with pytest.raises(ValueError, match="too short"):
        SubagentScheduler.detect_schedule(f"{MIN_INTERVAL_MS // 1000 - 1}s")
    with pytest.raises(ValueError, match="in the past"):
        SubagentScheduler.detect_schedule("2000-01-01T00:00:00")
    with pytest.raises(ValueError, match="5 fields|Invalid schedule"):
        SubagentScheduler.detect_schedule("* * * *")


def test_detect_schedule_takes_the_minimum_interval_boundary_inclusively() -> None:
    assert SubagentScheduler.detect_schedule(f"{MIN_INTERVAL_MS // 1000}s") == (
        "interval",
        MIN_INTERVAL_MS,
        "5s",
    )


def test_relative_and_interval_units_convert_to_milliseconds() -> None:
    assert SubagentScheduler.parse_interval("10s") == 10_000
    assert SubagentScheduler.parse_interval("5m") == 300_000
    assert SubagentScheduler.parse_interval("1h") == 3_600_000
    assert SubagentScheduler.parse_interval("2d") == 172_800_000
    assert SubagentScheduler.parse_interval("5x") is None
    assert SubagentScheduler.parse_relative_time("-5m") is None
    assert SubagentScheduler.parse_relative_time("5m") is None
    assert SubagentScheduler.parse_relative_time("+1h") is not None


# -- arming -------------------------------------------------------------------


async def test_start_arms_enabled_jobs_and_resumes_the_id_counter(
    scheduler: SubagentScheduler, store: ScheduleStore
) -> None:
    store.add(_job(id="job-7"))
    store.add(_job(id="job-8", enabled=False, name="disabled"))

    scheduler.start(store)

    assert scheduler.is_active()
    assert len(scheduler._timers) == 1, "the disabled job must not be armed"
    # Both stored ids count, so a disabled job's id is never handed out again.
    assert scheduler._id_counter == 8
    job = scheduler.add_job(name="next", description="d", schedule="1h", subagent_type="general", prompt="p")
    assert job.id == "job-9", "the next id follows the highest one already stored"


async def test_an_id_taken_by_another_process_is_stepped_over(
    scheduler: SubagentScheduler, store: ScheduleStore
) -> None:
    """A concurrent insert after start() must not cause an id collision."""
    store.add(_job(id="job-1"))
    scheduler.start(store)

    store.add(_job(id="job-2", name="inserted elsewhere"))  # raced in after start()
    job = scheduler.add_job(name="mine", description="d", schedule="1h", subagent_type="general", prompt="p")

    assert job.id == "job-3"
    assert store.get("job-2") is not None, "the other process's job is left alone"


async def test_unstarted_scheduler_refuses_job_operations(scheduler: SubagentScheduler) -> None:
    with pytest.raises(RuntimeError, match="not started"):
        scheduler.add_job(name="a", description="d", schedule="1h", subagent_type="general", prompt="p")
    assert scheduler.list() == []
    assert scheduler.get_next_run("job-1") is None


async def test_a_corrupt_entry_is_disabled_instead_of_becoming_a_hot_loop(
    scheduler: SubagentScheduler, store: ScheduleStore
) -> None:
    store.add(_job(schedule_type="interval", interval_ms=10))
    scheduler.start(store)

    job = store.get("job-1")

    assert job is not None
    assert job.enabled is False
    assert job.last_status == "error"
    assert scheduler._timers == {}


async def test_a_missed_one_shot_is_disabled_and_never_fires(
    scheduler: SubagentScheduler, store: ScheduleStore
) -> None:
    past = (datetime.now() - timedelta(minutes=5)).isoformat()
    store.add(_job(schedule_type="once", schedule=past))

    scheduler.start(store)

    stored = store.get("job-1")
    assert stored is not None and stored.enabled is False and stored.last_status == "error"
    assert scheduler._timers == {}


async def test_an_unparseable_cron_is_disabled(scheduler: SubagentScheduler, store: ScheduleStore) -> None:
    store.add(_job(schedule="every monday at nine"))
    scheduler.start(store)
    assert store.get("job-1").enabled is False  # type: ignore[union-attr]


# -- next-run reporting -------------------------------------------------------


async def test_next_run_reflects_schedule_type_and_enabled_state(
    scheduler: SubagentScheduler, store: ScheduleStore
) -> None:
    target = (datetime.now() + timedelta(days=2)).isoformat()
    store.add(_job(id="once-1", schedule_type="once", schedule=target))
    store.add(_job(id="int-1", schedule_type="interval", schedule="1h", interval_ms=3_600_000))
    store.add(_job(id="cron-1", schedule_type="cron", schedule="0 9 * * 1"))
    store.add(_job(id="off-1", enabled=False))
    scheduler.start(store)

    assert scheduler.get_next_run("once-1") == target
    interval_run = datetime.fromisoformat(str(scheduler.get_next_run("int-1")))
    assert abs((interval_run - datetime.now()).total_seconds() - 3_600) < 5
    cron_run = datetime.fromisoformat(str(scheduler.get_next_run("cron-1")))
    assert cron_run > datetime.now() and cron_run.weekday() == 0 and cron_run.hour == 9
    assert scheduler.get_next_run("off-1") is None
    assert scheduler.get_next_run("absent") is None


async def test_next_run_for_an_interval_measures_from_the_last_fire(
    scheduler: SubagentScheduler, store: ScheduleStore
) -> None:
    last = datetime.now() - timedelta(seconds=600)
    store.add(
        _job(
            id="int-1",
            schedule_type="interval",
            schedule="1h",
            interval_ms=3_600_000,
            last_run=last.isoformat(),
        )
    )
    scheduler.start(store)

    following = datetime.fromisoformat(str(scheduler.get_next_run("int-1")))

    assert abs((following - (last + timedelta(milliseconds=3_600_000))).total_seconds()) < 2


# -- firing -------------------------------------------------------------------


async def _fire(scheduler: SubagentScheduler, job_id: str) -> None:
    scheduler._on_fire(job_id)
    for task in list(scheduler._tasks):
        await task


async def test_a_firing_recurring_job_runs_and_counts_the_run(
    scheduler: SubagentScheduler, store: ScheduleStore
) -> None:
    scheduler.start(store)
    scheduler.add_job(
        name="nightly", description="suite", schedule="1h", subagent_type="general", prompt="run it"
    )
    job = store.get("job-1")
    assert job is not None

    await _fire(scheduler, "job-1")

    after = store.get("job-1")
    assert after is not None
    assert after.enabled is True, "a recurring job stays scheduled"
    assert after.run_count == 1
    assert after.last_status == "success"
    assert after.last_run is not None
    manager: FakeManager = scheduler._manager  # type: ignore[assignment]
    assert manager.spawned[0]["prompt"] == "run it"
    assert manager.spawned[0]["background"] is True
    assert manager.spawned[0]["bypass_queue"] is True


async def test_a_firing_one_shot_disables_itself_before_spawning(
    scheduler: SubagentScheduler, store: ScheduleStore
) -> None:
    future = (datetime.now() + timedelta(seconds=30)).isoformat()
    store.add(_job(schedule_type="once", schedule=future))
    scheduler.start(store)

    await _fire(scheduler, "job-1")

    after = store.get("job-1")
    assert after is not None
    assert after.enabled is False
    assert after.run_count == 1


async def test_an_unknown_agent_type_is_recorded_as_an_error(
    scheduler: SubagentScheduler, store: ScheduleStore
) -> None:
    store.add(_job(subagent_type="ghost"))
    scheduler.start(store)

    await _fire(scheduler, "job-1")

    after = store.get("job-1")
    assert after is not None
    assert after.last_status == "error"
    assert after.run_count == 0, "a run that never started is not counted"


async def test_a_failed_spawn_leaves_the_scheduler_alive(store: ScheduleStore, tmp_path: Path) -> None:
    manager = FakeManager(spawn_raises=True)
    scheduler = SubagentScheduler(manager)  # type: ignore[arg-type]
    store.add(_job())
    scheduler.start(store)

    await _fire(scheduler, "job-1")

    after = store.get("job-1")
    assert after is not None and after.last_status == "error"
    assert scheduler.is_active()


async def test_a_failing_run_marks_the_job_as_errored(tmp_path: Path, store: ScheduleStore) -> None:
    manager = FakeManager(final_status="error")
    scheduler = SubagentScheduler(manager)  # type: ignore[arg-type]
    store.add(_job())
    scheduler.start(store)

    await _fire(scheduler, "job-1")

    after = store.get("job-1")
    assert after is not None
    assert after.last_status == "error"
    assert after.run_count == 1


async def test_a_cancelled_run_leaves_the_record_alone(store: ScheduleStore) -> None:
    class CancelManager(FakeManager):
        async def _finish(self, run: FakeRun) -> None:
            raise asyncio.CancelledError

    scheduler = SubagentScheduler(CancelManager())  # type: ignore[arg-type]
    store.add(_job())
    scheduler.start(store)

    scheduler._on_fire("job-1")
    for task in list(scheduler._tasks):
        await task  # the scheduler absorbs the cancellation, so this completes

    after = store.get("job-1")
    assert after is not None
    assert after.last_status == "running", "shutdown mid-run keeps the prior state"
    assert after.run_count == 0


# -- removal and shutdown -----------------------------------------------------


async def test_removing_a_job_cancels_its_timer(scheduler: SubagentScheduler, store: ScheduleStore) -> None:
    scheduler.start(store)
    scheduler.add_job(name="gone", description="d", schedule="1h", subagent_type="general", prompt="p")
    handle = scheduler._timers["job-1"]

    assert scheduler.remove_job("absent") is False
    assert scheduler.remove_job("job-1") is True

    assert handle.cancelled() is True
    assert "job-1" not in scheduler._timers
    assert store.get("job-1") is None


async def test_stop_cancels_timers_and_releases_the_store(
    scheduler: SubagentScheduler, store: ScheduleStore
) -> None:
    scheduler.start(store)
    scheduler.add_job(name="live", description="d", schedule="1h", subagent_type="general", prompt="p")
    handle = scheduler._timers["job-1"]

    scheduler.stop()

    assert handle.cancelled() is True
    assert scheduler.is_active() is False
    assert scheduler.list() == []
    scheduler.stop()  # idempotent
