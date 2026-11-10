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
