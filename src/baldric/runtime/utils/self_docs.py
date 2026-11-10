"""Locations of Baldric's packaged self-documentation and examples."""

from __future__ import annotations

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_DATA_ROOT = _PACKAGE_ROOT / "data"


def baldric_readme_path() -> Path:
    """Return the installed overview document for Baldric-aware tasks."""
    return _DATA_ROOT / "docs" / "README.md"


def baldric_docs_path() -> Path:
    """Return the installed Baldric self-documentation directory."""
    return _DATA_ROOT / "docs"


def baldric_examples_path() -> Path:
    """Return the installed Baldric example directory."""
    return _DATA_ROOT / "examples"
