"""TUI screen implementations."""

from __future__ import annotations

from baldric.coding.tui.screens.command_output import CommandOutputScreen, CommandOutputScroll
from baldric.coding.tui.screens.extension import (
    ExtensionConfirmScreen,
    ExtensionInputScreen,
    ExtensionSelectScreen,
)
from baldric.coding.tui.screens.login import (
    CustomProviderLoginResult,
    CustomProviderLoginScreen,
    LoginMethodListView,
    LoginMethodPickerScreen,
    LoginProviderPickerScreen,
    LoginProviderSearchInput,
    LoginScreen,
    OAuthLoginScreen,
    _LoginFlowAction,
)
from baldric.coding.tui.screens.model_picker import ModelPickerScreen, ModelPickerSearchInput
from baldric.coding.tui.screens.prompt_templates import (
    PromptTemplateEditorScreen,
    PromptTemplatePickerResult,
    PromptTemplatePickerScreen,
)
from baldric.coding.tui.screens.session_picker import SessionPickerScreen, SessionPickerSearchInput
from baldric.coding.tui.screens.sidebar import (
    SidebarFileEditor,
    _atomic_write_sidebar_file,
    _read_sidebar_file,
    _SidebarFileSnapshot,
    _write_staged_utf8,
)
from baldric.coding.tui.screens.skill_picker import (
    SkillPickerResult,
    SkillPickerScreen,
    SkillPickerSearchInput,
)
from baldric.coding.tui.screens.theme import ThemePickerScreen
from baldric.coding.tui.screens.tools_reference import ToolsReferenceScreen, ToolsReferenceSearchInput
from baldric.coding.tui.screens.tree_picker import (
    BranchSummaryInstructionsScreen,
    TreePickerResult,
    TreePickerScreen,
    _TreePickerListItem,
)

__all__ = [
    "BranchSummaryInstructionsScreen",
    "CommandOutputScreen",
    "CommandOutputScroll",
    "CustomProviderLoginResult",
    "CustomProviderLoginScreen",
    "ExtensionConfirmScreen",
    "ExtensionInputScreen",
    "ExtensionSelectScreen",
    "LoginMethodListView",
    "LoginMethodPickerScreen",
    "LoginProviderPickerScreen",
    "LoginProviderSearchInput",
    "LoginScreen",
    "ModelPickerScreen",
    "ModelPickerSearchInput",
    "OAuthLoginScreen",
    "PromptTemplateEditorScreen",
    "PromptTemplatePickerResult",
    "PromptTemplatePickerScreen",
    "SessionPickerScreen",
    "SessionPickerSearchInput",
    "SidebarFileEditor",
    "SkillPickerResult",
    "SkillPickerScreen",
    "SkillPickerSearchInput",
    "ThemePickerScreen",
    "ToolsReferenceScreen",
    "ToolsReferenceSearchInput",
    "TreePickerResult",
    "TreePickerScreen",
    "_LoginFlowAction",
    "_SidebarFileSnapshot",
    "_TreePickerListItem",
    "_atomic_write_sidebar_file",
    "_read_sidebar_file",
    "_write_staged_utf8",
]
