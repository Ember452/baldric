"""Stable public surface for Baldric extension authors.

This package is the *compatibility facade* introduced by the structural
rearchitecture (stage A0). Its job is to fix the public import path **before**
the implementation moves underneath it: today it re-exports the current
``baldric.runtime.extensions.api`` symbols; as later stages relocate those
symbols (protocol shapes into ``baldric.protocol``, the behaviour classes into
the platform package), the re-exports here keep pointing at the same names so
no extension or example has to change its import path.

Rules for this facade (see ``docs/internal/plans/2026-11-12-structural-rearchitecture.md``):

* It re-exports only; it defines no behaviour of its own.
* The public names are grouped by consumer (see below) so reviewers can see the
  contract surface at a glance.
* Adding a name here is a public-contract decision, not an implementation
  detail — the ``EXTENSION_API_VERSION`` bump rule applies.
"""

from __future__ import annotations

# Cross-domain ports are genuine protocol shapes; the concrete wiring is
# injected at the composition root in a later stage.
from baldric.protocol.ports import FeatureSetup, HookDispatcher

# Everything else is re-exported from the runtime extension module for now. The
# pure contract shapes (events, type aliases, capability metadata) already live
# in ``baldric.protocol.extension`` and will be pointed there directly once every
# consumer has moved; the behaviour classes (ExtensionAPI and its context/ui)
# move with the platform package in a later stage. Until then this single import
# keeps the public path stable.
from baldric.runtime.extensions.api import (
    AGENT_EVENT_TYPES,
    AGENT_EVENT_WILDCARD,
    EVENT_NAME_ALIASES,
    EXTENSION_API_VERSION,
    LIFECYCLE_EVENT_TYPES,
    PROVIDER_EVENT_TYPES,
    CompactionSummaryResult,
    ComponentBridge,
    CustomEntryView,
    CustomMessageMarkup,
    CustomMessageView,
    DeliverAs,
    EntryRenderer,
    ExtensionAPI,
    ExtensionCapabilities,
    ExtensionCommandContext,
    ExtensionCommandHandler,
    ExtensionContext,
    ExtensionError,
    ExtensionHandler,
    ExtensionSidebar,
    ExtensionUi,
    InputEvent,
    InputHookResult,
    KeyInterceptor,
    MainViewFactory,
    MainViewHandle,
    MarkdownRenderContext,
    MarkdownTransformer,
    MessageRenderer,
    MessageRenderOptions,
    NotifyLevel,
    NullUiBridge,
    Placement,
    ProviderContextEvent,
    ProviderHeadersEvent,
    ProviderRequestEvent,
    ProviderResponseEvent,
    ProviderStreamEvent,
    SessionBeforeCompactEvent,
    SessionLifecycleReason,
    SessionShutdownEvent,
    SessionStartEvent,
    SidebarContent,
    SidebarWidgetFactory,
    SlotWidgetContent,
    SlotWidgetFactory,
    StderrUiBridge,
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
    UiBridge,
    UserBashEvent,
    UserBashResult,
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
    # cross-domain ports
    "FeatureSetup",
    "HookDispatcher",
]
