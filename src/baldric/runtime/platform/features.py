"""Static declaration of Baldric's bundled product features.

The plan (§6.3) deliberately keeps this a plain static tuple rather than a
registry of three (registration/catalog/usability) tables: with a handful of
features a registry is pure overhead and adds a "registry and catalog disagree"
failure mode. Each feature declares a stable name, a ``kind`` (so a UI can tell
a switchable capability from a backend/integration), and the *string path* to
its ``setup`` entry point.

The string path is load-bearing for S1a: the platform layer loads a feature via
``importlib`` from this path and never imports a feature implementation
statically, so ``core``/``platform``/``frontends`` cannot depend on a feature.

A feature that ships UI (subagents) statically imports Baldric's own TUI
frontend modules — ``frontends.tui.config`` / ``.state`` / ``.widgets`` — from
its ``ui`` subpackage. This is the one documented exception to "features do not
depend on frontends", machine-checked as a narrow AllowRule in
``scripts/check_import_graph.py`` (any other features->frontends import is a
violation); the *host wiring* still goes through the ``ComponentBridge``
protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FeatureKind = Literal["capability", "integration", "backend"]


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    """One bundled product feature's declaration.

    ``setup`` is a ``"module:attr"`` string path resolved by ``importlib`` (never
    a static import). ``kind`` distinguishes user-facing capabilities from
    backends/integrations so a frontend does not present a backend as a
    toggleable feature. There is intentionally no ``order`` field: integer order
    degenerates as the feature count grows and nothing depends on hook order yet.
    """

    name: str
    kind: FeatureKind
    setup: str


FEATURES: tuple[FeatureSpec, ...] = (
    FeatureSpec(name="mcp_tools", kind="integration", setup="baldric.runtime.features.mcp_tools:setup"),
    FeatureSpec(
        name="subagents",
        kind="capability",
        setup="baldric.runtime.features.subagents.extension:setup",
    ),
    FeatureSpec(name="llama_cpp", kind="backend", setup="baldric.runtime.features.llama_cpp:setup"),
)

__all__ = [
    "FEATURES",
    "FeatureKind",
    "FeatureSpec",
]
