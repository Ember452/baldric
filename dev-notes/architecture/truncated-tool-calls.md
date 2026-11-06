# Truncated responses never execute tool calls

**Status:** accepted — 2026-11-06 (branch `chore/p0-contract-baselines`)

## What changed

When an assistant turn stops because the output token limit was reached
(`stop_reason == "length"`) and it carries tool calls, the loop no longer runs
any of them. Each call is reported as a recoverable error instead:

- `tool_execution_start` / `tool_execution_end` with `is_error=true`;
- one `ToolResultMessage` per call whose text says the call was not executed and
  should be re-issued with complete arguments;
- the usual `turn_end`, then another turn so the model can re-issue.

A text-only truncated turn is unchanged: it still ends the run as before.

## Why

Streamed tool arguments are finalized with a best-effort JSON salvage. A cut-off
response can therefore carry arguments that parse and validate but are silently
incomplete. Schema validation cannot catch this class of error, because the
truncated value is still valid JSON of the right shape. The failure mode is a
real side effect from a partial command or a partial patch, so the only safe
default is to execute nothing.

## Bound

Re-issuing is only useful if the model can produce a complete response, so the
loop stops after three consecutive truncated tool turns. The counter resets on
any normal turn; without the bound, a model that always truncates would loop
forever, because a truncated turn advances no provider-failure counter.

## Tests

`tests/agent/test_agent_loop.py`:

- `test_length_truncated_tool_calls_are_not_executed` — two calls, tool never
  runs, both results are errors, the model gets a second request;
- `test_length_without_tool_calls_ends_normally` — the text-only control;
- `test_repeated_truncated_tool_turns_stop_the_run` — the bound is reached after
  exactly three requests;
- `test_a_normal_tool_turn_resets_the_truncation_budget` — two truncations, a
  normal tool turn, two more truncations still allow a final request.

The test builds `AssistantDoneEvent(reason="length", ...)` directly: the shared
`assistant_done` helper maps any message with tool calls to `toolUse`, which
would hide the case under test.

## Reference

Pi's `failToolCallsFromTruncatedMessage` in
`packages/agent/src/agent-loop.ts:488-513` treats the batch the same way. The
consecutive-turn bound is Baldric-specific: Pi has no unbounded-loop guard at
this point because its durable kernel schedules turns as tasks with their own
limits.
