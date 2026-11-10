"""Tests for the opencode-shaped theme schema parser (Task 1).

Reference semantics follow opencode-dev/packages/theme/src/tui/resolve.ts
(createResolver): a ``$a.b.c`` string resolves by walking the document with
dots, a missing path raises, and a reference cycle raises. Baldric additionally
allows a ``$a.b.c`` token embedded in a Rich style string such as
``"on $background.raised.base"`` (spec 2026-11-08 §4.1, roles.*.body).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from baldric.coding.rendering.theme_schema import (
    project_to_tui_theme,
    resolve_references,
)
from baldric.coding.rendering.themes import (
    BALDRIC_DARK_THEME,
    BALDRIC_LIGHT_THEME,
    HIGH_CONTRAST_THEME,
    THEME_COLOR_FIELDS,
    TuiTheme,
    theme_css_variables,
)

THEMES_DIR = Path(__file__).resolve().parents[3] / "src" / "baldric" / "coding" / "rendering" / "themes"


def test_resolve_single_level_hue_reference() -> None:
    data = {
        "hue": {"gray": {"200": "#eeeeee", "900": "#141414"}},
        "text": {"base": "$hue.gray.200"},
    }
    resolved = resolve_references(data)
    assert resolved["text"]["base"] == "#eeeeee"


def test_resolve_nested_background_reference() -> None:
    data = {
        "hue": {"gray": {"800": "#1e1e1e"}},
        "background": {"base": "#0a0a0a", "raised": {"base": "$hue.gray.800"}},
        "roles": {"user": {"body": "on $background.raised.base"}},
    }
    resolved = resolve_references(data)
    assert resolved["background"]["raised"]["base"] == "#1e1e1e"
    # A reference embedded in a Rich style string resolves the token only.
    assert resolved["roles"]["user"]["body"] == "on #1e1e1e"


def test_resolve_bare_background_reference_in_style_string() -> None:
    data = {
        "hue": {"gray": {"700": "#2a2a2a"}},
        "background": {"raised": {"base": "#1e1e1e"}},
        "roles": {"custom": {"body": "$background.raised.base"}},
    }
    resolved = resolve_references(data)
    # A lone reference token (no surrounding words) also resolves.
    assert resolved["roles"]["custom"]["body"] == "#1e1e1e"


def test_whole_value_reference_resolves_to_a_subtree() -> None:
    # opencode theme files alias whole scales ("accent": "$hue.purple"), so a
    # lone reference must resolve to any node, not only to a colour string.
    data = {
        "hue": {"purple": {"200": "#9d7cd8"}},
        "accent": "$hue.purple",
        "text": {"base": "$accent.200"},
    }
    resolved = resolve_references(data)
    assert resolved["accent"] == {"200": "#9d7cd8"}
    assert resolved["text"]["base"] == "#9d7cd8"


def test_embedded_reference_to_a_dict_still_raises() -> None:
    # A style string cannot embed a subtree; only whole-value references may.
    data = {
        "hue": {"purple": {"200": "#9d7cd8"}},
        "roles": {"user": {"body": "on $hue.purple"}},
    }
    with pytest.raises(TypeError):
        resolve_references(data)


def test_unresolved_reference_raises_keyerror_with_full_path() -> None:
    data = {"text": {"base": "$hue.nope.100"}}
    with pytest.raises(KeyError) as excinfo:
        resolve_references(data)
    # Must not silently return an empty string; message carries the full path.
    assert "hue.nope.100" in str(excinfo.value)


def test_unresolved_reference_in_style_string_raises() -> None:
    data = {"roles": {"user": {"body": "on $background.raised.missing"}}}
    with pytest.raises(KeyError) as excinfo:
        resolve_references(data)
    assert "background.raised.missing" in str(excinfo.value)


def test_cycle_raises_valueerror() -> None:
    data = {"a": "$nested.b", "nested": {"b": "$a"}}
    with pytest.raises(ValueError) as excinfo:
        resolve_references(data)
    assert "cycle" in str(excinfo.value).lower()


@pytest.mark.parametrize(
    "value",
    ["bold #ff0000", "on #101419", "#4fd6be", "bold", "a,b.c"],
)
def test_plain_strings_are_not_treated_as_references(value: str) -> None:
    data = {"colors": {"some_field": value}}
    resolved = resolve_references(data)
    assert resolved["colors"]["some_field"] == value


# --- Task 2: project a layered schema onto the flat TuiTheme (zero-break) ----

_BUILTIN_JSON_TO_THEME = {
    "baldric-dark.json": BALDRIC_DARK_THEME,
    "baldric-light.json": BALDRIC_LIGHT_THEME,
    "high-contrast.json": HIGH_CONTRAST_THEME,
}


@pytest.mark.parametrize("filename", sorted(_BUILTIN_JSON_TO_THEME))
def test_projection_matches_each_current_theme_field_by_field(filename: str) -> None:
    # The three shipped themes are the old flat format; projecting them must be
    # a byte-for-byte no-op on every colour field, so no existing theme shifts.
    reference = _BUILTIN_JSON_TO_THEME[filename]
    schema = json.loads((THEMES_DIR / filename).read_text(encoding="utf-8"))
    projected = project_to_tui_theme(schema)
    assert isinstance(projected, TuiTheme)
    for field_name in THEME_COLOR_FIELDS:
        assert getattr(projected, field_name) == getattr(reference, field_name), field_name
    assert projected.dark == reference.dark
    assert projected.syntax_theme == reference.syntax_theme
    assert projected.role_styles == reference.role_styles


@pytest.mark.parametrize("filename", sorted(_BUILTIN_JSON_TO_THEME))
def test_projection_preserves_css_variables(filename: str) -> None:
    # The published 32-key contract must not move when a theme round-trips
    # through the projection.
    reference = _BUILTIN_JSON_TO_THEME[filename]
    schema = json.loads((THEMES_DIR / filename).read_text(encoding="utf-8"))
    projected = project_to_tui_theme(schema)
    assert theme_css_variables(projected) == theme_css_variables(reference)


def test_projection_reads_a_nested_schema() -> None:
    # A future opencode-shaped theme has no ``colors`` block; each flat field
    # is derived from its layered source path instead.
    schema = {
        "name": "nested-demo",
        "appearance": "dark",
        "syntax_theme": "ansi_dark",
        "hue": {
            "gray": {"900": "#0a0a0a", "800": "#1e1e1e"},
            "accent": {"200": "#a7f3f0"},
            "green": {"200": "#9cffb1"},
            "red": {"200": "#ff4f4f"},
        },
        "text": {"base": "#d8dee9", "muted": "#667085"},
        "background": {"base": "$hue.gray.900", "raised": {"base": "$hue.gray.800"}},
        "roles": {
            "user": {"border": "#7c8ea6", "body": "#d8dee9 on $hue.gray.900"},
        },
    }
    projected = project_to_tui_theme(schema)
    assert projected.name == "nested-demo"
    assert projected.dark is True
    # Derived from the layered source path, not a hard-coded default.
    assert projected.screen_background == "#0a0a0a"
    assert projected.transcript_background == "#0a0a0a"
    assert projected.accent == "#a7f3f0"
    assert projected.screen_text == "#d8dee9"
    # A role body with an embedded reference resolves through the projection.
    assert projected.role_styles["user"].body == "#d8dee9 on #0a0a0a"


def test_projection_of_nested_schema_exposes_all_colour_fields() -> None:
    # Even a sparse nested schema must yield a complete, valid TuiTheme: no
    # field may be empty, so the TUI cannot crash applying a partial theme.
    schema = {"name": "sparse", "appearance": "dark"}
    projected = project_to_tui_theme(schema)
    for field_name in THEME_COLOR_FIELDS:
        assert getattr(projected, field_name), field_name
