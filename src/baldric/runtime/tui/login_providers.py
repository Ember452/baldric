"""Login/logout provider helpers shared by the TUI app and its pickers.

``_logout`` (still in the app) and the login/logout pickers (moved to
``tui/pickers.py``) both need these. They lived in ``tui/app.py``; living here
keeps a single definition and lets both modules import downward without a cycle.
"""

from __future__ import annotations

from collections.abc import Sequence

from baldric.runtime.auth.credentials import FileCredentialStore
from baldric.runtime.auth.registry import oauth_provider_ids
from baldric.runtime.providers.catalog import ProviderCatalogEntry

__all__ = [
    "NO_STORED_CREDENTIALS_MESSAGE",
    "api_key_login_providers",
    "credential_store_has_entry",
    "stored_credential_providers",
    "subscription_login_providers",
]

NO_STORED_CREDENTIALS_MESSAGE = (
    "No stored credentials to remove. /logout only removes credentials saved by /login; "
    "environment variables and providers.json config are unchanged."
)


def api_key_login_providers(
    providers: Sequence[ProviderCatalogEntry],
) -> tuple[ProviderCatalogEntry, ...]:
    return tuple(provider for provider in providers if "api_key" in provider.auth_methods)


def subscription_login_providers(
    providers: Sequence[ProviderCatalogEntry],
) -> tuple[ProviderCatalogEntry, ...]:
    provider_ids = oauth_provider_ids()
    return tuple(provider for provider in providers if provider.name in provider_ids)


def credential_store_has_entry(
    credential_store: FileCredentialStore,
    credential_name: str,
) -> bool:
    return (
        credential_store.get(credential_name) is not None
        or credential_store.get_oauth(credential_name) is not None
    )


def stored_credential_providers(
    providers: Sequence[ProviderCatalogEntry],
) -> tuple[ProviderCatalogEntry, ...]:
    credential_store = FileCredentialStore()
    return tuple(
        provider
        for provider in providers
        if provider.credential_name is not None
        and credential_store_has_entry(credential_store, provider.credential_name)
    )
