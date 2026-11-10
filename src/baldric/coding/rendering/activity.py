"""Prompt chrome for the prompt prefix: spinner and thinking-tinted border.

The braille glyph, its orbiting gap, and the accent fade live here so the
prompt stays wiring-only. Extracted verbatim from ``tui/app.py``; the spinner
frames and tick rate are the values spec 2026-11-08 §6 records as the current
ones (batch 2 swaps the frames for opencode/pi's ten-frame set).
"""

from __future__ import annotations

from rich.color import Color
from rich.text import Text

from baldric.coding.rendering.themes import TuiTheme

ACTIVITY_TICK_SECONDS = 0.08
ACTIVITY_COLOR_FADE_STEPS = 24
# opencode's SPINNER_FRAMES and pi's loader DEFAULT_FRAMES are identical
# (opencode-dev/packages/tui/src/component/spinner-frames.ts,
# pi-main/packages/tui/src/components/loader.ts); the 80 ms tick matches
# opencode's dots interval.
ACTIVITY_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
ACTIVITY_SPINNER_MAX_FADE = 0.55

# Pi's thinkingOff→Max ramp (pi-main/packages/coding-agent/src/modes/
# interactive/theme/dark.json), already resolved to hex — the same values
# pi-dark.json carries under text.thinking_levels. Until themes ship their own
# ramps, this one tints every theme's prompt border (spec 2026-11-08 §5.4).
THINKING_LEVEL_COLORS: dict[str, str] = {
    "off": "#444c4f",
    "minimal": "#445761",
    "low": "#366075",
    "medium": "#3e5e9f",
    "high": "#754cc4",
    "xhigh": "#b62b9c",
    "max": "#dd093b",
}


def thinking_prompt_border_color(theme: TuiTheme, level: str | None, *, shell_mode: bool) -> str:
    """Return the prompt border colour for the thinking level.

    Shell mode keeps the tool border, an unknown or absent level falls back to
    the theme's own prompt border, and a known level picks pi's ramp colour.
    """
    if shell_mode:
        return theme.role_styles["tool"].border
    if level is None:
        return theme.prompt_border
    return THINKING_LEVEL_COLORS.get(level, theme.prompt_border)


def render_activity_indicator(
    theme: TuiTheme,
    *,
    frame: int,
    running: bool,
    shell_mode: bool = False,
) -> Text:
    """Render the prompt prefix: a spinner while running, ``$`` in shell mode.

    While running, the ``τ`` glyph is replaced by a braille-dot spinner whose
    gap orbits the cell and whose accent color gently breathes toward the
    background every ``ACTIVITY_COLOR_FADE_STEPS`` frames.
    """
    if shell_mode and not running:
        return Text("$", style=f"bold {theme.role_styles['tool'].border}")
    if not running:
        return Text("τ", style=f"bold {theme.accent}")

    glyph = ACTIVITY_SPINNER_FRAMES[frame % len(ACTIVITY_SPINNER_FRAMES)]
    half_cycle = ACTIVITY_COLOR_FADE_STEPS / 2
    phase = frame % ACTIVITY_COLOR_FADE_STEPS
    distance_from_peak = phase if phase <= half_cycle else ACTIVITY_COLOR_FADE_STEPS - phase
    fade = ACTIVITY_SPINNER_MAX_FADE * (distance_from_peak / half_cycle)
    color = _blend_hex_colors(theme.accent, theme.screen_background, fraction=fade)
    return Text(glyph, style=f"bold {color}")


def _blend_hex_colors(start: str, end: str, *, fraction: float) -> str:
    """Blend two ``#rrggbb`` colors by ``fraction``."""
    start_rgb = _hex_to_rgb(start)
    end_rgb = _hex_to_rgb(end)
    blended = tuple(
        round(start_channel + (end_channel - start_channel) * fraction)
        for start_channel, end_channel in zip(start_rgb, end_rgb, strict=True)
    )
    return f"#{blended[0]:02x}{blended[1]:02x}{blended[2]:02x}"


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    """Parse a colour name or ``#hex`` into RGB.

    Themes may carry Rich/Textual named colours (``accent: "red"``), so a
    ``#rrggbb``-only parser would raise at runtime on a running spinner.
    Rich's parser resolves names and hex alike.
    """
    parsed = Color.parse(color)
    return parsed.get_truecolor()
