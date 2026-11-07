# Flaky test baseline

Policy: flakes are **recorded here, not retried away**. `--timeout-method=thread`
(pyproject) fails a hung test loudly instead of hanging CI. A test that flakes
twice in one week is promoted to a fix ticket; the flake count per test is a
ratchet — it must not grow silently.

| test id | first seen | last seen | occurrences | observed failure | note |
| --- | --- | --- | --- | --- | --- |
| `tests/coding/tui/test_tui_app.py::test_tui_app_uses_configured_newline_keybinding[asyncio-f7-F7]` | 2026-11-07 | 2026-11-07 | 1 | Failed once inside the full `tests/coding/tui` run (Windows, Proactor loop); passed 3/3 in isolation | Suspected ordering/timing pollution. No overlap with any recent change surface |
