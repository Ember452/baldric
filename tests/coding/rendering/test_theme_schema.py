"""Tests for the opencode-shaped theme schema parser (Task 1).

Reference semantics follow opencode-dev/packages/theme/src/tui/resolve.ts
(createResolver): a ``$a.b.c`` string resolves by walking the document with
dots, a missing path raises, and a reference cycle raises. Baldric additionally
allows a ``$a.b.c`` token embedded in a Rich style string such as
``"on $background.raised.base"`` (spec 2026-11-08 §4.1, roles.*.body).
"""

from __future__ import annotations

import pytest

from baldric_coding.rendering.theme_schema import (
    ThemeTokens,
    build_tokens,
    resolve_references,
)


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


def test_build_tokens_exposes_layering() -> None:
    schema = {
        "name": "demo",
        "appearance": "dark",
        "hue": {"gray": {"800": "#1e1e1e", "900": "#0a0a0a"}},
        "text": {"base": "#eeeeee", "muted": "#808080"},
        "background": {"base": "$hue.gray.900", "raised": {"base": "$hue.gray.800"}},
        "diff": {"background": {"added": "#20303b"}},
    }
    tokens = build_tokens(schema)
    assert isinstance(tokens, ThemeTokens)
    assert tokens.name == "demo"
    assert tokens.dark is True
    assert tokens.text_base == "#eeeeee"
    assert tokens.surface_base == "#0a0a0a"
    assert tokens.surface_raised == "#1e1e1e"
    assert tokens.diff_added_bg == "#20303b"


def test_build_tokens_tolerates_missing_fields() -> None:
    # A partial schema must not crash; missing sources fall back to defaults.
    tokens = build_tokens({"name": "partial"})
    assert isinstance(tokens, ThemeTokens)
    assert tokens.name == "partial"
    assert isinstance(tokens.text_base, str)
    assert isinstance(tokens.surface_base, str)
    # Optional role backgrounds default to None when absent.
    assert tokens.role_user_bg is None
    assert tokens.role_tool_pending_bg is None
    assert tokens.role_tool_success_bg is None
    assert tokens.role_tool_error_bg is None


def test_build_tokens_reads_optional_role_backgrounds() -> None:
    schema = {
        "roles": {
            "user": {"body": "on #101419"},
            "tool_success": {"background": "#1d783c"},
        }
    }
    tokens = build_tokens(schema)
    # roles.*.body is a Rich style string, not a plain colour, so body is not
    # a role background source; only an explicit ``background`` key is.
    assert tokens.role_tool_success_bg == "#1d783c"
