# Streamed tool-call arguments

**Status:** accepted — 2026-11-06 (branch `reliability/p3-and-followups`, #52)

## What changed

`ToolCallDeltaEvent` (`toolcall_delta`) was in the public assistant-stream
contract but never produced: every parser accumulated argument fragments and
emitted one complete `ProviderToolCallEvent`, so `stream.py` yielded
`toolcall_start` and `toolcall_end` back to back with nothing between. A
consumer could not render arguments as they arrived.

Pi emits `toolcall_delta` from each adapter as the fragment text streams in. The
same information now travels through Baldric:

- `ProviderToolCallStartEvent(index)` marks the first fragment of a call.
- `ProviderToolCallDeltaEvent(index, delta)` carries one raw JSON fragment.
- The complete `ProviderToolCallEvent` still ends the call.

Adapters emit start-on-first-fragment and delta-per-fragment: OpenAI-compatible
chat and Mistral from `tool_calls[].function.arguments`, Anthropic from
`input_json_delta` (start at `content_block_start`), and OpenAI Codex from
`response.function_call_arguments.delta`. Google's Gemini stream delivers the
whole `functionCall`, so it keeps the complete-only path — absence of deltas is
valid.

## Stream assembly

`baldric_ai/stream.py` allocates a placeholder `ToolCall` block on start, appends
each fragment to a buffer, and replaces the block with the final parsed call on
the complete event. Multi-call responses are paired in start order with a FIFO
queue, so interleaved calls end in the order they started even though the
complete events carry no index.

## Tests

- `tests/ai/test_stream_tool_deltas.py`: a streamed call yields
  start → deltas → end, fragments concatenate to the final arguments, the
  complete-only path still yields start/end, and two interleaved calls pair in
  order.
- `tests/ai/test_baldric_ai.py::test_openai_compatible_provider_streams_tool_calls`
  now asserts the adapter actually emits `toolcall_delta` between start and end.
