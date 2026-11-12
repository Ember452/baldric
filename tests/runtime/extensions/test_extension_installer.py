from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from baldric.runtime.context.resources import BaldricResourcePaths
from baldric.runtime.platform import discover_extensions
from baldric.runtime.platform.installer import (
    EXTENSION_REGISTRY_CORRUPT_SUFFIX,
    ExtensionInstallError,
    install_extension,
    parse_git_extension_source,
    read_extension_registry,
    registry_path,
    remove_extension,
    update_extension,
)


def test_install_local_extension_file_is_discovered(tmp_path: Path) -> None:
    source = tmp_path / "hello.py"
    source.write_text("def setup(baldric):\n    pass\n", encoding="utf-8")
    extensions_dir = tmp_path / "home" / "extensions"

    destination = install_extension(str(source), extensions_dir=extensions_dir)

    assert destination == extensions_dir / "hello.py"
    paths = BaldricResourcePaths(root=tmp_path / "home", cwd=tmp_path)
    discovered, diagnostics = discover_extensions(paths)
    assert [entry.name for entry in discovered] == ["hello"]
    assert diagnostics == ()


def test_install_local_package_copies_manifest_layout(tmp_path: Path) -> None:
    source = tmp_path / "my-extension"
    entry = source / "src" / "my_extension" / "extension.py"
    entry.parent.mkdir(parents=True)
    entry.write_text("from . import helper\n\ndef setup(baldric):\n    pass\n", encoding="utf-8")
    (entry.parent / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (source / "pyproject.toml").write_text(
        '[tool.baldric]\nextensions = ["src/my_extension/extension.py"]\n',
        encoding="utf-8",
    )
    extensions_dir = tmp_path / "home" / "extensions"

    destination = install_extension(str(source), extensions_dir=extensions_dir)

    assert (destination / "src" / "my_extension" / "helper.py").is_file()
    paths = BaldricResourcePaths(root=tmp_path / "home", cwd=tmp_path)
    discovered, diagnostics = discover_extensions(paths)
    assert [item.name for item in discovered] == ["my_extension"]
    assert diagnostics == ()


@pytest.mark.parametrize("nested_entry", ["one.py", "nested/extension.py"])
def test_install_rejects_directory_that_would_not_be_auto_discovered(
    tmp_path: Path, nested_entry: str
) -> None:
    source = tmp_path / "nested-only"
    entry = source / nested_entry
    entry.parent.mkdir(parents=True)
    entry.write_text("def setup(baldric):\n    pass\n", encoding="utf-8")

    with pytest.raises(ExtensionInstallError, match="extension.py"):
        install_extension(str(source), extensions_dir=tmp_path / "extensions")


def test_install_preserves_existing_extension_without_force(tmp_path: Path) -> None:
    source = tmp_path / "hello.py"
    source.write_text("new\n", encoding="utf-8")
    extensions_dir = tmp_path / "extensions"
    extensions_dir.mkdir()
    installed = extensions_dir / "hello.py"
    installed.write_text("old\n", encoding="utf-8")

    with pytest.raises(ExtensionInstallError, match="already installed"):
        install_extension(str(source), extensions_dir=extensions_dir)

    assert installed.read_text(encoding="utf-8") == "old\n"


def test_install_force_replaces_existing_extension(tmp_path: Path) -> None:
    source = tmp_path / "hello.py"
    source.write_text("new\n", encoding="utf-8")
    extensions_dir = tmp_path / "extensions"
    extensions_dir.mkdir()
    installed = extensions_dir / "hello.py"
    installed.write_text("old\n", encoding="utf-8")

    destination = install_extension(str(source), extensions_dir=extensions_dir, force=True)

    assert destination.read_text(encoding="utf-8") == "new\n"
    assert not (extensions_dir / ".hello.py.backup").exists()


@pytest.mark.parametrize(
    ("source", "url", "ref", "name"),
    [
        (
            "git:github.com/rian-dolphin/baldric-subagents@v1.2.0",
            "https://github.com/rian-dolphin/baldric-subagents",
            "v1.2.0",
            "baldric-subagents",
        ),
        (
            "https://github.com/rian-dolphin/baldric-subagents.git",
            "https://github.com/rian-dolphin/baldric-subagents.git",
            None,
            "baldric-subagents",
        ),
        (
            "git:git@github.com:rian-dolphin/baldric-subagents.git@abc123",
            "git@github.com:rian-dolphin/baldric-subagents.git",
            "abc123",
            "baldric-subagents",
        ),
    ],
)
def test_parse_git_extension_source(source: str, url: str, ref: str | None, name: str) -> None:
    parsed = parse_git_extension_source(source)

    assert (parsed.url, parsed.ref, parsed.name) == (url, ref, name)


def test_missing_git_is_reported_as_install_error(tmp_path: Path) -> None:
    def missing_git(
        command: list[str], *, capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess[str]:
        del command, capture_output, text, check
        raise FileNotFoundError("git executable not found")

    with pytest.raises(ExtensionInstallError, match="git executable not found"):
        install_extension(
            "git:github.com/example/baldric-demo",
            extensions_dir=tmp_path / "extensions",
            command_runner=missing_git,
        )


def test_failed_git_install_removes_partial_clone(tmp_path: Path) -> None:
    extensions_dir = tmp_path / "extensions"

    def fake_run(
        command: list[str], *, capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess[str]:
        del capture_output, text, check
        Path(command[-1]).mkdir()
        return subprocess.CompletedProcess(command, 1, "", "network failed")

    with pytest.raises(ExtensionInstallError, match="network failed"):
        install_extension(
            "git:github.com/example/baldric-demo",
            extensions_dir=extensions_dir,
            command_runner=fake_run,
        )

    assert list(extensions_dir.iterdir()) == []


def test_install_git_source_clones_and_checks_out_ref(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        command: list[str], *, capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess[str]:
        del capture_output, text, check
        calls.append(command)
        if command[1] == "clone":
            destination = Path(command[-1])
            destination.mkdir()
            (destination / "extension.py").write_text("def setup(baldric):\n    pass\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    destination = install_extension(
        "git:github.com/example/baldric-demo@v1",
        extensions_dir=tmp_path / "extensions",
        command_runner=fake_run,
    )

    assert destination == tmp_path / "extensions" / "baldric-demo"
    assert calls[0][:4] == ["git", "clone", "--", "https://github.com/example/baldric-demo"]
    assert calls[1][0:2] == ["git", "-C"]
    assert Path(calls[1][2]).name == destination.name
    assert calls[1][3:] == ["checkout", "--detach", "v1"]


def _git_fake_run(
    commit: str = "abc123def4567890",
) -> tuple[object, list[list[str]]]:
    calls: list[list[str]] = []

    def fake_run(
        command: list[str], *, capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess[str]:
        del capture_output, text, check
        calls.append(command)
        if command[1] == "clone":
            destination = Path(command[-1])
            destination.mkdir(parents=True)
            (destination / "extension.py").write_text("def setup(baldric):\n    pass\n", encoding="utf-8")
        if command[-1:] == ["HEAD"]:
            return subprocess.CompletedProcess(command, 0, commit, "")
        return subprocess.CompletedProcess(command, 0, "", "")

    return fake_run, calls


def test_install_records_managed_provenance(tmp_path: Path) -> None:
    fake_run, _ = _git_fake_run()
    extensions_dir = tmp_path / "extensions"

    install_extension(
        "git:github.com/example/baldric-demo@v1",
        extensions_dir=extensions_dir,
        command_runner=fake_run,
    )

    records = read_extension_registry(extensions_dir)
    record = records["baldric-demo"]
    assert record.kind == "git"
    assert record.source == "https://github.com/example/baldric-demo"
    assert record.ref == "v1"
    assert record.commit == "abc123def4567890"


def test_local_install_records_source_path(tmp_path: Path) -> None:
    source = tmp_path / "hello.py"
    source.write_text("def setup(baldric):\n    pass\n", encoding="utf-8")
    extensions_dir = tmp_path / "extensions"

    install_extension(str(source), extensions_dir=extensions_dir)

    record = read_extension_registry(extensions_dir)["hello.py"]
    assert record.kind == "local-file"
    assert record.source == str(source.resolve())


def test_registry_write_failure_keeps_previous_registry_readable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first.py"
    first.write_text("def setup(baldric):\n    pass\n", encoding="utf-8")
    second = tmp_path / "second.py"
    second.write_text("def setup(baldric):\n    pass\n", encoding="utf-8")
    extensions_dir = tmp_path / "extensions"
    install_extension(str(first), extensions_dir=extensions_dir)
    registry = registry_path(extensions_dir)
    before = registry.read_text(encoding="utf-8")

    import baldric.runtime.utils.atomic as atomic_utils

    def failing_fsync(descriptor: int) -> None:
        del descriptor
        raise OSError("disk full")

    # The atomic writer fsyncs before replacing, so interrupting the registry
    # write must leave the previous complete registry in place.
    monkeypatch.setattr(atomic_utils.os, "fsync", failing_fsync)

    with pytest.raises(ExtensionInstallError, match="disk full"):
        install_extension(str(second), extensions_dir=extensions_dir)

    assert registry.read_text(encoding="utf-8") == before
    assert list(read_extension_registry(extensions_dir)) == ["first.py"]
    assert list(extensions_dir.glob(f".{registry.name}.*.tmp")) == []


def test_corrupt_registry_is_preserved_as_backup_instead_of_cleared(tmp_path: Path) -> None:
    extensions_dir = tmp_path / "extensions"
    extensions_dir.mkdir()
    registry = registry_path(extensions_dir)
    registry.write_text("{not valid json", encoding="utf-8")

    assert read_extension_registry(extensions_dir) == {}

    backup = registry.with_name(f"{registry.name}{EXTENSION_REGISTRY_CORRUPT_SUFFIX}")
    assert backup.read_text(encoding="utf-8") == "{not valid json"

    # A later successful write must not erase the preserved recovery copy.
    source = tmp_path / "hello.py"
    source.write_text("def setup(baldric):\n    pass\n", encoding="utf-8")
    install_extension(str(source), extensions_dir=extensions_dir)

    assert backup.read_text(encoding="utf-8") == "{not valid json"
    assert list(read_extension_registry(extensions_dir)) == ["hello.py"]


def test_update_refreshes_managed_git_extension(tmp_path: Path) -> None:
    fake_run, calls = _git_fake_run(commit="fedcba0987654321")
    extensions_dir = tmp_path / "extensions"

    install_extension(
        "git:github.com/example/baldric-demo@v1",
        extensions_dir=extensions_dir,
        command_runner=fake_run,
    )
    destination = update_extension("baldric-demo", extensions_dir=extensions_dir, command_runner=fake_run)

    assert destination == extensions_dir / "baldric-demo"
    record = read_extension_registry(extensions_dir)["baldric-demo"]
    assert record.commit == "fedcba0987654321"
    clone_calls = [command for command in calls if command[1] == "clone"]
    assert len(clone_calls) == 2, "update re-clones from the recorded source"


def test_update_rejects_unmanaged_extension(tmp_path: Path) -> None:
    extensions_dir = tmp_path / "extensions"
    extensions_dir.mkdir()
    (extensions_dir / "manual").mkdir()

    with pytest.raises(ExtensionInstallError, match="not managed by Baldric"):
        update_extension("manual", extensions_dir=extensions_dir)


def test_update_rejects_local_source_extension(tmp_path: Path) -> None:
    source = tmp_path / "hello.py"
    source.write_text("def setup(baldric):\n    pass\n", encoding="utf-8")
    extensions_dir = tmp_path / "extensions"

    install_extension(str(source), extensions_dir=extensions_dir)

    with pytest.raises(ExtensionInstallError, match="installed from a local source"):
        update_extension("hello.py", extensions_dir=extensions_dir)


def test_update_requires_force_when_local_modifications_exist(tmp_path: Path) -> None:
    state = {"head": "abc123def4567890"}
    fake_run, _ = _git_fake_run(commit="fedcba0987654321")

    def runner(
        command: list[str], *, capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess[str]:
        if command[-1:] == ["HEAD"]:
            return subprocess.CompletedProcess(command, 0, state["head"], "")
        return fake_run(command, capture_output=capture_output, text=text, check=check)

    extensions_dir = tmp_path / "extensions"
    install_extension(
        "git:github.com/example/baldric-demo",
        extensions_dir=extensions_dir,
        command_runner=runner,
    )

    # The installed checkout moved to a different commit than the recorded one:
    # a user local modification that update must not silently discard.
    state["head"] = "9999998888887777"

    with pytest.raises(ExtensionInstallError, match="local modifications"):
        update_extension("baldric-demo", extensions_dir=extensions_dir, command_runner=runner)

    state["head"] = "fedcba0987654321"
    update_extension("baldric-demo", extensions_dir=extensions_dir, force=True, command_runner=runner)
    assert read_extension_registry(extensions_dir)["baldric-demo"].commit == "fedcba0987654321"


def test_remove_deletes_managed_extension_and_record(tmp_path: Path) -> None:
    source = tmp_path / "hello.py"
    source.write_text("def setup(baldric):\n    pass\n", encoding="utf-8")
    extensions_dir = tmp_path / "extensions"

    destination = install_extension(str(source), extensions_dir=extensions_dir)
    removed = remove_extension("hello.py", extensions_dir=extensions_dir)

    assert removed == destination
    assert not destination.exists()
    assert read_extension_registry(extensions_dir) == {}


def test_remove_never_touches_unmanaged_extensions(tmp_path: Path) -> None:
    extensions_dir = tmp_path / "extensions"
    extensions_dir.mkdir()
    manual = extensions_dir / "manual"
    manual.mkdir()

    with pytest.raises(ExtensionInstallError, match="not managed by Baldric"):
        remove_extension("manual", extensions_dir=extensions_dir)

    assert manual.exists()
    assert registry_path(extensions_dir).exists() is False
