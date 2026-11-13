import logging
from pathlib import Path
from stat import S_IMODE

import pytest

from baldric.runtime.providers.auth.credentials import (
    CredentialStoreError,
    FileCredentialStore,
    OAuthCredential,
)


def test_file_credential_store_round_trips_and_sets_private_permissions(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    store = FileCredentialStore(path)

    store.set("openai", "test-key")

    assert store.get("openai") == "test-key"
    assert S_IMODE(path.stat().st_mode) == 0o600


def test_file_credential_store_deletes_key(tmp_path) -> None:
    store = FileCredentialStore(tmp_path / "credentials.json")
    store.set("openai", "test-key")

    store.delete("openai")

    assert store.get("openai") is None


def test_file_credential_store_rejects_empty_values(tmp_path) -> None:
    store = FileCredentialStore(tmp_path / "credentials.json")

    with pytest.raises(CredentialStoreError, match="must not be empty"):
        store.set("openai", "")


def test_file_credential_store_round_trips_oauth_credentials(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    store = FileCredentialStore(path)
    credential = OAuthCredential(
        access="access-token",
        refresh="refresh-token",
        expires=123456,
        account_id="account-1",
    )

    store.set_oauth("openai-codex", credential)

    assert store.get("openai-codex") is None
    assert store.get_oauth("openai-codex") == credential
    assert '"type": "oauth"' in path.read_text(encoding="utf-8")


def test_baldric_home_isolates_default_oauth_credential_stores(monkeypatch, tmp_path) -> None:
    personal_home = tmp_path / ".baldric-personal"
    work_home = tmp_path / ".baldric-work"
    personal = OAuthCredential(access="personal", refresh="personal-refresh", expires=123456)
    work = OAuthCredential(access="work", refresh="work-refresh", expires=123456)

    monkeypatch.setenv("BALDRIC_HOME", str(personal_home))
    FileCredentialStore().set_oauth("anthropic", personal)
    monkeypatch.setenv("BALDRIC_HOME", str(work_home))
    FileCredentialStore().set_oauth("anthropic", work)

    assert FileCredentialStore().get_oauth("anthropic") == work
    monkeypatch.setenv("BALDRIC_HOME", str(personal_home))
    assert FileCredentialStore().get_oauth("anthropic") == personal
    assert not (tmp_path / ".baldric" / "credentials.json").exists()


def test_file_credential_store_round_trips_extensible_oauth_metadata(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    store = FileCredentialStore(path)
    credential = OAuthCredential(
        access="copilot-access",
        refresh="github-token",
        expires=123456,
        metadata={
            "enterprise_domain": "ghe.example.com",
            "available_model_ids": ["gpt-5.4", "claude-sonnet-4.6"],
        },
    )

    store.set_oauth("github-copilot", credential)

    assert store.get_oauth("github-copilot") == credential
    assert '"account_id"' not in path.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".credentials.json.*"))


def test_file_credential_store_loads_legacy_codex_oauth_shape(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    path.write_text(
        '{"openai-codex":{"type":"oauth","access":"a","refresh":"r","expires":123,"account_id":"account"}}',
        encoding="utf-8",
    )

    credential = FileCredentialStore(path).get_oauth("openai-codex")

    assert credential == OAuthCredential(
        access="a",
        refresh="r",
        expires=123,
        account_id="account",
    )


def test_corrupt_credentials_file_is_quarantined_and_store_starts_empty(
    tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "credentials.json"
    path.write_text('{"openai": "trunca', encoding="utf-8")
    store = FileCredentialStore(path)

    with caplog.at_level(logging.WARNING):
        assert store.get("openai") is None

    assert store.names() == ()
    assert Path(str(path) + ".corrupt").read_text(encoding="utf-8") == '{"openai": "trunca'
    assert not path.exists()
    assert "credentials.json" in caplog.text

    store.set("openai", "new-key")
    assert store.get("openai") == "new-key"


def test_credential_save_fsyncs_before_replace(tmp_path, monkeypatch) -> None:
    import baldric.runtime.utils.atomic as atomic_module

    order: list[str] = []
    real_fsync = atomic_module.os.fsync
    real_replace = atomic_module.os.replace
    monkeypatch.setattr(atomic_module.os, "fsync", lambda fd: (order.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(
        atomic_module.os, "replace", lambda src, dst: (order.append("replace"), real_replace(src, dst))[1]
    )
    store = FileCredentialStore(tmp_path / "credentials.json")

    store.set("openai", "test-key")

    assert order == ["fsync", "replace"]
