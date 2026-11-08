"""Parse an opencode-shaped theme schema into flat, layered tokens.

The data layer is nested (``hue.gray.200``, ``background.raised.base``) so a
theme can express *layering*; consumers get a flat ``ThemeTokens`` because a
renderer only ever wants "the raised surface colour", not the path to it.

Reference syntax follows opencode's theme files
(``opencode-dev/packages/theme/src/tui/resolve.ts``, ``createResolver``): a
string token beginning with ``$`` is a dotted path into the same document.
Baldric additionally allows a reference embedded inside a Rich style string,
because ``roles.*.body`` is written as ``"on $background.raised.base"`` (spec
2026-11-08 §4.1). Every whitespace-separated token is inspected, so plain words
(``on``, ``bold``) and literal colours (``#ff0000``) pass through untouched.

Token shape follows ``opencode-dev/packages/theme/src/tui/schema.ts``:
``hue.<name>.<step>``, ``text.*``, ``background.raised.{base,high,max}``,
``diff.*`` and a Baldric-specific ``roles.*`` layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from baldric_coding.rendering.themes import TuiTheme

_REFERENCE_PREFIX = "$"


def _lookup(document: object, path: str) -> object:
    """Walk *document* along a dotted *path*, raising ``KeyError`` on a miss."""
    node: object = document
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"unresolved theme reference: ${path}")
        node = node[part]
    return node


def _reference_path(token: str) -> str | None:
    """Return the dotted path when *token* is a ``$``-reference, else ``None``."""
    if not token.startswith(_REFERENCE_PREFIX):
        return None
    path = token[len(_REFERENCE_PREFIX) :]
    return path or None


def _resolve(node: object, *, root: object, seen: tuple[str, ...]) -> object:
    if isinstance(node, dict):
        return {key: _resolve(value, root=root, seen=seen) for key, value in node.items()}
    if isinstance(node, list):
        return [_resolve(item, root=root, seen=seen) for item in node]
    if isinstance(node, str):
        return _resolve_string(node, root=root, seen=seen)
    return node


def _resolve_string(value: str, *, root: object, seen: tuple[str, ...]) -> object:
    """Resolve every ``$``-token inside a (possibly style-string) value."""
    tokens = value.split()
    resolved_tokens: list[str] = []
    for token in tokens:
        path = _reference_path(token)
        if path is None:
            resolved_tokens.append(token)
            continue
        if path in seen:
            chain = " -> ".join(seen + (path,))
            raise ValueError(f"cycle in theme references: {chain}")
        target = _resolve(_lookup(root, path), root=root, seen=seen + (path,))
        if isinstance(target, str):
            resolved_tokens.append(target)
        elif isinstance(target, (dict, list)):
            raise TypeError(f"theme reference ${path} resolves to a non-color {type(target).__name__}")
        else:
            resolved_tokens.append(str(target))
    # Preserve the original single-value shape when there is exactly one token.
    if len(resolved_tokens) == 1 and len(tokens) == 1:
        return resolved_tokens[0]
    return " ".join(resolved_tokens)


def resolve_references(data: object) -> dict[str, Any]:
    """Return a deep copy of *data* with every ``$a.b.c`` reference resolved."""
    resolved = _resolve(data, root=data, seen=())
    if not isinstance(resolved, dict):
        raise TypeError("theme document must be an object")
    return resolved


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    """Flat, layered view of a theme for component code.

    Only the fields the first batch uses are declared; later batches append
    fields (never rename) so consumers stay stable. ``None`` backgrounds mean
    "no card surface" — assistant and thinking rows are deliberately bare.
    """

    name: str
    dark: bool
    # text
    text_base: str
    text_muted: str
    text_faint: str
    text_thinking: str
    # surfaces: the layering the flat TuiTheme could not express
    surface_base: str
    surface_raised: str
    surface_high: str
    surface_max: str
    # accents and status
    accent: str
    success: str
    error: str
    # diff
    diff_added_bg: str
    diff_removed_bg: str
    diff_added_text: str
    diff_removed_text: str
    diff_context_bg: str
    diff_line_number_text: str
    # role card backgrounds
    role_user_bg: str | None
    role_tool_pending_bg: str | None
    role_tool_success_bg: str | None
    role_tool_error_bg: str | None


def _get(document: dict[str, Any], *path: str, default: str) -> str:
    node: Any = document
    for part in path:
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node if isinstance(node, str) and node else default


def _optional(roles: Any, role: str, key: str) -> str | None:
    if not isinstance(roles, dict):
        return None
    node = roles.get(role)
    if not isinstance(node, dict):
        return None
    value = node.get(key)
    return value if isinstance(value, str) and value else None


def build_tokens(schema: dict[str, Any]) -> ThemeTokens:
    """Build the component-facing token view from a resolved schema."""
    resolved = resolve_references(schema)
    roles = resolved.get("roles", {})
    return ThemeTokens(
        name=str(resolved.get("name", "unnamed")),
        dark=str(resolved.get("appearance", "dark")) == "dark",
        text_base=_get(resolved, "text", "base", default="#d8dee9"),
        text_muted=_get(resolved, "text", "muted", default="#808080"),
        text_faint=_get(resolved, "text", "faint", default="#4c4c4c"),
        text_thinking=_get(resolved, "text", "thinking", default="#9ca3af"),
        surface_base=_get(resolved, "background", "base", default="#000000"),
        surface_raised=_get(resolved, "background", "raised", "base", default="#1e1e1e"),
        surface_high=_get(resolved, "background", "raised", "high", default="#2a2a2a"),
        surface_max=_get(resolved, "background", "raised", "max", default="#363636"),
        accent=_get(resolved, "hue", "accent", "200", default="#a7f3f0"),
        success=_get(resolved, "hue", "green", "200", default="#9cffb1"),
        error=_get(resolved, "hue", "red", "200", default="#ff4f4f"),
        diff_added_bg=_get(resolved, "diff", "background", "added", default="#20303b"),
        diff_removed_bg=_get(resolved, "diff", "background", "removed", default="#37222c"),
        diff_added_text=_get(resolved, "diff", "text", "added", default="#4fd6be"),
        diff_removed_text=_get(resolved, "diff", "text", "removed", default="#c53b53"),
        diff_context_bg=_get(resolved, "diff", "background", "context", default="#000000"),
        diff_line_number_text=_get(resolved, "diff", "lineNumber", "text", default="#8f8f8f"),
        role_user_bg=_optional(roles, "user", "background"),
        role_tool_pending_bg=_optional(roles, "tool_pending", "background"),
        role_tool_success_bg=_optional(roles, "tool_success", "background"),
        role_tool_error_bg=_optional(roles, "tool_error", "background"),
    )


# Flat TuiTheme colour field -> layered schema path. Only fields with a genuine
# schema home are listed (paths follow spec 2026-11-08 §4.1, which mirrors
# opencode's token sections); fields without one come from the ``colors``
# overlay or the default dark palette instead of a made-up path.
_FLAT_FIELD_SOURCE: dict[str, tuple[str, ...]] = {
    "screen_background": ("background", "base"),
    "screen_text": ("text", "base"),
    "chrome_background": ("background", "raised", "base"),
    "chrome_text": ("text", "base"),
    "muted_text": ("text", "muted"),
    "sidebar_background": ("background", "raised", "base"),
    "border": ("border", "base"),
    "transcript_background": ("background", "base"),
    "prompt_background": ("background", "raised", "base"),
    "prompt_text": ("text", "base"),
    "prompt_border": ("border", "accent"),
    "autocomplete_background": ("background", "raised", "base"),
    "accent": ("hue", "accent", "200"),
    "success": ("hue", "green", "200"),
    "error": ("hue", "red", "200"),
    "tool_success_text": ("hue", "green", "200"),
    "tool_error_text": ("hue", "red", "200"),
    "highlight_background": ("background", "raised", "high"),
    "highlight_text": ("text", "base"),
    "markdown_heading": ("markdown", "heading"),
    "markdown_table_header": ("markdown", "text"),
    "markdown_table_border": ("border", "base"),
    "markdown_inline_code": ("markdown", "code"),
    "markdown_code_block_background": ("markdown", "codeBlock"),
    "markdown_link": ("markdown", "link"),
    "markdown_bullet": ("markdown", "listEnumeration"),
    "completion_description": ("text", "muted"),
    "scrollbar": ("scrollbar", "base"),
}


def _peek(document: dict[str, Any], *path: str) -> str | None:
    """Return the string at *path*, or ``None`` when absent or not a colour str."""
    node: Any = document
    for part in path:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) and node else None


def project_to_tui_theme(schema: dict[str, Any]) -> TuiTheme:
    """Project a layered schema onto the flat, frozen TuiTheme contract.

    The flat view is what third-party extension factories receive
    (``Callable[[TuiTheme], Widget]`` in extensions/api.py), so its field
    semantics must not change: same names, same meaning, same role shape.

    Each colour field resolves through three layers, in order:

    1. the theme's own ``colors`` block — the old flat format passes through
       untouched, so shipped themes stay byte-for-byte identical;
    2. ``_FLAT_FIELD_SOURCE`` — the layered token a flat field is derived from;
    3. the built-in dark palette — a partial theme fills chrome fields from
       the shipped default instead of crashing or inventing a colour.

    Roles are projected only for names in ``TRANSCRIPT_ROLES``; the schema's
    ``tool_pending``/``tool_success``/``tool_error`` entries are consumed by
    :class:`ThemeTokens` and never leak into the flat view.
    """
    from baldric_coding.rendering.themes import (
        BALDRIC_DARK_THEME,
        THEME_COLOR_FIELDS,
        TRANSCRIPT_ROLES,
        TuiRoleStyle,
        TuiTheme,
    )

    resolved = resolve_references(schema)
    overlay = resolved.get("colors")
    overlay = overlay if isinstance(overlay, dict) else {}

    dark = resolved.get("dark")
    if not isinstance(dark, bool):
        dark = str(resolved.get("appearance", "dark")) == "dark"
    syntax = resolved.get("syntax_theme")
    if not isinstance(syntax, str) or not syntax:
        syntax = "ansi_dark" if dark else "ansi_light"

    def color(field: str) -> str:
        overlay_value = overlay.get(field)
        if isinstance(overlay_value, str) and overlay_value:
            return overlay_value
        path = _FLAT_FIELD_SOURCE.get(field)
        if path is not None:
            from_schema = _peek(resolved, *path)
            if from_schema is not None:
                return from_schema
        # field iterates THEME_COLOR_FIELDS, so the attribute is always a str.
        return cast(str, getattr(BALDRIC_DARK_THEME, field))

    roles_raw = resolved.get("roles")
    roles_raw = roles_raw if isinstance(roles_raw, dict) else {}
    role_styles = {
        role: TuiRoleStyle(
            border=(
                spec["border"] if isinstance(spec.get("border"), str) and spec["border"] else color("border")
            ),
            body=spec["body"] if isinstance(spec.get("body"), str) else "",
        )
        for role, spec in roles_raw.items()
        if role in TRANSCRIPT_ROLES and isinstance(spec, dict)
    }
    return TuiTheme(
        name=str(resolved.get("name", "unnamed")),
        dark=dark,
        syntax_theme=syntax,
        role_styles=role_styles,
        **{field: color(field) for field in THEME_COLOR_FIELDS},
    )
