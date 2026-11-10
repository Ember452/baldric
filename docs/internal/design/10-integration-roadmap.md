---
title: "10 — Upstream Capability Integration Roadmap"
---

This document plans the next stage of Baldric: porting the features that related
Tau projects have built **into Baldric itself** — code merged into the tree, not
bolted on as separate installs — while keeping the harness small, layered, and
readable.

It complements [00 — Roadmap](./00-roadmap.md), which records the foundational
pi→tau port (phases 0–23). Those phases describe the base; this file is the new
plan. The shared discussion hub is GitHub issue #2.

## Source projects surveyed

Each row is a project found downstream of [huggingface/tau](https://github.com/huggingface/tau)
(or, for Basic Memory and SWE-agent, adjacent projects in the same space that we
reference rather than fork). Full usage rights for all of
them have been obtained from their authors, so licensing is not a blocker here.

| Project | What it is | Value to Baldric | Overlap with current Baldric |
|---|---|---|---|
| [tau-subagents](https://github.com/rian-dolphin/tau-subagents) | Claude-Code-style subagents: an `agent` tool delegating to scoped, in-process child sessions | Largest single net-new capability | none (no subagent system today) |
| [MiniAgent](https://github.com/zhoushui521-alt/MiniAgent) (upstream PR tau#755) | (a) malformed tool-argument feedback; (b) run policies (cost/token/consecutive-error → steer/cancel) | (b) is net new; (a) is a small enhancement | (a) largely covered by `tool_arguments.py` |
| [tua-agent](https://github.com/anuphongsrinawong/tua-agent) | Rust-specialized fork; carries generic pieces beyond Rust | self-correction loop, git checkpoints/rollback, background review, command palette, diff viewer, multi-session tabs, permission prompts, dashboard | command autocomplete, transcript selection, project-trust gating, provider retries, prompt caching already exist |
| [basic-memory](https://github.com/basicmachines-co/basic-memory) | Local-first Markdown knowledge base: entities/observations/relations graph, semantic search, MCP | persistent memory subsystem (pragmatic scope) | none (only in-memory transcripts exist today) |
| [tau_hub](https://github.com/mmpouya/tau_hub) | Cross-service persistence/registry; providers/agents/tools/skills/configs/sessions in pluggable DBs; API keys encrypted at rest | optional infrastructure: encrypted-at-rest credentials, alternate session backends, registry | local JSONL sessions + `credentials.py` cover the default path |
| [tau-huggingface](https://github.com/alejandro-ao/tau-huggingface) | Hugging Face inference-provider routing (`/hf route`) + sidebar provider status | niche polish | APIs (`set_inference_provider`, sidebar) already present |
| [SWE-agent](https://github.com/SWE-agent/SWE-agent) | Princeton/Stanford research agent for autonomous SWE tasks (SWE-bench, EnIGMA). **Not tau-based** — an *adjacent reference* for tool/agent-loop design, not something we fork. Superseded by [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) (use the simpler one as the model) | design ideas only: pre-submit review, edit-time lint feedback, windowed search/edit, single-config agent, batch/eval harness | reference-only; informs Phases 4–5, not a standalone phase |

## What Baldric already provides (verified)

These facts reduce porting risk and are re-checked per phase before any port:

- Bundled extensions are first-class. `built_in_extensions.py` declares
  `BUILT_IN_EXTENSIONS`, and `extensions/runtime.py` auto-loads them at startup
  (the `llama.cpp` built-in works this way today). Built-in code lives under
  `src/baldric_coding/extensions/builtins/`, so it ships inside the wheel.
- The extension API already exposes the seams the newer derivatives rely on:
  `context.ui.components` (`supports_components`, `set_slot_widget`,
  `open_main_view`, `register_key_interceptor`), `context.ui.sidebar`, and
  `set_inference_provider` / `inference_provider`.
- Tool-call arguments are validated against each tool's JSON schema before
  execution (`baldric_agent/tool_arguments.py`).
- Sessions support branching, resume, compaction, and export.

## Integration principles

1. **Extension-first hybrid.** Ship pluggable capabilities as bundled built-in
   extensions. Move into a core package only what genuinely belongs there
   (run-policy at the coding layer, the memory store primitive, post-edit hooks).
   This keeps the harness lean **and preserves the authoring path so you can add
   your own features later** on the same seams.
2. **Respect the layer boundary.** `baldric_agent` stays independent of the CLI,
   Textual, Rich, and file layout; UI layers consume events.
3. **Evidence before code.** For every phase, diff the upstream source against
   current Baldric first, port only the genuine gap, and never re-add what
   already exists. Confirm the required extension APIs are present before porting.
4. **Atomic, tested, documented.** One coherent change per commit; add/extend
   deterministic tests (fake providers/tools) before expanding; update
   `dev-notes/` and, when behavior is user-facing, `website/content/`.
5. **Keep CI green.** `uv run pytest`, `ruff check`, `ruff format --check`, `mypy`.

## Distribution and out-of-the-box experience

A normal install (`pip install baldric`, `uv tool install baldric`) must be
**complete**: bundled extensions are shipped in the wheel and auto-registered, so
users do not install or enable anything extra. This is exactly how the `llama.cpp`
built-in behaves today.

The only exceptions are capabilities that pull heavy or optional third-party
dependencies. Baldric currently declares **no extras** (every dependency is a hard
base dependency). For this roadmap we add `[project.optional-dependencies]` for
the genuinely optional, heavy pieces — and they degrade gracefully when absent:

- `baldric[semantic-memory]` — embedding / cross-encoder rerank for memory search
  (Basic Memory's vector layer). Default memory keeps stdlib `sqlite3` FTS + keyword
  recall, fully functional.
- `baldric[hub-postgres]` / `[hub-mongo]` / `[hub-redis]` — external hub database
  backends. The default hub backend is TinyDB (pure Python) / SQLite (stdlib).

System tools (not pip dependencies) are assumed where relevant: `git` for worktree
isolation and checkpoints — a reasonable prerequisite for a coding agent.

## Phase plan

Each phase is independently shippable and lands as its own tested, documented
change. Ordering goes low-risk/high-value first, builds dependencies before
dependents, and defers the largest, most invasive edits (the Textual app) and the
optional infrastructure.

### Phase 1 — Run policies + malformed-argument hardening (MiniAgent)
- **Reference:** MiniAgent (upstream PR tau#755) — run-policy monitor and malformed-argument feedback.
- **Form:** coding-layer feature (`RunPolicyMonitor`) + a small provider-layer audit.
- **Scope:** configurable per-run cost ceiling, cumulative token budget, and
  consecutive-error-turn threshold; action `steer` (ask the model to wrap up) or
  `cancel` (hard stop after the current turn). Wire config through CLI / TUI / RPC
  and manage the monitor across session swap and shutdown. Defaults off.
- **Dedup:** audit `tool_arguments.py` and the provider stream parsers; adopt
  MiniAgent's malformed-argument original-text feedback only where Baldric's
  current coverage is thin — do not duplicate.
- **Verify:** fake-provider tests for each threshold and action; malformed-arg tests
  per provider path; run-policy does not reset on internal retries/steer.
- **Docs:** dev-note + configuration reference section.

### Phase 2 — Subagents (tau-subagents)
- **Reference:** tau-subagents (itself ported from pi-subagents) — the subagent system.
- **Form:** bundled built-in extension (Textual widgets via the component seam).
- **Scope (sub-steps, each tested):**
  1. Core: `agent` tool, foreground/background runs, `get_subagent_result`,
     `steer_subagent`, agent types `general` / `explore`, concurrency queue,
     turn limits with grace, resume.
  2. Isolation & fidelity: `fork` (inherit full conversation, parent model/tools/
     prompt), `isolation: worktree`, `inherit_context` digest, `prompt_mode: append`.
  3. Scheduling: cron / interval / one-shot jobs with a per-session store.
  4. UI: agents strip + conversation viewer + `/agents` menu; notification cards;
     usage reporting.
- **Deferred to Phase 3:** the `memory:` per-agent frontmatter.
- **Verify:** deterministic tests with fake provider/tools for spawn, foreground vs
  background, fork byte-identical prefix, worktree commit/branch naming, queue
  ordering, turn-limit steer-then-cancel, schedule parsing.
- **Docs:** dev-note; "Subagents" guide under the "Use Baldric" section.

### Phase 3 — Persistent memory subsystem (basic-memory + tau-subagents memory)
- **Reference:** basic-memory for the memory store/format and retrieval; tau-subagents for per-agent memory wiring.
- **Form:** memory store primitive (coding layer) + `memory` tool(s) + prompt
  injection; keep the retrieval interface pluggable.
- **Scope (pragmatic first):** Markdown notes with frontmatter + a `MEMORY.md`
  index; read/write/edit/search tools; a memory block injected into the system
  prompt; local/project/user scopes. Keyword + `sqlite3` full-text recall first.
- **Optional later:** knowledge-graph observations/relations and semantic search +
  rerank behind `baldric[semantic-memory]`.
- **Wire-back:** give Phase 2 agent types their `memory:` frontmatter now that the
  store exists.
- **Verify:** store round-trip, index rebuild, scope precedence, injection
  truncation; per-agent memory read/write vs read-only toolsets.
- **Docs:** dev-note; "Memory" concept guide.

### Phase 4 — Generic agent intelligence (tua-agent, non-Rust)
- **Reference:** tua-agent for the self-correction / checkpoint / review shape; SWE-agent for pre-submit review and edit-time lint feedback.
- **Form:** coding-layer hooks that compose with the loop and sessions.
- **Scope:** self-correction loop (run a verification command after edits, feed
  failures back for a bounded number of auto-fix turns); git checkpoint/rollback
  around edits; optional background review. Config toggles mirror tua but stay
  domain-neutral.
- **Out of scope:** Rust tools, Rust system prompt, Rust profiles/skills.
- **Verify:** fake-tool loops for correction cap and stop conditions; checkpoint
  create/rollback against a scratch git repo; no self-correction when disabled.
- **Docs:** dev-note.

### Phase 5 — TUI productivity features (tua-agent)
- **Reference:** tua-agent for command palette / diff viewer / multi-session tabs / permission prompts; SWE-agent for the diff/lint interaction model. Diff against Baldric's existing autocomplete, transcript selection, and project-trust gating first.
- **Form:** Textual-layer, behind the adapter boundary; **fill gaps only**.
- **Scope:** command palette, diff viewer, multi-session tabs, interactive
  permission approve/deny prompts — after diffing against existing autocomplete,
  transcript selection, and project-trust gating to avoid duplication.
- **Risk note:** `tui/app.py` is very large; prefer the component seam and small,
  reversible edits; add widget/interaction tests.
- **Docs:** dev-note; TUI reference updates.

### Phase 6 — Optional infrastructure (tau_hub)
- **Reference:** tau_hub — encryption-at-rest, registry, and DB-backed sessions. Per the scope below, backport only at-rest encryption and a pluggable session backend rather than vendoring the whole package.
- **Form:** a hub layer + `BaseAgentStore`-style backends, optional and off by
  default.
- **Scope:** encrypted-at-rest credential handling (first verify what
  `credentials.py` already does), pluggable session storage as an alternative to
  `JsonlSessionStorage`, and a providers/agents/tools/skills/configs registry.
- **Backends:** TinyDB/SQLite in the base; Postgres/Mongo/Redis behind extras.
- **Verify:** encrypt/decrypt round-trip, missing/wrong key errors, JSONL
  import/export losslessness, atomic append on concurrent writers.
- **Docs:** dev-note; library/integration guide.

### Phase 7 — Hugging Face inference-provider routing (tau-huggingface)
- **Reference:** tau-huggingface — the `/hf route` picker and sidebar provider-status section.
- **Form:** bundled built-in extension.
- **Scope:** `/hf route` picker to pin a live inference provider, plus a sidebar
  provider-status section that refreshes on model/route changes and hides when a
  non-HF provider is active. Baldric already exposes the required APIs, so this is
  expected to be a small, self-contained port.
- **Verify:** route fetch parsing with a stubbed model API, sidebar add/remove
  lifecycle, provider gating.
- **Docs:** dev-note; providers guide note.

## Pre-flight checks (before Phase 1)

- **Sync state:** the command shell cannot reach GitHub over SSH (`publickey`
  denied), so from here `main` only compares equal to the last-fetched
  `origin/main` (both at `v0.2.0`). Run `git fetch` in your own terminal to
  confirm `main` is current before starting.
- **Upstream drift:** Baldric's tree is a rebrand of an older upstream tag
  (`v0.2.0` vs upstream tau `0.4.9`) with newer extension APIs backported. Before
  each port, re-confirm the specific APIs a phase depends on exist in Baldric and
  behave as upstream expects; when they diverge, adapt to Baldric's shape rather
  than bending the core to the derivative.

## Explicitly out of scope

- Rust-specific specialization from tua-agent (tools, prompt, profiles, skills).
- Cloud/hosted surfaces from basic-memory (its paid cloud, telemetry, auth).
- Making subagents, hub, or memory dependencies of the reusable `baldric_agent` core.
