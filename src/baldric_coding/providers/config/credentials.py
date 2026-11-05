"""Durable provider configuration for Baldric coding sessions."""

from __future__ import annotations

from typing import Any

from baldric_coding.auth.registry import get_oauth_provider
from baldric_coding.providers.config.models import CredentialReader, ProviderConfig


def _provider_config_module() -> Any:
    import baldric_coding.providers.config as provider_config

    return provider_config


def provider_has_usable_credentials(
    provider: ProviderConfig,
    *,
    credential_reader: CredentialReader | None = None,
) -> bool:
    """Return whether Baldric can attempt calls for this provider without prompting setup."""
    if provider.credential_name and credential_reader is not None:
        get_oauth = getattr(credential_reader, "get_oauth", None)
        if (
            get_oauth_provider(provider.name) is not None
            and get_oauth is not None
            and get_oauth(provider.credential_name) is not None
        ):
            return True
        if credential_reader.get(provider.credential_name):
            return True
    return bool(_provider_config_module().environ.get(provider.api_key_env))


def _api_key_from_provider(
    provider: ProviderConfig,
    *,
    credential_reader: CredentialReader | None,
) -> str:
    if provider.credential_name and credential_reader is not None:
        credential = credential_reader.get(provider.credential_name)
        if credential:
            return credential
        get_oauth = getattr(credential_reader, "get_oauth", None)
        if get_oauth_provider(provider.name) is not None and get_oauth is not None:
            oauth_credential = get_oauth(provider.credential_name)
            if oauth_credential is not None:
                access = getattr(oauth_credential, "access", None)
                if isinstance(access, str) and access:
                    return access

    api_key = _provider_config_module().environ.get(provider.api_key_env)
    if isinstance(api_key, str) and api_key:
        return api_key
    credential_hint = f" or run /login {provider.name}" if provider.credential_name else ""
    raise RuntimeError(f"Missing provider API key. Set {provider.api_key_env}{credential_hint}.")
