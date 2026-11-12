"""Trusted built-in llama.cpp local backend."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from baldric.runtime.config.paths import BaldricPaths
from baldric.runtime.platform.builtin_registry import BuiltInExtensionContext
from baldric.runtime.providers.auth.credentials import FileCredentialStore, credentials_path

from .router import LLAMA_CPP_ROUTER_MAX_BUILD, LLAMA_CPP_ROUTER_MIN_BUILD
from .service import (
    DEFAULT_LLAMA_CPP_TIMEOUT_SECONDS,
    LLAMA_CPP_API_KEY_ENV,
    LLAMA_CPP_BACKEND_ID,
    LLAMA_CPP_DEFAULT_ENDPOINT,
    LLAMA_CPP_DISPLAY_NAME,
    LLAMA_CPP_ENDPOINT_ENV,
    LLAMA_CPP_PROVIDER_ID,
    LlamaCppDiscovery,
    LlamaCppEndpoint,
    LlamaCppEndpointError,
    LlamaCppError,
    LlamaCppService,
    normalize_llama_cpp_endpoint,
)
from .state import (
    LLAMA_CPP_CREDENTIAL_PREFIX,
    LLAMA_CPP_STATE_SCHEMA_VERSION,
    LlamaCppIntegrationState,
    LlamaCppStateError,
    LlamaCppStateStore,
    LlamaCppStoredModel,
)

if TYPE_CHECKING:
    from baldric.runtime.platform.api import ExtensionAPI


def setup(
    baldric: ExtensionAPI,
    context: BuiltInExtensionContext | None = None,
) -> None:
    """Register the trusted provider and provider-neutral local backend."""
    dependencies = context or BuiltInExtensionContext(
        paths=BaldricPaths(),
        credential_store=FileCredentialStore(credentials_path(BaldricPaths())),
        environment=dict(os.environ),
    )
    service = LlamaCppService(
        state_store=LlamaCppStateStore(paths=dependencies.paths),
        credential_store=dependencies.credential_store,
        environment=dependencies.environment,
        client=dependencies.http_client,
        register_provider=baldric.register_provider,
        update_provider=baldric.update_provider,
        register_backend=baldric.register_local_backend,
    )
    baldric.register_provider(service.provider())
    baldric.register_local_backend(service.backend())


__all__ = [
    "DEFAULT_LLAMA_CPP_TIMEOUT_SECONDS",
    "LLAMA_CPP_API_KEY_ENV",
    "LLAMA_CPP_CREDENTIAL_PREFIX",
    "LLAMA_CPP_BACKEND_ID",
    "LLAMA_CPP_DEFAULT_ENDPOINT",
    "LLAMA_CPP_DISPLAY_NAME",
    "LLAMA_CPP_ENDPOINT_ENV",
    "LLAMA_CPP_PROVIDER_ID",
    "LLAMA_CPP_ROUTER_MAX_BUILD",
    "LLAMA_CPP_ROUTER_MIN_BUILD",
    "LLAMA_CPP_STATE_SCHEMA_VERSION",
    "LlamaCppDiscovery",
    "LlamaCppEndpoint",
    "LlamaCppEndpointError",
    "LlamaCppError",
    "LlamaCppIntegrationState",
    "LlamaCppService",
    "LlamaCppStateError",
    "LlamaCppStateStore",
    "LlamaCppStoredModel",
    "normalize_llama_cpp_endpoint",
    "setup",
]
