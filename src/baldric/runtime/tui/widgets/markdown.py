"""Small Textual widgets for Baldric's interactive TUI."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, ClassVar, Literal

from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound
from rich.console import Console, Group, RenderableType
from rich.markdown import CodeBlock, Heading, Markdown
from rich.style import Style
from rich.syntax import Syntax
from rich.text import Text
from rich.theme import Theme
from textual.content import Content, Span
from textual.content import Style as TextualStyle  # type: ignore[attr-defined]
from textual.widgets import Markdown as TextualMarkdown
from textual.widgets._markdown import MarkdownParagraph  # not publicly re-exported
from textual.widgets.markdown import MarkdownFence

from baldric.runtime.tui.config import TuiTheme


class BaldricMarkdownBlock(MarkdownParagraph):
    """Markdown paragraph that applies Baldric's themed inline link color.

    Subclasses ``MarkdownParagraph`` (not ``MarkdownBlock``) so paragraph
    spacing rules that target ``MarkdownParagraph`` still apply.
    """

    DEFAULT_CSS = """
    BaldricMarkdownBlock {
        link-style: none;
        link-style-hover: underline;
        link-background-hover: transparent;
    }
    """

    @property
    def allow_select(self) -> bool:
        """Only allow native selection once Textual has mounted the block.

        Textual may hit freshly-created Markdown blocks during a mouse-down before
        they have a parent. Its selection startup path assumes selected content
        widgets have a parent container, so an unmounted selectable Markdown block
        can crash with ``container is None``.
        """
        return self.parent is not None and super().allow_select

    def _token_to_content(self, token: Any) -> Any:
        content = super()._token_to_content(token)
        markdown = self._markdown
        if not isinstance(markdown, ThemedMarkdownWidget):
            return content
        link_style = TextualStyle.parse(markdown.baldric_link_style)
        spans = []
        for span in content.spans:
            style = span.style
            if isinstance(style, TextualStyle) and "@click" in style.meta:
                style = link_style + style
            spans.append(type(span)(span.start, span.end, style))
        return type(content)(content.plain, spans=spans)


class BaldricMarkdownFence(MarkdownFence):
    """Code fence that discards invalid spans produced by Textual's highlighter."""

    @classmethod
    def highlight(
        cls,
        code: str,
        language: str,
        ansi: bool = False,
        dark: bool = False,
    ) -> Content:
        content = super().highlight(code, language, ansi=ansi, dark=dark)
        text_length = len(content.plain)
        if all(0 <= span.start < span.end <= text_length for span in content.spans):
            return content
        spans = [
            Span(max(0, span.start), min(text_length, span.end), span.style)
            for span in content.spans
            if max(0, span.start) < min(text_length, span.end)
        ]
        return Content(content.plain, spans=spans)


class ThemedMarkdownWidget(TextualMarkdown):
    """Textual Markdown widget reserved for Baldric transcript streaming."""

    @property
    def allow_select(self) -> bool:
        """Ignore stale mouse hits after a transcript widget is detached.

        Textual's selection startup dereferences the selected widget's parent.
        Its compositor can still return a removed widget before the next layout.
        """
        return self.parent is not None and super().allow_select

    BLOCKS = {
        **TextualMarkdown.BLOCKS,
        "paragraph_open": BaldricMarkdownBlock,
        "fence": BaldricMarkdownFence,
        "code_block": BaldricMarkdownFence,
    }

    DEFAULT_CSS = """
    ThemedMarkdownWidget MarkdownH1,
    ThemedMarkdownWidget MarkdownH2,
    ThemedMarkdownWidget MarkdownH3,
    ThemedMarkdownWidget MarkdownH4,
    ThemedMarkdownWidget MarkdownH5,
    ThemedMarkdownWidget MarkdownH6 {
        color: $baldric-markdown-highlight;
        content-align: left middle;
        text-style: bold;
    }

    ThemedMarkdownWidget MarkdownBlock > .code_inline {
        color: $baldric-markdown-inline-code !important;
        background: transparent !important;
    }

    ThemedMarkdownWidget MarkdownBullet {
        color: $baldric-markdown-bullet;
    }

    ThemedMarkdownWidget MarkdownFence {
        background: $baldric-markdown-code-block-background;
        overflow-x: auto;
        scrollbar-size-horizontal: 1;
    }

    /* Textual's built-in `MarkdownFence:light` rule (type + pseudo-class)
       outranks the plain descendant selector above, so restate the themed
       background for light themes. */
    ThemedMarkdownWidget MarkdownFence:light {
        background: $baldric-markdown-code-block-background;
    }

    ThemedMarkdownWidget MarkdownTableContent {
        keyline: thin $baldric-markdown-table-border;
    }

    ThemedMarkdownWidget MarkdownTableContent > .header {
        color: $baldric-markdown-table-header;
        text-style: bold;
    }
    """

    def __init__(
        self,
        markdown: str | None = None,
        *,
        theme: TuiTheme,
        classes: str | None = None,
    ) -> None:
        self.baldric_link_style = theme.markdown_link
        super().__init__(markdown, classes=classes)


_SYSTEM_PROMPT_TAG_PATTERN = re.compile(
    r"""
    </?
    [A-Za-z][A-Za-z0-9_.:-]*
    (?:
        \s+
        [A-Za-z_:][A-Za-z0-9_.:-]*
        \s*=\s*
        (?:
            "[^"]*"
            | '[^']*'
            | [^\s"'=<>`]+
        )
    )*
    \s*/?>
    """,
    re.VERBOSE,
)


_SYSTEM_PROMPT_FENCE_PATTERN = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})")


_SYSTEM_PROMPT_INDENTED_CODE_PATTERN = re.compile(r"^(?: {4,}|[ ]*\t)")


_SYSTEM_PROMPT_URI_AUTOLINK_PATTERN = re.compile(r"<[A-Za-z][A-Za-z0-9+.-]{1,31}:[^<>\s]+>")


def _system_prompt_markdown(text: str) -> str:
    """Protect prompt markup tags so Markdown displays them as highlighted code.

    Tags inside fenced blocks or existing inline code are left untouched. Tags
    containing backticks use a longer code-span delimiter so their source stays
    valid Markdown.
    """
    protected_ranges = _system_prompt_protected_ranges(text)
    output: list[str] = []
    cursor = 0
    for match in _SYSTEM_PROMPT_TAG_PATTERN.finditer(text):
        if _position_in_ranges(match.start(), protected_ranges):
            continue
        output.append(text[cursor : match.start()])
        tag = match.group(0)
        longest_backtick_run = max(
            (len(run) for run in re.findall(r"`+", tag)),
            default=0,
        )
        delimiter = "`" * (longest_backtick_run + 1)
        output.append(f"{delimiter}{tag}{delimiter}")
        cursor = match.end()
    output.append(text[cursor:])
    return "".join(output)


def _system_prompt_protected_ranges(text: str) -> tuple[tuple[int, int], ...]:
    """Return Markdown ranges that must not be rewritten."""
    block_ranges = [
        *_system_prompt_fenced_ranges(text),
        *_system_prompt_indented_code_ranges(text),
    ]
    ranges = [
        *block_ranges,
        *_system_prompt_uri_autolink_ranges(text),
        *_system_prompt_inline_code_ranges(text, block_ranges),
    ]
    return tuple(sorted(ranges))


def _system_prompt_fenced_ranges(text: str) -> tuple[tuple[int, int], ...]:
    """Find fenced Markdown blocks, including unterminated blocks."""
    ranges: list[tuple[int, int]] = []
    offset = 0
    fence_start: int | None = None
    fence_character: str | None = None
    fence_length = 0
    for line in text.splitlines(keepends=True):
        if fence_character is None:
            opening = _SYSTEM_PROMPT_FENCE_PATTERN.match(line)
            if opening is not None:
                marker = opening.group("marker")
                fence_start = offset
                fence_character = marker[0]
                fence_length = len(marker)
        elif _is_system_prompt_fence_close(
            line,
            character=fence_character,
            minimum_length=fence_length,
        ):
            assert fence_start is not None
            ranges.append((fence_start, offset + len(line)))
            fence_start = None
            fence_character = None
            fence_length = 0
        offset += len(line)
    if fence_start is not None:
        ranges.append((fence_start, len(text)))
    return tuple(ranges)


def _is_system_prompt_fence_close(
    line: str,
    *,
    character: str,
    minimum_length: int,
) -> bool:
    stripped = line.rstrip("\r\n")
    marker = re.match(rf"^ {{0,3}}{re.escape(character)}+", stripped)
    if marker is None or len(marker.group(0).lstrip()) < minimum_length:
        return False
    return not stripped[marker.end() :].strip()


def _system_prompt_indented_code_ranges(text: str) -> tuple[tuple[int, int], ...]:
    """Find lines belonging to indented Markdown code blocks."""
    ranges: list[tuple[int, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        if _SYSTEM_PROMPT_INDENTED_CODE_PATTERN.match(line) is not None:
            ranges.append((offset, offset + len(line)))
        offset += len(line)
    return tuple(ranges)


def _system_prompt_uri_autolink_ranges(text: str) -> tuple[tuple[int, int], ...]:
    """Find CommonMark URI autolinks, including schemes without ``//``."""
    return tuple((match.start(), match.end()) for match in _SYSTEM_PROMPT_URI_AUTOLINK_PATTERN.finditer(text))


def _system_prompt_inline_code_ranges(
    text: str,
    block_ranges: Sequence[tuple[int, int]],
) -> tuple[tuple[int, int], ...]:
    """Find inline backtick code spans outside Markdown code blocks."""
    ranges: list[tuple[int, int]] = []
    position = 0
    while position < len(text):
        block_end = _protected_range_end(position, block_ranges)
        if block_end is not None:
            position = block_end
            continue
        if text[position] != "`":
            position += 1
            continue
        opener_end = _backtick_run_end(text, position)
        delimiter_length = opener_end - position
        closing = _find_backtick_closer(
            text,
            start=opener_end,
            delimiter_length=delimiter_length,
            block_ranges=block_ranges,
        )
        if closing is None:
            position = opener_end
            continue
        closing_end = closing + delimiter_length
        ranges.append((position, closing_end))
        position = closing_end
    return tuple(ranges)


def _find_backtick_closer(
    text: str,
    *,
    start: int,
    delimiter_length: int,
    block_ranges: Sequence[tuple[int, int]],
) -> int | None:
    position = start
    while position < len(text):
        block_end = _protected_range_end(position, block_ranges)
        if block_end is not None:
            position = block_end
            continue
        if text[position] != "`":
            position += 1
            continue
        run_end = _backtick_run_end(text, position)
        if run_end - position == delimiter_length:
            return position
        position = run_end
    return None


def _backtick_run_end(text: str, start: int) -> int:
    end = start
    while end < len(text) and text[end] == "`":
        end += 1
    return end


def _protected_range_end(
    position: int,
    ranges: Sequence[tuple[int, int]],
) -> int | None:
    protected_end: int | None = None
    for start, end in ranges:
        if position < start:
            break
        if position < end:
            protected_end = max(protected_end or end, end)
    return protected_end


def _position_in_ranges(position: int, ranges: Sequence[tuple[int, int]]) -> bool:
    return _protected_range_end(position, ranges) is not None


def _plain_markdown(text: str) -> str:
    """Represent arbitrary plain text as wrapping Markdown paragraphs."""
    if not text:
        return ""
    return "\n".join(_escape_plain_markdown_line(line) for line in text.splitlines())


def _escape_plain_markdown_line(line: str) -> str:
    """Escape Markdown syntax while preserving plain, wrapping text."""
    escaped = line.replace("\\", "\\\\")
    for character in "`*_{}[]()#+-.!|>":
        escaped = escaped.replace(character, f"\\{character}")
    return escaped


class ThemedCodeBlock(CodeBlock):
    """Rich Markdown code block with Baldric's themed background color."""

    @classmethod
    def create(cls, markdown: Markdown, token: Any) -> ThemedCodeBlock:
        node_info = token.info or ""
        lexer_name = node_info.partition(" ")[0]
        code_block_background = getattr(markdown, "code_block_background", "default")
        return cls(lexer_name or "text", markdown.code_theme, code_block_background)

    def __init__(self, lexer_name: str, theme: str, code_block_background: str) -> None:
        super().__init__(lexer_name, theme)
        self.code_block_background = code_block_background

    def __rich_console__(self, console: Console, options: Any) -> Any:
        code = str(self.text).rstrip()
        yield Syntax(
            code,
            self.lexer_name,
            theme=self.theme,
            word_wrap=True,
            padding=1,
            background_color=self.code_block_background,
        )


class LeftAlignedMarkdownHeading(Heading):
    """Rich Markdown heading that keeps all heading levels left-aligned."""

    LEVEL_ALIGN: ClassVar[dict[str, Literal["default", "left", "center", "right", "full"]]] = {
        "h1": "left",
        "h2": "left",
        "h3": "left",
        "h4": "left",
        "h5": "left",
        "h6": "left",
    }


class ThemedMarkdown(Markdown):
    """Markdown renderer with Baldric's softer heading/accent colors."""

    elements = {
        **Markdown.elements,
        "heading_open": LeftAlignedMarkdownHeading,
        "fence": ThemedCodeBlock,
        "code_block": ThemedCodeBlock,
    }

    def __init__(
        self,
        markup: str,
        *,
        heading_style: str,
        inline_code_style: str,
        link_style: str,
        bullet_style: str,
        table_border_style: str,
        code_block_background: str,
        code_theme: str,
        inline_code_theme: str,
        style: str = "none",
    ) -> None:
        super().__init__(
            markup,
            style=style,
            code_theme=code_theme,
            inline_code_theme=inline_code_theme,
        )
        self.heading_style = heading_style
        self.inline_code_style = inline_code_style
        self.link_style = link_style
        self.bullet_style = bullet_style
        self.table_border_style = table_border_style
        self.code_block_background = code_block_background

    def __rich_console__(self, console: Console, options: Any) -> Any:
        with console.use_theme(
            _markdown_theme(
                self.heading_style,
                self.inline_code_style,
                self.link_style,
                self.bullet_style,
                self.table_border_style,
                self.code_block_background,
            )
        ):
            yield from super().__rich_console__(console, options)


def _markdown_highlight_style(theme: TuiTheme) -> str:
    return theme.markdown_heading


def _markdown_inline_code_style(theme: TuiTheme) -> str:
    return theme.markdown_inline_code


def _markdown_theme(
    heading_style: str,
    inline_code_style: str,
    link_style: str,
    bullet_style: str,
    table_border_style: str,
    code_block_background: str,
) -> Theme:
    highlight = Style.parse(heading_style)
    inline_code = Style.parse(inline_code_style)
    link = Style.parse(link_style)
    bullet = Style.parse(bullet_style)
    table_border = Style.parse(table_border_style)
    code_block = Style(bgcolor=code_block_background)
    return Theme(
        {
            "markdown.h1": highlight + Style(bold=True),
            "markdown.h2": highlight + Style(bold=True),
            "markdown.h3": highlight + Style(bold=True),
            "markdown.h4": highlight + Style(bold=True),
            "markdown.h5": highlight + Style(bold=True),
            "markdown.h6": highlight + Style(bold=True),
            "markdown.item.bullet": bullet,
            "markdown.item.number": bullet,
            "markdown.block_quote": highlight,
            "markdown.link": link,
            "markdown.link_url": link,
            "markdown.table.header": highlight + Style(bold=True),
            "markdown.table.border": table_border,
            "markdown.code": inline_code,
            "markdown.code_block": code_block,
        }
    )


def _render_fenced_body(
    text: str,
    *,
    body_style: str,
    syntax_theme: str,
    code_block_background: str,
) -> RenderableType | None:
    if "```" not in text:
        return None

    renderables: list[RenderableType] = []
    cursor = 0
    while cursor < len(text):
        fence_start = text.find("```", cursor)
        if fence_start == -1:
            _append_plain(renderables, text[cursor:], body_style=body_style)
            break

        line_start = text.rfind("\n", 0, fence_start) + 1
        if line_start != fence_start:
            return None

        fence_line_end = text.find("\n", fence_start)
        if fence_line_end == -1:
            return None
        closing_start = text.find("\n```", fence_line_end + 1)
        if closing_start == -1:
            return None

        _append_plain(renderables, text[cursor:fence_start], body_style=body_style)
        language = _syntax_language(text[fence_start + 3 : fence_line_end])
        code = text[fence_line_end + 1 : closing_start]
        renderables.append(
            Syntax(
                code.rstrip("\n"),
                language,
                theme=syntax_theme,
                word_wrap=True,
                background_color=code_block_background,
            )
        )
        closing_line_end = text.find("\n", closing_start + 1)
        cursor = len(text) if closing_line_end == -1 else closing_line_end + 1

    return Group(*renderables) if renderables else None


def _append_plain(
    renderables: list[RenderableType],
    text: str,
    *,
    body_style: str,
) -> None:
    if text:
        renderables.append(_plain_text(text.rstrip("\n"), body_style=body_style))


def _plain_text(text: str, *, body_style: str) -> Text:
    return Text(text, style=body_style, overflow="fold", no_wrap=False)


def _has_unclosed_fence(text: str) -> bool:
    fence_count = sum(1 for line in text.splitlines() if line.startswith("```"))
    return fence_count % 2 == 1


def _fence_language(raw: str) -> str:
    language = raw.strip().split(maxsplit=1)[0] if raw.strip() else ""
    return language or "text"


def _syntax_language(raw: str) -> str:
    language = _fence_language(raw)
    if language == "text":
        return language
    try:
        get_lexer_by_name(language)
    except ClassNotFound:
        return "text"
    return language
