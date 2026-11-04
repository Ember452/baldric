# Opt-in full (untruncated) TUI output

Issue #25 makes the hidden remainder of long tool results and `!` shell-command
output reachable without exporting the session. The TUI previews results to keep
a single result from flooding the transcript, but the preview is lossy: it drops
whole trailing lines and, once the character budget is spent, the tail of the
last kept line.

## What changed

- `ChatItem` retains a second, untruncated block (`tool_result_full_text`) and a
  per-row opt-in (`full_output`). `render_tool_result` only stores the full block
  when the preview actually dropped something, so short results are not stored
  twice.
- `ChatItem.result_text(expanded=...)` is the single accessor the renderers use:
  it returns the full block only when the tool-results toggle is on AND the row
  opted into full output; otherwise it returns the preview. The generic chat
  body and the plain-body transcript renderer both go through it.
- `format_tool_result_block`, `format_terminal_command_result_block`, and
  `_preview_text` gain a `full` flag that bypasses the preview limits.
- `TuiState.show_full_output` plus `set_full_output(enabled)` hold the opt-in and
  stamp already-present rows; `BaldricTuiApp` stamps `!`-command rows too.
- `baldric --show-full-output` sets the startup default. It is a
  per-invocation startup flag threaded CLI -> `run_openai_tui` -> `run_tui_app` ->
  the app, deliberately separate from durable `tui.json` settings (like the
  sidebar override), so it never persists.

Ctrl+O is the existing tool-results toggle; a row captured under full output
renders untruncated when expanded.

## What is out of scope

- Print-mode and session history are unchanged: they always held the complete
  result. Only the TUI preview is affected.
- Grouped tool calls and per-tool `render_result` markup keep their existing
  rendering; the full-output accessor applies to the generic result block.

## How to test

```bash
uv run pytest tests/test_tui_full_output.py -q
```

The suite covers the lossy default and `full` formatters, character-exact
recovery of a single huge line, lossy-only retention, per-row opt-in selection,
`set_full_output` updating existing rows, and the CLI flag reaching
`run_openai_tui` (present and absent). Automated coverage also lives in
`tests/test_cli.py`.
