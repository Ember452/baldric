"""Stable public surface for Baldric extension authors.

This is the facade extension code and examples import from. It re-exports only;
it defines no behaviour of its own, and the names are grouped by contract domain
so reviewers can read the surface at a glance.

Import sources are chosen so a consumer of the *shapes* never pulls the runtime:

* pure contract shapes (events, type aliases, capability metadata, contract
  constants) come straight from ``baldric.protocol``;
* the behaviour classes handed to an extension's ``setup`` (``ExtensionAPI`` and
  its context/ui facades) live in the platform layer and are imported from there.

Adding a name here is a public-contract decision, not an implementation detail —
the ``EXTENSION_API_VERSION`` bump rule applies.
"""

from __future__ import annotations

# Pure contract shapes: no runtime import required to use these.
from baldric.protocol.extension import (
    AGENT_EVENT_TYPES,
    AGENT_EVENT_WILDCARD,
    EVENT_NAME_ALIASES,
    EXTENSION_API_VERSION,
    LIFECYCLE_EVENT_TYPES,
    PROVIDER_EVENT_TYPES,
    CompactionSummaryResult,
    CustomEntryView,
    CustomMessageMarkup,
    CustomMessageView,
    DeliverAs,
    EntryRenderer,
    ExtensionCapabilities,
    InputEvent,
    InputHookResult,
    MarkdownRenderContext,
    MarkdownTransformer,
    MessageRenderer,
    MessageRenderOptions,
    NotifyLevel,
    ProviderContextEvent,
    ProviderHeadersEvent,
    ProviderRequestEvent,
    ProviderResponseEvent,
    ProviderStreamEvent,
    SessionBeforeCompactEvent,
    SessionLifecycleReason,
    SessionShutdownEvent,
    SessionStartEvent,
    ToolCallHookEvent,
    ToolCallHookResult,
    ToolCallMarkup,
    ToolCallResolver,
    ToolResultHookEvent,
    ToolResultHookResult,
    ToolResultMarkup,
    ToolResultResolver,
    TurnEndEvent,
    TurnStartEvent,
    UserBashEvent,
    UserBashResult,
)

# Behaviour handed to extensions: the setup() argument and its context/ui.
from baldric.runtime.platform.api import (
    ComponentBridge,
    ExtensionAPI,
    ExtensionCommandContext,
    ExtensionCommandHandler,
    ExtensionContext,
    ExtensionError,
    ExtensionHandler,
    ExtensionSidebar,
    ExtensionUi,
    KeyInterceptor,
    MainViewFactory,
    MainViewHandle,
    NullUiBridge,
    Placement,
    SidebarContent,
    SidebarWidgetFactory,
    SlotWidgetContent,
    SlotWidgetFactory,
    StderrUiBridge,
    UiBridge,
)

__all__ = [
    # event constants + contract version
    "AGENT_EVENT_TYPES",
    "AGENT_EVENT_WILDCARD",
    "EVENT_NAME_ALIASES",
    "EXTENSION_API_VERSION",
    "LIFECYCLE_EVENT_TYPES",
    "PROVIDER_EVENT_TYPES",
    # pure contract shapes / type aliases
    "CompactionSummaryResult",
    "CustomEntryView",
    "CustomMessageMarkup",
    "CustomMessageView",
    "DeliverAs",
    "EntryRenderer",
    "ExtensionCapabilities",
    "InputEvent",
    "InputHookResult",
    "MarkdownRenderContext",
    "MarkdownTransformer",
    "MessageRenderOptions",
    "MessageRenderer",
    "NotifyLevel",
    "ProviderContextEvent",
    "ProviderHeadersEvent",
    "ProviderRequestEvent",
    "ProviderResponseEvent",
    "ProviderStreamEvent",
    "SessionBeforeCompactEvent",
    "SessionLifecycleReason",
    "SessionShutdownEvent",
    "SessionStartEvent",
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
    "UserBashEvent",
    "UserBashResult",
    # behaviour handed to extensions
    "ComponentBridge",
    "ExtensionAPI",
    "ExtensionCommandContext",
    "ExtensionCommandHandler",
    "ExtensionContext",
    "ExtensionError",
    "ExtensionHandler",
    "ExtensionSidebar",
    "ExtensionUi",
    "KeyInterceptor",
    "MainViewFactory",
    "MainViewHandle",
    "NullUiBridge",
    "Placement",
    "SidebarContent",
    "SidebarWidgetFactory",
    "SlotWidgetContent",
    "SlotWidgetFactory",
    "StderrUiBridge",
    "UiBridge",
]
