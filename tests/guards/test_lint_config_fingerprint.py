"""Lint and type-configuration fingerprint.

Removing a ruff rule or relaxing a mypy switch is how a red check turns green
without fixing anything. The fingerprint below pins the exact normalized
configuration: changing it requires editing this file, which is the disclosure
step the ratchet is meant to force.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# Update this value together with an intentional configuration change, and say
# why in the commit message. A mismatch means the toolchain got quieter.
EXPECTED_FINGERPRINT = "969b387cbf0d584302bc88604c256bb03296b89b046add2fa19ec0a93f42a815"


def _config() -> dict[str, Any]:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    ruff = data.get("tool", {}).get("ruff", {})
    lint = ruff.get("lint", {})
    mypy = data.get("tool", {}).get("mypy", {})
    pytest_options = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    return {
        "ruff_select": sorted(lint.get("select", [])),
        "ruff_ignore": sorted(lint.get("ignore", [])),
        "ruff_per_file_ignores": sorted((lint.get("per-file-ignores") or {}).keys()),
        "ruff_line_length": ruff.get("line-length"),
        "ruff_target_version": ruff.get("target-version"),
        "mypy_strict": mypy.get("strict"),
        "mypy_python_version": mypy.get("python_version"),
        "mypy_packages": sorted(mypy.get("packages", [])),
        "mypy_override_count": len(mypy.get("overrides", [])),
        "pytest_addopts": pytest_options.get("addopts"),
    }


def fingerprint(config: dict[str, Any]) -> str:
    normalized = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def test_lint_and_type_configuration_is_unchanged() -> None:
    actual = fingerprint(_config())

    assert actual == EXPECTED_FINGERPRINT, (
        "ruff/mypy configuration changed. If the change is intentional, update "
        f"EXPECTED_FINGERPRINT to {actual!r} and explain the change in the commit message."
    )


def test_fingerprint_reacts_to_rule_removal() -> None:
    """Prove the lock is not vacuous: dropping a rule must change the hash."""
    config = _config()
    before = fingerprint(config)
    weakened = {**config, "ruff_select": config["ruff_select"][:-1]}

    assert fingerprint(weakened) != before


def test_fingerprint_reacts_to_mypy_relaxation() -> None:
    config = _config()
    before = fingerprint(config)
    relaxed = {**config, "mypy_strict": False}

    assert fingerprint(relaxed) != before
