"""Guard: ``_loads_object`` must have a single source of truth.

It used to be copy-pasted into six adapters (anthropic, google, mistral,
openai_codex, openai_compatible, http_errors) and had already drifted in return
types and exception handling. It now lives in ``baldric_ai._sse`` and is imported
by each adapter. Fail if a local definition reappears.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_DIR = REPO_ROOT / "src" / "baldric_ai"

# The single allowed definition site.
OWNER = AI_DIR / "_sse.py"


def test_loads_object_is_defined_only_in_shared_module() -> None:
    offenders: list[str] = []
    for path in AI_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        if re.search(r"^def loads_object\b", source, re.MULTILINE) and path != OWNER:
            offenders.append(path.name)
        # The old private name must not be re-defined anywhere.
        if re.search(r"^def _loads_object\b", source, re.MULTILINE):
            offenders.append(f"{path.name} (def _loads_object)")
    assert offenders == [], (
        f"loads_object must be defined only in baldric_ai/_sse.py; local copies found in: {offenders}"
    )


def test_owner_module_stays_a_leaf_helper() -> None:
    """The helper must stay dependency-free so any adapter can import it."""
    source = OWNER.read_text(encoding="utf-8")
    project_imports = [
        line for line in source.splitlines() if line.startswith(("import ", "from ")) and "baldric" in line
    ]
    assert project_imports == [], f"_sse.py must not import project modules; found: {project_imports}"
