"""Structured unified-diff rendering shared by the TUI and print modes.

Replaces the flat Pygments ``diff`` blob: patches render per file with a
line-number gutter, hunk headers, and word-level emphasis on the tokens that
actually changed between paired remove/add lines, so a reviewer sees what
moved inside a changed line without re-reading the whole line.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Final

from rich.console import Group, RenderableType
from rich.text import Text

from baldric_coding.rendering.theme_schema import ThemeTokens
from baldric_coding.rendering.themes import TuiTheme

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_TOKEN_RE = re.compile(r"\s+|\w+|[^\s\w]")

_GUTTER_WIDTH: Final = 4
# gutter is "{old:>4} {new:>4} " (10 columns), then the sign, then one space
# before the line content starts.
_GUTTER_OFFSET: Final = 2 * _GUTTER_WIDTH + 2

_CONTEXT: Final = "context"
_ADD: Final = "add"
_REMOVE: Final = "remove"
_HUNK: Final = "hunk"
_META: Final = "meta"


@dataclass(frozen=True, slots=True)
class DiffPalette:
    """Row colours for added/removed/context diff lines.

    Dark defaults are opencode's ``base.diff`` verbatim
    (opencode-dev/packages/tui/src/theme/assets/v2/opencode.json); the light
    variant is opencode's ``light.diff`` (``text.removed`` and
    ``background.context`` are absent there, so they fall back to the light
    red.100 and the plain white surface). A theme document can override every
    value through its schema's ``diff`` section; callers holding a
    :class:`ThemeTokens` pass it to :func:`render_patch`. Without tokens a
    theme still gets a palette that suits its own light/dark appearance rather
    than dark rows on a white transcript.
    """

    added_bg: str = "#20303b"
    removed_bg: str = "#37222c"
    added_text: str = "#4fd6be"
    removed_text: str = "#c53b53"
    context_bg: str = "#000000"
    line_number_text: str = "#8f8f8f"

    @classmethod
    def for_theme(cls, theme: TuiTheme) -> DiffPalette:
        """Return the palette matching *theme*'s light/dark appearance."""
        if theme.dark:
            return cls()
        return cls(
            added_bg="#d5e5d5",
            removed_bg="#f7d8db",
            added_text="#1e725c",
            removed_text="#c20f26",
            context_bg="#ffffff",
            line_number_text="#595959",
        )


@dataclass(frozen=True, slots=True)
class DiffLine:
    """One rendered diff row; ``text`` excludes the +/- marker."""

    kind: str
    old_number: int | None
    new_number: int | None
    text: str


@dataclass(frozen=True, slots=True)
class FileDiff:
    path: str
    lines: tuple[DiffLine, ...]


def parse_unified_patch(patch: str) -> tuple[FileDiff, ...]:
    """Parse a unified diff into per-file diffs with resolved line numbers.

    Hunk line kinds are decided by the hunk's remaining old/new line counts,
    never by the leading character alone: a removed line whose content begins
    with ``--`` renders as ``--- ...`` and an added line beginning with ``++``
    renders as ``+++ ...``. Treating those as file headers loses the content
    line entirely, so the counters are authoritative while a hunk is open and
    header detection only runs outside a hunk.
    """
    files: list[FileDiff] = []
    path: str | None = None
    lines: list[DiffLine] = []
    old_number = 0
    new_number = 0
    # Remaining lines announced by the current hunk header; once both reach
    # zero the hunk is closed and a leading ``--- ``/``+++ `` is a file header
    # again rather than diff content.
    old_remaining = 0
    new_remaining = 0

    def flush() -> None:
        nonlocal path, lines
        if path is not None and lines:
            files.append(FileDiff(path=path, lines=tuple(lines)))
        path = None
        lines = []

    def in_hunk() -> bool:
        return old_remaining > 0 or new_remaining > 0

    for raw in patch.splitlines():
        hunk = _HUNK_RE.match(raw)
        if hunk or raw.strip() == "@@":
            # A bare "@@" (no line numbers) is tolerated for hand-written
            # patches; difflib output always carries numbers. Without counts
            # the hunk stays open until the next header, which is the best a
            # count-less hunk can promise.
            if path is None:
                path = ""
            if hunk:
                old_number = int(hunk.group(1))
                new_number = int(hunk.group(3))
                old_remaining = int(hunk.group(2)) if hunk.group(2) is not None else 1
                new_remaining = int(hunk.group(4)) if hunk.group(4) is not None else 1
            else:
                old_remaining = new_remaining = 1
            lines.append(DiffLine(kind=_HUNK, old_number=None, new_number=None, text=raw))
            continue
        if not in_hunk() and raw.startswith("--- "):
            # A second --- header starts the next file body.
            flush()
            path = raw[4:].strip()
            continue
        if not in_hunk() and raw.startswith("+++ "):
            continue
        if path is None:
            continue
        if raw.startswith("+"):
            lines.append(DiffLine(kind=_ADD, old_number=None, new_number=new_number, text=raw[1:]))
            new_number += 1
            new_remaining = max(new_remaining - 1, 0)
        elif raw.startswith("-"):
            lines.append(DiffLine(kind=_REMOVE, old_number=old_number, new_number=None, text=raw[1:]))
            old_number += 1
            old_remaining = max(old_remaining - 1, 0)
        elif raw.startswith(" "):
            lines.append(
                DiffLine(
                    kind=_CONTEXT,
                    old_number=old_number,
                    new_number=new_number,
                    text=raw[1:],
                )
            )
            old_number += 1
            new_number += 1
            old_remaining = max(old_remaining - 1, 0)
            new_remaining = max(new_remaining - 1, 0)
        elif raw.startswith("\\"):
            lines.append(DiffLine(kind=_META, old_number=None, new_number=None, text=raw))
    flush()
    return tuple(files)


def _changed_word_ranges(old: str, new: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Return the (start, end) spans of tokens that differ between the pair."""
    old_tokens = [(match.group(), match.start(), match.end()) for match in _TOKEN_RE.finditer(old)]
    new_tokens = [(match.group(), match.start(), match.end()) for match in _TOKEN_RE.finditer(new)]
    matcher = difflib.SequenceMatcher(
        a=[token for token, _, _ in old_tokens],
        b=[token for token, _, _ in new_tokens],
        autojunk=False,
    )
    old_ranges: list[tuple[int, int]] = []
    new_ranges: list[tuple[int, int]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if i2 > i1:
            old_ranges.append((old_tokens[i1][1], old_tokens[i2 - 1][2]))
        if j2 > j1:
            new_ranges.append((new_tokens[j1][1], new_tokens[j2 - 1][2]))
    return old_ranges, new_ranges


def _gutter(old_number: int | None, new_number: int | None) -> str:
    old_text = "" if old_number is None else str(old_number)
    new_text = "" if new_number is None else str(new_number)
    return f"{old_text:>{_GUTTER_WIDTH}} {new_text:>{_GUTTER_WIDTH}} "


def _palette_for(tokens: ThemeTokens) -> DiffPalette:
    """Project a theme's layered diff tokens onto a row palette."""
    return DiffPalette(
        added_bg=tokens.diff_added_bg,
        removed_bg=tokens.diff_removed_bg,
        added_text=tokens.diff_added_text,
        removed_text=tokens.diff_removed_text,
        context_bg=tokens.diff_context_bg,
        line_number_text=tokens.diff_line_number_text,
    )


def render_patch(patch: str, *, theme: TuiTheme, tokens: ThemeTokens | None = None) -> RenderableType | None:
    """Render a unified patch as a structured, per-file rich renderable.

    *tokens* carries a theme's own diff palette (from its schema's ``diff``
    section); without it the opencode defaults apply, so every caller gets
    row backgrounds without new wiring.
    """
    files = parse_unified_patch(patch)
    if not files:
        return None

    palette = _palette_for(tokens) if tokens is not None else DiffPalette.for_theme(theme)
    parts: list[RenderableType] = []
    for file in files:
        parts.append(Text(file.path, style=f"bold {theme.accent}"))
        parts.extend(_render_file_lines(file, theme=theme, palette=palette))
        parts.append(Text(""))
    return Group(*parts[:-1])


def _render_file_lines(file: FileDiff, *, theme: TuiTheme, palette: DiffPalette) -> list[RenderableType]:
    body: list[RenderableType] = []
    index = 0
    lines = file.lines
    while index < len(lines):
        line = lines[index]
        if line.kind in (_REMOVE, _ADD):
            removed_run: list[DiffLine] = []
            while index < len(lines) and lines[index].kind == _REMOVE:
                removed_run.append(lines[index])
                index += 1
            added_run: list[DiffLine] = []
            while index < len(lines) and lines[index].kind == _ADD:
                added_run.append(lines[index])
                index += 1
            body.extend(_render_paired_run(removed_run, added_run, theme=theme, palette=palette))
            continue
        body.append(_render_single_line(line, theme=theme, palette=palette))
        index += 1
    return body


def _render_paired_run(
    removed_run: list[DiffLine], added_run: list[DiffLine], *, theme: TuiTheme, palette: DiffPalette
) -> list[RenderableType]:
    """Render one remove/add run with word-level emphasis on paired lines."""
    body: list[RenderableType] = []
    pair_count = min(len(removed_run), len(added_run))
    for position, line in enumerate(removed_run):
        ranges = _changed_word_ranges(line.text, added_run[position].text)[0] if position < pair_count else []
        body.append(
            _line_text(
                line,
                sign="-",
                style=palette.removed_text,
                emphasis_ranges=ranges,
                theme=theme,
                palette=palette,
            )
        )
    for position, line in enumerate(added_run):
        ranges = (
            _changed_word_ranges(removed_run[position].text, line.text)[1] if position < pair_count else []
        )
        body.append(
            _line_text(
                line,
                sign="+",
                style=palette.added_text,
                emphasis_ranges=ranges,
                theme=theme,
                palette=palette,
            )
        )
    return body


def _render_single_line(line: DiffLine, *, theme: TuiTheme, palette: DiffPalette) -> RenderableType:
    if line.kind == _CONTEXT:
        return _line_text(line, sign=" ", style=None, emphasis_ranges=[], theme=theme, palette=palette)
    if line.kind == _HUNK:
        text = Text(f"{_gutter(None, None)} {line.text}", style=theme.muted_text)
        return text
    if line.kind == _META:
        return Text(f"{_gutter(None, None)} {line.text}", style=theme.muted_text)
    return _line_text(line, sign=" ", style=None, emphasis_ranges=[], theme=theme, palette=palette)


def _line_text(
    line: DiffLine,
    *,
    sign: str,
    style: str | None,
    emphasis_ranges: list[tuple[int, int]],
    theme: TuiTheme,
    palette: DiffPalette,
) -> Text:
    text = Text(f"{_gutter(line.old_number, line.new_number)}{sign} ")
    text.append(line.text, style=style)
    # Background first, word emphasis after: the row colour is a floor the
    # emphasis layers on top of, and spans compose without shifting offsets.
    if line.kind == _ADD:
        row_bg = palette.added_bg
    elif line.kind == _REMOVE:
        row_bg = palette.removed_bg
    else:
        row_bg = palette.context_bg
    if row_bg:
        text.stylize(f"on {row_bg}", 0, len(text))
    # The line-number gutter reads as chrome, distinct from the content.
    text.stylize(palette.line_number_text, 0, _GUTTER_OFFSET)
    for start, end in emphasis_ranges:
        text.stylize(
            "bold",
            _GUTTER_OFFSET + len(sign) + 1 + start,
            _GUTTER_OFFSET + len(sign) + 1 + end,
        )
    return text
