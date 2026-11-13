"""External prompt-editor support for the Textual frontend.

The editor command is resolved from (first match wins):

1. The durable ``editor_command`` TUI setting
2. ``BALDRIC_EDITOR``
3. ``VISUAL``
4. ``EDITOR``
5. A platform default (``notepad`` on Windows, ``vi`` on POSIX)

The value may contain arguments (``code -w``, ``vim -f``) and is split with
``shlex`` so quoted paths work. The module has no Textual dependency beyond the
opt-in :func:`maybe_suspended` helper, so it stays unit-testable.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROMPT_FILE_SUFFIX = ".md"


class EditorError(RuntimeError):
    """Raised when the external editor cannot be resolved or fails."""


@contextmanager
def maybe_suspended(app: Any) -> Iterator[None]:
    """Suspend the Textual app when the environment allows it.

    Headless test runs and redirected output cannot hand the terminal back;
    the editor then runs inline so the action keeps working everywhere.
    """
    with ExitStack() as stack:
        try:
            suspend_cm = app.suspend()
        except Exception:  # textual raises SuspendNotSupported
            suspend_cm = None
        if suspend_cm is not None:
            try:
                stack.enter_context(suspend_cm)
            except Exception:  # raised on __enter__, not call
                suspend_cm = None
        yield


@dataclass(frozen=True, slots=True)
class EditorResult:
    """Outcome of one external editor invocation."""

    text: str
    changed: bool


def resolve_editor_command(
    settings_command: str | None,
    *,
    environ: dict[str, str] | None = None,
    platform: str | None = None,
) -> list[str]:
    """Resolve the editor argv, falling back to a platform default."""
    candidates: list[str | None] = [settings_command]
    env = os.environ if environ is None else environ
    candidates.extend(env.get(name) for name in ("BALDRIC_EDITOR", "VISUAL", "EDITOR"))
    for candidate in candidates:
        if candidate is None:
            continue
        normalized = candidate.strip()
        if normalized:
            # ``posix=False`` keeps Windows drive-letter backslashes intact but
            # retains quotes; strip one pair from each token so quoted paths
            # and quoted executables both work.
            tokens = [
                token[1:-1] if len(token) > 1 and token[0] == token[-1] and token[0] in {'"', "'"} else token
                for token in shlex.split(normalized, posix=False)
            ]
            if tokens:
                return tokens
    if (platform or os.name) == "nt":
        return ["notepad"]
    return ["vi"]


def edit_prompt_text(
    text: str,
    *,
    settings_command: str | None = None,
    environ: dict[str, str] | None = None,
    platform: str | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> EditorResult:
    """Open ``text`` in the resolved external editor and return the result.

    Blocks until the editor exits. Raises :class:`EditorError` when the editor
    cannot be started or exits with a nonzero status. An editor that saves no
    trailing newline (or deletes the temp file) keeps the original text.
    """
    argv = resolve_editor_command(settings_command, environ=environ, platform=platform)
    with tempfile.TemporaryDirectory(prefix="baldric-editor-") as tmp_dir:
        prompt_path = Path(tmp_dir) / f"prompt{PROMPT_FILE_SUFFIX}"
        prompt_path.write_text(text, encoding="utf-8")
        try:
            completed = run([*argv, str(prompt_path)], check=False)
        except OSError as exc:
            raise EditorError(f"Could not start editor {argv[0]!r}: {exc}") from exc
        if completed.returncode != 0:
            raise EditorError(f"Editor {argv[0]!r} exited with status {completed.returncode}")
        edited = prompt_path.read_text(encoding="utf-8")
    # Console editors force a trailing newline on save; a prompt does not need
    # it and it would show up as an empty line in the composer.
    edited = edited.rstrip("\n")
    return EditorResult(text=edited, changed=edited != text)


async def run_external_editor(
    app: Any,
    text: str,
    *,
    settings_command: str | None = None,
) -> EditorResult:
    """Run the external editor from async UI code.

    Suspends the Textual app when the environment allows it and runs the
    blocking editor in a worker thread, keeping the event loop responsive.
    Raises :class:`EditorError` on failure.
    """
    with maybe_suspended(app):
        return await asyncio.to_thread(
            edit_prompt_text,
            text,
            settings_command=settings_command,
        )
