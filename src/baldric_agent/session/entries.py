"""Append-only session entry models."""

from __future__ import annotations

from time import time
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from baldric_agent.messages import AgentMessage, Usage, UserContent
from baldric_agent.types import JSONValue

CURRENT_SCHEMA_VERSION = 1
"""Shape version of the persisted session-entry protocol.

Version 1 is the original Baldric shape and is never written to disk, so a
transcript produced by this build stays byte-identical to one produced before
the version field existed. A future incompatible change bumps this constant and
starts writing ``schema_version`` on new entries; readers refuse a transcript
newer than they support instead of failing with a pydantic validation dump.
"""


def new_entry_id() -> str:
    """Return a unique session entry id."""
    return uuid4().hex


def current_timestamp() -> float:
    """Return the current Unix timestamp."""
    return time()


class BaseSessionEntry(BaseModel):
    """Common fields shared by all append-only session entries."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_entry_id)
    parent_id: str | None = None
    timestamp: float = Field(default_factory=current_timestamp)
    # Omitted at the current version so existing readers keep working; present on
    # disk only once the shape changes incompatibly.
    schema_version: int = Field(
        default=CURRENT_SCHEMA_VERSION,
        exclude_if=lambda value: value == CURRENT_SCHEMA_VERSION,
    )


class MessageEntry(BaseSessionEntry):
    """A transcript message entry."""

    type: Literal["message"] = "message"
    message: AgentMessage


class CustomMessageEntry(BaseSessionEntry):
    """An extension-injected message that participates in model context."""

    type: Literal["custom_message"] = "custom_message"
    custom_type: str
    content: UserContent
    display: bool = True
    details: JSONValue = None


class ModelChangeEntry(BaseSessionEntry):
    """A model selection change entry.

    ``provider`` was added after Baldric's first session format.  It remains
    optional so older transcripts continue to load; new entries always carry
    the provider selected by the host.
    """

    type: Literal["model_change"] = "model_change"
    model: str
    provider: str | None = None


class ThinkingLevelChangeEntry(BaseSessionEntry):
    """A thinking/reasoning level change entry."""

    type: Literal["thinking_level_change"] = "thinking_level_change"
    thinking_level: str | None = None


class CompactionEntry(BaseSessionEntry):
    """A context summary that replaces older message entries during replay."""

    type: Literal["compaction"] = "compaction"
    summary: str
    # Legacy Baldric sessions stored every replaced id. Keep accepting and replaying
    # that shape, but omit the empty compatibility field from new JSONL records.
    replaces_entry_ids: list[str] = Field(default_factory=list, exclude_if=lambda ids: not ids)
    first_kept_entry_id: str | None = None
    tokens_before: int | None = None
    usage: Usage | None = None
    provider: str | None = None
    model: str | None = None
    response_provider: str | None = None


class BranchSummaryEntry(BaseSessionEntry):
    """A future branch summary entry."""

    type: Literal["branch_summary"] = "branch_summary"
    summary: str
    branch_root_id: str | None = None
    usage: Usage | None = None
    provider: str | None = None
    model: str | None = None
    response_provider: str | None = None


class LabelEntry(BaseSessionEntry):
    """A bookmark change attached to one session entry."""

    type: Literal["label"] = "label"
    target_id: str
    label: str | None = None


class LeafEntry(BaseSessionEntry):
    """A legacy active-tip pointer retained only for deserialization."""

    type: Literal["leaf"] = "leaf"
    entry_id: str | None = None


class SessionInfoEntry(BaseSessionEntry):
    """Basic session metadata entry."""

    type: Literal["session_info"] = "session_info"
    created_at: float = Field(default_factory=current_timestamp)
    cwd: str | None = None
    title: str | None = None


class CustomEntry(BaseSessionEntry):
    """Extension/application-owned session data."""

    type: Literal["custom"] = "custom"
    namespace: str
    data: dict[str, JSONValue] = Field(default_factory=dict)


type SessionEntry = Annotated[
    MessageEntry
    | CustomMessageEntry
    | ModelChangeEntry
    | ThinkingLevelChangeEntry
    | CompactionEntry
    | BranchSummaryEntry
    | LabelEntry
    | LeafEntry
    | SessionInfoEntry
    | CustomEntry,
    Field(discriminator="type"),
]

SESSION_ENTRY_MODELS: tuple[type[BaseSessionEntry], ...] = (
    MessageEntry,
    CustomMessageEntry,
    ModelChangeEntry,
    ThinkingLevelChangeEntry,
    CompactionEntry,
    BranchSummaryEntry,
    LabelEntry,
    LeafEntry,
    SessionInfoEntry,
    CustomEntry,
)
"""Every persisted entry model, so the persistence boundary can name the
supported ``type`` values without restating the union by hand."""
