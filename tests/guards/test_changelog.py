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
