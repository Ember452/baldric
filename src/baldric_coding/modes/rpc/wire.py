"""Pi-compatible JSONL RPC frontend for a Baldric coding session."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from baldric_agent.session import JsonlSessionStorage
from baldric_coding.modes.rpc.session import RpcSession
from baldric_coding.providers.config import (
    AnthropicProviderConfig,
    OpenAICompatibleProviderConfig,
    provider_thinking_levels,
)
from baldric_coding.session.session import (
    ModelChoice,
)
from baldric_protocol.messages import AssistantMessage, UserMessage
from baldric_protocol.session.entries import SessionEntry
from baldric_protocol.types import JSONValue


def _required_string(command: Mapping[str, object], key: str) -> str:
    value = command.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_bool(command: Mapping[str, object], key: str) -> bool:
    value = command.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _optional_string(command: Mapping[str, object], key: str) -> str | None:
    value = command.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _leaf_id(state: object) -> object:
    return getattr(state, "active_leaf_id", None)


def _model_wire(session: RpcSession, *, choice: ModelChoice | None = None) -> dict[str, JSONValue]:
    selected = choice or ModelChoice(provider_name=session.provider_name, model=session.model)
    provider = session.provider_config(selected.provider_name)
    metadata = provider.model_metadata.get(selected.model) if provider is not None else None
    configured_api = (
        provider.api
        if isinstance(provider, OpenAICompatibleProviderConfig | AnthropicProviderConfig)
        else None
    )
    api = (
        metadata.api
        if metadata is not None and metadata.api is not None
        else configured_api
        if isinstance(configured_api, str)
        else "openai-responses"
        if selected.provider_name == "openai-codex"
        else "openai-completions"
    )
    reasoning = (
        metadata.reasoning
        if metadata is not None and metadata.reasoning is not None
        else bool(provider_thinking_levels(provider, model=selected.model))
        if provider is not None
        else bool(session.available_thinking_levels)
    )
    context_window = (
        metadata.context_window
        if metadata is not None and metadata.context_window is not None
        else provider.context_windows.get(selected.model)
        if provider is not None
        else None
    )
    cost = metadata.cost if metadata is not None else {}
    return {
        "id": selected.model,
        "name": metadata.name if metadata is not None and metadata.name else selected.model,
        "api": api,
        "provider": selected.provider_name,
        "baseUrl": (
            metadata.base_url
            if metadata is not None and metadata.base_url is not None
            else provider.base_url
            if provider is not None
            else ""
        ),
        "reasoning": reasoning,
        "input": list(metadata.input) if metadata is not None and metadata.input else ["text"],
        "contextWindow": context_window or session.context_window_tokens,
        "maxTokens": (
            metadata.max_tokens if metadata is not None and metadata.max_tokens is not None else 16_384
        ),
        "cost": {
            "input": cost.get("input", 0.0),
            "output": cost.get("output", 0.0),
            "cacheRead": cost.get("cacheRead", 0.0),
            "cacheWrite": cost.get("cacheWrite", 0.0),
        },
    }


def _session_file(session: RpcSession) -> str | None:
    storage = session.storage
    return str(storage.path) if isinstance(storage, JsonlSessionStorage) else None


def _session_stats_wire(session: RpcSession) -> dict[str, JSONValue]:
    stats = session.session_stats
    user_messages = sum(isinstance(message, UserMessage) for message in session.messages)
    assistant_messages = sum(isinstance(message, AssistantMessage) for message in session.messages)
    uncached_input = max(
        0,
        stats.input_tokens - stats.cached_input_tokens - stats.cache_write_tokens,
    )
    return {
        "sessionFile": _session_file(session),
        "sessionId": session.session_id or "",
        "userMessages": user_messages,
        "assistantMessages": assistant_messages,
        "toolCalls": stats.tool_call_count,
        "toolResults": stats.tool_call_count,
        "totalMessages": len(session.messages),
        "tokens": {
            "input": uncached_input,
            "output": stats.output_tokens,
            "cacheRead": stats.cached_input_tokens,
            "cacheWrite": stats.cache_write_tokens,
            "total": (
                uncached_input + stats.output_tokens + stats.cached_input_tokens + stats.cache_write_tokens
            ),
        },
        "cost": stats.estimated_cost if stats.estimated_cost is not None else 0.0,
        "contextUsage": {
            "tokens": session.context_token_estimate,
            "contextWindow": session.context_window_tokens,
            "percent": round(
                session.context_token_estimate / session.context_window_tokens * 100,
                2,
            ),
        },
    }


def _entry_wire(entry: SessionEntry, provider_name: str) -> dict[str, JSONValue] | None:
    if entry.type == "leaf":
        return None
    timestamp = datetime.fromtimestamp(entry.timestamp, tz=UTC)
    base: dict[str, JSONValue] = {
        "type": entry.type,
        "id": entry.id,
        "parentId": entry.parent_id,
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
    }
    if entry.type == "message":
        return {**base, "message": _jsonable(entry.message)}
    if entry.type == "custom_message":
        return {
            **base,
            "customType": entry.custom_type,
            "content": _jsonable(entry.content),
            "details": entry.details,
            "display": entry.display,
        }
    if entry.type == "model_change":
        return {
            **base,
            "provider": entry.provider or provider_name,
            "modelId": entry.model,
        }
    if entry.type == "thinking_level_change":
        return {**base, "thinkingLevel": entry.thinking_level or "off"}
    if entry.type == "compaction":
        if entry.first_kept_entry_id is None or entry.tokens_before is None:
            return {
                **base,
                "type": "custom",
                "customType": "baldric.compaction",
                "data": {
                    "summary": entry.summary,
                    **({"usage": _jsonable(entry.usage)} if entry.usage is not None else {}),
                },
            }
        return {
            **base,
            "summary": entry.summary,
            "firstKeptEntryId": entry.first_kept_entry_id,
            "tokensBefore": entry.tokens_before,
            **({"usage": _jsonable(entry.usage)} if entry.usage is not None else {}),
            "details": {},
        }
    if entry.type == "branch_summary":
        return {
            **base,
            "fromId": entry.branch_root_id or entry.parent_id or entry.id,
            "summary": entry.summary,
            **({"usage": _jsonable(entry.usage)} if entry.usage is not None else {}),
            "details": {},
        }
    if entry.type == "custom":
        return {**base, "customType": entry.namespace, "data": entry.data}
    if entry.type == "label":
        return {**base, "targetId": entry.target_id, "label": entry.label}
    if entry.type == "session_info":
        return {**base, "name": entry.title}
    raise AssertionError(f"Unhandled Baldric session entry: {entry.type}")


def _tree_wire(entries: tuple[SessionEntry, ...], provider_name: str) -> list[JSONValue]:
    visible = tuple(entry for entry in entries if entry.type != "leaf")
    children: dict[str | None, list[SessionEntry]] = {}
    ids = {entry.id for entry in visible}
    for entry in visible:
        parent = entry.parent_id if entry.parent_id in ids else None
        children.setdefault(parent, []).append(entry)

    def build(entry: SessionEntry) -> dict[str, JSONValue]:
        projected = _entry_wire(entry, provider_name)
        if projected is None:
            raise AssertionError("Leaf entries must be filtered before tree projection")
        return {
            "entry": projected,
            "children": [build(child) for child in children.get(entry.id, [])],
        }

    return [build(entry) for entry in children.get(None, [])]


def _resolve_session_id(session: RpcSession, reference: str) -> str:
    manager = session.session_manager
    if manager is None:
        raise ValueError("Session manager is not available")
    direct = manager.get_session(reference)
    if direct is not None:
        return direct.id
    candidate = Path(reference).expanduser().resolve(strict=False)
    for record in manager.list_sessions():
        if record.path.resolve(strict=False) == candidate:
            return record.id
    raise ValueError(f"Unknown session: {reference}")


def _jsonable(value: object) -> JSONValue:
    if isinstance(value, BaseModel):
        return cast(JSONValue, value.model_dump(mode="json", by_alias=True))
    if is_dataclass(value) and not isinstance(value, type):
        return cast(JSONValue, asdict(value))
    if isinstance(value, Mapping):
        return cast(
            JSONValue,
            {str(key): _jsonable(item) for key, item in value.items()},
        )
    if isinstance(value, (list, tuple)):
        return cast(JSONValue, [_jsonable(item) for item in value])
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        return cast(JSONValue, value.model_dump(mode="json", by_alias=True))
    return str(value)
