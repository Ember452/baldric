# Documentation Structure Standardization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `docs/` the single source of truth for Baldric documentation, split by audience and laid out on the Diátaxis quadrants, with one standard file that governs placement and writing.

**Architecture:** `docs/user/` is the only published tree and becomes the Astro content base. `docs/internal/` holds contributor records (ADRs, architecture journals, designs, notes, plans, specs) and is never globbed by the site. `docs/AGENTS.md` defines the tier taxonomy and writing rules. Packaged self-knowledge in `src/baldric/runtime/data/docs/` stays a separate wheel artifact, documented as its own tier.

**Tech Stack:** Markdown + Astro 7 content collections (website/), Python 3.12 + pytest guards, GitHub Actions, PowerShell for local moves (git mv only).

**Spec:** None. Requirements were agreed in review; the decisions are recorded below and are authoritative for this plan.

## Decisions Locked

1. **`docs/` is the single root.** `website/content/` is removed.
2. **Diátaxis renames are in scope.** There is no release and no user, so no redirects are needed:
   - `/guides/...` → `/how-to/...`
   - `/internals/...` → `/explanation/...`
   - `/quickstart/` → `/tutorials/quickstart/`
   - `/concepts/` → `/explanation/concepts/`
   - `/what-is-baldric/` → `/explanation/what-is-baldric/`
   - `/reference/`, `/releases/`, `/roadmap/`, `/contributing/`, `/` keep their URLs.
3. **Audience split, not a hidden directory.** Published content lives in `docs/user/`; contributor content in `docs/internal/`.
4. **Packaged self-knowledge stays separate.** `src/baldric/runtime/data/docs/` ships in the wheel and is read by the agent at runtime. It is a documented tier, not a copy of the user docs.
5. **ADR sequence is consolidated.** `dev-notes/adr/0001-0003` stay; `plans/adr-0001-0003` become `0004-kernel-boundary.md`, `0005-god-class-deferral.md`, `0006-transcript-as-truth.md`.
6. **Deployment stays disabled.** `.github/workflows/docs.yml.disabled` and `publish.yml.disabled` are not re-enabled; CI still builds and tests the site in the existing `docs` job.

## Global Constraints

- **Move files with `git mv` only.** Never delete-and-recreate a document. History must follow the file.
- **Never rewrite document bodies with a script, `sed`, or a loop.** Use the editor tools per file. Bulk `git mv` loops move files without touching content and are allowed.
- **User docs describe current behavior.** History and rejected alternatives belong in `docs/internal/`.
- **One home per fact.** Link to the owning page instead of restating it.
- **Published boundary is absolute.** `docs/internal/`, `docs/templates/`, and `docs/assets/` must never be loaded by the Astro collection. The content base is exactly `docs/user`.
- **Root `AGENTS.md` may only grow in Task 6**, where the growth is justified by the new `docs/AGENTS.md` tier and re-baselined in the same commit.
- **Every task ends green** for the checks listed under that task. Do not stack failing commits.
- **Commit messages follow the repo style** (`docs: ...`, `chore: ...`), one coherent change per commit.

## Target Tree

```text
docs/
├── README.md                     # documentation map and reading paths
├── AGENTS.md                     # documentation standard (tier table + rules)
├── assets/
│   └── baldric-header.svg
├── templates/
│   ├── adr.md
│   ├── design.md
│   └── plan.md
├── user/                         # published — Astro content base
│   ├── _index.md
│   ├── contributing.md
│   ├── releases.md
│   ├── roadmap.md
│   ├── tutorials/
│   │   └── quickstart.md
│   ├── how-to/
│   │   ├── _index.md
│   │   ├── context.md
│   │   ├── extensions.md
│   │   ├── local-inference.md
│   │   ├── mcp.md
│   │   ├── print-mode.md
│   │   ├── project-instructions.md
│   │   ├── project-trust.md
│   │   ├── providers-and-models.md
│   │   ├── sessions.md
│   │   ├── skills-and-prompts.md
│   │   ├── themes.md
│   │   └── tui.md
│   ├── reference/
│   │   ├── _index.md
│   │   ├── cli.md
│   │   ├── configuration.md
│   │   ├── keybindings.md
│   │   ├── rpc.md
│   │   ├── slash-commands.md
│   │   └── tools.md
│   └── explanation/
│       ├── _index.md
│       ├── agent-loop.md
│       ├── architecture.md
│       ├── concepts.md
│       ├── custom-frontend.md
│       ├── design-principles.md
│       └── what-is-baldric.md
└── internal/                     # never published
    ├── README.md
    ├── adr/
    │   ├── 0001-use-textual-for-tui.md
    │   ├── 0002-keep-tool-docs-hand-written.md
    │   ├── 0003-unify-skill-discovery-on-agent-skills-spec.md
    │   ├── 0004-kernel-boundary.md
    │   ├── 0005-god-class-deferral.md
    │   └── 0006-transcript-as-truth.md
    ├── architecture/             # moved from dev-notes/architecture/
    ├── design/                   # moved from dev-notes/design/
    ├── notes/                    # moved from dev-notes/*.md (except README)
    ├── plans/                    # moved from plans/ and docs/superpowers/plans/
    └── specs/                    # moved from docs/superpowers/specs/
```

---

## Task 0: Record the starting point

**Files:** none.

**Interfaces:**
- Consumes: a clean `main` checkout.
- Produces: the branch `docs/standardize-structure` and a recorded green baseline.

- [ ] **Step 1: Confirm the worktree is clean**

Run:
```powershell
git status --short
```
Expected: no output.

- [ ] **Step 2: Record the baseline checks**

Run:
```powershell
uv run pytest -q tests/guards tests/test_package_metadata.py
npm --prefix website run build
npm --prefix website test
```
Expected: pytest passes; Astro build succeeds; `npm test` passes all site tests.

- [ ] **Step 3: Create the branch**

Run:
```powershell
git switch -c docs/standardize-structure
```
Expected: `Switched to a new branch 'docs/standardize-structure'`.

No commit in this task.

---

## Task 1: Establish `docs/` as the documentation root

**Files:**
- Create: `docs/README.md`
- Create: `docs/AGENTS.md`
- Create: `docs/templates/adr.md`
- Create: `docs/templates/design.md`
- Create: `docs/templates/plan.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the documentation standard every later task references; `docs/AGENTS.md` is the file the ratchet learns about in Task 6.

- [ ] **Step 1: Write `docs/README.md`**

```markdown
# Baldric documentation

This directory is the single source of truth for Baldric documentation.

## Start here

- New to Baldric: [tutorials/quickstart.md](user/tutorials/quickstart.md)
- What Baldric is and why: [explanation/what-is-baldric.md](user/explanation/what-is-baldric.md)
- Task recipes: [user/how-to/](user/how-to/_index.md)
- Lookup: [user/reference/](user/reference/_index.md)
- How Baldric works: [user/explanation/](user/explanation/_index.md)

## Map

| Directory | Audience | Contents |
| --- | --- | --- |
| `user/` | people using Baldric | published guides, reference, and explanations |
| `internal/` | contributors | ADRs, architecture journals, designs, notes, plans, specs |
| `assets/` | repository README and docs | images and diagrams |
| `templates/` | contributors | ADR, design, and plan starting points |

## For contributors

- Documentation standard: [AGENTS.md](AGENTS.md)
- Decisions: [internal/adr/](internal/adr/)
- Architecture journals: [internal/architecture/](internal/architecture/)
- Designs: [internal/design/](internal/design/)
- Feature notes: [internal/notes/](internal/notes/)
- Plans and specs: [internal/plans/](internal/plans/), [internal/specs/](internal/specs/)

## Published site

`docs/user/` is the Astro content base configured in `website/src/content.config.ts`.
`docs/internal/`, `docs/templates/`, and `docs/assets/` are never published.

Packaged self-knowledge in `src/baldric/runtime/data/docs/` ships inside the wheel
and is read by the agent at runtime; it is intentionally separate from this tree.
```

- [ ] **Step 2: Write `docs/AGENTS.md`**

```markdown
# docs/ - Documentation Standard

This file governs everything under `docs/`. The root `AGENTS.md` still applies;
this file only adds placement and writing rules for documentation.

## Two audiences

| Path | Audience | Published? |
| --- | --- | --- |
| `docs/user/` | people using Baldric | yes, by `website/` |
| `docs/internal/` | contributors maintaining Baldric | no |
| `docs/assets/` | the repository README and docs | no |
| `docs/templates/` | starting points for new docs | no |

`src/baldric/runtime/data/docs/` is a separate tier: self-knowledge packaged
into the wheel and read by the agent at runtime. Do not move user docs there and
do not treat it as the documentation source.

## Placement (one home per fact)

| Directory | Job | Does not belong |
| --- | --- | --- |
| `docs/user/tutorials/` | ordered first-run path; introduce only what the next step needs | reference tables, design rationale |
| `docs/user/how-to/` | task recipes: goal, steps, verification | teaching sequences, architecture essays |
| `docs/user/reference/` | lookup: commands, flags, environment variables, file formats | narrative, tutorials |
| `docs/user/explanation/` | why the system is shaped this way; architecture and concepts | step-by-step procedures |
| `docs/internal/adr/` | accepted or declined decisions, one per file, numbered | open work plans |
| `docs/internal/architecture/` | as-built phase journals and subsystem notes | forward-looking proposals |
| `docs/internal/design/` | designs written before implementation | incident stories |
| `docs/internal/notes/` | feature build journals and investigations | current user-facing explanations |
| `docs/internal/plans/` | executable work plans | decisions already accepted (make an ADR) |
| `docs/internal/specs/` | detailed specifications a plan implements | running task lists |

When a fact belongs somewhere else, link to the owning document instead of
repeating it.

## Writing rules

- `docs/user/` describes current behavior. History, rejected alternatives, and
  implementation journals belong in `docs/internal/`.
- Use root-relative site links in user docs: `/how-to/...`, `/reference/...`,
  `/explanation/...`. The Astro build rewrites them for the published base path.
- Use repository-relative Markdown links for files. Never hard-code a
  `github.com/.../blob/main/...` URL for a file in this repository.
- Every `docs/user/` page starts with `title` frontmatter; every multi-page site
  section (`how-to/`, `reference/`, `explanation/`) has exactly one `_index.md`;
  the single-page `tutorials/` section has none.
- Reference pages are tables or definition lists. No narrative sections.
- Commands are copy-pasteable and use `uv run` for Python.
- Do not write status annotations ("implemented", "coming soon") in user docs.
  Status belongs in the roadmap and release notes.
- A new decision gets an ADR from `docs/templates/adr.md`; a new multi-step
  effort gets a plan from `docs/templates/plan.md`.

## Verification

- User docs: `npm --prefix website run build && npm --prefix website test`.
- Contributor docs: links in changed files must resolve relative to their new
  location.
- The published site must never contain `docs/internal/`, `docs/templates/`, or
  `docs/assets/`: the Astro content base is exactly `docs/user`.
```

- [ ] **Step 3: Write `docs/templates/adr.md`**

```markdown
# ADR-0000: <short decision title>

- Status: Proposed | Accepted | Declined | Superseded by ADR-0000
- Date: YYYY-MM-DD

## Context

What forces are at play? What breaks if nothing changes?

## Decision

The decision, stated in the present tense, with the constraints it imposes.

## Consequences

What becomes easier, what becomes harder, and how the decision is enforced
(tests, guards, or review rules).

## Alternatives considered

Each rejected alternative and why it lost.
```

- [ ] **Step 4: Write `docs/templates/design.md`**

```markdown
# <Design title>

- Status: Draft | Ready for implementation | Implemented
- Owner: <name or agent>
- Related ADR: <link or "none">

## Problem

The user-visible or architectural problem this design solves.

## Constraints

Version floors, compatibility promises, and boundaries that cannot move.

## Proposal

The chosen shape: modules, data flow, and public interfaces.

## Rejected alternatives

Each alternative and the reason it was rejected.

## Verification

How the design will be proven correct: tests, guards, and manual checks.
```

- [ ] **Step 5: Write `docs/templates/plan.md`**

```markdown
# <Plan title>

**Goal:** One sentence describing the finished state.

**Spec:** Link to the design or spec this plan implements.

## Global Constraints

Project-wide rules that apply to every task.

## Task 1: <name>

**Files:**
- Create: `exact/path`
- Modify: `exact/path:line`

**Interfaces:**
- Consumes: what this task uses from earlier tasks.
- Produces: what later tasks rely on.

- [ ] Step 1: write the failing check
- [ ] Step 2: run it and confirm it fails
- [ ] Step 3: implement
- [ ] Step 4: run it and confirm it passes
- [ ] Step 5: commit
```

- [ ] **Step 6: Verify nothing else moved and commit**

Run:
```powershell
git status --short
uv run pytest -q tests/guards
```
Expected: only the five new files are untracked; guard tests pass.

```powershell
git add docs/README.md docs/AGENTS.md docs/templates
git commit -m "docs: add documentation root index, standard, and templates"
```

---

## Task 2: Move published docs to `docs/user` and repoint Astro

**Files:**
- Move: `website/content/` → `docs/user/`
- Modify: `website/src/content.config.ts`
- Modify: `website/src/pages/[...slug].astro`
- Modify: `website/src/data.ts`
- Modify: `website/tests/site.test.mjs`
- Modify: `website/data/sidebar.yaml`
- Modify: `website/src/components/Footer.astro`, `Navbar.astro`, `Home.astro`
- Modify: `website/src/components/Roadmap.astro`

**Interfaces:**
- Consumes: `docs/` from Task 1.
- Produces: the Astro collection base `docs/user`; the published pages `tutorials/`, `how-to/`, `reference/`, `explanation/`, plus the top-level home, `contributing`, `releases`, `roadmap`.

- [ ] **Step 1: Move the tree with history**

Run:
```powershell
git mv website/content docs/user
git mv docs/user/guides docs/user/how-to
git mv docs/user/internals docs/user/explanation
New-Item -ItemType Directory -Path "docs/user/tutorials" -Force | Out-Null
git mv docs/user/quickstart.md docs/user/tutorials/quickstart.md
git mv docs/user/concepts.md docs/user/explanation/concepts.md
git mv docs/user/what-is-baldric.md docs/user/explanation/what-is-baldric.md
```
Expected: `website/content` no longer exists; `git status --short` shows renames.

- [ ] **Step 2: Repoint the content collection**

In `website/src/content.config.ts`, change:

```ts
loader: glob({ pattern: "**/*.md", base: "./content" }),
```

to:

```ts
loader: glob({ pattern: "**/*.md", base: "../docs/user" }),
```

- [ ] **Step 3: Derive the edit-link path from the entry id**

In `website/src/pages/[...slug].astro`, replace:

```ts
const file = entry.filePath?.replace(/^.*?content\//, "") ?? `${entry.id}.md`;
```

with:

```ts
const file = `${entry.id}.md`;
```

- [ ] **Step 4: Repoint the edit URL**

In `website/src/data.ts`, change:

```ts
editRepoUrl: "https://github.com/Ember452/baldric/edit/main/website/content",
```

to:

```ts
editRepoUrl: "https://github.com/Ember452/baldric/edit/main/docs/user",
```

- [ ] **Step 5: Update the sidebar paths and labels**

Replace `website/data/sidebar.yaml` with:

```yaml
- label: Home
  link: /
- label: Use Baldric
  items:
    - label: What is Baldric?
      path: /explanation/what-is-baldric/
    - label: Quickstart
      path: /tutorials/quickstart/
    - label: Core concepts
      path: /explanation/concepts/
- label: How-to guides
  items:
    - label: The interactive session
      path: /how-to/tui/
    - label: Sessions
      path: /how-to/sessions/
    - label: Providers & models
      path: /how-to/providers-and-models/
    - label: Skills & prompt templates
      path: /how-to/skills-and-prompts/
    - label: Project instructions
      path: /how-to/project-instructions/
    - label: Managing context
      path: /how-to/context/
    - label: Print mode & scripting
      path: /how-to/print-mode/
    - label: Extensions
      path: /how-to/extensions/
    - label: MCP servers
      path: /how-to/mcp/
    - label: Themes
      path: /how-to/themes/
- label: Reference
  items:
    - label: CLI
      path: /reference/cli/
    - label: Slash commands
      path: /reference/slash-commands/
    - label: Keyboard shortcuts
      path: /reference/keybindings/
    - label: Configuration & files
      path: /reference/configuration/
    - label: Built-in tools
      path: /reference/tools/
- label: How Baldric works
  items:
    - label: Architecture overview
      path: /explanation/architecture/
    - label: The agent loop & events
      path: /explanation/agent-loop/
    - label: Design principles
      path: /explanation/design-principles/
    - label: Build your own frontend
      path: /explanation/custom-frontend/
- label: Release notes
  link: /releases/
- label: Roadmap
  link: /roadmap/
- label: Contributing
  path: /contributing/
```

- [ ] **Step 6: Update the site test fixtures**

In `website/tests/site.test.mjs`:

Change line 20 from:

```js
for (const file of await files(path.resolve("content"))) {
```

to:

```js
for (const file of await files(path.resolve("../docs/user"))) {
```

Change the route base:

```js
.relative(path.resolve("content"), file)
```

to:

```js
.relative(path.resolve("../docs/user"), file)
```

Change the quickstart fixture from:

```js
const html = await readFile(path.join(dist, "quickstart/index.html"), "utf8");
```

to:

```js
const html = await readFile(path.join(dist, "tutorials/quickstart/index.html"), "utf8");
```

Change the edit-link expectation from:

```js
"/edit/main/website/content/quickstart.md",
```

to:

```js
"/edit/main/docs/user/tutorials/quickstart.md",
```

- [ ] **Step 7: Update hard-coded site links in components**

Use the editor on each file with these replacements:

- `website/src/components/Footer.astro`: `/quickstart/` → `/tutorials/quickstart/` (1), `/internals/` → `/explanation/` (1).
- `website/src/components/Navbar.astro`: `/quickstart/` → `/tutorials/quickstart/` (1), `/internals/` → `/explanation/` (1).
- `website/src/components/Home.astro`: `/quickstart/` → `/tutorials/quickstart/` (2), `/internals/` → `/explanation/` (5), `/guides/` → `/how-to/` (1).
- `website/src/components/Roadmap.astro`: `/internals/` → `/explanation/` (1); replace both `<code>dev-notes/</code>` occurrences with `<code>docs/internal/</code>`.
- `website/src/pages/404.astro`: `/quickstart/` → `/tutorials/quickstart/` (1).

- [ ] **Step 8: Build and test**

Run:
```powershell
npm --prefix website run check
npm --prefix website run format:check
npm --prefix website run build
npm --prefix website test
```
Expected: type check passes, formatting is clean, the build emits `dist/tutorials/quickstart/index.html`, `dist/how-to/tui/index.html`, `dist/explanation/architecture/index.html`, and every site test passes.

- [ ] **Step 9: Commit**

```powershell
git add -A
git commit -m "docs: move published docs to docs/user with Diátaxis layout"
```

---

## Task 3: Rewrite the published URL namespace inside user docs

**Files (all under `docs/user/`):**
- `docs/user/explanation/concepts.md`: 7 `/guides/`, 1 `/internals/`
- `docs/user/tutorials/quickstart.md`: 5 `/guides/`, 1 `/concepts/`
- `docs/user/explanation/what-is-baldric.md`: 1 `/guides/`, 1 `/internals/`, 2 `/quickstart/`, 2 `/concepts/`
- `docs/user/contributing.md`: 1 `/internals/`
- `docs/user/how-to/*.md`: 8 files, 19 `/guides/`
- `docs/user/explanation/*.md` (the four moved internals pages): 7 `/guides/`, 10 `/internals/`
- `docs/user/reference/*.md`: 4 files, 18 `/guides/`, 1 `/internals/`

**Interfaces:**
- Consumes: the new URL namespace from Task 2.
- Produces: zero remaining links to `/guides/`, `/internals/`, `/quickstart/`, `/concepts/`, or `/what-is-baldric/`.

- [ ] **Step 1: Rewrite the specific moved pages first**

For each file below, use the editor's replace-all in this order.

1. In `docs/user/tutorials/quickstart.md`:
   - `(/concepts/)` → `(/explanation/concepts/)`
   - `(/guides/` → `(/how-to/`
2. In `docs/user/explanation/concepts.md`:
   - `(/internals/` → `(/explanation/`
   - `(/guides/` → `(/how-to/`
3. In `docs/user/explanation/what-is-baldric.md`:
   - `(/quickstart/)` → `(/tutorials/quickstart/)`
   - `(/concepts/)` → `(/explanation/concepts/)`
   - `(/guides/` → `(/how-to/`
   - `(/internals/` → `(/explanation/`
4. In `docs/user/contributing.md`:
   - `(/internals/` → `(/explanation/`

- [ ] **Step 2: Rewrite the section links everywhere else**

Use the editor's replace-all on every file under `docs/user/how-to/`, `docs/user/reference/`, and `docs/user/explanation/`:

- `(/guides/` → `(/how-to/`
- `(/internals/` → `(/explanation/`

Do not touch `docs/internal/`.

- [ ] **Step 3: Verify no stale site links remain**

Run:
```powershell
Select-String -Path "docs/user/**/*.md" -Pattern '\(/guides/|\(/internals/|\(/quickstart/|\(/concepts/|\(/what-is-baldric/'
```
Expected: no output. (`docs/user/**/*.md` requires PowerShell 7 for recursive globbing; if unavailable, run `Get-ChildItem -LiteralPath docs/user -Recurse -File -Filter *.md | Select-String -Pattern ...`.)

Also verify the new paths exist:

```powershell
Select-String -Path "docs/user/**/*.md" -Pattern '\(/how-to/|\(/explanation/|\(/tutorials/'
```
Expected: matches in the files listed above.

- [ ] **Step 4: Build and test the site**

Run:
```powershell
npm --prefix website run build
npm --prefix website test
```
Expected: build succeeds and the link-resolution test passes with the new routes.

- [ ] **Step 5: Commit**

```powershell
git add docs/user
git commit -m "docs: point user docs at the Diátaxis URL namespace"
```

---

## Task 4: Move contributor documentation into `docs/internal`

**Files:**
- Move: `dev-notes/adr/` → `docs/internal/adr/`
- Move: `dev-notes/architecture/` → `docs/internal/architecture/`
- Move: `dev-notes/design/` → `docs/internal/design/`
- Move: `dev-notes/*.md` (except `README.md`) → `docs/internal/notes/`
- Move: `dev-notes/README.md` → `docs/internal/README.md`
- Move: `plans/` → `docs/internal/plans/`
- Move: `docs/superpowers/plans/*.md` → `docs/internal/plans/`
- Move: `docs/superpowers/specs/*.md` → `docs/internal/specs/`
- Modify: `docs/internal/README.md`
- Modify: `docs/internal/design/03-tools.md`
- Modify: `docs/internal/design/mcp-client-build.md`
- Modify: `src/baldric/runtime/data/docs/architecture.md`
- Modify: `src/baldric/runtime/data/docs/extensions.md`
- Modify: `src/baldric/runtime/data/docs/models.md`
- Modify: `src/baldric/runtime/data/docs/skills.md`

> This task moves this plan file itself: `docs/superpowers/plans/2026-11-10-docs-structure-standardization.md`
> lands at `docs/internal/plans/2026-11-10-docs-structure-standardization.md`. Track progress
> against the new path afterwards.

**Interfaces:**
- Consumes: `docs/internal/` placement rules from `docs/AGENTS.md`.
- Produces: the six internal subdirectories and no `dev-notes/`, `plans/`, or `docs/superpowers/` directories.

- [ ] **Step 1: Move the directories**

Run in this exact order:
```powershell
git mv dev-notes/adr docs/internal/adr
git mv dev-notes/architecture docs/internal/architecture
git mv dev-notes/design docs/internal/design
git mv plans docs/internal/plans
New-Item -ItemType Directory -Path "docs/internal/notes" -Force | Out-Null
Get-ChildItem -LiteralPath "dev-notes" -File -Filter *.md | Where-Object { $_.Name -ne "README.md" } | ForEach-Object { git mv $_.FullName "docs/internal/notes/$($_.Name)" }
git mv dev-notes/README.md docs/internal/README.md
New-Item -ItemType Directory -Path "docs/internal/specs" -Force | Out-Null
Get-ChildItem -LiteralPath "docs/superpowers/plans" -File -Filter *.md | ForEach-Object { git mv $_.FullName "docs/internal/plans/$($_.Name)" }
Get-ChildItem -LiteralPath "docs/superpowers/specs" -File -Filter *.md | ForEach-Object { git mv $_.FullName "docs/internal/specs/$($_.Name)" }
```
Git does not delete the emptied source directories on Windows, so verify they are empty and remove them:
```powershell
Get-ChildItem -LiteralPath dev-notes, docs/superpowers -Force -ErrorAction SilentlyContinue
```
Expected: no files are listed. Then:
```powershell
Remove-Item -LiteralPath dev-notes, docs/superpowers -Recurse -Force -ErrorAction SilentlyContinue
```
Expected: `dev-notes`, `plans`, and `docs/superpowers` are gone; `git status --short` reports renames, not additions/deletions.

- [ ] **Step 2: Rewrite `docs/internal/README.md`**

Replace the file body with:

```markdown
# Baldric internal documentation

These are the internal build journals, designs, decisions, and plans for Baldric.
They are **not** published on the docs site. User-facing documentation lives in
`docs/user/`.

## Contents

- `adr/` - architecture decision records, numbered in one sequence.
- `architecture/` - per-phase implementation notes and subsystem journals. Each
  answers: what was added, why it exists, and how later phases use it.
- `design/` - designs written before implementation, kept for rationale.
- `notes/` - feature build journals and investigations that are not a phase.
- `plans/` - executable work plans. A finished plan either lands in `adr/` as a
  decision or stays here as history.
- `specs/` - detailed specifications that a plan implements.

The roadmap is tracked in [GitHub issue #2](https://github.com/Ember452/baldric/issues/2).
Documentation rules are in [../AGENTS.md](../AGENTS.md).
```

- [ ] **Step 3: Fix the two relative links broken by the move**

In `docs/internal/design/03-tools.md`, change:

```markdown
[ADR 0002](./adr/0002-keep-tool-docs-hand-written.md)
```

to:

```markdown
[ADR 0002](../adr/0002-keep-tool-docs-hand-written.md)
```

In `docs/internal/design/mcp-client-build.md`, change:

```markdown
[plans/mcp-client-implementation.md](../../plans/mcp-client-implementation.md)
```

to:

```markdown
[plans/mcp-client-implementation.md](../plans/mcp-client-implementation.md)
```

- [ ] **Step 4: Update the packaged self-knowledge paths**

Use the editor on these files under `src/baldric/runtime/data/docs/`:

- `architecture.md`: `website/content/internals/architecture.md` → `docs/user/explanation/architecture.md`; `dev-notes/architecture/` → `docs/internal/architecture/`.
- `extensions.md`: `website/content/guides/extensions.md` → `docs/user/how-to/extensions.md` (three occurrences); `dev-notes/architecture/phase-21-extensions.md` → `docs/internal/architecture/phase-21-extensions.md`.
- `models.md`: `website/content/guides/providers-and-models.md` → `docs/user/how-to/providers-and-models.md`.
- `skills.md`: `website/content/guides/skills-and-prompts.md` → `docs/user/how-to/skills-and-prompts.md`.

Also update live repository-path references in the published docs:

- `docs/user/contributing.md`: `dev-notes/design/` → `docs/internal/design/`, `dev-notes/architecture/` → `docs/internal/architecture/`, `dev-notes/adr/` → `docs/internal/adr/`, remaining `dev-notes/` → `docs/internal/`, and `website/content/` → `docs/user/`.
- `docs/user/how-to/extensions.md:928`: `dev-notes/architecture/phase-21-extensions.md` → `docs/internal/architecture/phase-21-extensions.md`.
- `docs/user/explanation/architecture.md:95`: `` `dev-notes/` `` → `` `docs/internal/` ``.
- `docs/user/explanation/custom-frontend.md:110`: `` `dev-notes/` `` → `` `docs/internal/` ``.
- `docs/user/explanation/design-principles.md:54`: `` `dev-notes/` `` → `` `docs/internal/` ``.
- `docs/user/reference/rpc.md:78`: `dev-notes/design/rpc-runtime-interchangeability-plan.md` → `docs/internal/design/rpc-runtime-interchangeability-plan.md`.

- [ ] **Step 5: Verify moves and links**

Run:
```powershell
git status --short
Test-Path dev-notes, plans, docs/superpowers
Get-ChildItem -LiteralPath docs/internal -Directory | Select-Object -ExpandProperty Name
Select-String -Path "docs/internal/**/*.md" -Pattern '\]\(\.\./\.\./plans/|\]\(\./adr/'
```
Expected: `Test-Path` returns `False, False, False`; the six internal directories are listed (`adr`, `architecture`, `design`, `notes`, `plans`, `specs`); the link search returns no output.

- [ ] **Step 6: Run the Python guards and wheel test**

Run:
```powershell
uv run pytest -q tests/guards tests/test_package_metadata.py
```
Expected: all pass, including the wheel test that asserts the packaged docs are present.

- [ ] **Step 7: Commit**

```powershell
git add -A
git commit -m "docs: move contributor records under docs/internal"
```

---

## Task 5: Consolidate the ADR sequence

**Files:**
- Rename: `docs/internal/plans/adr-0001-kernel-boundary.md` → `docs/internal/adr/0004-kernel-boundary.md`
- Rename: `docs/internal/plans/adr-0002-god-class-deferral.md` → `docs/internal/adr/0005-god-class-deferral.md`
- Rename: `docs/internal/plans/adr-0003-transcript-as-truth.md` → `docs/internal/adr/0006-transcript-as-truth.md`
- Modify: `docs/internal/adr/0004-kernel-boundary.md` (title)
- Modify: `docs/internal/adr/0005-god-class-deferral.md` (title)
- Modify: `docs/internal/adr/0006-transcript-as-truth.md` (title and self-references)
- Modify: `docs/internal/plans/agent-kernel-parity-plan.md`
- Modify: `docs/internal/plans/kernel-refactor-plan.md`
- Modify: `docs/internal/specs/2026-11-08-tui-visual-system-design.md`
- Modify: `src/baldric/runtime/extensions/builtins/subagents/extension.py`
- Modify: `tests/runtime/extensions/test_subagents_extension.py`

**Interfaces:**
- Consumes: the single `docs/internal/adr/` directory from Task 4.
- Produces: one ADR sequence `0001`-`0006`; all references use the final numbers and paths.

- [ ] **Step 1: Rename the ADRs**

```powershell
git mv docs/internal/plans/adr-0001-kernel-boundary.md docs/internal/adr/0004-kernel-boundary.md
git mv docs/internal/plans/adr-0002-god-class-deferral.md docs/internal/adr/0005-god-class-deferral.md
git mv docs/internal/plans/adr-0003-transcript-as-truth.md docs/internal/adr/0006-transcript-as-truth.md
```

- [ ] **Step 2: Renumber the titles**

Use the editor on each file:

- `docs/internal/adr/0004-kernel-boundary.md`: `# ADR-0001：` → `# ADR-0004：`
- `docs/internal/adr/0005-god-class-deferral.md`: `# ADR-0002：` → `# ADR-0005：`
- `docs/internal/adr/0006-transcript-as-truth.md`: `# ADR-0003：` → `# ADR-0006：`

Inside `0004-kernel-boundary.md`, change the cross-reference text `adr-0002-god-class-deferral.md` to `0005-god-class-deferral.md`.
Inside `0006-transcript-as-truth.md`, change `(ADR-0001)` to `(ADR-0004)`.

- [ ] **Step 3: Update plan references**

In `docs/internal/plans/agent-kernel-parity-plan.md`, first replace `plans/adr-0003-transcript-as-truth.md` with `../adr/0006-transcript-as-truth.md`, then replace every remaining `adr-0003-transcript-as-truth.md` with `../adr/0006-transcript-as-truth.md`, and every `ADR-0003` (all refer to the transcript decision) with `ADR-0006`.

In `docs/internal/plans/kernel-refactor-plan.md`, first replace `plans/adr-0001-kernel-boundary.md` with `../adr/0004-kernel-boundary.md`, then replace `adr-0003-transcript-as-truth.md` with `../adr/0006-transcript-as-truth.md`, `adr-0002-god-class-deferral.md` with `../adr/0005-god-class-deferral.md`, and every remaining `adr-0001-kernel-boundary.md` with `../adr/0004-kernel-boundary.md`.

In `docs/internal/specs/2026-11-08-tui-visual-system-design.md`, replace every `plans/adr-0003-transcript-as-truth.md` with `../adr/0006-transcript-as-truth.md`, and every `ADR-0003` that refers to transcript-as-truth with `ADR-0006`.

- [ ] **Step 4: Update the code comments that name the transcript ADR**

In `src/baldric/runtime/extensions/builtins/subagents/extension.py`, change the comment prefix at the durable-transcript line from `ADR 0003:` to `ADR 0006:`.

In `tests/runtime/extensions/test_subagents_extension.py`, change both durable-transcript comments from `ADR 0003` to `ADR 0006`.

Do not change `src/baldric/runtime/context/skills/skills.py:185`: its `ADR 0003` refers to skill discovery, which keeps that number.

- [ ] **Step 5: Verify the renumbering**

Run:
```powershell
Get-ChildItem -LiteralPath docs/internal/adr -File | Select-Object -ExpandProperty Name
Get-ChildItem -LiteralPath docs/internal -Recurse -File -Filter *.md | Select-String -Pattern 'adr-000[123]-(kernel|god|transcript)|plans/adr-000'
Select-String -LiteralPath "src/baldric/runtime/extensions/builtins/subagents/extension.py","tests/runtime/extensions/test_subagents_extension.py" -Pattern 'ADR 0003'
```
Expected: the ADR directory lists `0001`-`0006`; the first search returns no output; the second search returns no output (the transcript comments now say `ADR 0006`). The skill-discovery `ADR 0003` in `src/baldric/runtime/context/skills/skills.py` is correct and is not part of either search.

- [ ] **Step 6: Run the affected tests**

Run:
```powershell
uv run pytest -q tests/runtime/extensions/test_subagents_extension.py tests/guards
```
Expected: all pass.

- [ ] **Step 7: Commit**

```powershell
git add -A
git commit -m "docs: merge ADR sequences under docs/internal/adr"
```

---

## Task 6: Update guidance entry points and extend the agent-guidance ratchet

**Files:**
- Modify: `README.md:201`, `README.md:258`
- Modify: `CONTRIBUTING.md:115-137`
- Modify: `AGENTS.md:148-231`
- Modify: `scripts/check_agent_guidance.py`
- Modify: `tests/guards/test_agent_guidance_ratchet.py`
- Modify: `agent-guidance-baseline.json`

**Interfaces:**
- Consumes: the final paths from Tasks 1-5.
- Produces: guidance files that point at the new tree; the ratchet now covers `docs/AGENTS.md`; a re-baselined `agent-guidance-baseline.json`.

- [ ] **Step 1: Update `README.md`**

Change:

```markdown
  `dev-notes/` preserves the phase-by-phase build journal.
```

to:

```markdown
  `docs/internal/` preserves the phase-by-phase build journal.
```

Change:

```markdown
User docs are published at <https://ember452.github.io/baldric/> and live in
`website/content/`.
```

to:

```markdown
User docs are published at <https://ember452.github.io/baldric/> and live in
`docs/user/`.
```

- [ ] **Step 2: Update `CONTRIBUTING.md`**

Change:

```markdown
For substantial architectural or phase-oriented work, add beginner-friendly notes under `dev-notes/` explaining:
```

to:

```markdown
For substantial architectural or phase-oriented work, add beginner-friendly notes under `docs/internal/` explaining:
```

Change:

```markdown
```text
website/content/
```
```

to:

```markdown
```text
docs/user/
```
```

Change:

```markdown
See [dev-notes/release-process.md](dev-notes/release-process.md) for the full
```

to:

```markdown
See [docs/internal/notes/release-process.md](docs/internal/notes/release-process.md) for the full
```

- [ ] **Step 3: Update `AGENTS.md`**

In the Scoped Instructions list, add:

```markdown
- `docs/AGENTS.md` - documentation placement and writing rules
```

In Documentation Expectations, change `dev-notes/` to `docs/internal/` and `website/content/` to `docs/user/`.

- [ ] **Step 4: Teach the ratchet about `docs/AGENTS.md`**

In `scripts/check_agent_guidance.py`, replace `_managed_files` with:

```python
def _managed_files() -> list[Path]:
    """Return root, docs, and package guidance files, shallow to deep."""
    files: list[Path] = []
    for name in GUIDANCE_NAMES:
        candidate = ROOT / name
        if candidate.exists():
            files.append(candidate)
    guidance_dirs = [ROOT / "docs", *sorted((ROOT / "src" / "baldric").glob("*"))]
    for guidance_dir in guidance_dirs:
        if not guidance_dir.is_dir():
            continue
        for name in GUIDANCE_NAMES:
            candidate = guidance_dir / name
            if candidate.exists():
                files.append(candidate)
    return files
```

- [ ] **Step 5: Assert the new tier in the guard test**

In `tests/guards/test_agent_guidance_ratchet.py`, extend `test_baseline_is_committed_and_readable` with:

```python
    assert "docs/AGENTS.md" in baseline["files"]
```

- [ ] **Step 6: Re-baseline and verify**

Run:
```powershell
uv run python scripts/check_agent_guidance.py --init
uv run python scripts/check_agent_guidance.py
uv run pytest -q tests/guards/test_agent_guidance_ratchet.py
```
Expected: the baseline lists `docs/AGENTS.md`; the check prints `agent-guidance ratchet: OK`; the guard tests pass.

- [ ] **Step 7: Commit**

```powershell
git add README.md CONTRIBUTING.md AGENTS.md scripts/check_agent_guidance.py tests/guards/test_agent_guidance_ratchet.py agent-guidance-baseline.json
git commit -m "docs: point guidance files at docs/ and ratchet docs/AGENTS.md"
```

---

## Task 7: Add GitHub community files and a generated changelog

**Files:**
- Create: `SECURITY.md`
- Create: `CODE_OF_CONDUCT.md`
- Create: `SUPPORT.md`
- Create: `CHANGELOG.md` (generated)
- Create: `scripts/render_changelog.py`
- Create: `tests/guards/test_changelog.py`
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Modify: `.github/workflows/ci.yml` (add a changelog check to the `static` job)

**Interfaces:**
- Consumes: `src/baldric/runtime/data/release-notes/releases.json` as the single source of release facts.
- Produces: GitHub-recognized community files and a changelog that cannot drift from the release data.

- [ ] **Step 1: Write `SECURITY.md`**

```markdown
# Security policy

## Supported versions

The latest published minor release receives security fixes. Older minors are
supported only while they are the current release line.

## Reporting a vulnerability

Do not open a public issue for a vulnerability. Report it through the
repository's private security advisory form:

<https://github.com/Ember452/baldric/security/advisories/new>

Include the affected version, the smallest reproduction you can produce, and the
impact you believe is possible. You will receive an acknowledgement and a
remediation plan before any public disclosure.
```

- [ ] **Step 2: Write `CODE_OF_CONDUCT.md`**

```markdown
# Code of conduct

This project follows the [Contributor Covenant, version 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

## Scope

It applies in every project space: issues, pull requests, discussions, and any
other channel where someone represents the project.

## Reporting

Report unacceptable behavior to the maintainers through a private security
advisory at <https://github.com/Ember452/baldric/security/advisories/new>.
Reports are reviewed promptly and kept confidential. Maintainers may remove,
edit, or reject contributions that violate this code.
```

- [ ] **Step 3: Write `SUPPORT.md`**

```markdown
# Support

## Questions and usage help

Open a discussion at <https://github.com/Ember452/baldric/discussions>.
Include the Baldric version, your platform, and the command you ran.

## Bugs and feature requests

Open an issue with the matching template:
<https://github.com/Ember452/baldric/issues/new/choose>

## Security

Do not open a public issue. Follow [SECURITY.md](SECURITY.md).

## Documentation

Start at [docs/README.md](docs/README.md). User docs are published at
<https://ember452.github.io/baldric/>.
```

- [ ] **Step 4: Write the issue templates**

`.github/ISSUE_TEMPLATE/bug_report.yml`:

```yaml
name: Bug report
description: Report behavior that is broken or surprising.
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: Thanks for reporting. Remove secrets and private paths from logs.
  - type: textarea
    id: what-happened
    attributes:
      label: What happened?
      description: The observed behavior, including the exact command.
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: What did you expect?
    validations:
      required: true
  - type: textarea
    id: reproduction
    attributes:
      label: Reproduction
      description: Smallest steps or repository that reproduces the problem.
    validations:
      required: true
  - type: input
    id: version
    attributes:
      label: Baldric version
      placeholder: output of `baldric --version`
    validations:
      required: true
  - type: input
    id: platform
    attributes:
      label: Platform
      placeholder: OS, terminal, and Python version
    validations:
      required: true
```

`.github/ISSUE_TEMPLATE/feature_request.yml`:

```yaml
name: Feature request
description: Propose a capability or a change in behavior.
labels: ["enhancement"]
body:
  - type: textarea
    id: problem
    attributes:
      label: Problem
      description: What can you not do today, and who does it affect?
    validations:
      required: true
  - type: textarea
    id: proposal
    attributes:
      label: Proposal
      description: The smallest change that solves the problem.
    validations:
      required: true
  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives
      description: Other approaches and why they lose.
    validations:
      required: false
```

`.github/ISSUE_TEMPLATE/config.yml`:

```yaml
blank_issues_enabled: false
contact_links:
  - name: Usage questions
    url: https://github.com/Ember452/baldric/discussions
    about: Ask for help with installation, configuration, or workflows.
  - name: Security reports
    url: https://github.com/Ember452/baldric/security/advisories/new
    about: Report vulnerabilities privately.
```

- [ ] **Step 5: Write the changelog renderer**

Create `scripts/render_changelog.py`:

```python
#!/usr/bin/env python3
"""Render CHANGELOG.md from the packaged release notes.

`releases.json` is the single source of release facts: the CLI reads it at
startup and the website renders it. The changelog is generated from the same
file so the two cannot drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "baldric" / "runtime" / "data" / "release-notes" / "releases.json"
TARGET = ROOT / "CHANGELOG.md"
SECTION_ALIASES = {"New": "Added"}
HEADER = [
    "# Changelog",
    "",
    "All notable changes to this project are documented in this file.",
    "",
    "The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),",
    "and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).",
    "",
]


def render() -> str:
    """Return the full changelog for the current release notes."""
    releases = json.loads(SOURCE.read_text(encoding="utf-8"))
    lines = list(HEADER)
    for release in releases:
        heading = f"## [{release['version']}]"
        if release.get("date"):
            heading += f" - {release['date']}"
        lines.extend([heading, ""])
        for section, items in release["sections"].items():
            lines.extend([f"### {SECTION_ALIASES.get(section, section)}", ""])
            lines.extend(f"- {item}" for item in items)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    if "--check" in sys.argv[1:]:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != render():
            print("CHANGELOG.md is out of date; run `uv run python scripts/render_changelog.py`")
            return 1
        print("CHANGELOG.md is up to date")
        return 0
    TARGET.write_text(render(), encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Write the changelog guard test**

Create `tests/guards/test_changelog.py`:

```python
"""The generated changelog must stay in sync with the release notes."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_changelog_matches_release_notes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/render_changelog.py", "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 7: Generate the changelog and add the CI check**

Run:
```powershell
uv run python scripts/render_changelog.py
```
Expected: `wrote CHANGELOG.md`.

In `.github/workflows/ci.yml`, in the `static` job, after the agent-guidance step, add:

```yaml
      - name: Check changelog is current
        run: uv run python scripts/render_changelog.py --check
```

- [ ] **Step 8: Verify and commit**

Run:
```powershell
uv run ruff check scripts/render_changelog.py tests/guards/test_changelog.py
uv run pytest -q tests/guards/test_changelog.py
uv run python scripts/render_changelog.py --check
```
Expected: lint passes; the test passes; the check prints `CHANGELOG.md is up to date`.

```powershell
git add SECURITY.md CODE_OF_CONDUCT.md SUPPORT.md CHANGELOG.md scripts/render_changelog.py tests/guards/test_changelog.py .github/ISSUE_TEMPLATE .github/workflows/ci.yml
git commit -m "docs: add community files and generated changelog"
```

---

## Task 8: Final verification sweep

**Files:** none by default. Fix only what the sweep proves is stale, one file at a time, then amend into a new commit (never rewrite a previous commit).

**Interfaces:**
- Consumes: every earlier task.
- Produces: proof that the tree is standard, the site is clean, and no live reference points at a removed path.

- [ ] **Step 1: Prove no live references point at removed roots**

Run:
```powershell
$targets = @("README.md", "CONTRIBUTING.md", "AGENTS.md")
$targets += Get-ChildItem -LiteralPath docs, website/src, website/tests, src/baldric/runtime/data/docs -Recurse -File -Include *.md, *.ts, *.astro, *.mjs -ErrorAction SilentlyContinue | ForEach-Object FullName
$targets | Select-String -Pattern 'website/content|dev-notes/|docs/superpowers|\(/guides/|\(/internals/'
```
Expected: no output. Historical filename mentions inside `docs/internal/` prose are allowed only when they are not Markdown links; if a link appears, fix it.

- [ ] **Step 2: Prove the published tree is exactly `docs/user`**

Run:
```powershell
Get-ChildItem -LiteralPath docs/user -Directory | Select-Object -ExpandProperty Name
```
Expected: `how-to`, `explanation`, `reference`, `tutorials`.

- [ ] **Step 3: Run the static tier**

Run:
```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python scripts/check_import_graph.py
uv run python scripts/check_structure.py
uv run python scripts/check_suppressions.py
uv run python scripts/check_agent_guidance.py
uv run python scripts/verify_versions.py
```
Expected: all green. The known 14 Windows-only mypy errors in `trust/policy.py` and `session/storage.py` may appear locally; they are documented limitations and CI runs mypy on Linux.

- [ ] **Step 4: Run the fast suite**

Run:
```powershell
uv run pytest -q --ignore=tests/runtime/tui
```
Expected: all pass (the documented Windows skips are expected).

- [ ] **Step 5: Run the website checks**

Run:
```powershell
npm --prefix website run check
npm --prefix website run format:check
npm --prefix website run build
npm --prefix website test
```
Expected: all pass; `dist/tutorials/quickstart/index.html`, `dist/how-to/`, `dist/explanation/`, and `dist/reference/` exist.

- [ ] **Step 6: Inspect the final diff**

Run:
```powershell
git status --short
git diff --stat main...HEAD
```
Expected: only documentation moves, site wiring, guidance files, community files, and the changelog tooling. No source behavior change outside the ADR comment updates in Task 5.

- [ ] **Step 7: Commit any sweep fixes**

If Step 1 or any check required a fix, commit it as:

```powershell
git add -A
git commit -m "docs: fix stale documentation references"
```

If nothing was stale, no commit.

---

## Follow-ups (explicitly out of scope)

Do not add these in this plan; they are separate, reviewable changes:

- Generated Python API reference under `docs/user/reference/api/`.
- `docs/user/explanation/glossary.md` and `docs/user/how-to/troubleshooting.md` (write after the structure settles).
- A repository-wide Markdown link checker for `docs/internal/` (the history contains prose path mentions that need an audit first).
- Re-enabling `.github/workflows/docs.yml.disabled` for GitHub Pages deployment.
- i18n, postmortem, and archive tiers.
- Removing the stray root files (`033662d6*.html`, `084dc60e*.html`, `landing.html`, `_pytest_channels.log`, `interview-prep-bytedance.md`); they need an owner decision, not a docs move.

## Self-Review

- **Decision coverage:** single root (`docs/`), Diátaxis renames, audience split, packaged self-docs tier, ADR merge, CI/community files - each maps to a task (1-7) and is verified in Task 8.
- **No placeholders:** every file to create has full content; every move has an exact command; every check has a command and expected result.
- **Name consistency:** `docs/user`, `docs/internal`, `docs/internal/adr`, `docs/internal/notes`, `docs/templates`, `docs/AGENTS.md`, `docs/README.md` are used with the same spelling in every task.
- **Known risk:** the `git mv` loop for `dev-notes/*.md` must run before `dev-notes/README.md` is moved; the step order above enforces that.
- **Known risk:** `Select-String -Path "docs/**/*.md"` needs PowerShell 7 recursive globbing; the fallback `Get-ChildItem | Select-String` is provided inline.
