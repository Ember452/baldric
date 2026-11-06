# Cancellation that interrupts a stalled stream

**Status:** accepted — 2026-11-06 (branch `chore/p0-contract-baselines`)

## What changed

Cancellation used to be a boolean polled between SSE lines. That only helps when
a line eventually arrives: while a provider holds the connection open (a queued
request, a silent upstream), no line exists to check, so the run waited for the
HTTP read timeout — 60 seconds by default. Ctrl+C looked like a hang.

Three pieces now make cancellation prompt:

1. `CancellationToken` gained `async def wait_cancelled()`. `SimpleCancellationToken`
   implements it with an `asyncio.Event`.
2. `baldric_ai.http.iter_sse_lines(response, signal)` races every line read
   against `wait_cancelled()` and stops as soon as the token fires. All five
   adapters read through it and return before finalizing, so a cancelled stream
   never produces a `done` event.
3. When a provider stream fails while the token is cancelled, the loop reports
   the turn as `aborted` instead of `error`. Without this, a user cancellation
   surfaced as "Provider stream ended without a terminal event".

## Why the waiter is per read

A single waiter kept across the generator would stay pending for every request
that ends normally: a caller that leaves the `async for` does not close this
generator, so its `finally` may never run. Creating a waiter per read and
cancelling it as soon as the read wins keeps the cost proportional to lines read
and leaves nothing behind.

## Comparison with Pi

Pi passes an `AbortSignal` down into the provider SDK and its SSE iteration
(`packages/ai/src/api/openai-completions.ts:378`,
`anthropic-messages.ts:775`), so aborting the signal cancels the transport read
itself; the SDK also maps it to `stopReason: "aborted"`
(`openai-completions.ts:700`).

Baldric's transport is `httpx`, which has no per-request abort signal for a
stream already being read. The two options are closing the response from a
watcher, which raises `StreamClosed` outside the retryable-transport set and
would surface as a provider error, or racing the read against the token. This
change takes the race, which keeps the failure path identical to a normal end of
stream.

The resulting semantics match Pi: the run ends as `aborted`, not `error`. Only
the mechanism differs, because it is a transport-layer difference rather than a
design one.

## What is still polling

- Tools keep the synchronous `ToolCancellationToken` contract; the loop cancels
  the tool task when the run is cancelled.
- Killing a POSIX/Windows process tree on timeout is a separate item: the shell
  tool's own timeout path owns it.

## Tests

- `tests/ai/test_cancellation.py` — a read that never yields returns within
  100 ms of cancel; an already-cancelled token reads nothing; lines pass through
  without a token; an idle stream ends normally.
- `tests/agent/test_agent_loop.py::test_cancel_during_a_stalled_stream_ends_as_aborted`
  — the cancelled turn ends as `aborted` with `Operation aborted`, not as a
  provider error.
- `tests/ai/test_baldric_ai.py` keeps the existing retry-backoff cancellation
  coverage; its token double subclasses `SimpleCancellationToken`, so it inherits
  the new method.
