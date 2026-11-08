"""Activity spinner chrome for the prompt prefix.

The braille glyph, its orbiting gap, and the accent fade live here so the
prompt stays wiring-only. Extracted verbatim from ``tui/app.py``; the spinner
frames and tick rate are the values spec 2026-11-08 §6 records as the current
ones (batch 2 swaps the frames for opencode/pi's ten-frame set).
"""

from __future__ import annotations

from rich.text import Text

from baldric_coding.rendering.themes import TuiTheme

ACTIVITY_TICK_SECONDS = 0.15
ACTIVITY_COLOR_FADE_STEPS = 24
ACTIVITY_SPINNER_FRAMES = ("⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷")
ACTIVITY_SPINNER_MAX_FADE = 0.55


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
    value = color.removeprefix("#")
    if len(value) != 6:
        raise ValueError(f"Expected #rrggbb color, got {color!r}")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
