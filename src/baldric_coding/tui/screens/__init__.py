"""TUI screen implementations."""

from __future__ import annotations

from baldric_coding.tui.screens.command_output import CommandOutputScreen, CommandOutputScroll
from baldric_coding.tui.screens.extension import (
    ExtensionConfirmScreen,
    ExtensionInputScreen,
    ExtensionSelectScreen,
)
from baldric_coding.tui.screens.login import (
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
from baldric_coding.tui.screens.model_picker import ModelPickerScreen, ModelPickerSearchInput
from baldric_coding.tui.screens.prompt_templates import (
    PromptTemplateEditorScreen,
    PromptTemplatePickerResult,
    PromptTemplatePickerScreen,
)
from baldric_coding.tui.screens.session_picker import SessionPickerScreen, SessionPickerSearchInput
from baldric_coding.tui.screens.sidebar import (
    SidebarFileEditor,
    _atomic_write_sidebar_file,
    _read_sidebar_file,
    _SidebarFileSnapshot,
    _write_staged_utf8,
)
from baldric_coding.tui.screens.skill_picker import (
    SkillPickerResult,
    SkillPickerScreen,
    SkillPickerSearchInput,
)
from baldric_coding.tui.screens.theme import ThemePickerScreen
from baldric_coding.tui.screens.tools_reference import ToolsReferenceScreen, ToolsReferenceSearchInput
from baldric_coding.tui.screens.tree_picker import (
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
