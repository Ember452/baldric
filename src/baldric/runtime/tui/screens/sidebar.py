"""Minimal Textual app for Baldric coding sessions."""

from __future__ import annotations

import asyncio
import errno
import os
import stat
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, ClassVar, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import (
    Static,
    TextArea,
)

from baldric.runtime.platform.api import (
    MainViewHandle,
)

if TYPE_CHECKING:
    from baldric.runtime.tui.app import BaldricTuiApp


def _app_module() -> Any:
    import baldric.runtime.tui.app as app_module

    return app_module


type BindingEntry = Binding | tuple[str, str] | tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class _SidebarFileSnapshot:
    """Resolved target and exact bytes observed when a sidebar file was loaded."""

    target: Path
    content: bytes


def _read_sidebar_file(path: Path) -> tuple[str, _SidebarFileSnapshot]:
    """Read a sidebar file without normalizing its encoded contents."""
    target = path.resolve(strict=True)
    content = target.read_bytes()
    return content.decode("utf-8"), _SidebarFileSnapshot(target=target, content=content)


def _atomic_write_sidebar_file(
    path: Path,
    source: str,
    expected: _SidebarFileSnapshot,
) -> _SidebarFileSnapshot:
    """Atomically replace an unchanged, writable file and preserve its mode/symlink."""
    target = path.resolve(strict=True)
    replacement = source.encode("utf-8")
    if target != expected.target:
        raise OSError(f"File target changed on disk; reopen before saving: {path}")
    # Ask the OS to enforce ownership/ACL rules without truncating the target.
    authorization = os.open(
        target,
        os.O_WRONLY | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        target_stat = os.fstat(authorization)
        # Privileged processes may open 0444 files, but the editor treats an
        # explicitly read-only resource as not authorized for replacement.
        if target_stat.st_mode & 0o222 == 0:
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), target)
        target_mode = stat.S_IMODE(target_stat.st_mode)
    finally:
        os.close(authorization)

    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, raw_temporary = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(raw_temporary)
        os.chmod(temporary, target_mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            _app_module()._write_staged_utf8(handle, source)
            handle.flush()
            os.fsync(handle.fileno())
        current_target = path.resolve(strict=True)
        if current_target != expected.target or current_target.read_bytes() != expected.content:
            raise OSError(f"File changed on disk; reopen before saving: {path}")
        os.replace(temporary, target)
        temporary = None
        return _SidebarFileSnapshot(target=target, content=replacement)
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink()


class SidebarFileEditor(Vertical):
    """Main-area editor for a file selected from the session sidebar."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "close", "Close", show=False, priority=True),
        Binding("ctrl+s", "save", "Save", show=False, priority=True),
    ]

    def __init__(
        self,
        *,
        handle: MainViewHandle,
        path: Path,
        label: str,
        kind: str,
        source: str,
        snapshot: _SidebarFileSnapshot,
    ) -> None:
        super().__init__(id="sidebar-file-editor")
        self.handle = handle
        self.path = path
        self.label = label
        self.kind = kind
        self.source = source
        self._saved_source = source
        self._snapshot = snapshot
        self._saving = False

    def compose(self) -> ComposeResult:
        yield Static(f"Edit {self.kind}: {self.label}", id="sidebar-file-editor-title")
        yield Static(str(self.path), id="sidebar-file-editor-path")
        yield TextArea(self.source, id="sidebar-file-editor-input")
        yield Static(
            "Ctrl+S saves - Escape closes",
            id="sidebar-file-editor-help",
        )
        yield Static("", id="sidebar-file-editor-status")

    def on_mount(self) -> None:
        self.query_one("#sidebar-file-editor-input", TextArea).focus()

    @property
    def is_dirty(self) -> bool:
        """Return whether the mounted editor differs from its last saved source."""
        try:
            source = self.query_one("#sidebar-file-editor-input", TextArea).text
        except NoMatches:
            return False
        return source != self._saved_source

    def action_save(self) -> None:
        """Write the current editor contents without closing the editor."""
        if self._saving:
            return
        self._saving = True
        self.query_one("#sidebar-file-editor-status", Static).update("Saving…")
        self.app.run_worker(self._save(), exclusive=False)

    async def _save(self) -> None:
        source = self.query_one("#sidebar-file-editor-input", TextArea).text
        try:
            snapshot = await asyncio.to_thread(
                _app_module()._atomic_write_sidebar_file,
                self.path,
                source,
                self._snapshot,
            )
        except Exception as exc:  # noqa: BLE001 - filesystem worker boundary
            message = f"Could not save {self.path}: {exc}"
            self.query_one("#sidebar-file-editor-status", Static).update(message)
            cast("BaldricTuiApp", self.app)._notify(message, severity="error")
        else:
            self._snapshot = snapshot
            self._saved_source = source
            message = f"Saved {self.path}"
            self.query_one("#sidebar-file-editor-status", Static).update(message)
            cast("BaldricTuiApp", self.app)._notify(message)
        finally:
            self._saving = False

    def action_close(self) -> None:
        """Close the editor and restore the transcript."""
        self.handle.close()


def _write_staged_utf8(handle: BinaryIO, source: str) -> None:
    """Write complete UTF-8 editor contents to an open staging file."""
    remaining = memoryview(source.encode("utf-8"))
    while remaining:
        written = handle.write(remaining)
        if written is None or written <= 0:
            raise OSError("staged write did not make progress")
        remaining = remaining[written:]
