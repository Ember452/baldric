"""Install Baldric extensions from local paths or Git repositories."""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import mkdtemp
from typing import Literal

from baldric.runtime.config.paths import BaldricPaths
from baldric.runtime.context.resources import BaldricResourcePaths
from baldric.runtime.extensions import discover_extensions
from baldric.runtime.utils.atomic import atomic_write_text

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]

EXTENSION_REGISTRY_FILENAME = ".baldric-extensions.json"
# A corrupt registry is copied here before the next write can replace it, so the
# install records are never silently lost to a single unreadable file.
EXTENSION_REGISTRY_CORRUPT_SUFFIX = ".corrupt"


class ExtensionInstallError(RuntimeError):
    """Raised when an extension source cannot be installed safely."""


@dataclass(frozen=True, slots=True)
class GitExtensionSource:
    """A normalized Git repository source and optional checkout ref."""

    url: str
    ref: str | None
    name: str


@dataclass(frozen=True, slots=True)
class ExtensionInstallRecord:
    """Durable provenance for one Baldric-managed extension install.

    The registry distinguishes Baldric-managed directories from coincidentally
    located user files: only managed installs may be updated or removed by
    ``baldric extensions`` commands.
    """

    name: str
    kind: Literal["git", "local-file", "local-dir"]
    source: str
    ref: str | None = None
    commit: str | None = None
    installed_at: int = 0


def registry_path(extensions_dir: Path | None = None) -> Path:
    """Return the durable install-registry path for Baldric-managed extensions."""
    root = extensions_dir or BaldricPaths().user_extensions_dir
    return root / EXTENSION_REGISTRY_FILENAME


def read_extension_registry(extensions_dir: Path | None = None) -> dict[str, ExtensionInstallRecord]:
    """Load the managed-install registry keyed by extension name.

    An unreadable or malformed registry is preserved as a ``.corrupt`` backup
    before returning empty: the host cannot trust the records, but silently
    dropping them and letting the next write replace the file would erase every
    managed install.
    """
    path = registry_path(extensions_dir)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _preserve_corrupt_registry(path)
        return {}
    if not isinstance(raw, dict):
        _preserve_corrupt_registry(path)
        return {}
    records: dict[str, ExtensionInstallRecord] = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict) or not isinstance(name, str):
            continue
        try:
            records[name] = ExtensionInstallRecord(
                name=name,
                kind=entry["kind"],
                source=entry["source"],
                ref=entry.get("ref"),
                commit=entry.get("commit"),
                installed_at=int(entry.get("installed_at", 0)),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return records


def _preserve_corrupt_registry(path: Path) -> None:
    """Copy an unusable registry beside itself for manual recovery."""
    backup = path.with_name(f"{path.name}{EXTENSION_REGISTRY_CORRUPT_SUFFIX}")
    with contextlib.suppress(OSError):
        shutil.copy2(path, backup)


def _write_extension_registry(
    records: dict[str, ExtensionInstallRecord],
    extensions_dir: Path,
) -> None:
    path = registry_path(extensions_dir)
    payload = {name: asdict(record) for name, record in sorted(records.items())}
    atomic_write_text(path, json.dumps(payload, indent=2) + "\n")


def install_extension(
    source: str,
    *,
    force: bool = False,
    extensions_dir: Path | None = None,
    command_runner: CommandRunner = subprocess.run,
) -> Path:
    """Install one extension into Baldric's user extension directory.

    Local Python files are copied. Local package directories and Git
    repositories must expose ``extension.py`` or ``[tool.baldric].extensions`` so
    the normal user-directory discovery path can load them on the next run.
    """
    destination_root = extensions_dir or BaldricPaths().user_extensions_dir
    staging_root: Path | None = None
    try:
        destination_root.mkdir(parents=True, exist_ok=True)
        local_source = Path(source).expanduser()
        resolved_source: Path | None = None
        git_source: GitExtensionSource | None = None
        if local_source.exists():
            resolved_source = local_source.resolve()
            name = _local_install_name(resolved_source)
        else:
            git_source = parse_git_extension_source(source)
            name = git_source.name
        destination = destination_root / name

        # Reproduce the exact <Baldric home>/extensions/<name> shape during validation.
        # This catches layouts that explicit -e discovery accepts but normal
        # user-directory discovery would skip, such as nested/extension.py.
        staging_root = Path(mkdtemp(prefix=".extension-install-", dir=destination_root))
        staging = staging_root / "extensions" / name
        staging.parent.mkdir()
        if resolved_source is not None and resolved_source.is_file():
            shutil.copy2(resolved_source, staging)
        elif resolved_source is not None and resolved_source.is_dir():
            shutil.copytree(resolved_source, staging, ignore=_local_copy_ignore)
        elif git_source is not None:
            _clone_git_source(git_source, staging, command_runner=command_runner)
        else:
            raise ExtensionInstallError(f"unsupported local extension source: {source}")

        _validate_staged_extension(staging_root)
        commit = _staged_git_commit(staging, git_source, command_runner=command_runner)
        _publish_staged_extension(staging, destination, force=force)
        _record_install(
            destination_root,
            name=name,
            resolved_source=resolved_source,
            git_source=git_source,
            commit=commit,
        )
        return destination
    except OSError as exc:
        raise ExtensionInstallError(f"extension installation failed: {exc}") from exc
    finally:
        if staging_root is not None:
            with contextlib.suppress(OSError):
                _remove_path(staging_root)


def _staged_git_commit(
    staging: Path,
    git_source: GitExtensionSource | None,
    *,
    command_runner: CommandRunner,
) -> str | None:
    if git_source is None:
        return None
    result = command_runner(
        ["git", "-C", str(staging), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _record_install(
    extensions_dir: Path,
    *,
    name: str,
    resolved_source: Path | None,
    git_source: GitExtensionSource | None,
    commit: str | None,
) -> None:
    records = read_extension_registry(extensions_dir)
    if git_source is not None:
        record = ExtensionInstallRecord(
            name=name,
            kind="git",
            source=git_source.url,
            ref=git_source.ref,
            commit=commit,
            installed_at=int(time.time() * 1000),
        )
    elif resolved_source is not None and resolved_source.is_file():
        record = ExtensionInstallRecord(
            name=name,
            kind="local-file",
            source=str(resolved_source),
            installed_at=int(time.time() * 1000),
        )
    else:
        record = ExtensionInstallRecord(
            name=name,
            kind="local-dir",
            source=str(resolved_source) if resolved_source is not None else name,
            installed_at=int(time.time() * 1000),
        )
    records[name] = record
    _write_extension_registry(records, extensions_dir)


def update_extension(
    name: str,
    *,
    force: bool = False,
    extensions_dir: Path | None = None,
    command_runner: CommandRunner = subprocess.run,
) -> Path:
    """Refresh one Baldric-managed Git extension from its recorded source.

    Local modifications (the installed checkout differs from the recorded
    commit) require ``--force`` so user work is never silently replaced.
    """
    destination_root = extensions_dir or BaldricPaths().user_extensions_dir
    records = read_extension_registry(destination_root)
    record = records.get(name)
    if record is None:
        raise ExtensionInstallError(
            f"extension {name!r} is not managed by Baldric; only installed extensions can be updated"
        )
    if record.kind != "git":
        raise ExtensionInstallError(
            f"extension {name!r} was installed from a local source; reinstall it instead"
        )
    destination = destination_root / name
    if not destination.exists():
        raise ExtensionInstallError(f"extension {name!r} is registered but missing on disk")
    if record.commit is not None and not force:
        result = command_runner(
            ["git", "-C", str(destination), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        current_commit = result.stdout.strip() if result.returncode == 0 else None
        if current_commit is not None and current_commit != record.commit:
            raise ExtensionInstallError(
                f"extension {name!r} has local modifications; pass --force to discard them"
            )
    return install_extension(
        _git_source_string(record),
        force=True,
        extensions_dir=destination_root,
        command_runner=command_runner,
    )


def _git_source_string(record: ExtensionInstallRecord) -> str:
    source = record.source
    if source.startswith(("https://", "http://", "ssh://", "git://", "file://")):
        source = source.removeprefix("https://")
    if record.ref:
        return f"git:{source}@{record.ref}"
    return f"git:{source}"


def remove_extension(
    name: str,
    *,
    extensions_dir: Path | None = None,
) -> Path:
    """Remove one Baldric-managed extension and its registry record.

    Unmanaged directories (manual, project, or explicit-path extensions) are
    never touched: Baldric does not claim ownership of files it did not install.
    """
    destination_root = extensions_dir or BaldricPaths().user_extensions_dir
    records = read_extension_registry(destination_root)
    record = records.get(name)
    if record is None:
        raise ExtensionInstallError(
            f"extension {name!r} is not managed by Baldric; remove it manually if you own it"
        )
    destination = destination_root / name
    if destination.exists() or destination.is_symlink():
        _remove_path(destination)
    del records[name]
    _write_extension_registry(records, destination_root)
    return destination


def parse_git_extension_source(source: str) -> GitExtensionSource:
    """Normalize a Pi-style Git source accepted by ``baldric install``."""
    raw = source[4:] if source.startswith("git:") else source
    if not raw:
        raise ExtensionInstallError("Git extension source is empty")

    ref: str | None = None
    last_at = raw.rfind("@")
    last_separator = max(raw.rfind("/"), raw.rfind(":"))
    if last_at > last_separator:
        raw, ref = raw[:last_at], raw[last_at + 1 :]
        if not ref:
            raise ExtensionInstallError("Git extension ref is empty")

    if raw.startswith("github.com/"):
        url = f"https://{raw}"
    elif raw.startswith(("https://", "http://", "ssh://", "git://", "file://", "git@")):
        url = raw
    else:
        raise ExtensionInstallError(
            "extension source does not exist locally and is not a supported Git source; "
            "use a local path, git:github.com/owner/repo, or a Git URL"
        )

    repository_path = raw.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    name = repository_path.removesuffix(".git")
    _validate_install_name(name)
    return GitExtensionSource(url=url, ref=ref, name=name)


def _clone_git_source(
    source: GitExtensionSource,
    destination: Path,
    *,
    command_runner: CommandRunner,
) -> None:
    result = command_runner(
        ["git", "clone", "--", source.url, str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "git clone failed").strip()
        raise ExtensionInstallError(f"could not clone {source.url}: {detail}")
    if source.ref is None:
        return
    result = command_runner(
        ["git", "-C", str(destination), "checkout", "--detach", source.ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "git checkout failed").strip()
        raise ExtensionInstallError(f"could not check out ref {source.ref!r}: {detail}")


def _local_install_name(source: Path) -> str:
    if source.is_file() and source.suffix != ".py":
        raise ExtensionInstallError("a local extension file must have a .py suffix")
    name = source.name
    _validate_install_name(name)
    return name


def _validate_install_name(name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name) or name in {".", ".."}:
        raise ExtensionInstallError(f"extension source has an unsupported install name: {name!r}")


def _validate_staged_extension(staging_root: Path) -> None:
    paths = BaldricResourcePaths(root=staging_root, cwd=Path.cwd())
    discovered, diagnostics = discover_extensions(paths)
    errors = [diagnostic.message for diagnostic in diagnostics if diagnostic.severity == "error"]
    if errors:
        raise ExtensionInstallError("invalid extension package: " + "; ".join(errors))
    if not discovered:
        raise ExtensionInstallError(
            "an extension directory must contain extension.py or declare "
            "[tool.baldric].extensions in pyproject.toml"
        )


def _publish_staged_extension(staging: Path, destination: Path, *, force: bool) -> None:
    if destination.exists() or destination.is_symlink():
        if not force:
            raise ExtensionInstallError(
                f"extension is already installed at {destination}; pass --force to replace it"
            )
        backup = destination.with_name(f".{destination.name}.backup")
        _remove_path(backup)
        destination.replace(backup)
        try:
            staging.replace(destination)
        except BaseException:
            backup.replace(destination)
            raise
        _remove_path(backup)
        return
    staging.replace(destination)


def _local_copy_ignore(_directory: str, names: Sequence[str]) -> set[str]:
    ignored = {".git", ".hg", ".svn", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
    return ignored.intersection(names)


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)
