# Provider retry policy

**Status:** accepted — 2026-11-06 (branch `chore/p0-contract-baselines`)

## What changed

Four adapters each carried the same `_should_retry` copy, none read `Retry-After`,
and `retry_delay_seconds` always used a fixed exponential delay. A `429` that
asked for 60 seconds was retried after 250 milliseconds, which lengthens the rate
limit instead of riding it out.

One policy now lives in `baldric_ai/retry.py`:

| Behaviour | Rule |
| --- | --- |
| Retryable statuses | 408, 409, 425, 429, and >= 500 |
| Server guidance | `retry-after-ms`, then `retry-after` (seconds or an HTTP date), used exactly |
| Server override | `x-should-retry: true/false` wins over the status default |
| Delay above the limit | the request fails immediately with a note instead of blocking |
| Fallback delay | exponential, capped, with up to 25% jitter |
| Context overflow | never retried, even though it arrives as a 400 |
| Auth failures | never retried |

Each failure also carries a stable code: `auth`, `timeout`, `conflict`,
`too_early`, `rate_limit`, `context_overflow`, `server_error`,
`invalid_request`, `retry_after_too_long` (and `rate_limit_exhausted` for
Codex's terminal quota errors). Codes travel in `ProviderErrorEvent.data["code"]`
and therefore reach the persisted provider diagnostic, so the loop and the UI can
branch on them instead of matching message text.

## Deliberate choices

- **Fail fast on a long server delay.** Baldric's default
  `max_retry_delay_seconds` is one second, so a server asking for 60 seconds is
  reported as `retry_after_too_long` rather than retried three times. Pi makes
  the same call against a 60-second budget: a request that cannot be retried
  inside the caller's budget should say so.
- **Jitter only on the fallback.** A server-provided delay is used exactly; jitter
  exists so simultaneous clients do not retry in lockstep.
- **425 stays retryable.** It is rare, but removing it would silently stop
  retrying a case that used to work.
- **Stream-level retries keep the exponential delay.** Those paths have no
  response headers to honour; only the HTTP failure path gained server guidance.

## What is not covered

- `ProviderRetryEvent` is still dropped by `baldric_ai/stream.py`, so the user
  does not yet see "retrying" in the UI. That is #47.
- Provider-specific stream errors (Anthropic `overloaded_error`, Codex transient
  markers) keep their own predicates; only the HTTP path was centralised.

## Tests

- `tests/ai/test_retry_policy.py`: exact `Retry-After` seconds, `retry-after-ms`
  precedence, HTTP-date parsing, fail-fast above the limit, jitter band, stable
  codes, context-overflow and auth refusal, `x-should-retry` overrides, attempt
  limit, unparsable values, and a zero delay budget.
- `tests/ai/test_retry_http.py`: a `429` with `Retry-After: 0.01` succeeds on the
  second request; a 60-second request fails after one request with
  `retry_after_too_long` in the diagnostic; a context-overflow body is not
  retried.
- Existing adapter tests assert the whole diagnostic object, which now includes
  `code`; those expectations were extended rather than loosened.
