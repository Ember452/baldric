# Single-Package src Layout Migration Plan

> **For agentic workers:** This plan is executed inline by the Lead in one
> session per the owner's direct order ("开一个新分支，将该做的做完"). Steps use
> checkbox syntax for tracking. The bulk rewrite follows the AGENTS.md escape
> hatch: genuinely required bulk rewrite → separate commit → dry-run review first.

**Goal:** Consolidate the five top-level packages `src/baldric_{protocol,ai,agent,coding,mcp}`
into one import package `src/baldric/{protocol,ai,agent,coding,mcp}` matching the
distribution name `baldric`, with zero behavior change.

**Architecture:** Pure mechanical rename. Directory moves via `git mv` (history
preserved); import/string/comment renames via a token-level Python script with
mandatory dry-run review; config, gate-script logic, and path-segment fixes by
hand; ratchet baselines regenerated and diff-reviewed. Layer boundaries stay
enforced by `check_import_graph.py` with translated prefixes.

**Tech Stack:** Python 3.12, uv, hatchling, pytest, ruff, mypy, project ratchets.

**Spec:** Owner decision in conversation (2026-11-10): single `baldric` import
root is the more conventional layout for one distribution; pre-1.0 (0.3.0) is
the cheap moment to do it. Hard rules from `AGENTS.md` apply.

## Global Constraints

- Zero behavior change: no reformatting, no renames beyond the package map, no
  assertion weakening, no test deletion/skipping.
- Package map (exact): `baldric_protocol→baldric.protocol`, `baldric_ai→baldric.ai`,
  `baldric_agent→baldric.agent`, `baldric_coding→baldric.coding`, `baldric_mcp→baldric.mcp`.
- Distribution name stays `baldric`; version stays `0.3.0`; `uv.lock` must not change.
- Historical records are NOT rewritten: `dev-notes/**`, `plans/**`,
  `docs/superpowers/**` (except this new plan), `src/**/data/release-notes/**`,
  gitignored artifacts. They describe past states in old names by design.
- Guidance-file edits must be byte-length-neutral where possible
  (`baldric_x` → `baldric.x` and `src/baldric_x/` → `src/baldric/x/` are
  same-length), so the guidance ratchet stays green without `--init` growth.
- Known Windows baseline: 14 mypy errors in `trust/policy.py` +
  `session/storage.py`; ~121 POSIX skips. These must remain the ONLY mypy errors.
- One atomic commit on branch `refactor/single-package-src-layout`.

## Inventory (verified 2026-11-10)

- src: 1432 absolute-import lines; 3 string refs (`files("baldric_coding")` ×2 —
  runtime-critical resource anchors; `source="baldric_coding.system_prompt"` label).
  No `import_module`/`__import__` in src. Extension loader uses synthetic module
  names (`spec_from_file_location`), unaffected. `files(__package__)` in themes
  adapts automatically. `version.py` reads distribution metadata — unaffected.
- tests: imports + dotted strings (monkeypatch/logger/import_module) + 13
  path-segment lines needing manual two-segment fixes (list in Task 5).
- scripts: `check_import_graph.py` (string prefixes only; `_module_name` is
  path-generic), `check_structure.py` (fan-out root set + membership logic),
  `check_agent_guidance.py` (discovery depth `src/*` → `src/baldric/*`),
  `generate_models.py` (imports + one slash path). `check_suppressions.py`,
  `check_move_only.py`, `verify_versions.py` need no change.
- config: `pyproject.toml` 4 spots (entry point, coverage omit, hatch packages,
  mypy packages). `.pre-commit-config.yaml` uses generic `^src/` — no change.
  `.github/**` — no references.
- docs/site: root `AGENTS.md`/`README.md`/`CONTRIBUTING.md`, 3 scoped `AGENTS.md`,
  `landing.html`, `website/content/**` (8 files), `website/src/data.ts` (release
  notes path — functional), `website/src/components/Home.astro`,
  `website/data/roadmap.yaml` (1 line), bundled `src/baldric_coding/data/docs/**`
  and `data/examples/extensions/*.py`.
- tracked project extension `.baldric/extensions/ask_user_question.py` — imports
  must be renamed or the local extension breaks.
- `py.typed`: one marker per old package (5). New layout: single marker at
  `src/baldric/py.typed` (PEP 561 package root); remove the five subpackage copies.

---

### Task 1: Baseline evidence (DONE)

- [x] Clean worktree on `main` @ 9f77fa3; branch `refactor/single-package-src-layout` created.
- [x] Static gates green: ruff check, ruff format (466 files), import-graph,
      structure, suppressions, guidance, versions (0.3.0).
- [x] mypy: exactly 14 known Windows errors in 2 files.
- [ ] Fast suite `uv run pytest -q --ignore=tests/coding/tui` — record result.

### Task 2: Directory moves + package root

**Files:**
- Move: `src/baldric_protocol` → `src/baldric/protocol` (and ai/agent/coding/mcp)
- Create: `src/baldric/__init__.py` (docstring only, no re-exports)
- Move: `src/baldric/protocol/py.typed` → `src/baldric/py.typed`
- Delete: `src/baldric/{ai,agent,coding,mcp}/py.typed` (redundant under one root)

- [ ] `New-Item -ItemType Directory src/baldric` then five `git mv` commands.
- [ ] `git mv` one py.typed to the root; `git rm` the other four.
- [ ] Write `src/baldric/__init__.py` with a one-line docstring.
- [ ] Verify: `git status` shows renames; `Get-ChildItem src/baldric` shows 5 dirs
      + `__init__.py` + `py.typed`.

### Task 3: Migration script + dry-run review

**Files:**
- Create: `D:\DEVELOP\Solis\_migrate_baldric_single_package.py` (outside repo,
  one-shot scratch convention; NOT committed)
- Output: `D:\DEVELOP\Solis\_migration_report.txt`

Script contract:
- `.py` pass (src, tests, scripts, examples, .baldric/extensions): tokenize;
  replace exact NAME tokens via the map; rewrite STRING/FSTRING_MIDDLE/COMMENT
  token text with ordered rules:
  1. `src[/\]baldric_x` → `src/baldric/x`
  2. `baldric_x/` → `baldric/x/`
  3. `baldric_x.` → `baldric.x.`
  4. bare `baldric_x` → `baldric.x` (flagged REVIEW: may be a path segment)
- Text pass (root AGENTS/README/CONTRIBUTING/landing.html, src/**/*.md,
  website/content/**/*.md, website/src/data.ts, Home.astro, roadmap.yaml):
  same four rules on raw text.
- Preserve bytes outside edited spans; preserve line endings and line counts;
  `ast.parse` must succeed on every rewritten .py before writing.
- Dry-run (default) writes the full report; `--apply` writes files.

- [ ] Run dry-run; read the FULL report; review every REVIEW-flagged bare string
      and the leftovers section (expected leftovers: test function names containing
      `baldric_` as substring, e.g. `test_baldric_coding_public_surface_is_frozen`).
- [ ] Confirm counts: ~250 src files, tests/scripts/examples touched; no
      release-notes/dev-notes/plans/docs-superpowers files in the report.

### Task 4: Apply + config edits

- [ ] Run script `--apply`; re-run dry-run → report must show zero changes.
- [ ] `pyproject.toml` (4 manual edits):
  - `baldric = "baldric.coding.cli:app"`
  - `omit = ["src/baldric/coding/data/*"]`
  - `[tool.hatch.build.targets.wheel] packages = ["src/baldric"]`
  - `[tool.mypy] packages = ["baldric"]`
- [ ] `scripts/check_structure.py`: fan-out membership test
      `target.split(".")[0] in project_roots` → prefix match
      (`target == root or target.startswith(root + ".")`), roots set already
      translated by the script to `{"baldric.agent","baldric.ai","baldric.coding"}`.
      Keeps the metric semantics identical (protocol/mcp stay excluded as before).
- [ ] `scripts/check_agent_guidance.py`: discovery `(ROOT/"src").glob("*")` →
      `(ROOT/"src"/"baldric").glob("*")` (scoped files are now one level deeper).

### Task 5: Path-segment fixes (manual, 13 lines)

After the script, these read `"src" / "baldric.x"` (one wrong segment); fix each
to `"src" / "baldric" / "x"`:

- [ ] `tests/test_package_metadata.py:8`
- [ ] `tests/helpers/subagents_shared.py:21`
- [ ] `tests/guards/test_session_state_write_ratchet.py:25`
- [ ] `tests/guards/test_provider_helpers_single_source.py:15`
- [ ] `tests/guards/event_union.py:20,21`
- [ ] `tests/guards/test_import_boundaries.py:67,83,95,137,152,166`
- [ ] `tests/coding/rendering/test_theme_schema.py:30`
- [ ] Verify: grep tests for `/ "baldric\.` → zero hits.

### Task 6: Environment + baselines

- [ ] `uv sync` (rebuild editable install against new layout); `uv.lock` diff must
      be empty.
- [ ] Regenerate: `uv run python scripts/check_structure.py --init`,
      `check_suppressions.py --init`, `check_agent_guidance.py --init`.
- [ ] Review each baseline diff: structure/suppressions = pure key renames with
      identical values; guidance = key renames with identical byte sizes.
- [ ] Smoke: `uv run python -c "import baldric, baldric.coding, baldric.ai,
      baldric.agent, baldric.protocol, baldric.mcp"`; `uv run baldric --version`.

### Task 7: Full verification (cross-package refactor → full tier)

- [ ] `uv run ruff check .` and `uv run ruff format --check .` → green.
- [ ] `uv run mypy` → exactly the 14 known Windows errors, new paths.
- [ ] `uv run python scripts/check_import_graph.py` → OK.
- [ ] Three ratchets + `verify_versions.py` → OK.
- [ ] `uv run pytest` (FULL, ~4 min) → same pass/skip profile as baseline.
- [ ] `uv build` → wheel contains `baldric/coding/data/...`, `baldric/py.typed`,
      entry point `baldric.coding.cli:app`; no `baldric_*` paths.
- [ ] Resource smoke: `uv run python -c "from importlib.resources import files;
      print(files('baldric.coding').joinpath('data/catalog.toml').read_text()[:80])"`.

### Task 8: Journal + atomic commit

- [ ] Add `dev-notes/architecture/single-package-layout.md`: what/why/how,
      old→new map, what was deliberately left in old names (historical records),
      verification evidence, extension-API break note for third-party extensions
      (`from baldric_coding.extensions import ...` → `from baldric.coding.extensions import ...`).
- [ ] `git add -A` (repo only); review `git status` + `git diff --stat` tail;
      confirm no scratch files, no uv.lock change, no historical-doc churn.
- [ ] Commit: `refactor: consolidate five baldric_* packages into src/baldric/`
      with body describing the mechanical rename, gate evidence, and the
      public-import break at 0.3.0.
- [ ] Report to owner with evidence; branch left for review (no merge without ask).