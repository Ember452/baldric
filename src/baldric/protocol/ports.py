"""Cross-domain ports consumed by the core.

These are pure ``Protocol`` shapes: a core module names the capability it needs
and the concrete implementation satisfies it structurally, so the core never
imports the platform package for it. Like ``baldric.protocol.extension``, this
module imports nothing from the runtime, agent, ai, or frontend layers.

Ports are added only when a real consumer exists — every port here is exercised
by production code today (:class:`ProviderCatalog`/:class:`EffectiveProviderView`
by the local-backend registry). Two intended-contract-first ports defined early
in the rearchitecture (``HookDispatcher``, ``FeatureSetup``) were removed as
zero-consumer speculation: the core→platform break landed as the composition
root (``runtime/app.py``) instead of port injection, and uniform feature
teardown is carried by the ``session_shutdown`` lifecycle event plus
``ExtensionRuntime.retire()``. Re-introduce a port only against a real caller;
see the structural plan §0.2.
"""

from __future__ import annotations

from typing import Protocol

from baldric.protocol.provider import ProviderLayerToken


class EffectiveProviderView(Protocol):
    """The one field the local-backend registry reads from an effective provider.

    The backend registry only needs the effective provider's ``layer_token`` to
    confirm a backend is paired with the still-current provider layer; it never
    touches the provider definition itself. Typing it as this narrow port keeps
    the backend registry from importing the concrete provider registry shape.
    """

    @property
    def layer_token(self) -> ProviderLayerToken | None:
        """Return the effective provider's layer token, or ``None`` for a static provider."""
        ...


class ProviderCatalog(Protocol):
    """What the local-backend registry needs from the provider registry.

    Captures exactly the members ``LocalBackendRegistry`` uses: the generation
    identity it binds to, plus the layer-token and effective-provider lookups it
    pairs backends against. The concrete ``DynamicProviderRegistry`` satisfies
    this structurally, so the backend registry can depend on the protocol and no
    longer import ``baldric.runtime.platform.provider_registry``.
    """

    @property
    def generation_id(self) -> str:
        """Return this registry generation's stable identity."""
        ...

    def layer_token(self, provider_id: str, source_id: str) -> ProviderLayerToken | None:
        """Return the layer token for one provider published by one source, if any."""
        ...

    def effective(self, provider_id: str) -> EffectiveProviderView | None:
        """Return the effective definition for one provider id, if any."""
        ...


__all__ = [
    "EffectiveProviderView",
    "ProviderCatalog",
]
