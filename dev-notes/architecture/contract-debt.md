# Contract debt: fields with no producer or consumer

**Status:** open register — 2026-11-06

The P0 contract work pinned the shapes; this note records where a contract exists
without the mechanism behind it. Each row is either wired, deleted, or has a
named owner and an exit condition.

| Field / type | State after review |
| --- | --- |
| `AgentTool.execution_mode` | Default is now `"sequential"`, which is what the loop does. `"parallel"` is accepted for Pi compatibility but not honoured yet; implementing parallel execution is a separate feature. |
| `AgentToolResult.added_tool_names` | Propagated end to end (`tools.py` → `ToolResultMessage` → JSONL). Pi carries the same field to mark where late tools become available; the consumer here lands with dynamic tool loadout. Kept as wire parity. |
| `ToolCallDeltaEvent` | Still has no producer: parsers emit one complete `ProviderToolCallEvent`. Pi's adapters emit `toolcall_delta` while streamed arguments arrive, so this is a real gap — tracked in #52. |
| `ProviderRetryEvent` (AI internal) | Now surfaced: `stream.py` converts it to `AssistantRetryEvent`, the loop to `RetryAttemptEvent`, coding to `auto_retry_start` / `auto_retry_end` (#47). |
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
