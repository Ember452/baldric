# Contract debt: fields with no producer or consumer

**Status:** open register — updated 2026-11-07 after the audit follow-ups

The P0 contract work pinned the shapes; this note records where a contract exists
without the mechanism behind it. Each row is either wired, deleted, or has a
named owner and an exit condition.

| Field / type | State after review |
| --- | --- |
| `AgentTool.execution_mode` | **Wired as a rejection.** Pi's loop runs a `parallel` batch concurrently through its `toolExecution` option; this harness runs tools one at a time, so `AgentHarness` now refuses a tool that declares `parallel` instead of silently serialising it. Implementing parallel execution is still a separate feature. |
| `AgentToolResult.added_tool_names` | Propagated end to end (`tools.py` → `ToolResultMessage` → JSONL). Pi carries the same field to mark where late tools become available; the consumer here lands with dynamic tool loadout. Kept as wire parity. |
| `ToolCallDeltaEvent` | **Producer landed** (#52): `openai_compatible`, `openai_codex`, `anthropic` and `mistral` all emit it while streamed arguments arrive, and `tests/ai/test_stream_tool_deltas.py` covers it. The earlier "no producer" row was stale. |
| `ProviderRetryEvent` (AI internal) | Now surfaced: `stream.py` converts it to `AssistantRetryEvent`, the loop to `RetryAttemptEvent`, coding to `auto_retry_start` / `auto_retry_end` (#47). Since the audit, the event's `data` (HTTP status and body) also lands on the assistant message diagnostics, truncated and never model-visible. |
| `Usage.cost` | **Still debt.** `sum_usage` and `session/stats.py` read it, nothing produces it: every adapter reports zero. Removing it changes the wire shape; wiring it needs pricing in the provider layer, where it does not live. Exit: the first consumer that needs cost to survive an export. |
| `EntryAppendedEvent` | **Deleted**, together with its `entry_appended` entry in the extension event whitelist: nothing emitted or consumed it, so extensions were subscribing to an event that could never fire. A guard test now fails if the whitelist names any event the event modules do not declare. |
| `BashExecutionMessage` | **Wired.** `run_terminal_command(add_to_context=True)` now persists one, `provider_context` renders it into the same plain text the model saw before, `exclude_from_context` keeps an execution in the transcript but out of the request, and the transcript loader renders it on resume. |
| `sum_usage` | Already wired (`session/branch_summary.py`, `session/session.py`). Not debt. |

## Rule

Every field or type ported from Pi lands with a producer, a consumer, and a test,
or it does not land. Removing a dead one is always in scope for the change that
touches its file.

## Exit criteria

- Each row is either wired (with a test that fails without it) or deleted.
- `tests/agent/test_wire_contract.py` and
  `tests/agent/test_session_entry_contract.py` change in the same commit that
  changes the shape, so the removal is a reviewed diff rather than a silent one.

Tracking: #51.
