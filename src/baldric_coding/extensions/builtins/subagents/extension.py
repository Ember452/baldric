"""Subagents extension for Baldric, ported from tintinweb/pi-subagents.

Registers an `agent` tool that spawns autonomous subagents in-process (a
scoped `CodingSession` with its own tools and system prompt), a
`get_subagent_result` tool for background runs, a `steer_subagent` tool for
redirecting live runs, and an `/agents` command.

Foreground agents block and return their final assistant text. Background
agents return an id immediately and deliver a `<task-notification>` back into
the parent conversation when they finish. Only background agents count toward
the `maxConcurrent` limit; excess background spawns are queued FIFO and started
as slots free up.

Install by copying this directory into `~/.baldric/extensions/subagents/`, or run:

    baldric -e examples/extensions/subagents
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from baldric_coding import (
    CodingSession,
    CodingSessionConfig,
    load_provider_settings,
    resolve_provider_selection,
)
from baldric_coding.config.paths import BaldricPaths
from baldric_coding.context.thinking import THINKING_LEVELS, ThinkingLevel
from baldric_coding.extensions import ExtensionAPI
from baldric_coding.providers.runtime import create_model_provider
from baldric_coding.tools.registry import create_coding_tools
from baldric_protocol.messages import AssistantMessage, TextContent
from baldric_protocol.session import SessionEntry
from baldric_protocol.tools import AgentTool, AgentToolResult, ToolCancellationToken, ToolUpdateCallback
from baldric_protocol.types import JSONValue

from .agents import AgentDefinition, format_agent_type_list, load_agent_definitions
from .agents_menu import (
    show_agents_menu,
    supports_menu,
)
from .fork import ForkCapture, build_fork_entries, capture_fork, wrap_fork_task
from .group_join import DEFAULT_TIMEOUT, STRAGGLER_TIMEOUT, GroupJoinManager
from .memory import prepare_memory
from .notification_format import (
    COMPLETION_NOTICE,
    GROUP_RESULT_CHARS,
    _duration_ms,
    _notification_renderer,
    build_notification_details,
    format_background_spawn,
    format_group_notification,
    format_live_stats,
    format_run_summary,
    format_task_notification,
    format_usage_parts,
    lifetime_tokens,
    render_agent_call,
    render_get_result_call,
    render_steer_call,
)
from .notification_render import render_agent_result
from .output_file import OutputFileWriter, output_file_path, sweep_transcripts
from .prompts import (
    build_child_system_prompt,
    build_parent_context,
    detect_environment,
    inherited_resource_paths,
    resolve_skill_blocks,
)
from .schedule import SubagentScheduler
from .schedule_store import ScheduleStore, resolve_store_path
from .settings import SubagentSettings, load_subagent_settings
from .worktree import (
    WORKTREE_ERROR_MESSAGE,
    Worktree,
    cleanup_worktree,
    create_worktree,
    prune_worktrees,
    worktree_notice,
)

if TYPE_CHECKING:
    from baldric_coding.events import CodingSessionEvent
    from baldric_coding.extensions import ExtensionCommandContext, ExtensionContext

    from .ui import SubagentUiController

# Fit-or-fetch caps for the model-visible completion notifications: a result
# that fits is included whole; a longer one is omitted entirely (with a
# get_subagent_result pointer) rather than truncated — a partial preview
# tempts the parent to act on incomplete information instead of fetching.
# Display-only budget for the foreground card's expanded view (Ctrl+O). More
# generous than the notification previews above, which also enter the model's
# context: the old generic result block showed the full text, so a tight cap
# here would be a regression.
FOREGROUND_RESULT_CHARS = 6_000
RECORD_RESULT_CHARS = 4_000
BATCH_DEBOUNCE_SECONDS = 0.1
NUDGE_HOLD_SECONDS = 0.2
GROUP_TIMEOUT_SECONDS = DEFAULT_TIMEOUT
STRAGGLER_TIMEOUT_SECONDS = STRAGGLER_TIMEOUT
STALE_AFTER_SECONDS = 600.0
TERMINAL_STATUSES = ("completed", "steered", "aborted", "error", "cancelled")
# Event types that change what a viewer would show (session.messages / status).
# Streaming (message_update) is skipped: it never touches session.messages, so
# pushing on it would redraw identical content on every token. Errors need no
# entry of their own: they arrive as assistant messages with stop_reason
# "error"/"aborted", i.e. through message_end.
RUN_PUSH_EVENTS = frozenset({"message_end", "tool_execution_start", "tool_execution_end", "turn_end"})
SOFT_LIMIT_MESSAGE = "You have reached your turn limit. Wrap up immediately — provide your final answer now."


class _MemoryStorage:
    """Append-only in-memory storage for subagent sessions."""

    def __init__(self) -> None:
        self.entries: list[SessionEntry] = []

    async def append(self, entry: SessionEntry) -> None:
        self.entries.append(entry)

    async def append_batch(self, entries: Sequence[SessionEntry]) -> None:
        # The storage protocol makes the batch the durable transaction boundary;
        # for an in-memory list extending it is already all-or-nothing.
        self.entries.extend(entries)

    async def read_all(self) -> list[SessionEntry]:
        return list(self.entries)


@dataclass(slots=True)
class AgentRun:
    """State of one spawned subagent."""

    agent_id: str
    agent_type: str
    description: str
    prompt: str
    background: bool
    status: str = "running"
    result_text: str = ""
    error: str | None = None
    turns: int = 0
    tool_calls: int = 0
    revision: int = 0
    task: asyncio.Task[None] | None = None
    session: CodingSession | None = None
    provider: object | None = None
    result_consumed: bool = False
    started_at: float | None = None
    completed_at: float | None = None
    context_tokens: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_cache_write: int = 0
    # Terminal error carried by the last assistant message seen so far. Only a
    # tentative signal while the run is live: baldric (like pi) can recover from a
    # mid-run overflow error via compaction + auto-retry, so a later successful
    # assistant message clears it and the final verdict is taken once the event
    # stream is exhausted (never mid-stream).
    pending_error: str | None = None
    # Resolved model id actually running this agent (None while queued).
    # requested_model below is only the tool-param request, which frontmatter
    # may override — the viewer header shows this resolved value.
    model: str | None = None
    requested_provider: str | None = None
    requested_model: str | None = None
    requested_thinking: str | None = None
    requested_max_turns: int | None = None
    max_turns: int | None = None
    grace_turns: int = 5
    soft_limit_reached: bool = False
    aborted: bool = False
    pending_steers: list[str] = field(default_factory=list)
    # Live stats ticker (foreground runs only): the executor's on_update
    # callback, set for the duration of the blocking tool call. Takes a partial
    # AgentToolResult (pi's AgentToolUpdateCallback). `last_progress` dedups so
    # the line only repaints when a stat actually changed.
    on_update: Callable[[AgentToolResult], None] | None = None
    last_progress: str = ""
    join_mode: str | None = None
    requested_isolation: str | None = None
    # `isolated: true` (pi's param): spawn the child without extensions, so
    # it gets core tools only and cannot spawn subagents of its own.
    requested_isolated: bool = False
    # Parent-session snapshot for fork runs, captured at tool-call time and
    # cleared once the seed entries are built (it pins a full transcript copy).
    fork_capture: ForkCapture | None = None
    # Seeded parent message count for fork runs; None for every other agent
    # type. Sizes the output-file skip so the seeded prefix stays out of it.
    fork_inherited: int | None = None
    worktree: Worktree | None = None
    used_worktree: bool = False
    output_writer: OutputFileWriter | None = None
    output_file: str | None = None
    # Per-run push listeners (component seam): fired when this run's content or
    # status changes so an open conversation viewer can re-render. The direct
    # analog of pi's ``session.subscribe(() => tui.requestRender())``. Safe to
    # call widget methods from here because runs are asyncio tasks on the TUI
    # event loop (see the design's push-refresh invariant).
    listeners: list[Callable[[], None]] = field(default_factory=list)

    @property
    def has_usage(self) -> bool:
        """Whether the provider reported any billed usage (pi gates on total > 0).

        Usage is always present on new-protocol assistant messages (zeros when
        the provider reports nothing), so presence can't be the signal anymore;
        a nonzero lifetime total is. Zero-usage runs fall back to the chars/4
        context estimate everywhere this gate is checked.
        """
        return lifetime_tokens(self) > 0


class SubagentManager:
    """Spawns and tracks subagent runs for one Baldric session."""

    def __init__(self, api: ExtensionAPI) -> None:
        self._api = api
        self._runs: dict[str, AgentRun] = {}
        self._counter = 0
        self._settings: SubagentSettings | None = None
        self._running_background = 0
        self._queue: list[tuple[AgentRun, AgentDefinition]] = []
        self._shutting_down = False
        self._batch: list[AgentRun] = []
        self._batch_timer: asyncio.TimerHandle | None = None
        self._batch_counter = 0
        self._group_join: GroupJoinManager | None = None
        self._worktree_repos: set[str] = set()
        self._nudge_timers: dict[str, asyncio.TimerHandle] = {}
        # Roster change signal: fired when the run list or a run's status
        # changes. On the component seam it is wired (in setup()) to the UI
        # controller's on_change, which refreshes the extension's own strip
        # and any open viewer. (The name predates the seam migration: it once
        # pointed at baldric core's removed transcript-sources callback.)
        self.sources_changed: Callable[[], None] | None = None

    def _notify_sources(self) -> None:
        callback = self.sources_changed
        if callback is not None:
            with contextlib.suppress(Exception):
                callback()

    def _notify_run(self, run: AgentRun) -> None:
        """Fire a run's per-run listeners (viewer push); guarded per listener."""
        for listener in tuple(run.listeners):
            with contextlib.suppress(Exception):
                listener()

    @property
    def runs(self) -> dict[str, AgentRun]:
        return self._runs

    @property
    def max_concurrent(self) -> int:
        return self._get_settings().max_concurrent

    def definitions(self) -> dict[str, AgentDefinition]:
        return load_agent_definitions(
            self._api.context.paths,
            self._api.context.cwd,
            project_trusted=self._api.context.project_trusted,
        )

    def _get_settings(self) -> SubagentSettings:
        if self._settings is None:
            self._settings = load_subagent_settings(
                self._api.context.paths,
                self._api.context.cwd,
                project_trusted=self._api.context.project_trusted,
            )
        return self._settings

    def spawn(
        self,
        *,
        agent_type: AgentDefinition,
        prompt: str,
        description: str,
        background: bool,
        max_turns: int | None = None,
        isolation: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        thinking: str | None = None,
        bypass_queue: bool = False,
        fork_capture: ForkCapture | None = None,
        isolated: bool = False,
    ) -> AgentRun:
        self._counter += 1
        run = AgentRun(
            agent_id=f"agent-{self._counter}",
            agent_type=agent_type.name,
            description=description,
            prompt=prompt,
            background=background,
            requested_provider=provider,
            requested_model=model,
            requested_thinking=thinking,
            requested_max_turns=max_turns,
            requested_isolation=isolation,
            requested_isolated=isolated,
            fork_capture=fork_capture,
            fork_inherited=len(fork_capture.messages) if fork_capture else None,
        )
        run.output_writer = OutputFileWriter(
            output_file_path(
                self._api.context.cwd,
                self._api.context.session_id,
                run.agent_id,
                # Locations come from the injected paths, as everywhere else in
                # this capability, so an alternate BALDRIC_HOME is honoured.
                home=self._api.context.paths.home,
                # transcriptRetentionDays: 0 opts out of durable storage;
                # an unset value keeps durable transcripts indefinitely.
                durable=self._get_settings().transcript_retention_days != 0,
            ),
            run.agent_id,
            self._api.context.cwd,
            # Seeded parent messages stay out of the durable transcript.
            inherited=run.fork_inherited or 0,
        )
        run.output_file = str(run.output_writer.path)
        self._runs[run.agent_id] = run
        if background:
            run.join_mode = self._get_settings().default_join_mode
            if run.join_mode in ("smart", "group"):
                self._batch.append(run)
                self._schedule_batch_finalize()
        if background and not bypass_queue and self._running_background >= self.max_concurrent:
            run.status = "queued"
            self._queue.append((run, agent_type))
            self._notify_sources()
            return run
        self._start(run, agent_type)
        self._notify_sources()
        return run

    def _get_group_join(self) -> GroupJoinManager:
        if self._group_join is None:
            self._group_join = GroupJoinManager(
                self._deliver_group_notification,
                group_timeout=GROUP_TIMEOUT_SECONDS,
                straggler_timeout=STRAGGLER_TIMEOUT_SECONDS,
            )
        return self._group_join

    def _schedule_batch_finalize(self) -> None:
        if self._batch_timer is not None:
            self._batch_timer.cancel()
        self._batch_timer = asyncio.get_running_loop().call_later(
            BATCH_DEBOUNCE_SECONDS, self._finalize_batch
        )

    def _finalize_batch(self) -> None:
        self._batch_timer = None
        batch = self._batch
        self._batch = []
        if len(batch) >= 2:
            self._batch_counter += 1
            self._get_group_join().register_group(
                f"batch-{self._batch_counter}", [run.agent_id for run in batch]
            )
            for run in batch:
                if run.status in TERMINAL_STATUSES and run.status != "cancelled":
                    self._get_group_join().on_agent_complete(run)
            return
        for run in batch:
            if run.status in TERMINAL_STATUSES and run.status != "cancelled":
                self._deliver_background_result(run)

    def _start(self, run: AgentRun, definition: AgentDefinition) -> None:
        run.status = "running"
        run.started_at = time.monotonic()
        if run.background:
            self._running_background += 1
        run.task = asyncio.get_running_loop().create_task(self._run_agent(run, definition))

    def _drain_queue(self) -> None:
        if self._shutting_down:
            return
        while self._queue and self._running_background < self.max_concurrent:
            run, definition = self._queue.pop(0)
            if run.status != "queued":
                continue
            self._start(run, definition)

    async def resume(self, run: AgentRun, prompt: str) -> None:
        """Resume a finished run's live session with a follow-up prompt."""
        session = run.session
        assert session is not None
        run.status = "running"
        run.error = None
        run.pending_error = None
        run.result_text = ""
        run.aborted = False
        run.soft_limit_reached = False
        run.started_at = time.monotonic()
        run.completed_at = None
        self._notify_sources()
        self._notify_run(run)
        final_text: list[str] = []
        try:
            async for event in session.prompt(prompt):
                self._observe(run, event, final_text)
            run.result_text = final_text[-1] if final_text else ""
            run.context_tokens = session.context_token_estimate
            self._finalize_status(run)
        except asyncio.CancelledError:
            # The resume runs inline in the tool coroutine, so a parent Esc
            # (hard-cancel) lands here; settle the record before re-raising.
            run.status = "cancelled"
            raise
        except Exception as exc:  # noqa: BLE001 - report subagent failures as results
            run.status = "error"
            run.error = str(exc)
        finally:
            await self._persist_record(run)
            run.completed_at = time.monotonic()
            self._notify_sources()
            self._notify_run(run)

    async def shutdown(self) -> None:
        self._shutting_down = True
        try:
            if self._batch_timer is not None:
                self._batch_timer.cancel()
                self._batch_timer = None
            self._batch.clear()
            if self._group_join is not None:
                self._group_join.cancel_all()
            for handle in self._nudge_timers.values():
                handle.cancel()
            self._nudge_timers.clear()
            for run, _definition in self._queue:
                if run.status == "queued":
                    run.status = "cancelled"
                    run.completed_at = time.monotonic()
            self._queue.clear()
            pending: list[asyncio.Task[None]] = []
            for run in self._runs.values():
                if run.task is not None and not run.task.done():
                    if run.session is not None:
                        run.session.cancel()
                    run.task.cancel()
                    pending.append(run.task)
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for run in self._runs.values():
                await self.close_run(run)
            for repo in self._worktree_repos:
                with contextlib.suppress(Exception):
                    await prune_worktrees(Path(repo))
            self._worktree_repos.clear()
        finally:
            self._shutting_down = False
            self._notify_sources()

    async def evict_stale(self) -> None:
        """Close sessions of consumed terminal runs older than the staleness cap."""
        now = time.monotonic()
        for run in self._runs.values():
            if run.session is None and run.provider is None:
                continue
            if run.status not in TERMINAL_STATUSES or not run.result_consumed:
                continue
            if run.completed_at is None or now - run.completed_at < STALE_AFTER_SECONDS:
                continue
            await self.close_run(run)

    async def close_run(self, run: AgentRun) -> None:
        session = run.session
        if session is not None:
            with contextlib.suppress(Exception):  # best-effort cleanup
                await session.aclose()
        closer = getattr(run.provider, "aclose", None)
        if closer is not None:
            with contextlib.suppress(Exception):  # best-effort cleanup
                await closer()
        run.session = None
        run.provider = None

    async def _run_agent(self, run: AgentRun, definition: AgentDefinition) -> None:
        try:
            await self._execute(run, definition)
        except asyncio.CancelledError:
            run.status = "cancelled"
            raise
        except Exception as exc:  # noqa: BLE001 - report subagent failures as results
            run.status = "error"
            run.error = str(exc)
        finally:
            await self._finalize_run(run)
            run.completed_at = time.monotonic()
            self._notify_sources()
            self._notify_run(run)
            if run.background:
                self._running_background -= 1
                self._drain_queue()
                self._handle_background_completion(run)

    async def _finalize_run(self, run: AgentRun) -> None:
        if run.output_writer is not None and run.session is not None:
            with contextlib.suppress(Exception):
                await run.output_writer.flush(run.session.messages)
        if run.worktree is not None:
            await self._cleanup_worktree(run)
        await self._persist_record(run)

    async def _cleanup_worktree(self, run: AgentRun) -> None:
        worktree = run.worktree
        run.worktree = None
        assert worktree is not None
        try:
            result = await cleanup_worktree(worktree, run.description)
        except Exception:  # noqa: BLE001 - worktree cleanup is best-effort
            return
        notice = worktree_notice(result)
        if notice:
            run.result_text += notice
            # Error terminals surface run.error, not result_text — annotate both
            # so saved or preserved work is never invisible.
            if run.status == "error":
                run.error = (run.error or "subagent failed") + notice

    async def _persist_record(self, run: AgentRun) -> None:
        with contextlib.suppress(Exception):  # record persistence is best-effort
            await self._api.append_entry(
                "subagents:record",
                {
                    "id": run.agent_id,
                    "type": run.agent_type,
                    "description": run.description,
                    "status": run.status,
                    "result": run.result_text[:RECORD_RESULT_CHARS],
                    "error": run.error,
                    "turns": run.turns,
                    "tool_calls": run.tool_calls,
                    "total_tokens": lifetime_tokens(run) if run.has_usage else None,
                },
            )

    def _handle_background_completion(self, run: AgentRun) -> None:
        if run.status == "cancelled":
            return
        if run.join_mode in ("smart", "group"):
            if any(pending is run for pending in self._batch):
                return  # the batch finalizer will route this completion
            if self._get_group_join().on_agent_complete(run) != "pass":
                return
        self._deliver_background_result(run)

    async def _execute(self, run: AgentRun, definition: AgentDefinition) -> None:
        settings = self._get_settings()
        cwd = self._api.context.cwd
        # Create the provider before the first await so concurrent spawns
        # claim providers in spawn order (tests script provider sequences).
        # Frontmatter wins over the tool param, per pi precedence.
        # When neither the agent definition nor the tool call specifies a
        # provider/model, inherit the parent session's active selection so
        # subagents naturally match the caller instead of falling back to
        # the durable Baldric settings default.
        parent_provider = self._api.context.provider_name
        parent_model = self._api.context.model
        provider_settings = load_provider_settings()
        if definition.fork:
            capture = run.fork_capture
            assert capture is not None
            # A fork resolves against the snapshot taken at tool-call time,
            # not the live parent: a queued fork must run the model the
            # parent had when it forked (a /model switch in between would
            # otherwise break the shared prompt cache).
            selection = resolve_provider_selection(
                provider_settings,
                provider_name=capture.provider_name,
                model=capture.model,
            )
            thinking_level = capture.thinking_level
        else:
            selection = resolve_provider_selection(
                provider_settings,
                provider_name=run.requested_provider or parent_provider,
                model=definition.model or run.requested_model or parent_model,
            )
            # An explicit level (frontmatter or parameter) passes through
            # untouched: it is a stated intent, and the provider reports it when
            # the model cannot honour it.
            #
            # With no explicit level, a child on the parent's own provider and
            # model continues at the parent's live level. The hardcoded default
            # this replaces failed outright on models that do not offer it, and
            # made a child think less than the conversation that spawned it.
            #
            # A child on a different model gets nothing, which is the host's "no
            # thinking parameter" case - the model's own default then applies
            # (provider_config.py:1775, 1809 return early on None). The parent's
            # level says nothing about that model's supported set.
            explicit = definition.thinking or run.requested_thinking
            if explicit:
                thinking_level = explicit
            elif selection.provider.name == parent_provider and selection.model == parent_model:
                thinking_level = self._api.context.thinking_level
            else:
                thinking_level = None
        provider = create_model_provider(
            selection.provider,
            model=selection.model,
            # Forks run the parent's live thinking level (captured at
            # tool-call time). Any other level would put a different thinking
            # config in the fork's request and cost (part of) the shared
            # prompt cache. A capture without the level leaves the model's own
            # default in place.
            thinking_level=cast("ThinkingLevel | None", thinking_level),
        )
        run.provider = provider
        run.model = selection.model
        # A viewer opened on the queued run painted its header without a
        # model; push so it picks the resolved one up immediately.
        self._notify_run(run)
        child_cwd = cwd
        if (definition.isolation or run.requested_isolation) == "worktree":
            worktree = await create_worktree(cwd, run.agent_id)
            if worktree is None:
                raise RuntimeError(WORKTREE_ERROR_MESSAGE)
            run.worktree = worktree
            run.used_worktree = True
            self._worktree_repos.add(str(worktree.repo))
            child_cwd = worktree.work_path
        if run.output_writer is not None:
            await run.output_writer.write_initial(run.prompt)
        storage = _MemoryStorage()
        extra_config: dict[str, Any] = {}
        memory_block: str | None = None
        memory_rw = False
        if definition.fork:
            # Fork: seed the child storage with the parent transcript and keep
            # the parent system prompt byte-identical (shared prompt cache).
            # No memory, skill preloads, or tool gating — the fork is the
            # parent session continued, minus recursive subagent tools.
            assert capture is not None
            storage.entries = build_fork_entries(capture, child_cwd)
            prompt_text: str | None = capture.system_prompt
            append_active = True
            # The snapshot pins a full transcript copy; the seed has it now.
            run.fork_capture = None
        else:
            skill_blocks = resolve_skill_blocks(
                definition.skills if isinstance(definition.skills, tuple) else None,
                self._api.context.paths,
                cwd,
                project_trusted=self._api.context.project_trusted,
            )
            if definition.memory is not None:
                memory_rw = definition.tools is None or bool({"write", "edit"} & set(definition.tools))
                memory_block = await prepare_memory(
                    definition.name,
                    definition.memory,
                    self._api.context.paths,
                    cwd,
                    read_write=memory_rw,
                    project_trusted=self._api.context.project_trusted,
                )
            parent_prompt: str | None = None
            if definition.prompt_mode == "append":
                try:
                    parent_prompt = self._api.context.system_prompt
                except Exception:  # noqa: BLE001 - fall back to replace-mode assembly
                    parent_prompt = None
            environment = ""
            if definition.prompt_mode == "append" and parent_prompt:
                environment = await detect_environment(child_cwd)
            prompt_text = build_child_system_prompt(
                definition,
                parent_prompt=parent_prompt,
                environment=environment,
                skill_blocks=skill_blocks,
                memory_block=memory_block,
            )
            append_active = definition.prompt_mode == "append" and bool(parent_prompt)
            # skills: none/false disables skill discovery; a named CSV also
            # disables it so preloaded bodies aren't double-listed in the index
            # (pi sets noSkills for both).
            if definition.skills is False or isinstance(definition.skills, tuple):
                extra_config["skills_enabled"] = False
        session = await CodingSession.load(
            CodingSessionConfig(
                provider=provider,
                model=selection.model,
                cwd=child_cwd,
                # Forward the parent's decision: a child resolving trust on its
                # own has no way to ask, and the default lands on declined, which
                # silently drops project skills and context files from it.
                trust_override=("approve" if self._api.context.project_trusted else "decline"),
                # Inherit the parent's shell selection so a child runs bash
                # commands in the same shell the user configured; otherwise the
                # child's bash tool silently defaults to 'auto' and a user's
                # explicit choice (e.g. bash on Windows) would not apply.
                shell=self._api.context.shell,
                shell_command_prefix=self._api.context.shell_command_prefix,
                storage=storage,
                system=prompt_text if append_active else None,
                custom_system_prompt=None if append_active else prompt_text,
                # Children always discover skills natively (Baldric defaults
                # resource paths from the session cwd). What `skills: true`
                # adds here is the inherited roots and trust flag: Baldric
                # treats a resource plan as destination-bound and re-resolves
                # the project directory from the child's own cwd
                # (resources.py:292-308), so a worktree child reads the
                # worktree's copy of the project resources.
                resource_paths=(
                    inherited_resource_paths(
                        self._api.context.paths,
                        cwd,
                        project_trusted=self._api.context.project_trusted,
                    )
                    if definition.skills is True
                    else None
                ),
                provider_name=selection.provider.name,
                auto_compact_enabled=False,
                # Children load extensions natively (pi parity), so subagents
                # can spawn subagents and a fork's tool pool matches the
                # parent's (shared prompt cache). `isolated: true` opts a
                # child out, restoring a core-tools-only session - see the
                # filter below, because a switch that only covers filesystem
                # extensions cannot remove a capability that ships built in.
                extensions_enabled=not run.requested_isolated,
                # Children never get MCP: every child spawning its own server
                # processes is waste (the composition-level gate, see the
                # session config field). Revisit with a shared supervisor.
                disabled_built_in_extensions=frozenset({"mcp"}),
                # Inherit the parent's approval gate: a child session that
                # dropped it would let subagents run mutating tools behind the
                # user's back while approval mode is on.
                before_tool_call=self._api.context.before_tool_call,
                **extra_config,
            )
        )
        run.session = session
        for message in run.pending_steers:
            session.queue_steering_message(message)
        run.pending_steers.clear()
        run.max_turns = _effective_max_turns(
            definition.max_turns, run.requested_max_turns, settings.default_max_turns
        )
        run.grace_turns = settings.grace_turns
        if run.requested_isolated:
            # `extensions_enabled=False` covers filesystem extensions; bundled
            # capabilities load whatever that switch says, so an isolated child
            # would otherwise still see the agent tools it asked not to have.
            # Restricting the pool to the core coding tools is what keeps the
            # promise, and it is the same post-load narrowing the per-type
            # `tools:` gate below already uses.
            core_names = {tool.name for tool in create_coding_tools(cwd=child_cwd)}
            session._harness.config.tools = [  # noqa: SLF001 - scoped tool gating
                tool for tool in session._harness.config.tools if tool.name in core_names
            ]
        if definition.tools is not None:
            allowed = set(definition.tools)
            if memory_block is not None:
                allowed |= {"read", "write", "edit"} if memory_rw else {"read"}
            session._harness.config.tools = [  # noqa: SLF001 - scoped tool gating
                tool for tool in session._harness.config.tools if tool.name in allowed
            ]
        final_text: list[str] = []
        async for event in session.prompt(run.prompt):
            self._observe(run, event, final_text)
            if event.type == "turn_end":
                self._enforce_turn_limit(run)
                run.context_tokens = session.context_token_estimate
                if run.output_writer is not None:
                    await run.output_writer.flush(session.messages)
        run.result_text = final_text[-1] if final_text else ""
        run.context_tokens = session.context_token_estimate
        self._finalize_status(run)

    def _finalize_status(self, run: AgentRun) -> None:
        """Decide a run's terminal status once its event stream is exhausted.

        Never decided mid-stream (pi semantics): a message_end with
        stop_reason "error" may be recovered by overflow compaction +
        auto-retry, so only the error still pending at stream end counts.
        """
        if run.aborted:
            run.status = "aborted"
        elif run.pending_error is not None:
            run.status = "error"
            run.error = run.pending_error
        elif run.status == "running":
            run.status = "steered" if run.soft_limit_reached else "completed"

    def _enforce_turn_limit(self, run: AgentRun) -> None:
        if run.max_turns is None or run.session is None:
            return
        if not run.soft_limit_reached and run.turns >= run.max_turns:
            run.soft_limit_reached = True
            run.session.queue_steering_message(SOFT_LIMIT_MESSAGE)
        elif run.soft_limit_reached and not run.aborted and run.turns >= run.max_turns + run.grace_turns:
            run.aborted = True
            run.session.cancel()

    def _observe(self, run: AgentRun, event: CodingSessionEvent, final_text: list[str]) -> None:
        run.revision += 1
        if event.type == "turn_end":
            run.turns += 1
        elif event.type == "tool_execution_start":
            run.tool_calls += 1
        elif event.type == "message_end":
            message = event.message
            # Equivalent to the role check this replaces: every message class in
            # the union carries a distinct role literal, and only AssistantMessage
            # has "assistant" (messages.py:131-268). Testing the class lets the
            # union narrow so usage/stop_reason/text resolve.
            if isinstance(message, AssistantMessage):
                # Real billed usage. Lifetime sum of input + output +
                # cache_write per response; cache reads are excluded because
                # each turn re-reads the whole cached prefix, so summing them
                # counts the prefix N times (pi issue #38).
                usage = message.usage
                run.tokens_input += usage.input
                run.tokens_output += usage.output
                run.tokens_cache_write += usage.cache_write
                # Terminal errors ride the assistant message now (pi protocol:
                # there is no separate error event). Tentative until the stream
                # ends: an overflow error can be compacted away and retried, in
                # which case the next assistant message clears it.
                if message.stop_reason == "error":
                    run.pending_error = message.error_message or "subagent provider error"
                else:
                    run.pending_error = None
                text = message.text.strip()
                if text:
                    final_text.append(text)
        self._emit_progress(run, event)
        if event.type in RUN_PUSH_EVENTS:
            self._notify_run(run)

    def _emit_progress(self, run: AgentRun, event: CodingSessionEvent) -> None:
        """Update the live stats ticker under the tool row (foreground runs).

        One stable, cumulative line in the completion card's stats vocabulary
        (turns · tool uses · tokens), so the running row morphs into the
        finished card — unlike the per-event activity echo this replaces
        (dropped as noise in d0d5ac8), the line only changes when a stat does.
        """
        if run.on_update is None:
            return
        if event.type not in ("turn_end", "tool_execution_start", "message_end"):
            return
        message = format_live_stats(run)
        if not message or message == run.last_progress:
            return
        run.last_progress = message
        data: dict[str, JSONValue] = {
            "agent_id": run.agent_id,
            "turns": run.turns,
            "tool_uses": run.tool_calls,
        }
        if run.has_usage:
            data["total_tokens"] = lifetime_tokens(run)
        with contextlib.suppress(Exception):
            run.on_update(AgentToolResult(content=[TextContent(text=message)], details=data))

    def _deliver_background_result(self, run: AgentRun) -> None:
        if run.result_consumed:
            return
        self._schedule_nudge(run.agent_id, lambda: self._send_individual_nudge(run))

    def _deliver_group_notification(self, records: list[AgentRun], partial: bool) -> None:
        key = "group:" + ",".join(run.agent_id for run in records)
        self._schedule_nudge(key, lambda: self._send_group_notification(records, partial))

    def _schedule_nudge(self, key: str, send: Callable[[], None]) -> None:
        """Hold a notification briefly so a prompt result read can cancel it."""
        existing = self._nudge_timers.pop(key, None)
        if existing is not None:
            existing.cancel()

        def fire() -> None:
            self._nudge_timers.pop(key, None)
            send()

        self._nudge_timers[key] = asyncio.get_running_loop().call_later(NUDGE_HOLD_SECONDS, fire)

    def cancel_nudge(self, agent_id: str) -> None:
        """Cancel a pending individual nudge for a consumed run."""
        handle = self._nudge_timers.pop(agent_id, None)
        if handle is not None:
            handle.cancel()

    def _send_individual_nudge(self, run: AgentRun) -> None:
        if run.result_consumed:
            return
        try:
            self._api.notify(
                f"Subagent {run.agent_id} ({run.description}) {run.status}.",
                "info" if run.status in ("completed", "steered") else "warning",
            )
            self._deliver_notification(
                f"{format_task_notification(run)}\n{COMPLETION_NOTICE}",
                build_notification_details(run),
            )
        except Exception:  # noqa: BLE001 - timer callbacks must never crash the loop
            pass

    def _send_group_notification(self, records: list[AgentRun], partial: bool) -> None:
        unconsumed = [run for run in records if not run.result_consumed]
        if not unconsumed:
            return
        try:
            details = build_notification_details(unconsumed[0], GROUP_RESULT_CHARS)
            details["others"] = [
                build_notification_details(run, GROUP_RESULT_CHARS) for run in unconsumed[1:]
            ]
            self._deliver_notification(
                format_group_notification(unconsumed, partial=partial),
                details,
            )
        except Exception:  # noqa: BLE001 - timer callbacks must never crash the loop
            pass

    def _deliver_notification(self, content: str, details: dict[str, JSONValue]) -> None:
        """Send as a custom message so the registered renderer draws the card."""
        self._api.send_custom_message(
            content,
            custom_type="subagent-notification",
            details=details,
            deliver_as="follow_up",
        )


def _effective_max_turns(frontmatter: int | None, param: int | None, default: int | None) -> int | None:
    """Resolve the turn limit: frontmatter wins over param wins over default."""
    raw: int | None
    if frontmatter is not None:
        raw = frontmatter
    elif param is not None:
        raw = param
    else:
        raw = default
    if raw is None or raw <= 0:
        return None
    return max(1, raw)


def setup(baldric: ExtensionAPI) -> None:
    """Register subagent tools, the /agents command, and shutdown cleanup."""
    manager = SubagentManager(baldric)
    # Notifications render as pi-style cards instead of raw
    # <task-notification> XML bubbles.
    baldric.register_message_renderer("subagent-notification", _notification_renderer)
    scheduler = SubagentScheduler(manager)

    def start_scheduler() -> None:
        # Session-scoped: the store is built once the session id is available
        # (mirrors pi, which constructs it in session_start). Scheduling is
        # non-essential — swallow failures so an unwritable .baldric/ can't break
        # the rest of the extension.
        try:
            session_id = baldric.context.session_id
            if not session_id:
                return  # id not yet available — retry on the next session_start
            store = ScheduleStore(resolve_store_path(baldric.context.paths, baldric.context.cwd, session_id))
            scheduler.start(store)
        except Exception:  # noqa: BLE001 - scheduling must never break the session
            pass

    # Component seam: the extension owns the agents strip and the
    # conversation viewer as Textual widgets mounted through the component
    # bridge. Installed lazily on session_start — NOT in setup() — because the
    # host attaches its UI bridge (making supports_components True) only after
    # CodingSession.load has already run setup() with the print-mode NullUiBridge.
    ui_controller: list[SubagentUiController] = []  # 0 or 1 element (a nonlocal-friendly cell)

    def _install_ui_components() -> None:
        # supports_components is a runtime gate, not feature detection: the
        # print-mode NullUiBridge reports False, and the extension then runs
        # dialog-only, no strip.
        components = baldric.context.ui.components
        if not components.supports_components:
            return
        # Defensive reinstall (bug fix 2): a controller can survive into the next
        # bind if a session_start arrives without a matching shutdown (or the host
        # force-cleared its slots on rebind). Tear the stale one down and mount
        # fresh widgets against the host's current slots. The host sequences the
        # same-tick teardown+reinstall, so the strip's slot never collides on its
        # id (which used to raise DuplicateIds and drop the strip).
        existing = _current_controller()
        if existing is not None:
            existing.teardown()
            ui_controller.clear()
        from .ui import SubagentUiController

        controller = SubagentUiController(manager, components)
        controller.install()
        manager.sources_changed = controller.on_change
        ui_controller.append(controller)

    def _current_controller() -> SubagentUiController | None:
        return ui_controller[0] if ui_controller else None

    async def on_session_start(event: object, context: object) -> None:
        del event, context
        if not scheduler.is_active():
            start_scheduler()
        _install_ui_components()
        # ADR 0003: age out durable transcripts. Best-effort and off-loop so
        # an enormous or slow ~/.baldric/subagents/ tree cannot delay startup.
        retention = manager._get_settings().transcript_retention_days
        if retention is not None and retention > 0:
            with contextlib.suppress(OSError):
                await asyncio.to_thread(sweep_transcripts, retention)

    async def run_agent_tool(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
        on_update: ToolUpdateCallback | None = None,
    ) -> AgentToolResult:
        del tool_call_id
        await manager.evict_stale()
        if arguments.get("schedule"):
            return await run_schedule(arguments)
        resume_id = arguments.get("resume")
        if resume_id:
            return await run_resume(str(resume_id), arguments, on_update)

        definitions = manager.definitions()
        agent_type = str(arguments.get("subagent_type", "general"))
        definition = definitions.get(agent_type)
        if definition is None:
            available = ", ".join(sorted(definitions))
            return _tool_result(
                content=f"Unknown subagent_type: {agent_type}. Available: {available}",
            )
        prompt = str(arguments.get("prompt", "")).strip()
        if not prompt:
            return _tool_result(content="prompt is required")
        description = str(arguments.get("description", "")) or f"{agent_type} agent"
        background = bool(arguments.get("run_in_background", False))
        max_turns = _coerce_max_turns(arguments.get("max_turns"))
        isolation = "worktree" if arguments.get("isolation") == "worktree" else None
        isolated = bool(arguments.get("isolated", False))
        fork_capture = None
        if definition.fork:
            # Reject, never silently ignore: a fork always runs the parent's
            # model, thinking config, and tool pool (anything else breaks the
            # shared prompt cache). Dropping a `model` param quietly would let
            # the parent believe it spawned a cheaper model while the fork
            # actually runs the parent's — a silent cost surprise.
            rejected = [name for name in ("provider", "model", "thinking", "isolated") if arguments.get(name)]
            if rejected:
                return _tool_result(
                    content=f"A fork cannot take {', '.join(rejected)} — it"
                    " always runs the parent's provider, model, thinking"
                    " config, and tool pool (a different one would break the"
                    " shared prompt cache). Omit the parameter(s), or spawn a"
                    " different agent type with inherit_context=true to use"
                    " another provider/model with the conversation context.",
                )
            # Captured at tool-call time (like inherit_context): queued forks
            # see the conversation as of this call. inherit_context stays
            # accepted — the fork fulfills exactly that request.
            fork_capture = capture_fork(baldric.context)
            prompt = wrap_fork_task(prompt, worktree=isolation == "worktree")
        inherit = arguments.get("inherit_context")
        if inherit is None:
            inherit = definition.inherit_context
        if inherit and not definition.fork:
            # Captured at spawn time (pi semantics): the digest reflects the
            # parent conversation as of this tool call, even for queued runs.
            parent_context = build_parent_context(baldric.context.transcript)
            if parent_context:
                prompt = parent_context + prompt
        provider = str(arguments.get("provider")) if arguments.get("provider") else None
        model = str(arguments.get("model")) if arguments.get("model") else None
        thinking = arguments.get("thinking")
        if thinking is not None:
            thinking = str(thinking)
            if thinking not in THINKING_LEVELS:
                return _tool_result(
                    content=f"Invalid thinking level: {thinking}."
                    f" Valid options: {', '.join(THINKING_LEVELS)}",
                )

        run = manager.spawn(
            agent_type=definition,
            prompt=prompt,
            description=description,
            background=background,
            max_turns=max_turns,
            isolation=isolation,
            provider=provider,
            model=model,
            thinking=thinking,
            fork_capture=fork_capture,
            isolated=isolated,
        )
        if background:
            return _tool_result(
                content=format_background_spawn(run, manager.max_concurrent),
                # A "background" card: the row confirms the spawn in one dim
                # line; completion arrives later as a notification card.
                details={
                    "status": "background",
                    "agent_id": run.agent_id,
                    "queued": run.status == "queued",
                    "output_file": run.output_file,
                },
            )

        async def cancel_child() -> None:
            """Stop the child and settle its record (pi's parent-abort cascade)."""
            if run.session is not None:
                run.session.cancel()
            assert run.task is not None
            run.task.cancel()
            # asyncio.wait (not `await run.task`) so the child's CancelledError
            # is never raised here — a plain suppress would also swallow a
            # cancellation aimed at THIS coroutine landing at that await.
            await asyncio.wait({run.task})
            # Settle before the async close: a cancel that lands before the
            # task first runs never reaches _run_agent's CancelledError
            # handler, and a re-cancel during close_run must not skip this.
            if run.status not in TERMINAL_STATUSES:
                run.status = "cancelled"
            if run.completed_at is None:
                run.completed_at = time.monotonic()
            await manager.close_run(run)

        # Live stats ticker: only valid while this tool call is executing, so
        # foreground-only. The try/finally clears it even when baldric hard-cancels
        # this coroutine mid-wait.
        run.on_update = on_update
        assert run.task is not None
        try:
            while not run.task.done():
                if signal is not None and signal.is_cancelled():
                    await cancel_child()
                    if run.status in ("completed", "steered"):
                        # The run beat the cancel to the finish line — report
                        # the real result, not a phantom cancellation.
                        return _foreground_result(run)
                    return _tool_result(
                        content="Subagent cancelled",
                        # Cancelled runs stay in the card family (∅ cancelled).
                        details=build_notification_details(run, FOREGROUND_RESULT_CHARS),
                    )
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            # Esc in the TUI: baldric hard-cancels this tool coroutine (the event
            # stream is torn down before the 50ms poll can see the signal), so
            # the cooperative branch above never runs. Take the child down
            # with us — otherwise it keeps running as a zombie and its result
            # is silently dropped. Background runs are untouched by design:
            # they never pass through this wait loop (pi wires the parent
            # abort signal on the foreground path only).
            await cancel_child()
            raise
        finally:
            run.on_update = None

        return _foreground_result(run)

    async def run_resume(
        agent_id: str,
        arguments: Mapping[str, JSONValue],
        on_update: ToolUpdateCallback | None = None,
    ) -> AgentToolResult:
        run = manager.runs.get(agent_id)
        if run is None:
            return _tool_result(
                content=f'Agent not found: "{agent_id}". It may have been cleaned up.',
            )
        if run.task is not None and not run.task.done():
            return _tool_result(
                content=f'Agent "{agent_id}" is still running. Use steer_subagent to redirect it.',
            )
        if run.used_worktree:
            return _tool_result(
                content=f'Agent "{agent_id}" ran in an isolated worktree that has'
                " been cleaned up; resume is not supported for worktree agents.",
            )
        if run.session is None:
            return _tool_result(
                content=f'Agent "{agent_id}" has no active session to resume.',
            )
        prompt = str(arguments.get("prompt", "")).strip()
        if not prompt:
            return _tool_result(content="prompt is required")
        run.on_update = on_update
        run.last_progress = ""
        try:
            await manager.resume(run, prompt)
        finally:
            run.on_update = None
        return _foreground_result(run)

    async def run_schedule(arguments: Mapping[str, JSONValue]) -> AgentToolResult:
        # Guards mirror pi: a scheduled job creates a fresh background agent at
        # fire time, so it is incompatible with resume, inherit_context, and a
        # foreground run.
        if arguments.get("resume"):
            return _tool_result(
                content="Cannot combine `schedule` with `resume` — schedules create fresh agents.",
            )
        if arguments.get("inherit_context"):
            return _tool_result(
                content="Cannot combine `schedule` with `inherit_context` —"
                " there is no parent conversation at fire time.",
            )
        if arguments.get("run_in_background") is False:
            return _tool_result(
                content="Cannot combine `schedule` with `run_in_background: false`"
                " — scheduled jobs always run in background.",
            )
        definitions = manager.definitions()
        agent_type = str(arguments.get("subagent_type", "general"))
        definition = definitions.get(agent_type)
        if definition is None:
            available = ", ".join(sorted(definitions))
            return _tool_result(
                content=f"Unknown subagent_type: {agent_type}. Available: {available}",
            )
        if definition.fork:
            return _tool_result(
                content="Cannot schedule a fork — there is no parent conversation to inherit at fire time.",
            )
        if not scheduler.is_active():
            return _tool_result(
                content="Scheduler is not active in this session yet."
                " Try again after the session has fully started.",
            )
        prompt = str(arguments.get("prompt", "")).strip()
        if not prompt:
            return _tool_result(content="prompt is required")
        description = str(arguments.get("description", "")) or f"{agent_type} agent"
        thinking = arguments.get("thinking")
        if thinking is not None:
            thinking = str(thinking)
            if thinking not in THINKING_LEVELS:
                return _tool_result(
                    content=f"Invalid thinking level: {thinking}."
                    f" Valid options: {', '.join(THINKING_LEVELS)}",
                )
        isolation = "worktree" if arguments.get("isolation") == "worktree" else None
        try:
            job = scheduler.add_job(
                name=description,
                description=description,
                schedule=str(arguments.get("schedule")),
                subagent_type=agent_type,
                prompt=prompt,
                provider=(str(arguments.get("provider")) if arguments.get("provider") else None),
                model=str(arguments.get("model")) if arguments.get("model") else None,
                thinking=thinking,
                max_turns=_coerce_max_turns(arguments.get("max_turns")),
                isolation=isolation,
            )
        except (ValueError, RuntimeError) as exc:
            return _tool_result(content=str(exc))
        next_run = scheduler.get_next_run(job.id) or "(unknown)"
        return _tool_result(
            content=(
                f'Scheduled "{job.name}" (id: {job.id}, type: {job.schedule_type}).'
                f" Next run: {next_run}."
                " Manage via /agents -> Scheduled jobs."
            ),
        )

    async def run_get_result_tool(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
        on_update: ToolUpdateCallback | None = None,
    ) -> AgentToolResult:
        del tool_call_id, signal, on_update
        await manager.evict_stale()
        agent_id = str(arguments.get("agent_id", ""))
        run = manager.runs.get(agent_id)
        if run is None:
            known = ", ".join(sorted(manager.runs)) or "none"
            return _tool_result(
                content=f"Unknown agent_id: {agent_id}. Known agents: {known}",
            )
        if bool(arguments.get("wait", False)) and run.status in ("running", "queued"):
            # Claim the result before waiting so the background completion
            # path skips its redundant follow-up notification. Poll on status
            # rather than the task so a queued run is followed through its
            # queued -> started -> finished transitions.
            run.result_consumed = True
            manager.cancel_nudge(agent_id)
            while run.status in ("running", "queued"):
                await asyncio.sleep(0.05)
        header = format_run_summary(run)
        header += f"\nUsage: {format_usage_parts(run)}"
        if run.output_file:
            header += f"\nOutput file: {run.output_file}"
        if run.status == "queued":
            return _tool_result(
                content=f"{header}\n\nStill queued (max {manager.max_concurrent} concurrent).",
            )
        if run.status == "running":
            return _tool_result(
                content=f"{header}\n\nStill running.",
            )
        run.result_consumed = True
        manager.cancel_nudge(agent_id)
        body = run.error if run.status == "error" else run.result_text
        return _tool_result(
            content=f"{header}\n\n{body or '(no output)'}",
        )

    async def run_steer_tool(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
        on_update: ToolUpdateCallback | None = None,
    ) -> AgentToolResult:
        del tool_call_id, signal, on_update
        agent_id = str(arguments.get("agent_id", ""))
        message = str(arguments.get("message", ""))
        run = manager.runs.get(agent_id)
        if run is None:
            return _tool_result(
                content=f'Agent not found: "{agent_id}". It may have been cleaned up.',
            )
        if run.status not in ("running", "queued"):
            return _tool_result(
                content=f'Agent "{agent_id}" is not running (status: {run.status}).'
                " Cannot steer a non-running agent.",
            )
        if run.session is None:
            run.pending_steers.append(message)
            return _tool_result(
                content=f"Steering message queued for agent {agent_id}."
                " It will be delivered once the session initializes.",
            )
        run.session.queue_steering_message(message)
        state_parts = []
        if run.has_usage:
            state_parts.append(f"{lifetime_tokens(run)} tokens")
        state_parts.append(f"{run.tool_calls} tool uses")
        with contextlib.suppress(Exception):
            state_parts.append(f"~{run.session.context_token_estimate} context tokens")
        return _tool_result(
            content=f"Steering message sent to agent {agent_id}."
            " The agent will process it after its current tool execution.\n"
            f"Current state: {' · '.join(state_parts)}",
        )

    menu_tasks: set[asyncio.Task[None]] = set()

    def agents_command(args: str, context: ExtensionCommandContext) -> str | None:
        del args, context
        ui = baldric.context.ui
        if supports_menu(ui):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                # Sync handlers can't await dialogs; drive the menu from a
                # loop task (the documented ui-dialogs pattern). Return no
                # message: any text would open a modal the user must dismiss
                # before the menu appears.
                task = loop.create_task(
                    show_agents_menu(manager, ui, scheduler, controller=_current_controller())
                )
                menu_tasks.add(task)
                task.add_done_callback(menu_tasks.discard)
                return None
        definitions = manager.definitions()
        lines = ["Agent types:", format_agent_type_list(definitions)]
        if manager.runs:
            lines.append("")
            lines.append("Runs:")
            lines.extend(format_run_summary(run) for run in manager.runs.values())
        else:
            lines.append("")
            lines.append("No agents have been spawned in this session.")
        return "\n".join(lines)

    async def on_shutdown(event: object, context: ExtensionContext) -> None:
        # Tear down on every shutdown reason (new/resume/branch/quit): runs
        # belong to the outgoing transcript and would otherwise leak sessions.
        del event, context
        scheduler.stop()
        controller = _current_controller()
        if controller is not None:
            # pi parity: the extension clears its own widgets on shutdown (the
            # host also force-clears as a safety net on the next bridge install).
            controller.teardown()
            ui_controller.clear()
        await manager.shutdown()
        manager.runs.clear()
        manager._notify_sources()  # noqa: SLF001 - same-module teardown signal

    # Built before any session is bound, so there is no trust decision to read
    # yet: the description lists the user's types, and project agent types stay
    # spawnable but unlisted until a session supplies its own trust state.
    type_list = format_agent_type_list(
        load_agent_definitions(BaldricPaths(), Path.cwd(), project_trusted=False)
    )
    baldric.register_tool(
        AgentTool(
            name="agent",
            label="Agent",
            description=(
                "Spawn an autonomous subagent to handle a task. The subagent works"
                " in its own context with its own tools and returns its final"
                " report. Set run_in_background=true for long tasks; a completion"
                " notification will arrive when it finishes. Use steer_subagent to"
                " redirect a running agent, and resume=<id> with a new prompt to"
                " continue a finished agent's session. Two ways to share this"
                " conversation: inherit_context=true prepends a text digest of"
                " the user and assistant messages only (no tool calls or"
                " results) to a fresh agent of any type/model; subagent_type"
                " fork runs on this conversation's actual messages, including"
                " every tool call and result, with the same system prompt,"
                " tools, and model, so the prompt cache is shared.\n\nAvailable"
                f" agent types:\n{type_list}"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The task for the subagent to perform.",
                    },
                    "description": {
                        "type": "string",
                        "description": "A short (3-5 word) description of the task.",
                    },
                    "subagent_type": {
                        "type": "string",
                        "description": "The agent type to spawn (default: general).",
                    },
                    "run_in_background": {
                        "type": "boolean",
                        "description": "Return immediately and notify on completion.",
                    },
                    "provider": {
                        "type": "string",
                        "description": "Exact Baldric provider ID for the subagent"
                        " (default: the calling session's provider).",
                    },
                    "model": {
                        "type": "string",
                        "description": "Exact model ID for the subagent (default:"
                        " the agent type's model, else the calling session's"
                        " model).",
                    },
                    "thinking": {
                        "type": "string",
                        "enum": list(THINKING_LEVELS),
                        "description": (
                            "Reasoning effort for the subagent. Omit it to keep this"
                            " session's level when the subagent runs the same model;"
                            " another model then uses its own default."
                        ),
                    },
                    "max_turns": {
                        "type": "number",
                        "minimum": 1,
                        "description": "Soft turn limit; the agent is asked to wrap"
                        " up, then hard-cancelled after a grace period.",
                    },
                    "resume": {
                        "type": "string",
                        "description": "Id of a finished agent to resume with this"
                        " prompt (always runs foreground).",
                    },
                    "isolation": {
                        "type": "string",
                        "enum": ["worktree"],
                        "description": 'Set to "worktree" to run the agent in an'
                        " isolated git worktree; changes are saved to a"
                        " baldric-agent-<id> branch.",
                    },
                    "isolated": {
                        "type": "boolean",
                        "description": "If true, spawn the agent without"
                        " extension tools (core tools only); it cannot spawn"
                        " subagents of its own. Default: false.",
                    },
                    "inherit_context": {
                        "type": "boolean",
                        "description": "If true, prepend a text digest of the"
                        " parent conversation (user and assistant messages;"
                        " tool calls and results omitted) to the agent's"
                        " prompt. Default: false (fresh context). No effect on"
                        " forks, which already have the full history.",
                    },
                    "schedule": {
                        "type": "string",
                        "description": "Opt-in only — fire later instead of now."
                        " Omit to run immediately (the default, almost always"
                        ' correct). Formats: 5-field cron ("0 9 * * 1" = 9am Mon),'
                        ' interval ("5m"/"1h"), one-shot ("+10m" or ISO). Forces'
                        " run_in_background; incompatible with inherit_context and"
                        " resume. Returns a job ID.",
                    },
                },
                "required": ["prompt", "description"],
            },
            execute_fn=run_agent_tool,
            prompt_snippet="Spawn an autonomous subagent for delegated tasks.",
            render_call=render_agent_call,
            render_result=render_agent_result,
        )
    )
    baldric.register_tool(
        AgentTool(
            name="get_subagent_result",
            label="Get subagent result",
            description="Get the status or final result of a spawned subagent.",
            parameters={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "The id returned when the agent was spawned.",
                    },
                    "wait": {
                        "type": "boolean",
                        "description": "Block until the agent finishes.",
                    },
                },
                "required": ["agent_id"],
            },
            execute_fn=run_get_result_tool,
            render_call=render_get_result_call,
        )
    )
    baldric.register_tool(
        AgentTool(
            name="steer_subagent",
            label="Steer subagent",
            description=(
                "Send a steering message to a running subagent. It will be"
                " delivered after the agent's current tool execution and appear as"
                " a user message in the agent's conversation."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "The id of the running agent to steer.",
                    },
                    "message": {
                        "type": "string",
                        "description": "The message to send. This will appear as a"
                        " user message in the agent's conversation.",
                    },
                },
                "required": ["agent_id", "message"],
            },
            execute_fn=run_steer_tool,
            render_call=render_steer_call,
        )
    )
    baldric.register_command(
        "agents",
        agents_command,
        description="List subagent types and runs.",
    )
    baldric.on("session_start", on_session_start)
    baldric.on("session_shutdown", on_shutdown)


def _foreground_result(run: AgentRun) -> AgentToolResult:
    details = build_notification_details(run, FOREGROUND_RESULT_CHARS)
    if run.status in ("completed", "steered"):
        content = run.result_text or "(subagent produced no output)"
        duration = _duration_ms(run)
        seconds = f"{duration / 1000:.1f}" if duration is not None else "?"
        if run.has_usage:
            tokens_note = f", {lifetime_tokens(run)} tokens"
        elif run.context_tokens:
            tokens_note = f", ~{run.context_tokens} context tokens"
        else:
            tokens_note = ""
        completed_line = f"Agent completed in {seconds}s ({run.tool_calls} tool uses{tokens_note})."
        return _tool_result(
            content=f"{format_run_summary(run)}\n{completed_line}\n\n{content}",
            details=details,
        )
    return _tool_result(
        content=f"{format_run_summary(run)}\n\n{run.error or 'subagent failed'}",
        details=details,
    )


def _coerce_max_turns(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _tool_result(
    *,
    content: str,
    details: dict[str, JSONValue] | None = None,
) -> AgentToolResult:
    """Build a plain text tool result (pi-subagents' textResult).

    Failures are returned as ordinary results whose text says what went wrong,
    never raised: pi-subagents does the same on every path, and raising would
    drop `details` (the completion card) — the loop's error handler rebuilds
    results with empty details.
    """
    return AgentToolResult(content=[TextContent(text=content)], details=details)
