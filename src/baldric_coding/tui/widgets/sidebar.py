"""Small Textual widgets for Baldric's interactive TUI."""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from subprocess import TimeoutExpired
from typing import Any, Protocol, cast

from rich.align import Align
from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.padding import Padding
from rich.rule import Rule
from rich.text import Text
from textual.containers import Container, Vertical, VerticalScroll
from textual.content import Content
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Collapsible, Static

from baldric_coding.context.prompts import PromptTemplate
from baldric_coding.context.skills.skills import Skill
from baldric_coding.context.system_prompt import (
    ProjectContextFile,
    format_skills_for_prompt,
)
from baldric_coding.session.compaction.context_window import estimate_text_tokens
from baldric_coding.session.stats import SessionStats
from baldric_coding.tui.config import BALDRIC_DARK_THEME, TuiTheme
from baldric_coding.version import current_version
from baldric_protocol.tools import AgentTool

BALDRIC_SIDEBAR_LOGO = "τ = 2π"


SIDEBAR_BULLET_LIST_LIMIT = 5


SIDEBAR_COMMA_LIST_MAX_LINES = 3


class SessionSummarySource(Protocol):
    """Session attributes displayed by the sidebar."""

    @property
    def cwd(self) -> Path: ...

    @property
    def model(self) -> str: ...

    @property
    def provider_name(self) -> str: ...

    @property
    def tools(self) -> Sequence[AgentTool]: ...

    @property
    def skills(self) -> Sequence[Skill]: ...

    @property
    def prompt_templates(self) -> Sequence[PromptTemplate]: ...

    @property
    def context_files(self) -> Sequence[ProjectContextFile]: ...

    @property
    def system_prompt_files(self) -> Sequence[Path]: ...

    @property
    def context_token_estimate(self) -> int: ...

    @property
    def has_provider_context_usage(self) -> bool: ...

    @property
    def auto_compact_token_threshold(self) -> int | None: ...

    @property
    def context_window_tokens(self) -> int: ...

    @property
    def thinking_level(self) -> str: ...

    @property
    def session_title(self) -> str | None: ...

    @property
    def extension_names(self) -> Sequence[str]: ...

    @property
    def session_stats(self) -> SessionStats: ...


class SidebarFileItem(Static):
    """One keyboard- and mouse-openable file in the session sidebar."""

    can_focus = True

    class OpenRequested(Message):
        """Request opening this item's file in the main area."""

        def __init__(self, item: SidebarFileItem) -> None:
            super().__init__()
            self.item = item

    def __init__(self, label: str, *, path: Path, kind: str, bullet: str = "•") -> None:
        super().__init__(f"  {bullet} {label}", classes="sidebar-file-item", markup=False)
        self.path = path
        self.kind = kind
        self.file_label = label
        self.tooltip = str(path)

    def on_click(self, event: Any) -> None:
        """Open the represented file on a primary click."""
        if event.button == 1:
            event.stop()
            self.post_message(self.OpenRequested(self))

    def on_key(self, event: Any) -> None:
        """Open the represented file from keyboard focus."""
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.OpenRequested(self))


def _set_collapsible_title(collapsible: Collapsible, title: str) -> None:
    """Set a Collapsible title, forcing a re-render on style-only changes.

    Textual's ``CollapsibleTitle`` keeps the title in a reactive ``label`` whose
    change detection compares plain text only, so re-theming a title whose text
    is unchanged leaves the previously baked colors in place. When the new
    markup differs from the current label, push it directly onto the label
    widget and keep its reactive state in sync so later collapse/expand toggles
    keep the new colors.
    """
    collapsible.title = title
    title_widget = collapsible._title
    new_label = Content.from_markup(title)
    current_label = title_widget.label
    if isinstance(current_label, Content) and new_label.is_same(current_label):
        return
    symbol = title_widget.expanded_symbol if not title_widget.collapsed else title_widget.collapsed_symbol
    title_widget.update(Content.assemble(symbol, " ", new_label))
    if hasattr(title_widget, "_reactive_label"):
        title_widget._reactive_label = new_label


class SessionSidebar(Vertical):
    """Compact sidebar with collapsible resource lists and pinned branding."""

    def compose(self) -> Any:
        with VerticalScroll(id="sidebar-scroll"):
            yield Static("", id="sidebar-content")
            yield Static(_sidebar_separator(theme=BALDRIC_DARK_THEME), classes="sidebar-separator")
            yield Static("context", id="sidebar-context-title", classes="sidebar-section-title")
            yield Vertical(id="sidebar-context-content", classes="sidebar-file-list")
            yield Static(_sidebar_separator(theme=BALDRIC_DARK_THEME), classes="sidebar-separator")
            yield Static("", id="sidebar-after-context-content")
            yield Static(_sidebar_separator(theme=BALDRIC_DARK_THEME), classes="sidebar-separator")
            yield Collapsible(
                Vertical(id="sidebar-skills-content", classes="sidebar-file-list"),
                title=_sidebar_resource_title(
                    "skills",
                    "0 · ~0 tokens",
                    theme=BALDRIC_DARK_THEME,
                ),
                collapsed=True,
                id="sidebar-skills",
                classes="sidebar-resource-section",
            )
            yield Static(_sidebar_separator(theme=BALDRIC_DARK_THEME), classes="sidebar-separator")
            yield Collapsible(
                Vertical(id="sidebar-prompts-content", classes="sidebar-file-list"),
                title=_sidebar_resource_title("prompts", "0", theme=BALDRIC_DARK_THEME),
                collapsed=True,
                id="sidebar-prompts",
                classes="sidebar-resource-section",
            )
            yield Static(_sidebar_separator(theme=BALDRIC_DARK_THEME), classes="sidebar-separator")
            yield Static("", id="sidebar-extensions-content")
            yield Container(id="sidebar-extension-sections")
        yield Static("", id="sidebar-brand")

    _summary_fingerprint: tuple[object, ...] | None = None
    _resource_fingerprint: tuple[object, ...] | None = None

    def update_from_session(
        self,
        session: SessionSummarySource,
        *,
        theme: TuiTheme = BALDRIC_DARK_THEME,
    ) -> None:
        """Redraw only the sidebar sections whose displayed inputs changed."""
        fingerprint = _session_summary_fingerprint(session, theme=theme)
        if fingerprint == self._summary_fingerprint:
            return
        self._summary_fingerprint = fingerprint
        content = _build_sidebar_content(session, theme=theme)
        self.query_one("#sidebar-content", Static).update(
            Group(*_separate_sidebar_sections(content.summary_sections[:4], theme=theme)),
        )
        self.query_one("#sidebar-after-context-content", Static).update(
            Group(*_separate_sidebar_sections(content.summary_sections[5:], theme=theme)),
        )
        self.query_one("#sidebar-extensions-content", Static).update(
            _sidebar_section("extensions", content.extensions, theme=theme),
        )
        # Usage and context totals change after every message; the resource
        # lists below are remounted only when the resources themselves change.
        resource_fingerprint = _session_resource_fingerprint(session, theme=theme)
        if resource_fingerprint == self._resource_fingerprint:
            return
        self._resource_fingerprint = resource_fingerprint
        self._update_resource_sections(session, theme=theme)

    def _update_resource_sections(
        self,
        session: SessionSummarySource,
        *,
        theme: TuiTheme,
    ) -> None:
        self.query_one("#sidebar-context-title", Static).styles.color = theme.prompt_text
        _replace_sidebar_file_widgets(
            self.query_one("#sidebar-context-content", Vertical),
            _context_file_widgets(session.context_files, cwd=session.cwd, theme=theme),
        )
        skills = self.query_one("#sidebar-skills", Collapsible)
        _set_collapsible_title(skills, _skill_section_title(session, theme=theme))
        _replace_sidebar_file_widgets(
            self.query_one("#sidebar-skills-content", Vertical),
            _skill_file_widgets(session.skills, cwd=session.cwd, theme=theme),
        )
        prompts = self.query_one("#sidebar-prompts", Collapsible)
        _set_collapsible_title(
            prompts,
            _sidebar_resource_title(
                "prompts",
                str(len(session.prompt_templates)),
                theme=theme,
            ),
        )
        _replace_sidebar_file_widgets(
            self.query_one("#sidebar-prompts-content", Vertical),
            _prompt_file_widgets(session.prompt_templates, cwd=session.cwd, theme=theme),
        )
        for separator in self.query(Static).filter(".sidebar-separator"):
            separator.update(_sidebar_separator(theme=theme))
        self.query_one("#sidebar-brand", Static).update(
            _sidebar_brand(theme=theme),
            layout=False,
        )


class CompactSessionInfo(Static):
    """Single-line session metadata for narrow TUI layouts."""

    _summary_fingerprint: tuple[object, ...] | None = None

    def update_from_session(
        self,
        session: SessionSummarySource,
        *,
        theme: TuiTheme = BALDRIC_DARK_THEME,
    ) -> None:
        """Redraw compact session metadata only when its inputs changed."""
        fingerprint = _session_summary_fingerprint(session, theme=theme)
        if fingerprint == self._summary_fingerprint:
            return
        self._summary_fingerprint = fingerprint
        self.update(render_compact_session_info(session, theme=theme))


def _sidebar_resource_title(label: str, detail: str, *, theme: TuiTheme) -> str:
    """Style a resource label separately from its quieter summary."""
    return f"[bold {theme.prompt_text}]{label}[/] [{theme.completion_description}]({detail})[/]"


def _skill_section_title(session: SessionSummarySource, *, theme: TuiTheme) -> str:
    """Summarize skill count and estimated system-prompt footprint."""
    skill_prompt = (
        format_skills_for_prompt(session.skills) if any(tool.name == "read" for tool in session.tools) else ""
    )
    estimated_tokens = estimate_text_tokens(skill_prompt)
    return _sidebar_resource_title(
        "skills",
        f"{len(session.skills)} · ~{_compact_usage_count(estimated_tokens)} tokens",
        theme=theme,
    )


def _session_summary_fingerprint(
    session: SessionSummarySource,
    *,
    theme: TuiTheme,
) -> tuple[object, ...]:
    return (
        *_session_resource_fingerprint(session, theme=theme),
        session.provider_name,
        session.model,
        session.thinking_level,
        session.context_token_estimate,
        session.has_provider_context_usage,
        session.auto_compact_token_threshold,
        session.context_window_tokens,
        session.session_title,
        session.session_stats,
        tuple(session.extension_names),
        tuple(session.system_prompt_files),
    )


def _session_resource_fingerprint(
    session: SessionSummarySource,
    *,
    theme: TuiTheme,
) -> tuple[object, ...]:
    """Inputs of the sidebar's mounted context, skill, and prompt lists."""
    return (
        theme.name,
        session.cwd,
        tuple(tool.name for tool in session.tools),
        tuple(
            (skill.name, skill.path, skill.description, skill.disable_model_invocation)
            for skill in session.skills
        ),
        tuple((template.name, template.path) for template in session.prompt_templates),
        tuple(context.path for context in session.context_files),
    )


@dataclass(frozen=True, slots=True)
class _SidebarContent:
    summary_sections: tuple[RenderableType, ...]
    skills: RenderableType
    prompts: RenderableType
    extensions: RenderableType


def render_session_sidebar(
    session: SessionSummarySource,
    *,
    theme: TuiTheme = BALDRIC_DARK_THEME,
) -> RenderableType:
    """Render a static summary of the active coding session."""
    content = _build_sidebar_content(session, theme=theme)
    sections = (
        *content.summary_sections,
        _sidebar_section("skills", content.skills, theme=theme),
        _sidebar_section("prompts", content.prompts, theme=theme),
        _sidebar_section("extensions", content.extensions, theme=theme),
    )
    return Group(*_separate_sidebar_sections(sections, theme=theme))


def _build_sidebar_content(
    session: SessionSummarySource,
    *,
    theme: TuiTheme,
) -> _SidebarContent:
    """Build shared sidebar renderables for static and interactive views."""
    title = Text(session.session_title or "Untitled session", style=f"bold {theme.accent}")
    stats = session.session_stats
    activity = Text(
        f"{stats.turn_count} {_plural(stats.turn_count, 'turn')}, "
        f"{stats.tool_call_count} tool {_plural(stats.tool_call_count, 'call')}",
        style=theme.completion_description,
    )
    usage = Text(style=theme.completion_description)
    usage.append(f"{_compact_usage_count(stats.input_tokens)} in, ")
    usage.append(f"{_compact_usage_count(stats.output_tokens)} out")
    usage.append(" · ", style=theme.completion_description)
    if stats.estimated_cost is None:
        usage.append("$N/A", style=theme.completion_description)
    else:
        usage.append(f"~{_format_cost(stats.estimated_cost)}")
    cache_rates: list[str] = []
    if (latest_hit_rate := stats.latest_cache_hit_rate) is not None:
        cache_rates.append(f"{latest_hit_rate:.0%} latest")
    if (session_hit_rate := stats.cache_hit_rate) is not None:
        cache_rates.append(f"{session_hit_rate:.0%} session")
    if cache_rates:
        usage.append("\ncache: ", style=theme.completion_description)
        usage.append(" · ".join(cache_rates), style=theme.completion_description)
    performance: list[str] = []
    if (session_speed := stats.output_tokens_per_second) is not None:
        performance.append(f"avg TPS: {session_speed:.1f}")
    if (average_ttft := stats.average_time_to_first_output_ms) is not None:
        performance.append(f"avg TTFT: {_format_milliseconds(average_ttft)}")
    if performance:
        usage.append(f"\n{' · '.join(performance)}", style=theme.completion_description)

    threshold = session.auto_compact_token_threshold
    compaction = Text(
        "off" if threshold is None else f"auto at {_compact_token_count(threshold)}",
        style=theme.completion_description,
    )
    context = _limited_bullet_list(
        _context_file_labels(session.context_files, cwd=session.cwd),
        empty="No context files",
        theme=theme,
    )
    system_prompt_sections: tuple[RenderableType, ...] = ()
    if session.system_prompt_files:
        system_prompt_files = _limited_bullet_list(
            [_context_file_label(path, cwd=session.cwd) for path in session.system_prompt_files],
            empty="No system prompt files",
            theme=theme,
        )
        system_prompt_sections = (_sidebar_section("system prompt", system_prompt_files, theme=theme),)
    tools = _comma_list([tool.name for tool in session.tools], empty="No tools", theme=theme)
    return _SidebarContent(
        summary_sections=(
            Padding(title, (0, 0, 0, 1)),
            _sidebar_section("activity", activity, theme=theme),
            _sidebar_section("usage", usage, theme=theme),
            _sidebar_section("compaction", compaction, theme=theme),
            _sidebar_section("context", context, theme=theme),
            *system_prompt_sections,
            _sidebar_section("tools", tools, theme=theme),
        ),
        skills=_grouped_skill_list(session.skills, cwd=session.cwd, theme=theme),
        prompts=_grouped_prompt_list(session.prompt_templates, cwd=session.cwd, theme=theme),
        extensions=_comma_list(
            list(session.extension_names),
            empty="No extensions",
            theme=theme,
        ),
    )


def _separate_sidebar_sections(
    sections: Sequence[RenderableType],
    *,
    theme: TuiTheme,
) -> list[RenderableType]:
    separated: list[RenderableType] = []
    for index, section in enumerate(sections):
        if index:
            separated.append(_sidebar_separator(theme=theme))
        separated.append(section)
    return separated


def _sidebar_section(
    title: str,
    body: RenderableType,
    *,
    theme: TuiTheme,
) -> RenderableType:
    """Render one sidebar section without a surrounding border."""
    header = Text(title, style=f"bold {theme.prompt_text}")
    return Group(Padding(header, (0, 0, 0, 1)), Padding(body, (0, 0, 0, 1)))


def _sidebar_separator(*, theme: TuiTheme) -> RenderableType:
    """Render a spaced divider between adjacent sidebar sections."""
    return Padding(Rule(style=theme.border), (0, 0, 1, 0))


def _sidebar_brand(*, theme: TuiTheme) -> RenderableType:
    brand = Text(style=f"bold {theme.prompt_text}")
    brand.append(BALDRIC_SIDEBAR_LOGO)
    brand.append(f"  {current_version()}", style=theme.completion_description)
    return Align.center(brand)


def render_compact_session_info(
    session: SessionSummarySource,
    *,
    theme: TuiTheme = BALDRIC_DARK_THEME,
) -> RenderableType:
    """Render the session facts as one status line below the prompt.

    Segments whose data is absent are dropped; every value already existed on
    the session (spec 2026-11-08 §5.4, zero new queries) and ``fold`` keeps
    narrow terminals wrapping instead of truncating.
    """
    segments: list[Text] = [_styled_cwd(session.cwd, theme=theme)]
    model_segment = Text(style=theme.muted_text)
    model_segment.append(session.provider_name, style=theme.completion_description)
    model_segment.append(f":{session.model}", style=theme.prompt_text)
    thinking_level = _thinking_level(session)
    if thinking_level is not None:
        model_segment.append(f" ({thinking_level})", style=theme.completion_description)
    segments.append(model_segment)
    context_segment = Text(_context_usage(session), style=theme.completion_description)
    if session.has_provider_context_usage:
        limit = session.auto_compact_token_threshold
        if limit is None or limit <= 0:
            limit = session.context_window_tokens
        if limit > 0:
            share = round(session.context_token_estimate * 100 / limit)
            context_segment.append(f" ({share}%)")
    segments.append(context_segment)
    stats = session.session_stats
    if stats.estimated_cost is not None:
        segments.append(Text(f"${stats.estimated_cost:.2f}", style=theme.completion_description))
    tokens_per_second = stats.output_tokens_per_second
    if tokens_per_second is not None:
        segments.append(Text(f"{tokens_per_second:.0f} tps", style=theme.completion_description))
    ttft_ms = stats.average_time_to_first_output_ms
    if ttft_ms is not None:
        segments.append(Text(f"TTFT {ttft_ms / 1000:.1f}s", style=theme.completion_description))
    line = Text(style=theme.muted_text, overflow="fold", no_wrap=False)
    for index, segment in enumerate(segments):
        if index:
            line.append(" · ", style=theme.muted_text)
        line.append_text(segment)
    return line


def _context_usage(session: SessionSummarySource) -> str:
    threshold = session.auto_compact_token_threshold
    limit = session.context_window_tokens if threshold is None or threshold <= 0 else threshold
    used = _compact_token_count(session.context_token_estimate) if session.has_provider_context_usage else "?"
    return f"{used}/{_compact_token_count(limit)}"


def _styled_cwd(cwd: Path, *, theme: TuiTheme) -> Text:
    """Style the parent path as metadata while emphasizing the working directory."""
    short_path = _short_path(cwd)
    parent, separator, name = short_path.rpartition("/")
    text = Text(overflow="fold", no_wrap=False)
    if separator and name:
        text.append(f"{parent}{separator}", style=theme.completion_description)
        text.append(name, style=theme.prompt_text)
    else:
        text.append(short_path, style=theme.prompt_text)
    text.append(f" ({_git_branch(cwd)})", style=theme.completion_description)
    return text


def _format_milliseconds(value: float) -> str:
    rounded = round(value)
    if rounded < 1000:
        return f"{rounded}ms"
    return f"{rounded / 1000:.1f}s"


def _compact_token_count(value: int) -> str:
    if value <= 0:
        return "0k"
    if value < 1000:
        return "<1k"
    return f"{(value + 500) // 1000}k"


def _context_file_labels(
    context_files: Sequence[ProjectContextFile],
    *,
    cwd: Path,
) -> list[str]:
    return [_context_file_label(Path(context_file.path), cwd=cwd) for context_file in context_files]


def _context_file_label(path: Path, *, cwd: Path) -> str:
    expanded_path = path.expanduser()
    if not expanded_path.is_absolute():
        expanded_path = cwd / expanded_path
    try:
        return str(expanded_path.resolve().relative_to(cwd.expanduser().resolve()))
    except (OSError, ValueError):
        try:
            absolute_path = expanded_path.resolve()
        except OSError:
            absolute_path = expanded_path.absolute()
        return _short_path(absolute_path)


def _thinking_level(session: SessionSummarySource) -> str | None:
    available = getattr(session, "available_thinking_levels", None)
    if available == ():
        return None
    explicit_level = getattr(session, "thinking_level", None)
    if explicit_level:
        return str(explicit_level)
    state = getattr(session, "state", None)
    thinking_level = getattr(state, "thinking_level", None)
    return str(thinking_level) if thinking_level else "--"


# Background refreshes keep git off the render path, and `HEAD`-stamp
# invalidation catches branch switches immediately, so the periodic recheck
# only exists for setups where `HEAD` cannot be found or does not move
# (for example reftable repos); a slow fallback interval is fine there.
GIT_BRANCH_RECHECK_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class _GitBranchLookup:
    head_stamp: tuple[int, int, int] | None
    checked_at: float
    branch: str


_GIT_BRANCH_CACHE: dict[Path, _GitBranchLookup] = {}
_GIT_BRANCH_REFRESH_LOCK = threading.Lock()
_GIT_BRANCH_REFRESHING: set[Path] = set()


def _widgets_package() -> Any:
    import baldric_coding.tui.widgets as widgets

    return widgets


def _git_branch(cwd: Path) -> str:
    """Return the checked-out branch without ever running git on the caller's thread.

    Session chrome re-renders after every message, and a synchronous git
    subprocess there stalls the UI. A background worker refreshes the cache
    instead, so the render path only reads it and reports ``--`` until the
    first lookup lands. Checkouts rewrite `HEAD`, so its stamp catches branch
    switches immediately; the periodic recheck covers setups where `HEAD`
    cannot be found or does not move (for example reftable repos).
    """
    head_stamp = _git_head_stamp(cwd)
    now = time.monotonic()
    with _GIT_BRANCH_REFRESH_LOCK:
        cached = _GIT_BRANCH_CACHE.get(cwd)
        if (
            cached is not None
            and cached.head_stamp == head_stamp
            and now - cached.checked_at < GIT_BRANCH_RECHECK_SECONDS
        ):
            return cached.branch
        _schedule_git_branch_refresh(cwd)
        return "--" if cached is None else cached.branch


def _schedule_git_branch_refresh(cwd: Path) -> None:
    """Start one background refresh for `cwd`; concurrent refreshes are deduped."""
    if cwd in _GIT_BRANCH_REFRESHING:
        return
    _GIT_BRANCH_REFRESHING.add(cwd)
    threading.Thread(
        target=_refresh_git_branch,
        args=(cwd,),
        name=f"baldric-git-branch-{cwd.name}",
        daemon=True,
    ).start()


def _refresh_git_branch(cwd: Path) -> None:
    """Run git off the UI thread and publish the result into the cache."""
    try:
        branch = _read_git_branch(cwd)
        stamp = _git_head_stamp(cwd)
        with _GIT_BRANCH_REFRESH_LOCK:
            _GIT_BRANCH_CACHE[cwd] = _GitBranchLookup(
                head_stamp=stamp,
                checked_at=time.monotonic(),
                branch=branch,
            )
    finally:
        with _GIT_BRANCH_REFRESH_LOCK:
            _GIT_BRANCH_REFRESHING.discard(cwd)


def _git_head_stamp(cwd: Path) -> tuple[int, int, int] | None:
    """Return the stamp of the `HEAD` file git would use for `cwd`, if found."""
    for directory in (cwd, *cwd.parents):
        dot_git = directory / ".git"
        try:
            if dot_git.is_dir():
                head = dot_git / "HEAD"
            elif dot_git.is_file():
                # Worktrees and submodules point at their git dir from a file.
                pointer = dot_git.read_text(encoding="utf-8").strip()
                if not pointer.startswith("gitdir:"):
                    return None
                head = (directory / pointer.removeprefix("gitdir:").strip()) / "HEAD"
            else:
                continue
            stat = head.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size, stat.st_ino)
    return None


def _read_git_branch(cwd: Path) -> str:
    try:
        result = _widgets_package().run(
            ["git", "-C", str(cwd), "branch", "--show-current"],
            capture_output=True,
            check=False,
            text=True,
            timeout=0.5,
        )
    except OSError:
        return "--"
    except TimeoutExpired:
        return "--"
    branch = cast(str, result.stdout.strip())
    if branch:
        return branch
    return "--"


@dataclass(frozen=True, slots=True)
class _LineLimitedCommaList:
    items: tuple[str, ...]
    empty: str
    style: str

    def __rich_console__(
        self,
        console: Console,
        options: ConsoleOptions,
    ) -> RenderResult:
        if not self.items:
            yield Text(self.empty, style=self.style)
            return

        visible_count = 0
        for count in range(1, len(self.items) + 1):
            candidate = self._text(self.items[:count])
            if len(candidate.wrap(console, options.max_width)) > SIDEBAR_COMMA_LIST_MAX_LINES:
                break
            visible_count = count

        if visible_count:
            text = self._text(self.items[:visible_count])
        else:
            visible_count = 1
            text = self._truncate_to_line_budget(
                self._text(self.items[:visible_count]),
                console=console,
                width=options.max_width,
            )

        hidden_count = len(self.items) - visible_count
        if hidden_count:
            text.append("\n")
            text.append(f"...({hidden_count} more)", style=self.style)
        yield text

    def _truncate_to_line_budget(self, text: Text, *, console: Console, width: int) -> Text:
        wrapped_lines = list(text.wrap(console, width))
        visible_lines = [line.copy() for line in wrapped_lines[:SIDEBAR_COMMA_LIST_MAX_LINES]]
        if len(wrapped_lines) > SIDEBAR_COMMA_LIST_MAX_LINES:
            last_line = visible_lines[-1]
            last_line.truncate(max(0, width - 1), overflow="crop")
            last_line.append("…", style=self.style)
        return Text("\n").join(visible_lines)

    def _text(self, items: Sequence[str]) -> Text:
        return Text(
            ", ".join(items),
            style=self.style,
            overflow="fold",
            no_wrap=False,
        )


def _comma_list(
    items: Sequence[str],
    *,
    empty: str,
    theme: TuiTheme,
) -> RenderableType:
    return _LineLimitedCommaList(
        items=tuple(items),
        empty=empty,
        style=theme.completion_description,
    )


def _compact_usage_count(value: int) -> str:
    if value < 1_000:
        return str(value)
    if value < 1_000_000:
        return f"{value / 1_000:.1f}".rstrip("0").rstrip(".") + "k"
    return f"{value / 1_000_000:.1f}".rstrip("0").rstrip(".") + "m"


def _format_cost(value: float) -> str:
    if 0 < value < 0.01:
        return f"${value:.3f}"
    return f"${value:.2f}"


def _plural(count: int, singular: str) -> str:
    return singular if count == 1 else f"{singular}s"


def _replace_sidebar_file_widgets(container: Vertical, widgets: Sequence[Widget]) -> None:
    """Replace a sidebar file list after its session-resource fingerprint changed."""
    container.remove_children()
    if widgets:
        container.mount(*widgets)


def _context_file_widgets(
    context_files: Sequence[ProjectContextFile],
    *,
    cwd: Path,
    theme: TuiTheme,
) -> list[Widget]:
    widgets: list[Widget] = [
        SidebarFileItem(
            _context_file_label(Path(context_file.path), cwd=cwd),
            path=_absolute_sidebar_path(Path(context_file.path), cwd=cwd),
            kind="Context",
        )
        for context_file in context_files[:SIDEBAR_BULLET_LIST_LIMIT]
    ]
    hidden_count = len(context_files) - len(widgets)
    if hidden_count:
        widgets.append(
            Static(
                f"  ...({hidden_count} more)",
                classes="sidebar-file-overflow",
                markup=False,
            )
        )
    if not widgets:
        widgets.append(Static("No context files", classes="sidebar-file-empty", markup=False))
    for widget in widgets:
        if not isinstance(widget, SidebarFileItem):
            widget.styles.color = theme.completion_description
    return widgets


def _skill_file_widgets(
    skills: Sequence[Skill],
    *,
    cwd: Path,
    theme: TuiTheme,
) -> list[Widget]:
    grouped: dict[str, list[Skill]] = {}
    for skill in skills:
        origin = skill.path.parent.parent if skill.path.name == "SKILL.md" else skill.path.parent
        grouped.setdefault(_resource_origin_label(origin, cwd=cwd), []).append(skill)
    return _grouped_sidebar_file_widgets(grouped, cwd=cwd, kind="Skill", theme=theme)


def _prompt_file_widgets(
    templates: Sequence[PromptTemplate],
    *,
    cwd: Path,
    theme: TuiTheme,
) -> list[Widget]:
    grouped: dict[str, list[PromptTemplate]] = {}
    for template in templates:
        origin = _resource_origin_label(template.path.parent, cwd=cwd)
        grouped.setdefault(origin, []).append(template)
    return _grouped_sidebar_file_widgets(grouped, cwd=cwd, kind="Prompt", theme=theme)


def _grouped_sidebar_file_widgets[SidebarResource: (Skill, PromptTemplate)](
    grouped: dict[str, list[SidebarResource]],
    *,
    cwd: Path,
    kind: str,
    theme: TuiTheme,
) -> list[Widget]:
    if not grouped:
        empty = "No skills loaded" if kind == "Skill" else "No prompt templates"
        widget = Static(empty, classes="sidebar-file-empty", markup=False)
        widget.styles.color = theme.completion_description
        return [widget]

    widgets: list[Widget] = []
    for origin in sorted(grouped, key=_resource_origin_sort_key):
        origin_widget = Static(origin, classes="sidebar-resource-origin", markup=False)
        origin_widget.styles.color = theme.completion_description
        widgets.append(origin_widget)
        for resource in sorted(grouped[origin], key=lambda item: item.name):
            path = resource.path
            widgets.append(
                SidebarFileItem(
                    resource.name,
                    path=_absolute_sidebar_path(path, cwd=cwd),
                    kind=kind,
                    bullet=(
                        "◦" if isinstance(resource, Skill) and resource.disable_model_invocation else "•"
                    ),
                )
            )
    return widgets


def _resource_origin_sort_key(origin: str) -> tuple[int, str]:
    precedence = {
        "~/.baldric/skills": 0,
        "~/.agents/skills": 1,
        "./.baldric/skills": 2,
        "./.agents/skills": 3,
        "~/.baldric/prompts": 0,
        "~/.agents/prompts": 1,
        "./.baldric/prompts": 2,
        "./.agents/prompts": 3,
    }
    return precedence.get(origin, len(precedence)), origin


def _absolute_sidebar_path(path: Path, *, cwd: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = cwd / expanded
    return expanded.absolute()


def _grouped_skill_list(
    skills: Sequence[Skill],
    *,
    cwd: Path,
    theme: TuiTheme,
) -> Text:
    if not skills:
        return Text("No skills loaded", style=theme.completion_description)

    grouped: dict[str, list[tuple[str, bool]]] = {}
    for skill in skills:
        origin = skill.path.parent.parent if skill.path.name == "SKILL.md" else skill.path.parent
        label = _resource_origin_label(origin, cwd=cwd)
        grouped.setdefault(label, []).append((skill.name, skill.disable_model_invocation))
    return _grouped_resource_names(grouped, directory="skills", theme=theme)


def _grouped_prompt_list(
    templates: Sequence[PromptTemplate],
    *,
    cwd: Path,
    theme: TuiTheme,
) -> Text:
    if not templates:
        return Text("No prompt templates", style=theme.completion_description)

    grouped: dict[str, list[tuple[str, bool]]] = {}
    for template in templates:
        label = _resource_origin_label(template.path.parent, cwd=cwd)
        grouped.setdefault(label, []).append((template.name, False))
    return _grouped_resource_names(grouped, directory="prompts", theme=theme)


def _grouped_resource_names(
    grouped: dict[str, list[tuple[str, bool]]],
    *,
    directory: str,
    theme: TuiTheme,
) -> Text:
    origin_precedence = {
        f"~/.agents/{directory}": 1,
        f"./.baldric/{directory}": 2,
        f"./.agents/{directory}": 3,
    }
    # The remaining origin is the configurable user Baldric home. Its rendered
    # path may be ~/.baldric, another path beneath ~, or an absolute path.
    ordered_origins = sorted(
        grouped,
        key=lambda origin: (origin_precedence.get(origin, 0), origin),
    )
    text = Text()
    for origin in ordered_origins:
        if text:
            text.append("\n")
        text.append(origin, style=theme.completion_description)
        for name, hollow_bullet in sorted(grouped[origin]):
            bullet = "◦" if hollow_bullet else "•"
            text.append(f"\n  {bullet} ", style=theme.completion_description)
            text.append(name, style=theme.completion_description)
    return text


def _resource_origin_label(origin: Path, *, cwd: Path) -> str:
    expanded_origin = origin.expanduser()
    if not expanded_origin.is_absolute():
        expanded_origin = cwd / expanded_origin
    absolute_origin = expanded_origin.absolute()
    absolute_cwd = cwd.expanduser().absolute()
    try:
        relative = absolute_origin.relative_to(absolute_cwd)
    except ValueError:
        pass
    else:
        return f"./{relative.as_posix()}"

    home = Path.home().absolute()
    try:
        return f"~/{absolute_origin.relative_to(home).as_posix()}"
    except ValueError:
        return str(absolute_origin)


def _limited_bullet_list(
    items: Sequence[str],
    *,
    empty: str,
    theme: TuiTheme,
) -> Text:
    text = _bullet_list(
        items[:SIDEBAR_BULLET_LIST_LIMIT],
        empty=empty,
        theme=theme,
    )
    hidden_count = len(items) - SIDEBAR_BULLET_LIST_LIMIT
    if hidden_count > 0:
        text.append(f"\n...({hidden_count} more)", style=theme.completion_description)
    return text


def _bullet_list(
    items: Sequence[str],
    *,
    empty: str,
    theme: TuiTheme,
) -> Text:
    text = Text()
    if not items:
        text.append(empty, style=theme.completion_description)
        return text

    for index, item in enumerate(items):
        if index:
            text.append("\n")
        text.append("• ", style=theme.completion_description)
        text.append(item, style=theme.completion_description)
    return text


def _short_path(path: Path) -> str:
    home = Path.home()
    try:
        return f"~/{path.relative_to(home)}"
    except ValueError:
        return str(path)
