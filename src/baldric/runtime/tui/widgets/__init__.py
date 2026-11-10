"""TUI widgets."""

from __future__ import annotations

from subprocess import run as run

from baldric.runtime.rendering.tool_state import (
    split_rich_style_colors as _split_rich_style_colors,
)
from baldric.runtime.tui.widgets.core import (
    _BORDERLESS_TRANSCRIPT_ROLES as _BORDERLESS_TRANSCRIPT_ROLES,
)
from baldric.runtime.tui.widgets.core import (
    _HIDDEN_THINKING_PLACEHOLDER as _HIDDEN_THINKING_PLACEHOLDER,
)
from baldric.runtime.tui.widgets.core import (
    _TOOL_GROUP_INVOCATION_PATTERN as _TOOL_GROUP_INVOCATION_PATTERN,
)
from baldric.runtime.tui.widgets.core import (
    TRANSCRIPT_WINDOW_ITEMS as TRANSCRIPT_WINDOW_ITEMS,
)
from baldric.runtime.tui.widgets.core import (
    TRANSCRIPT_WINDOW_OVERSCAN_ITEMS as TRANSCRIPT_WINDOW_OVERSCAN_ITEMS,
)
from baldric.runtime.tui.widgets.core import (
    TRANSCRIPT_WINDOW_PAGE_ITEMS as TRANSCRIPT_WINDOW_PAGE_ITEMS,
)
from baldric.runtime.tui.widgets.core import (
    StreamingTranscriptMessageWidget as StreamingTranscriptMessageWidget,
)
from baldric.runtime.tui.widgets.core import (
    TranscriptLine as TranscriptLine,
)
from baldric.runtime.tui.widgets.core import (
    TranscriptMessageWidget as TranscriptMessageWidget,
)
from baldric.runtime.tui.widgets.core import (
    TranscriptView as TranscriptView,
)
from baldric.runtime.tui.widgets.core import (
    TranscriptWindowBoundary as TranscriptWindowBoundary,
)
from baldric.runtime.tui.widgets.core import (
    _bash_row_is_description_only as _bash_row_is_description_only,
)
from baldric.runtime.tui.widgets.core import (
    _chat_item_role_style as _chat_item_role_style,
)
from baldric.runtime.tui.widgets.core import (
    _clip_selection_offset as _clip_selection_offset,
)
from baldric.runtime.tui.widgets.core import (
    _clip_selection_to_text as _clip_selection_to_text,
)
from baldric.runtime.tui.widgets.core import (
    _custom_body_renderable as _custom_body_renderable,
)
from baldric.runtime.tui.widgets.core import (
    _custom_markup_to_text as _custom_markup_to_text,
)
from baldric.runtime.tui.widgets.core import (
    _custom_selection_text as _custom_selection_text,
)
from baldric.runtime.tui.widgets.core import (
    _extract_text_selection as _extract_text_selection,
)
from baldric.runtime.tui.widgets.core import (
    _identity_index as _identity_index,
)
from baldric.runtime.tui.widgets.core import (
    _last_transcript_child_is_hidden_thinking_placeholder as _last_transcript_child_is_hidden_thinking_placeholder,  # noqa: E501
)
from baldric.runtime.tui.widgets.core import (
    _render_chat_body as _render_chat_body,
)
from baldric.runtime.tui.widgets.core import (
    _render_patch_body as _render_patch_body,
)
from baldric.runtime.tui.widgets.core import (
    _render_tool_chat_body as _render_tool_chat_body,
)
from baldric.runtime.tui.widgets.core import (
    _render_tool_invocation as _render_tool_invocation,
)
from baldric.runtime.tui.widgets.core import (
    _render_transcript_tool_batch as _render_transcript_tool_batch,
)
from baldric.runtime.tui.widgets.core import (
    _render_transcript_tool_invocation as _render_transcript_tool_invocation,
)
from baldric.runtime.tui.widgets.core import (
    _split_tool_invocation_sections as _split_tool_invocation_sections,
)
from baldric.runtime.tui.widgets.core import (
    _styled_tool_invocation as _styled_tool_invocation,
)
from baldric.runtime.tui.widgets.core import (
    _tool_accent_style as _tool_accent_style,
)
from baldric.runtime.tui.widgets.core import (
    _tool_batch_row_invocation as _tool_batch_row_invocation,
)
from baldric.runtime.tui.widgets.core import (
    _tool_batch_selection_text as _tool_batch_selection_text,
)
from baldric.runtime.tui.widgets.core import (
    _transcript_item_markdown as _transcript_item_markdown,
)
from baldric.runtime.tui.widgets.core import (
    _transcript_plain_body_text as _transcript_plain_body_text,
)
from baldric.runtime.tui.widgets.core import (
    _transcript_widget as _transcript_widget,
)
from baldric.runtime.tui.widgets.core import (
    _use_plain_transcript_body as _use_plain_transcript_body,
)
from baldric.runtime.tui.widgets.core import (
    _visible_chat_text as _visible_chat_text,
)
from baldric.runtime.tui.widgets.core import (
    render_chat_item as render_chat_item,
)
from baldric.runtime.tui.widgets.core import (
    render_completion_suggestions as render_completion_suggestions,
)
from baldric.runtime.tui.widgets.core import (
    transcript_item_selection_text as transcript_item_selection_text,
)
from baldric.runtime.tui.widgets.markdown import (
    _SYSTEM_PROMPT_FENCE_PATTERN as _SYSTEM_PROMPT_FENCE_PATTERN,
)
from baldric.runtime.tui.widgets.markdown import (
    _SYSTEM_PROMPT_INDENTED_CODE_PATTERN as _SYSTEM_PROMPT_INDENTED_CODE_PATTERN,
)
from baldric.runtime.tui.widgets.markdown import (
    _SYSTEM_PROMPT_TAG_PATTERN as _SYSTEM_PROMPT_TAG_PATTERN,
)
from baldric.runtime.tui.widgets.markdown import (
    _SYSTEM_PROMPT_URI_AUTOLINK_PATTERN as _SYSTEM_PROMPT_URI_AUTOLINK_PATTERN,
)
from baldric.runtime.tui.widgets.markdown import (
    BaldricMarkdownBlock as BaldricMarkdownBlock,
)
from baldric.runtime.tui.widgets.markdown import (
    BaldricMarkdownFence as BaldricMarkdownFence,
)
from baldric.runtime.tui.widgets.markdown import (
    LeftAlignedMarkdownHeading as LeftAlignedMarkdownHeading,
)
from baldric.runtime.tui.widgets.markdown import (
    ThemedCodeBlock as ThemedCodeBlock,
)
from baldric.runtime.tui.widgets.markdown import (
    ThemedMarkdown as ThemedMarkdown,
)
from baldric.runtime.tui.widgets.markdown import (
    ThemedMarkdownWidget as ThemedMarkdownWidget,
)
from baldric.runtime.tui.widgets.markdown import (
    _append_plain as _append_plain,
)
from baldric.runtime.tui.widgets.markdown import (
    _backtick_run_end as _backtick_run_end,
)
from baldric.runtime.tui.widgets.markdown import (
    _escape_plain_markdown_line as _escape_plain_markdown_line,
)
from baldric.runtime.tui.widgets.markdown import (
    _fence_language as _fence_language,
)
from baldric.runtime.tui.widgets.markdown import (
    _find_backtick_closer as _find_backtick_closer,
)
from baldric.runtime.tui.widgets.markdown import (
    _has_unclosed_fence as _has_unclosed_fence,
)
from baldric.runtime.tui.widgets.markdown import (
    _is_system_prompt_fence_close as _is_system_prompt_fence_close,
)
from baldric.runtime.tui.widgets.markdown import (
    _markdown_highlight_style as _markdown_highlight_style,
)
from baldric.runtime.tui.widgets.markdown import (
    _markdown_inline_code_style as _markdown_inline_code_style,
)
from baldric.runtime.tui.widgets.markdown import (
    _markdown_theme as _markdown_theme,
)
from baldric.runtime.tui.widgets.markdown import (
    _plain_markdown as _plain_markdown,
)
from baldric.runtime.tui.widgets.markdown import (
    _plain_text as _plain_text,
)
from baldric.runtime.tui.widgets.markdown import (
    _position_in_ranges as _position_in_ranges,
)
from baldric.runtime.tui.widgets.markdown import (
    _protected_range_end as _protected_range_end,
)
from baldric.runtime.tui.widgets.markdown import (
    _render_fenced_body as _render_fenced_body,
)
from baldric.runtime.tui.widgets.markdown import (
    _syntax_language as _syntax_language,
)
from baldric.runtime.tui.widgets.markdown import (
    _system_prompt_fenced_ranges as _system_prompt_fenced_ranges,
)
from baldric.runtime.tui.widgets.markdown import (
    _system_prompt_indented_code_ranges as _system_prompt_indented_code_ranges,
)
from baldric.runtime.tui.widgets.markdown import (
    _system_prompt_inline_code_ranges as _system_prompt_inline_code_ranges,
)
from baldric.runtime.tui.widgets.markdown import (
    _system_prompt_markdown as _system_prompt_markdown,
)
from baldric.runtime.tui.widgets.markdown import (
    _system_prompt_protected_ranges as _system_prompt_protected_ranges,
)
from baldric.runtime.tui.widgets.markdown import (
    _system_prompt_uri_autolink_ranges as _system_prompt_uri_autolink_ranges,
)
from baldric.runtime.tui.widgets.markdown_stream import (
    STREAM_FLUSH_INTERVAL_SECONDS as STREAM_FLUSH_INTERVAL_SECONDS,
)
from baldric.runtime.tui.widgets.markdown_stream import (
    TranscriptMarkdownStream as TranscriptMarkdownStream,
)
from baldric.runtime.tui.widgets.prompt_input import (
    PASTE_DISPLAY_THRESHOLD as PASTE_DISPLAY_THRESHOLD,
)
from baldric.runtime.tui.widgets.prompt_input import (
    CompletionActionTarget as CompletionActionTarget,
)
from baldric.runtime.tui.widgets.prompt_input import (
    PromptInput as PromptInput,
)
from baldric.runtime.tui.widgets.prompt_input import (
    _hidden_prompt_bindings as _hidden_prompt_bindings,
)
from baldric.runtime.tui.widgets.prompt_input import (
    _is_thinking_cycle_key as _is_thinking_cycle_key,
)
from baldric.runtime.tui.widgets.prompt_input import (
    _key_hint as _key_hint,
)
from baldric.runtime.tui.widgets.prompt_input import (
    _prompt_bindings as _prompt_bindings,
)
from baldric.runtime.tui.widgets.prompt_input import (
    _terminal_command_prefix_span as _terminal_command_prefix_span,
)
from baldric.runtime.tui.widgets.sidebar import (
    BALDRIC_SIDEBAR_LOGO as BALDRIC_SIDEBAR_LOGO,
)
from baldric.runtime.tui.widgets.sidebar import (
    GIT_BRANCH_RECHECK_SECONDS as GIT_BRANCH_RECHECK_SECONDS,
)
from baldric.runtime.tui.widgets.sidebar import (
    SIDEBAR_BULLET_LIST_LIMIT as SIDEBAR_BULLET_LIST_LIMIT,
)
from baldric.runtime.tui.widgets.sidebar import (
    SIDEBAR_COMMA_LIST_MAX_LINES as SIDEBAR_COMMA_LIST_MAX_LINES,
)
from baldric.runtime.tui.widgets.sidebar import (
    CompactSessionInfo as CompactSessionInfo,
)
from baldric.runtime.tui.widgets.sidebar import (
    SessionSidebar as SessionSidebar,
)
from baldric.runtime.tui.widgets.sidebar import (
    SessionSummarySource as SessionSummarySource,
)
from baldric.runtime.tui.widgets.sidebar import (
    SidebarFileItem as SidebarFileItem,
)
from baldric.runtime.tui.widgets.sidebar import (
    _absolute_sidebar_path as _absolute_sidebar_path,
)
from baldric.runtime.tui.widgets.sidebar import (
    _build_sidebar_content as _build_sidebar_content,
)
from baldric.runtime.tui.widgets.sidebar import (
    _bullet_list as _bullet_list,
)
from baldric.runtime.tui.widgets.sidebar import (
    _comma_list as _comma_list,
)
from baldric.runtime.tui.widgets.sidebar import (
    _compact_token_count as _compact_token_count,
)
from baldric.runtime.tui.widgets.sidebar import (
    _compact_usage_count as _compact_usage_count,
)
from baldric.runtime.tui.widgets.sidebar import (
    _context_file_label as _context_file_label,
)
from baldric.runtime.tui.widgets.sidebar import (
    _context_file_labels as _context_file_labels,
)
from baldric.runtime.tui.widgets.sidebar import (
    _context_file_widgets as _context_file_widgets,
)
from baldric.runtime.tui.widgets.sidebar import (
    _context_usage as _context_usage,
)
from baldric.runtime.tui.widgets.sidebar import (
    _format_cost as _format_cost,
)
from baldric.runtime.tui.widgets.sidebar import (
    _format_milliseconds as _format_milliseconds,
)
from baldric.runtime.tui.widgets.sidebar import (
    _git_branch as _git_branch,
)
from baldric.runtime.tui.widgets.sidebar import (
    _git_head_stamp as _git_head_stamp,
)
from baldric.runtime.tui.widgets.sidebar import (
    _GitBranchLookup as _GitBranchLookup,
)
from baldric.runtime.tui.widgets.sidebar import (
    _grouped_prompt_list as _grouped_prompt_list,
)
from baldric.runtime.tui.widgets.sidebar import (
    _grouped_resource_names as _grouped_resource_names,
)
from baldric.runtime.tui.widgets.sidebar import (
    _grouped_sidebar_file_widgets as _grouped_sidebar_file_widgets,
)
from baldric.runtime.tui.widgets.sidebar import (
    _grouped_skill_list as _grouped_skill_list,
)
from baldric.runtime.tui.widgets.sidebar import (
    _limited_bullet_list as _limited_bullet_list,
)
from baldric.runtime.tui.widgets.sidebar import (
    _LineLimitedCommaList as _LineLimitedCommaList,
)
from baldric.runtime.tui.widgets.sidebar import (
    _plural as _plural,
)
from baldric.runtime.tui.widgets.sidebar import (
    _prompt_file_widgets as _prompt_file_widgets,
)
from baldric.runtime.tui.widgets.sidebar import (
    _read_git_branch as _read_git_branch,
)
from baldric.runtime.tui.widgets.sidebar import (
    _replace_sidebar_file_widgets as _replace_sidebar_file_widgets,
)
from baldric.runtime.tui.widgets.sidebar import (
    _resource_origin_label as _resource_origin_label,
)
from baldric.runtime.tui.widgets.sidebar import (
    _resource_origin_sort_key as _resource_origin_sort_key,
)
from baldric.runtime.tui.widgets.sidebar import (
    _separate_sidebar_sections as _separate_sidebar_sections,
)
from baldric.runtime.tui.widgets.sidebar import (
    _session_resource_fingerprint as _session_resource_fingerprint,
)
from baldric.runtime.tui.widgets.sidebar import (
    _session_summary_fingerprint as _session_summary_fingerprint,
)
from baldric.runtime.tui.widgets.sidebar import (
    _set_collapsible_title as _set_collapsible_title,
)
from baldric.runtime.tui.widgets.sidebar import (
    _short_path as _short_path,
)
from baldric.runtime.tui.widgets.sidebar import (
    _sidebar_brand as _sidebar_brand,
)
from baldric.runtime.tui.widgets.sidebar import (
    _sidebar_resource_title as _sidebar_resource_title,
)
from baldric.runtime.tui.widgets.sidebar import (
    _sidebar_section as _sidebar_section,
)
from baldric.runtime.tui.widgets.sidebar import (
    _sidebar_separator as _sidebar_separator,
)
from baldric.runtime.tui.widgets.sidebar import (
    _SidebarContent as _SidebarContent,
)
from baldric.runtime.tui.widgets.sidebar import (
    _skill_file_widgets as _skill_file_widgets,
)
from baldric.runtime.tui.widgets.sidebar import (
    _skill_section_title as _skill_section_title,
)
from baldric.runtime.tui.widgets.sidebar import (
    _styled_cwd as _styled_cwd,
)
from baldric.runtime.tui.widgets.sidebar import (
    _thinking_level as _thinking_level,
)
from baldric.runtime.tui.widgets.sidebar import (
    render_compact_session_info as render_compact_session_info,
)
from baldric.runtime.tui.widgets.sidebar import (
    render_session_sidebar as render_session_sidebar,
)
from baldric.runtime.tui.widgets.system_prompt import (
    SystemPromptSectionWidget as SystemPromptSectionWidget,
)
from baldric.runtime.tui.widgets.system_prompt import (
    SystemPromptSourcesWidget as SystemPromptSourcesWidget,
)
from baldric.runtime.tui.widgets.system_prompt import (
    _system_prompt_source_color as _system_prompt_source_color,
)

__all__ = [
    "BaldricMarkdownBlock",
    "BaldricMarkdownFence",
    "LeftAlignedMarkdownHeading",
    "ThemedCodeBlock",
    "ThemedMarkdown",
    "ThemedMarkdownWidget",
    "_SYSTEM_PROMPT_FENCE_PATTERN",
    "_SYSTEM_PROMPT_INDENTED_CODE_PATTERN",
    "_SYSTEM_PROMPT_TAG_PATTERN",
    "_SYSTEM_PROMPT_URI_AUTOLINK_PATTERN",
    "_append_plain",
    "_backtick_run_end",
    "_escape_plain_markdown_line",
    "_fence_language",
    "_find_backtick_closer",
    "_has_unclosed_fence",
    "_is_system_prompt_fence_close",
    "_markdown_highlight_style",
    "_markdown_inline_code_style",
    "_markdown_theme",
    "_plain_markdown",
    "_plain_text",
    "_position_in_ranges",
    "_protected_range_end",
    "_render_fenced_body",
    "_syntax_language",
    "_system_prompt_fenced_ranges",
    "_system_prompt_indented_code_ranges",
    "_system_prompt_inline_code_ranges",
    "_system_prompt_markdown",
    "_system_prompt_protected_ranges",
    "_system_prompt_uri_autolink_ranges",
    "PASTE_DISPLAY_THRESHOLD",
    "CompletionActionTarget",
    "PromptInput",
    "_hidden_prompt_bindings",
    "_is_thinking_cycle_key",
    "_key_hint",
    "_prompt_bindings",
    "_terminal_command_prefix_span",
    "BALDRIC_SIDEBAR_LOGO",
    "SIDEBAR_BULLET_LIST_LIMIT",
    "SIDEBAR_COMMA_LIST_MAX_LINES",
    "TranscriptLine",
    "SessionSummarySource",
    "SidebarFileItem",
    "_set_collapsible_title",
    "SessionSidebar",
    "CompactSessionInfo",
    "_sidebar_resource_title",
    "_skill_section_title",
    "_session_summary_fingerprint",
    "_session_resource_fingerprint",
    "BaldricMarkdownBlock",
    "BaldricMarkdownFence",
    "ThemedMarkdownWidget",
    "_BORDERLESS_TRANSCRIPT_ROLES",
    "_HIDDEN_THINKING_PLACEHOLDER",
    "TRANSCRIPT_WINDOW_ITEMS",
    "TRANSCRIPT_WINDOW_PAGE_ITEMS",
    "TRANSCRIPT_WINDOW_OVERSCAN_ITEMS",
    "TranscriptWindowBoundary",
    "SystemPromptSectionWidget",
    "SystemPromptSourcesWidget",
    "_system_prompt_source_color",
    "TranscriptMessageWidget",
    "STREAM_FLUSH_INTERVAL_SECONDS",
    "TranscriptMarkdownStream",
    "StreamingTranscriptMessageWidget",
    "TranscriptView",
    "_identity_index",
    "_last_transcript_child_is_hidden_thinking_placeholder",
    "_transcript_widget",
    "transcript_item_selection_text",
    "_custom_markup_to_text",
    "_custom_selection_text",
    "_custom_body_renderable",
    "_split_rich_style_colors",
    "_use_plain_transcript_body",
    "_transcript_plain_body_text",
    "_render_transcript_tool_invocation",
    "_transcript_item_markdown",
    "_SYSTEM_PROMPT_TAG_PATTERN",
    "_SYSTEM_PROMPT_FENCE_PATTERN",
    "_SYSTEM_PROMPT_INDENTED_CODE_PATTERN",
    "_SYSTEM_PROMPT_URI_AUTOLINK_PATTERN",
    "_system_prompt_markdown",
    "_system_prompt_protected_ranges",
    "_system_prompt_fenced_ranges",
    "_is_system_prompt_fence_close",
    "_system_prompt_indented_code_ranges",
    "_system_prompt_uri_autolink_ranges",
    "_system_prompt_inline_code_ranges",
    "_find_backtick_closer",
    "_backtick_run_end",
    "_protected_range_end",
    "_position_in_ranges",
    "_plain_markdown",
    "_escape_plain_markdown_line",
    "_extract_text_selection",
    "_clip_selection_to_text",
    "_clip_selection_offset",
    "_SidebarContent",
    "render_session_sidebar",
    "_build_sidebar_content",
    "_separate_sidebar_sections",
    "_sidebar_section",
    "_sidebar_separator",
    "_sidebar_brand",
    "render_compact_session_info",
    "render_chat_item",
    "_chat_item_role_style",
    "_tool_accent_style",
    "_bash_row_is_description_only",
    "_tool_batch_row_invocation",
    "_tool_batch_selection_text",
    "_render_transcript_tool_batch",
    "_render_tool_chat_body",
    "_render_tool_invocation",
    "_TOOL_GROUP_INVOCATION_PATTERN",
    "_styled_tool_invocation",
    "_split_tool_invocation_sections",
    "_visible_chat_text",
    "_render_chat_body",
    "_render_patch_body",
    "ThemedCodeBlock",
    "LeftAlignedMarkdownHeading",
    "ThemedMarkdown",
    "_markdown_highlight_style",
    "_markdown_inline_code_style",
    "_markdown_theme",
    "_render_fenced_body",
    "_append_plain",
    "_plain_text",
    "_context_usage",
    "_styled_cwd",
    "_format_milliseconds",
    "_compact_token_count",
    "_context_file_labels",
    "_context_file_label",
    "_thinking_level",
    "GIT_BRANCH_RECHECK_SECONDS",
    "_GitBranchLookup",
    "_GIT_BRANCH_CACHE",
    "_git_branch",
    "_git_head_stamp",
    "_read_git_branch",
    "_has_unclosed_fence",
    "_fence_language",
    "_syntax_language",
    "render_completion_suggestions",
    "_LineLimitedCommaList",
    "_comma_list",
    "_compact_usage_count",
    "_format_cost",
    "_plural",
    "_replace_sidebar_file_widgets",
    "_context_file_widgets",
    "_skill_file_widgets",
    "_prompt_file_widgets",
    "_grouped_sidebar_file_widgets",
    "_resource_origin_sort_key",
    "_absolute_sidebar_path",
    "_grouped_skill_list",
    "_grouped_prompt_list",
    "_grouped_resource_names",
    "_resource_origin_label",
    "_limited_bullet_list",
    "_bullet_list",
    "_short_path",
]

from baldric.runtime.tui.widgets.sidebar import _GIT_BRANCH_CACHE as _GIT_BRANCH_CACHE
