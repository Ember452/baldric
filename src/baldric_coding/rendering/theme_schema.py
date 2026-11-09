"""Parse an opencode-shaped theme schema and project it to a flat TuiTheme.

The data layer is nested (``hue.gray.200``, ``background.raised.base``) so a
theme can express *layering*; the projection flattens it onto the frozen
``TuiTheme`` contract the components already consume.

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

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from baldric_coding.rendering.themes import TuiTheme

_REFERENCE_PREFIX = "$"


def _lookup(root: object, path: str, seen: tuple[str, ...]) -> object:
    """Walk *root* along a dotted *path*, resolving reference hops on the way.

    An intermediate hop may itself be a reference (opencode aliases whole
    scales: ``"accent": "$hue.purple"``), so each string node met on the way
    is resolved before descending further.
    """
    node: object = root
    for part in path.split("."):
        if isinstance(node, str):
            tokens = node.split()
            if len(tokens) == 1:
                hop = _reference_path(tokens[0])
                if hop is not None:
                    node = _resolve_reference(hop, root=root, seen=seen)
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"unresolved theme reference: ${path}")
        node = node[part]
    return node


def _resolve_reference(path: str, *, root: object, seen: tuple[str, ...]) -> object:
    """Resolve one ``$path`` reference with cycle detection."""
    if path in seen:
        chain = " -> ".join(seen + (path,))
        raise ValueError(f"cycle in theme references: {chain}")
    return _resolve(_lookup(root, path, seen + (path,)), root=root, seen=seen + (path,))


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
    if len(tokens) == 1:
        whole_path = _reference_path(tokens[0])
        if whole_path is not None:
            # A lone reference is a whole-value reference: opencode theme
            # files alias entire scales ("accent": "$hue.purple"), so it may
            # resolve to any node, not only to a colour string.
            return _resolve_reference(whole_path, root=root, seen=seen)
    resolved_tokens: list[str] = []
    for token in tokens:
        path = _reference_path(token)
        if path is None:
            resolved_tokens.append(token)
            continue
        target = _resolve_reference(path, root=root, seen=seen)
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
    "markdown_table_header": ("text", "muted"),
    "markdown_table_border": ("border", "muted"),
    "markdown_inline_code": ("markdown", "code"),
    # opencode's markdown.codeBlock is the code block *text* colour; the code
    # block surface is the raised layer.
    "markdown_code_block_background": ("background", "raised", "base"),
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


def _resolve_dark(resolved: dict[str, Any]) -> bool:
    """Resolve a document's light/dark identity.

    Layered documents use ``appearance``; old flat ones use ``dark: bool``.
    Prefer ``appearance`` when present, then an explicit ``dark`` boolean, then
    default to dark — mirroring the flat parser's inference order.
    """
    appearance = resolved.get("appearance")
    if isinstance(appearance, str) and appearance:
        return appearance == "dark"
    dark = resolved.get("dark")
    if isinstance(dark, bool):
        return dark
    return True


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

    Roles are projected only for names in ``TRANSCRIPT_ROLES``; any other role
    entries in the document are ignored rather than leaking into the flat view.
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

    dark = _resolve_dark(resolved)
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
