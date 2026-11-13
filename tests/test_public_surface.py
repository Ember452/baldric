"""Contract tests for the public surfaces.

Two surfaces are pinned here:

* ``baldric.api`` — the stable facade extension authors import. It is frozen by
  name so a split refactor cannot silently drop an export (the
  ``EXTENSION_API_VERSION`` contract governs changes to it).
* ``baldric.runtime`` — deliberately *not* a facade any more. It exports only the
  package version, so a bare ``import baldric.runtime`` stays cheap; the eager
  139-name aggregate (which pulled 156 application modules) was replaced by
  per-submodule imports. The test asserts both the tiny ``__all__`` and the
  absence of an eager import, so the aggregate cannot creep back.
"""

from __future__ import annotations

import os
import subprocess
import sys

import baldric.api
import baldric.runtime

EXPECTED_API = (
    "AGENT_EVENT_TYPES",
    "AGENT_EVENT_WILDCARD",
    "CompactionSummaryResult",
    "ComponentBridge",
    "CustomEntryView",
    "CustomMessageMarkup",
    "CustomMessageView",
    "DeliverAs",
    "EVENT_NAME_ALIASES",
    "EXTENSION_API_VERSION",
    "EntryRenderer",
    "ExtensionAPI",
    "ExtensionCapabilities",
    "ExtensionCommandContext",
    "ExtensionCommandHandler",
    "ExtensionContext",
    "ExtensionError",
    "ExtensionHandler",
    "ExtensionSidebar",
    "ExtensionUi",
    "InputEvent",
    "InputHookResult",
    "KeyInterceptor",
    "LIFECYCLE_EVENT_TYPES",
    "MainViewFactory",
    "MainViewHandle",
    "MarkdownRenderContext",
    "MarkdownTransformer",
    "MessageRenderOptions",
    "MessageRenderer",
    "NotifyLevel",
    "NullUiBridge",
    "PROVIDER_EVENT_TYPES",
    "Placement",
    "ProviderContextEvent",
    "ProviderHeadersEvent",
    "ProviderRequestEvent",
    "ProviderResponseEvent",
    "ProviderStreamEvent",
    "SessionBeforeCompactEvent",
    "SessionLifecycleReason",
    "SessionShutdownEvent",
    "SessionStartEvent",
    "SidebarContent",
    "SidebarWidgetFactory",
    "SlotWidgetContent",
    "SlotWidgetFactory",
    "StderrUiBridge",
    "ToolCallHookEvent",
    "ToolCallHookResult",
    "ToolCallMarkup",
    "ToolCallResolver",
    "ToolResultHookEvent",
    "ToolResultHookResult",
    "ToolResultMarkup",
    "ToolResultResolver",
    "TurnEndEvent",
    "TurnStartEvent",
    "UiBridge",
    "UserBashEvent",
    "UserBashResult",
)


def test_baldric_api_public_surface_is_frozen() -> None:
    """Pin the explicit ``baldric.api`` facade extension authors import."""
    assert tuple(sorted(baldric.api.__all__)) == EXPECTED_API
    missing = [name for name in baldric.api.__all__ if not hasattr(baldric.api, name)]
    assert missing == [], f"__all__ names with no attribute: {missing}"
    assert len(baldric.api.__all__) == len(EXPECTED_API)


def test_runtime_root_exports_only_the_version() -> None:
    """``baldric.runtime`` is not a facade: only the package version lives there."""
    assert baldric.runtime.__all__ == ["__version__"]
    assert isinstance(baldric.runtime.__version__, str)


def test_importing_runtime_root_does_not_pull_the_application() -> None:
    """A bare ``import baldric.runtime`` must not load the app's heavy modules.

    Regression guard for the aggregate-facade removal: the old root re-exported
    139 names and eagerly imported 156 modules (auth flows, session, tools,
    frontends). Asserting on ``sys.modules`` in a clean interpreter is what
    catches a re-export reappearing via an ``__init__`` side effect.
    """
    code = (
        "import sys\n"
        "import baldric.runtime\n"
        "heavy = sorted(\n"
        "    m for m in sys.modules\n"
        "    if m.startswith('baldric.runtime.')\n"
        "    and not m.startswith('baldric.runtime.version')\n"
        ")\n"
        "print('\\n'.join(heavy))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=os.getcwd(),
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert result.returncode == 0, result.stderr
    leaked = [line for line in result.stdout.split() if line]
    assert leaked == [], f"import baldric.runtime eagerly pulled: {leaked}"
