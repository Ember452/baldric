"""Print frontend: the non-interactive (one-shot) surface.

Owns only the orchestration of a single prompt run; rendering lives in
``baldric.runtime.rendering``. See ``mode.py``.
"""

from __future__ import annotations

from baldric.runtime.frontends.print.mode import (
    run_openai_print_mode,
    run_print_mode,
)

__all__ = [
    "run_openai_print_mode",
    "run_print_mode",
]
