"""Output formatting and temporary-file helpers for tools."""

from __future__ import annotations

import tempfile


def format_size(bytes_count: int) -> str:
    if bytes_count < 1024:
        return f"{bytes_count}B"
    if bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f}KB"
    return f"{bytes_count / (1024 * 1024):.1f}MB"


def append_status_block(text: str, status: str) -> str:
    """Append command status text after a blank line when output already exists."""
    return f"{text}\n\n{status}" if text else status


def write_temp_output(output: str, *, prefix: str, suffix: str) -> str:
    """Persist full tool output to a temp file and return its path.

    The house convention for outputs too large for the model: a system temp
    file (``delete=False``) named with the tool-specific ``prefix``.
    """
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=prefix,
        suffix=suffix,
        delete=False,
    ) as handle:
        handle.write(output)
        return handle.name


def _write_temp_output(output: str) -> str:
    return write_temp_output(output, prefix="baldric-bash-", suffix=".log")
