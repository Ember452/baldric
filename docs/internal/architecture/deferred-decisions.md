# Deferred reliability decisions (#48)

**Status:** decisions recorded — 2026-11-06

These three were deferred from the reliability pass on purpose: each is a format
or mechanism change that should land together with its first real consumer, not
speculatively. This note records the decision so a future change starts from a
reasoned position.

## 1. Session format version field

- **Decision:** do not add a `v` field yet.
- **Why:** the session format is a product contract and older data must stay
  readable. Today's reader is forward-tolerant: unknown keys are ignored and a
  torn tail is repaired. A version field only earns its cost when the first
  incompatible change arrives; adding it now would be an unused wire field by the
  same rule that removed the other dead contracts.
- **Trigger to revisit:** the first change that cannot be expressed as an
  additive, tolerantly-read field.

## 2. Provider record/replay

- **Decision:** not built. Tests use `FakeProvider` and fake HTTP payloads.
- **Why:** deterministic agent-loop tests already avoid live calls; a
  record/replay layer is a large surface with no failing test it would fix.
- **Trigger:** a real provider regression that a recorded transcript would have
  caught and a unit test could not, or the first conformance suite.

## 3. Fault injection

- **Decision:** not built as a product feature; failures are injected in tests by
  fakes.
- **Why:** the retry policy and classification are already exercised by
  `tests/ai/test_retry_*`, and a runtime fault-injection switch would be a
  debugging-only path with no user-facing consumer.
- **Trigger:** a class of bug that only reproduces across the real HTTP/SSE stack
  and cannot be modelled with fakes.

## Rule

Each item lands only with its first consumer, with a test that fails without it.
This mirrors the contract rule in `contract-debt.md`.
