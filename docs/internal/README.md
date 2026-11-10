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
