# Transcript vertical scrollbar

Issue #24 re-enables the vertical scrollbar on the `#transcript` panel and
themes it via `baldric-scrollbar` / `baldric-scrollbar-hover` CSS variables.
Previously the panel forced `scrollbar-size-vertical: 0`, so long sessions had
no orientation cue about scroll position (only horizontal scrolling had one).

## What changed

- `#transcript` sets `scrollbar-size-vertical: 1` (default) and adds
  `scrollbar-color` / `scrollbar-color-hover` wired to the new theme vars.
  The extension-mount seam keeps its original (no vertical) behaviour.
- `TuiTheme` gains `scrollbar` / `scrollbar_hover` fields; because
  `THEME_COLOR_FIELDS` is derived from `fields(TuiTheme)`, they are
  automatically required by the parse validation (unlike the upstream
  approach, which needed an explicit tuple append).
- `theme_css_variables` exposes `baldric-scrollbar` / `baldric-scrollbar-hover`
  so the transcript CSS can consume them via `Var` references.
- All three bundled themes (`baldric-dark`, `baldric-light`, `high-contrast`)
  define the two colors.

## What is out of scope

- The component-extension seam (`[data-baldric-extension-mount]`) still hides
  its vertical scrollbar; extensions that want one can set it themselves.
- Scrollbar width / thumb length are Textual defaults; not exposed per theme.

## How to test

```bash
uv run pytest tests/test_tui_themes.py -q
```

`test_builtin_themes_wire_scrollbar_colors_to_css_variables` verifies the two
fields are in `THEME_COLOR_FIELDS`, that every builtin theme defines them, and
that `theme_css_variables` publishes the two vars. Existing `_theme_data`
helpers auto-enumerate `THEME_COLOR_FIELDS`, so custom-theme parse tests pick
the new fields up automatically with no source change.
