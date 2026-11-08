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

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
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


# --- okhsl colour conversion (authoring-time support for pi-derived themes) --
#
# Straight port of pi-main/packages/tui/src/oklab.ts (``okhslToRgb``), which is
# itself Björn Ottosson's OKHSL reference implementation (MIT). pi expresses
# theme colours as ``okhsl(h s% l%)``; ``okhsl_to_hex`` converts them to the
# hex values shipped in ``pi-dark.json``. The unit tests pin the original's
# output (ground truth produced by running the TypeScript source directly).

type _Vec3 = tuple[float, float, float]

_LAB_TO_LMS: tuple[_Vec3, _Vec3, _Vec3] = (
    (1.0, 0.3963377773761749, 0.2158037573099136),
    (1.0, -0.1055613458156586, -0.0638541728258133),
    (1.0, -0.0894841775298119, -1.2914855480194092),
)
_LMS_TO_LINEAR_SRGB: tuple[_Vec3, _Vec3, _Vec3] = (
    (4.0767416360759583, -3.3077115392580629, 0.2309699031821043),
    (-1.2684379732850315, 2.6097573492876882, -0.341319376002657),
    (-0.0041960761386756, -0.7034186179359362, 1.7076146940746117),
)
# Per sRGB channel (red, green, blue): the (a, b) half-plane where that channel
# clips first, and the polynomial approximating the maximum saturation there.
_SATURATION_FIT: tuple[tuple[tuple[float, float], tuple[float, float, float, float, float]], ...] = (
    ((-1.8817031, -0.80936501), (1.19086277, 1.76576728, 0.59662641, 0.75515197, 0.56771245)),
    ((1.8144408, -1.19445267), (0.73956515, -0.45954404, 0.08285427, 0.12541073, -0.14503204)),
    ((0.13110758, 1.81333971), (1.35733652, -0.00915799, -1.1513021, -0.50559606, 0.00692167)),
)
_OKHSL_K1 = 0.206
_OKHSL_K2 = 0.03
_OKHSL_K3 = (1 + _OKHSL_K1) / (1 + _OKHSL_K2)

_OKHSL_PATTERN = re.compile(r"^okhsl\(\s*(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%\s*\)$")


def _multiply3(matrix: tuple[_Vec3, _Vec3, _Vec3], vector: _Vec3) -> _Vec3:
    x, y, z = vector
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z,
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z,
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z,
    )


def _dot3(weights: _Vec3, values: Sequence[float]) -> float:
    return weights[0] * values[0] + weights[1] * values[1] + weights[2] * values[2]


def _cbrt(value: float) -> float:
    # Math.cbrt semantics: sign-preserving real cube root (Python's ** would
    # return a complex number for negative operands).
    return math.copysign(abs(value) ** (1 / 3), value)


def _okhsl_to_oklab_lightness(x: float) -> float:
    k = _OKHSL_K3 * x - _OKHSL_K1
    return 0.5 * (k + math.sqrt(k * k + 4 * _OKHSL_K2 * _OKHSL_K3 * x))


def _linear_to_srgb(value: float) -> float:
    return 1.055 * value ** (1 / 2.4) - 0.055 if value > 0.0031308 else 12.92 * value


def _oklab_to_linear_srgb(lab: _Vec3) -> _Vec3:
    lms = _multiply3(_LAB_TO_LMS, lab)
    cubed: _Vec3 = (lms[0] ** 3, lms[1] ** 3, lms[2] ** 3)
    return _multiply3(_LMS_TO_LINEAR_SRGB, cubed)


def _lms_slopes(a: float, b: float) -> _Vec3:
    return (
        _LAB_TO_LMS[0][1] * a + _LAB_TO_LMS[0][2] * b,
        _LAB_TO_LMS[1][1] * a + _LAB_TO_LMS[1][2] * b,
        _LAB_TO_LMS[2][1] * a + _LAB_TO_LMS[2][2] * b,
    )


def _max_saturation(a: float, b: float) -> float:
    channel = 2
    for index in (0, 1):
        x, y = _SATURATION_FIT[index][0]
        if x * a + y * b > 1:
            channel = index
            break
    k0, k1, k2, k3, k4 = _SATURATION_FIT[channel][1]
    weights = _LMS_TO_LINEAR_SRGB[channel]
    saturation = k0 + k1 * a + k2 * b + k3 * a * a + k4 * a * b
    slopes = _lms_slopes(a, b)
    base = [1 + saturation * k for k in slopes]
    f = _dot3(weights, [value**3 for value in base])
    f1 = _dot3(weights, [3 * slopes[index] * base[index] ** 2 for index in range(3)])
    f2 = _dot3(weights, [6 * slopes[index] ** 2 * base[index] for index in range(3)])
    return saturation - (f * f1) / (f1 * f1 - 0.5 * f * f2)


def _cusp(a: float, b: float) -> tuple[float, float]:
    saturation = _max_saturation(a, b)
    linear = _oklab_to_linear_srgb((1.0, saturation * a, saturation * b))
    lightness = _cbrt(1.0 / max(linear))
    return lightness, lightness * saturation


def _max_chroma(a: float, b: float, lightness: float, cusp: tuple[float, float]) -> float:
    cusp_l, cusp_c = cusp
    if lightness <= cusp_l:
        return cusp_c * lightness / cusp_l
    t = cusp_c * (lightness - 1) / (cusp_l - 1)
    slopes = _lms_slopes(a, b)
    lms = [lightness + t * k for k in slopes]
    cubes = [value**3 for value in lms]
    first = [3 * slopes[index] * lms[index] ** 2 for index in range(3)]
    second = [6 * slopes[index] ** 2 * lms[index] for index in range(3)]
    steps: list[float] = []
    for row in _LMS_TO_LINEAR_SRGB:
        f = _dot3(row, cubes) - 1
        f1 = _dot3(row, first)
        f2 = _dot3(row, second)
        u = f1 / (f1 * f1 - 0.5 * f * f2)
        steps.append(-f * u if u >= 0 else math.inf)
    return t + min(steps)


def _chroma_stops(lightness: float, a: float, b: float) -> tuple[float, float, float]:
    """OKHSL's chroma reference points at lightness L and hue (a, b)."""
    peak = _cusp(a, b)
    c_max = _max_chroma(a, b, lightness, peak)
    k = c_max / min(lightness * (peak[1] / peak[0]), (1 - lightness) * (peak[1] / (1 - peak[0])))
    mid_s = 0.11516993 + 1 / (
        7.4477897
        + 4.1590124 * b
        + a
        * (
            -2.19557347
            + 1.75198401 * b
            + a * (-2.13704948 - 10.02301043 * b + a * (-4.24894561 + 5.38770819 * b + 4.69891013 * a))
        )
    )
    mid_t = 0.11239642 + 1 / (
        1.6132032
        - 0.68124379 * b
        + a
        * (
            0.40370612
            + 0.90148123 * b
            + a * (-0.27087943 + 0.6122399 * b + a * (0.00299215 - 0.45399568 * b - 0.14661872 * a))
        )
    )
    c_mid = (
        0.9
        * k
        * math.sqrt(math.sqrt(1 / (1 / (lightness * mid_s) ** 4 + 1 / ((1 - lightness) * mid_t) ** 4)))
    )
    c_0 = math.sqrt(1 / (1 / (lightness * 0.4) ** 2 + 1 / ((1 - lightness) * 0.8) ** 2))
    return c_0, c_mid, c_max


def _okhsl_to_rgb(hue: float, saturation: float, lightness: float) -> tuple[int, int, int]:
    lab: _Vec3 = (_okhsl_to_oklab_lightness(lightness), 0.0, 0.0)
    lab_l = lab[0]
    if 0 < lab_l < 1 and saturation > 0:
        angle = 2 * math.pi * ((hue % 360 + 360) % 360) / 360
        a = math.cos(angle)
        b = math.sin(angle)
        c_0, c_mid, c_max = _chroma_stops(lab_l, a, b)
        # Chroma rises from 0 through c_mid at s = 0.8 to c_max at s = 1.
        if saturation < 0.8:
            t = 1.25 * saturation
            k1 = 0.8 * c_0
            chroma = (t * k1) / (1 - (1 - k1 / c_mid) * t)
        else:
            t = 5 * (saturation - 0.8)
            k1 = (0.2 * c_mid**2 * 1.25**2) / c_0
            chroma = c_mid + (t * k1) / (1 - (1 - k1 / (c_max - c_mid)) * t)
        lab = (lab_l, chroma * a, chroma * b)
    # Math.round rounds half up; floor(v + 0.5) reproduces that exactly.
    linear = _oklab_to_linear_srgb(lab)
    channels = (math.floor(min(1.0, max(0.0, _linear_to_srgb(value))) * 255 + 0.5) for value in linear)
    red, green, blue = channels
    return red, green, blue


def okhsl_to_hex(okhsl: str) -> str:
    """Convert ``okhsl(h s% l%)`` to ``#rrggbb``.

    Ported from ``pi-main/packages/tui/src/oklab.ts`` (``okhslToRgb``), which
    implements Björn Ottosson's OKHSL (MIT); opencode's ``color.ts`` agrees on
    the same pipeline. This is a straight port, not a re-derivation.
    """
    match = _OKHSL_PATTERN.match(okhsl.strip())
    if match is None:
        raise ValueError(f"not an okhsl() colour: {okhsl!r}")
    hue = float(match.group(1))
    saturation = float(match.group(2))
    lightness = float(match.group(3))
    red, green, blue = _okhsl_to_rgb(hue, saturation / 100, lightness / 100)
    return f"#{red:02x}{green:02x}{blue:02x}"
