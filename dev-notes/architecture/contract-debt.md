# Contract debt: fields with no producer or consumer

**Status:** open register — 2026-11-06

The P0 contract work pinned the shapes; this note records the places where a Pi
contract was ported but the mechanism behind it was not. Each one passes type
checks and tests while promising something the code does not do, which is worse
than a missing feature because a reviewer reads the field as evidence.

| Field / type | Where | State | Owner |
| --- | --- | --- | --- |
| `AgentTool.execution_mode` | `src/baldric_agent/tools.py` | Defaults to `"parallel"`; nothing reads it. The loop executes tools sequentially. | Parallel tool execution (platform and tools phase) |
| `AgentToolResult.added_tool_names` | `src/baldric_agent/tools.py`, carried into `ToolResultMessage` and JSONL | Copied end to end; no consumer. | Dynamic tool loadout decision (#48) |
| `ToolCallDeltaEvent` | `src/baldric_agent/provider_events.py` | Type exists; no adapter produces it, so tool arguments always arrive whole at `ToolCallEndEvent`. | Streaming tool arguments (platform and tools phase) |
| `ProviderRetryEvent` | `src/baldric_ai/retry.py`, built by every adapter | Dropped in `src/baldric_ai/stream.py`, so a retrying request still looks like a hang. | #47 |
| `sum_usage` | `src/baldric_agent/messages.py` | No caller; session usage sums fields directly. | Cost accounting (quality and release phase), or delete |

## Rule

Every field or type ported from Pi lands with a producer, a consumer, and a test,
or it does not land. Adding another one is a review blocker. Removing a dead one
is always in scope for the change that touches its file.

## Exit criteria

- Each row is either wired (with a test that fails without it) or deleted.
- `tests/agent/test_wire_contract.py` and
  `tests/agent/test_session_entry_contract.py` change in the same commit that
  changes the shape, so the removal is a reviewed diff rather than a silent one.

Tracking: #51.
