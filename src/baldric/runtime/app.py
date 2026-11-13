"""Composition root: build the platform runtime a session needs.

This module is the single place in the core that *constructs* the concrete
``ExtensionRuntime``: ``CodingSession.load``, the reload/rebind lifecycle, and
the bare-session fallback all ask these factories instead of constructing the
platform class themselves. Stage F moved *where the runtime is built* to the
composition root; it did not remove every runtime import from session — the
session still statically imports platform contracts for the event and provider
types it consumes (``UserBashEvent``, ``DynamicProvider``, ...). See the
structural plan §0.2 for the precise scope of the inversion.

Two entry points, matching the two construction contexts that existed inline
before:

* :func:`prepare_runtime_for_load` — the fresh runtime staged inside
  ``CodingSession.load`` from the session config plus the previous runtime (carry
  credentials/environment across a destination snapshot). It performs the first,
  resource-dir-only ``load``; the caller runs project-trust resolution and then
  the project-dir ``load`` itself, because that stays interleaved with session
  staging.
* :func:`stage_runtime_for_reload` — the replacement runtime staged by the
  reload/rebind lifecycle from a live session (carry its credentials, environment,
  UI bridge, and paths).

Behaviour is byte-for-byte the same as the inline blocks these replace; the tests
that cover resume/branch/reload/replacement are the regression guard.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import baldric.runtime.platform.builtin_registry as built_in_extension_registry
from baldric.runtime.config.paths import BaldricPaths
from baldric.runtime.context.resources import BaldricResourcePaths, resource_paths_with_cwd
from baldric.runtime.platform.builtin_registry import BuiltInExtension
from baldric.runtime.platform.runtime import ExtensionRuntime
from baldric.runtime.providers.auth.credentials import (
    CredentialStore,
    FileCredentialStore,
    credentials_path,
)
from baldric.runtime.providers.config.models import CredentialReader, ProviderConfig

if TYPE_CHECKING:
    import httpx

    from baldric.runtime.session.session import CodingSessionConfig


@dataclass(frozen=True, slots=True)
class PreparedRuntime:
    """A runtime staged for ``CodingSession.load`` plus the paths it was built on.

    ``load`` needs ``runtime_paths`` / ``credential_store`` / ``unfiltered_resource_paths``
    after the runtime is built (for codex catalog lookup and provider prep), so
    the factory returns them alongside the runtime instead of recomputing.
    """

    extension_runtime: ExtensionRuntime
    runtime_paths: BaldricPaths
    credential_store: FileCredentialStore
    unfiltered_resource_paths: BaldricResourcePaths


def eligible_built_in_extensions(
    config: CodingSessionConfig,
) -> tuple[BuiltInExtension, ...] | None:
    """Filter the built-in registry by the session's disabled set.

    ``None`` keeps the runtime's default registry, so sessions that disable
    nothing behave exactly as before; an explicit tuple makes the exclusion
    real — a disabled built-in never runs its setup. The registry is read through
    its module (not a copied name) so this filter always sees the same registry
    the runtime loader reads.
    """
    if not config.disabled_built_in_extensions:
        return None
    return tuple(
        built_in
        for built_in in built_in_extension_registry.BUILT_IN_EXTENSIONS
        if built_in.name not in config.disabled_built_in_extensions
    )


def _default_runtime_paths(unfiltered_resource_paths: BaldricResourcePaths) -> BaldricPaths:
    """Derive the runtime paths from a resource-path snapshot (or sensible default)."""
    if unfiltered_resource_paths.paths:
        return unfiltered_resource_paths.paths
    return BaldricPaths(
        home=unfiltered_resource_paths.root,
        agents_home=unfiltered_resource_paths.agents_root or Path.home() / ".agents",
    )


def build_runtime() -> ExtensionRuntime:
    """Build a bare runtime for a session constructed outside ``load``.

    Mirrors the old ``ExtensionRuntime()`` fallback in ``CodingSession.__init__``;
    keeping it here means the core module never imports the platform class at
    runtime.
    """
    return ExtensionRuntime()


def prepare_runtime_for_load(
    config: CodingSessionConfig,
    previous_runtime: ExtensionRuntime | None,
) -> PreparedRuntime:
    """Build and first-load the fresh runtime for ``CodingSession.load``.

    Mirrors the inline staging previously in ``CodingSession.load``: a runtime is
    cwd-bound, so always stage a fresh eligible-only runtime for a destination
    snapshot; never reuse source-project code across a replacement trust
    boundary. Project-dir extensions are loaded later by the caller, after trust
    resolution.
    """
    unfiltered_resource_paths = resource_paths_with_cwd(config.resource_paths, config.cwd)
    runtime_paths = _default_runtime_paths(unfiltered_resource_paths)
    credential_store = FileCredentialStore(credentials_path(runtime_paths))
    injected_credentials = previous_runtime.provider_credentials if previous_runtime is not None else None
    extension_runtime = ExtensionRuntime(
        paths=runtime_paths,
        credentials=injected_credentials or credential_store,
        environment=(previous_runtime.provider_environment if previous_runtime is not None else None),
        built_in_credentials=(
            previous_runtime.built_in_credentials if previous_runtime is not None else None
        ),
        built_in_http_client=(
            previous_runtime.built_in_http_client if previous_runtime is not None else None
        ),
        durable_providers=(config.provider_settings.providers if config.provider_settings else ()),
        built_in_extensions=eligible_built_in_extensions(config),
    )
    extension_runtime.load(
        unfiltered_resource_paths,
        extra_paths=config.extension_paths,
        include_resource_dirs=config.extensions_enabled,
        include_project_dir=False,
    )
    return PreparedRuntime(
        extension_runtime=extension_runtime,
        runtime_paths=runtime_paths,
        credential_store=credential_store,
        unfiltered_resource_paths=unfiltered_resource_paths,
    )


def stage_runtime_for_reload(
    *,
    durable_providers: Sequence[ProviderConfig],
    credentials: CredentialReader,
    environment: Mapping[str, str] | None,
    built_in_credentials: CredentialStore,
    built_in_http_client: httpx.AsyncClient | None,
    built_in_extensions: tuple[BuiltInExtension, ...] | None,
    runtime_paths: BaldricPaths,
    unfiltered_resource_paths: BaldricResourcePaths,
    extra_paths: tuple[Path, ...],
    extensions_enabled: bool,
) -> ExtensionRuntime:
    """Build and first-load the replacement runtime for reload/rebind.

    Mirrors the inline staging in the session lifecycle: carry the live session's
    credentials, environment, built-in context, and paths into a fresh runtime,
    then load eligible extensions (project extensions excluded). ``built_in_extensions``
    carries the session's disabled-built-in filter; passing ``None`` would load
    the full registry and silently re-enable a capability the session disabled.
    """
    staged_runtime = ExtensionRuntime(
        durable_providers=durable_providers,
        credentials=credentials,
        environment=environment,
        built_in_credentials=built_in_credentials,
        built_in_http_client=built_in_http_client,
        built_in_extensions=built_in_extensions,
        paths=runtime_paths,
    )
    staged_runtime.load(
        unfiltered_resource_paths,
        extra_paths=extra_paths,
        include_resource_dirs=extensions_enabled,
        include_project_dir=False,
    )
    return staged_runtime


__all__ = [
    "PreparedRuntime",
    "build_runtime",
    "eligible_built_in_extensions",
    "prepare_runtime_for_load",
    "stage_runtime_for_reload",
]
