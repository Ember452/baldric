"""Cross-domain ports used to break ``core -> platform`` hard dependencies.

These are pure ``Protocol`` shapes: they name the capabilities a core module may
rely on so the concrete implementation can be injected at the composition root
(``runtime/app.py``, built in a later stage) instead of imported directly. Like
``baldric.protocol.extension``, this module imports nothing from the runtime,
agent, ai, or frontend layers.

This stage defines only the ports that are unambiguous today:

* :class:`HookDispatcher` — what a session needs from the extension runtime to
  fire a lifecycle hook and run a ``user_bash`` command itself. It depends only
  on :class:`~baldric.protocol.extension.UserBashEvent`, which is already a
  protocol shape.
* :class:`FeatureSetup` — the symmetric setup/teardown contract every product
  feature will follow. It returns an optional disposer so a feature's teardown
  is uniform instead of each feature inventing its own shutdown path.

The provider-catalog and session-lifecycle ports are deliberately **not**
defined yet: their return types (a provider record, a rebindable lifecycle) do
not have a stable shape until the provider domain and session facade are
extracted (stages D and H). Defining them now would invent types that do not
exist. See ``docs/internal/plans/2026-11-12-structural-rearchitecture.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from baldric.protocol.extension import UserBashEvent


class HookDispatcher(Protocol):
    """What a session core needs from the extension runtime, exactly.

    The session fires lifecycle events and answers ``user_bash`` through this
    port; it never imports the concrete ``ExtensionRuntime``.
    """

    async def dispatch(self, event: object) -> object | None:
        """Dispatch one extension event and return a handler result, if any."""
        ...

    def run_user_bash(self, event: UserBashEvent) -> object:
        """Run a ``user_bash`` command through the extension hooks."""
        ...


class FeatureSetup(Protocol):
    """The symmetric setup/teardown contract for one product feature.

    A feature's ``setup`` receives the live ``ExtensionAPI`` (the behaviour class
    that lives in the runtime the platform package — deliberately *not* imported
    here, because protocol must not depend on an upper layer; the parameter is
    typed as ``object`` so the port stays a pure shape while callers pass the
    real API) and returns either a teardown disposer or ``None`` when it
    registered nothing to tear down. The composition root calls every returned
    disposer at session end, so teardown is uniform across features instead of
    each feature inventing its own close path (``register_key_interceptor``
    already returns a disposer — this makes that the contract, not an exception).
    """

    def __call__(self, api: object) -> Callable[[], None] | None:
        """Register the feature against the live extension API; return a teardown or ``None``."""
        ...


__all__ = [
    "FeatureSetup",
    "HookDispatcher",
]
