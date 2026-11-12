"""Pi-compatible JSONL RPC frontend for a Baldric coding session."""

from __future__ import annotations

import contextlib
import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import IO, Literal, cast

import anyio

from baldric.protocol.messages import AssistantMessage, UserMessage
from baldric.runtime.events import CodingSessionEvent
from baldric.runtime.frontends.rpc.session import RpcSession
from baldric.runtime.frontends.rpc.wire import (
    _entry_wire,
    _jsonable,
    _leaf_id,
    _model_wire,
    _optional_string,
    _required_bool,
    _required_string,
    _resolve_session_id,
    _session_file,
    _session_stats_wire,
    _tree_wire,
)
from baldric.runtime.session.session import (
    CodingSession,
    ModelChoice,
)

_MAX_RECORD_BYTES = 16 * 1024 * 1024


def _configure_rpc_stream(stream: IO[str], *, newline: str | None) -> None:
    """Force UTF-8 and, for output, literal LF framing.

    A Windows console pipes JSON through text-mode streams that default to the
    system code page for reading and translate ``\\n`` to ``\\r\\n`` for writing.
    Pi's protocol is UTF-8 with LF-delimited records, so a peer reading bytes
    would otherwise see a carriage return it did not expect, and inbound UTF-8
    (for example non-ASCII prompts) could fail to decode. Streams without
    ``reconfigure`` (in-memory test doubles) keep their current settings.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    with contextlib.suppress(AttributeError, ValueError):
        reconfigure(encoding="utf-8", newline=newline)


class RpcServer:
    """Read Pi-style commands and stream responses/events as strict JSONL."""

    def __init__(
        self,
        session: RpcSession,
        *,
        stdin: IO[str] | None = None,
        stdout: IO[str] | None = None,
    ) -> None:
        self._session = session
        self._stdin = stdin or sys.stdin
        self._stdout = stdout or sys.stdout
        self._write_lock = anyio.Lock()
        self._active_prompt_tasks = 0

    async def run(self) -> None:
        """Serve commands until stdin reaches EOF."""
        _configure_rpc_stream(self._stdin, newline=None)
        _configure_rpc_stream(self._stdout, newline="\n")
        await self._session.emit_pending_session_start()
        async with anyio.create_task_group() as tasks:
            while True:
                line = await anyio.to_thread.run_sync(self._stdin.readline)
                if line == "":
                    break
                if line.endswith("\n"):
                    line = line[:-1]
                if line.endswith("\r"):
                    line = line[:-1]
                if not line:
                    continue
                if len(line.encode("utf-8")) > _MAX_RECORD_BYTES:
                    await self._error(None, "parse", "RPC record exceeds 16 MiB")
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    await self._error(None, "parse", f"Failed to parse command: {exc.msg}")
                    continue
                if not isinstance(value, dict):
                    await self._error(None, "parse", "Command must be a JSON object")
                    continue
                await self._dispatch(cast(dict[str, object], value), tasks)
            if self._active_prompt_tasks:
                self._session.cancel()
        await self._session.aclose()

    async def _dispatch(self, command: dict[str, object], tasks: anyio.abc.TaskGroup) -> None:
        request_id = command.get("id")
        command_type = command.get("type")
        if not isinstance(command_type, str):
            await self._error(request_id, "parse", "Command requires a string 'type'")
            return
        try:
            if command_type in {"prompt", "steer", "follow_up"}:
                message = _required_string(command, "message")
                behavior: Literal["steer", "follow_up"] | None = None
                if command_type == "steer":
                    behavior = "steer"
                elif command_type == "follow_up":
                    behavior = "follow_up"
                explicit = command.get("streamingBehavior")
                if explicit is not None:
                    if explicit not in {"steer", "followUp"}:
                        raise ValueError("streamingBehavior must be 'steer' or 'followUp'")
                    behavior = "follow_up" if explicit == "followUp" else "steer"
                if self._active_prompt_tasks and behavior is None:
                    raise ValueError("Agent is already streaming; set streamingBehavior to steer or followUp")
                stream = self._session.prompt(message, streaming_behavior=behavior)
                try:
                    first_event = await anext(stream)
                except StopAsyncIteration:
                    await self._response(request_id, command_type)
                    return
                self._active_prompt_tasks += 1
                await self._response(request_id, command_type)
                tasks.start_soon(self._run_prompt, stream, first_event)
                return
            if command_type == "abort":
                self._session.cancel()
                await self._response(request_id, command_type)
                return
            if command_type == "get_state":
                await self._response(
                    request_id,
                    command_type,
                    {
                        "model": _model_wire(self._session),
                        "thinkingLevel": self._session.thinking_level,
                        "isStreaming": self._active_prompt_tasks > 0,
                        "isCompacting": False,
                        "steeringMode": "one-at-a-time",
                        "followUpMode": "one-at-a-time",
                        "sessionFile": _session_file(self._session),
                        "sessionId": self._session.session_id or "",
                        "sessionName": self._session.session_title,
                        "autoCompactionEnabled": self._session.auto_compaction_enabled,
                        "messageCount": len(self._session.messages),
                        "pendingMessageCount": self._session.queued_message_count,
                    },
                )
                return
            if command_type == "get_messages":
                await self._response(request_id, command_type, {"messages": list(self._session.messages)})
                return
            if command_type == "get_available_models":
                await self._response(
                    request_id,
                    command_type,
                    {
                        "models": [
                            _model_wire(self._session, choice=choice)
                            for choice in self._session.available_model_choices
                        ]
                    },
                )
                return
            if command_type == "set_model":
                provider = command.get("provider", self._session.provider_name)
                if not isinstance(provider, str):
                    raise ValueError("provider must be a string")
                self._session.set_model_choice(
                    ModelChoice(
                        provider_name=provider,
                        model=_required_string(command, "modelId"),
                    )
                )
                await self._response(request_id, command_type, _model_wire(self._session))
                return
            if command_type == "cycle_model":
                choices = self._session.available_model_choices
                if len(choices) <= 1:
                    await self._response(request_id, command_type, None, include_data=True)
                    return
                current = ModelChoice(
                    provider_name=self._session.provider_name,
                    model=self._session.model,
                )
                try:
                    index = choices.index(current)
                except ValueError:
                    index = -1
                choice = choices[(index + 1) % len(choices)]
                self._session.set_model_choice(choice)
                await self._response(
                    request_id,
                    command_type,
                    {
                        "model": _model_wire(self._session),
                        "thinkingLevel": self._session.thinking_level,
                        "isScoped": False,
                    },
                )
                return
            if command_type == "cycle_thinking_level":
                levels = self._session.available_thinking_levels
                if len(levels) <= 1:
                    await self._response(request_id, command_type, None, include_data=True)
                    return
                level = await self._session.cycle_thinking_level()
                await self._response(request_id, command_type, {"level": level})
                return
            if command_type == "get_available_thinking_levels":
                await self._response(
                    request_id,
                    command_type,
                    {"levels": list(self._session.available_thinking_levels)},
                )
                return
            if command_type == "set_thinking_level":
                await self._session.set_thinking_level(_required_string(command, "level"))
                await self._response(request_id, command_type)
                return
            if command_type == "compact":
                instructions = _optional_string(command, "customInstructions")
                result = await self._session.compact_detailed(instructions)
                await self._response(
                    request_id,
                    command_type,
                    {
                        "summary": result.summary,
                        "firstKeptEntryId": result.first_kept_entry_id,
                        "tokensBefore": result.tokens_before,
                        "estimatedTokensAfter": result.estimated_tokens_after,
                        "details": {},
                    },
                )
                return
            if command_type == "set_auto_compaction":
                self._session.set_auto_compaction_enabled(_required_bool(command, "enabled"))
                await self._response(request_id, command_type)
                return
            if command_type == "bash":
                bash_result = await self._session.run_terminal_command(
                    _required_string(command, "command"),
                    add_to_context=not bool(command.get("excludeFromContext", False)),
                )
                await self._response(
                    request_id,
                    command_type,
                    {
                        "output": bash_result.output,
                        "exitCode": bash_result.exit_code,
                        "cancelled": False,
                        "truncated": False,
                    },
                )
                return
            if command_type == "abort_bash":
                raise ValueError("abort_bash is not supported by Baldric yet")
            if command_type == "new_session":
                await self._session.new_session()
                await self._response(request_id, command_type, {"cancelled": False})
                return
            if command_type == "switch_session":
                session_ref = command.get("sessionId", command.get("sessionPath"))
                if not isinstance(session_ref, str):
                    raise ValueError("switch_session requires sessionPath")
                session_id = _resolve_session_id(self._session, session_ref)
                await self._session.resume(session_id)
                await self._response(request_id, command_type, {"cancelled": False})
                return
            if command_type == "get_session_stats":
                await self._response(
                    request_id,
                    command_type,
                    _session_stats_wire(self._session),
                )
                return
            if command_type == "export_html":
                output_path = _optional_string(command, "outputPath")
                path = await self._session.export(
                    Path(output_path).expanduser() if output_path is not None else None,
                    format="html",
                )
                await self._response(request_id, command_type, {"path": str(path)})
                return
            if command_type == "get_fork_messages":
                entries = await self._session.session_entries()
                await self._response(
                    request_id,
                    command_type,
                    {
                        "messages": [
                            {"entryId": entry.id, "text": entry.message.text}
                            for entry in entries
                            if entry.type == "message" and isinstance(entry.message, UserMessage)
                        ]
                    },
                )
                return
            if command_type == "get_entries":
                cursor_entries = list(await self._session.session_entries())
                since = _optional_string(command, "since")
                if since is not None:
                    try:
                        index = next(i for i, entry in enumerate(cursor_entries) if entry.id == since)
                    except StopIteration as exc:
                        raise ValueError(f"Entry not found: {since}") from exc
                    cursor_entries = cursor_entries[index + 1 :]
                await self._response(
                    request_id,
                    command_type,
                    {
                        "entries": [
                            projected
                            for entry in cursor_entries
                            if (projected := _entry_wire(entry, self._session.provider_name)) is not None
                        ],
                        "leafId": _leaf_id(self._session.state),
                    },
                )
                return
            if command_type == "get_tree":
                entries = await self._session.session_entries()
                await self._response(
                    request_id,
                    command_type,
                    {
                        "tree": _tree_wire(entries, self._session.provider_name),
                        "leafId": _leaf_id(self._session.state),
                    },
                )
                return
            if command_type == "get_last_assistant_text":
                text = next(
                    (
                        message.text
                        for message in reversed(self._session.messages)
                        if isinstance(message, AssistantMessage)
                    ),
                    None,
                )
                await self._response(request_id, command_type, {"text": text})
                return
            if command_type == "set_session_name":
                await self._session.set_session_name(_required_string(command, "name"))
                await self._response(request_id, command_type)
                return
            if command_type == "fork":
                entry_id = _required_string(command, "entryId")
                entries = await self._session.session_entries()
                selected_text = next(
                    (
                        entry.message.text
                        for entry in entries
                        if entry.id == entry_id
                        and entry.type == "message"
                        and isinstance(entry.message, UserMessage)
                    ),
                    "",
                )
                await self._session.branch_to_entry(entry_id)
                await self._response(
                    request_id,
                    command_type,
                    {"text": selected_text, "cancelled": False},
                )
                return
            if command_type == "get_commands":
                commands = self._session.command_registry.list_commands()
                await self._response(
                    request_id,
                    command_type,
                    {
                        "commands": [
                            {
                                "name": item.name,
                                "description": item.description,
                                "source": "extension",
                                "sourceInfo": {
                                    "path": "baldric://command/" + item.name,
                                    "source": "baldric",
                                    "scope": "temporary",
                                    "origin": "top-level",
                                },
                            }
                            for item in commands
                        ]
                    },
                )
                return
            raise ValueError(f"Unknown command: {command_type}")
        except Exception as exc:
            await self._error(request_id, command_type, str(exc))

    async def _run_prompt(
        self,
        stream: AsyncIterator[CodingSessionEvent],
        first_event: CodingSessionEvent,
    ) -> None:
        try:
            await self._write(first_event)
            async for event in stream:
                await self._write(event)
        except (RuntimeError, ValueError) as exc:
            await self._write({"type": "rpc_error", "error": str(exc)})
        finally:
            self._active_prompt_tasks -= 1

    async def _response(
        self,
        request_id: object,
        command: str,
        data: object | None = None,
        *,
        include_data: bool = False,
    ) -> None:
        response: dict[str, object] = {
            "type": "response",
            "command": command,
            "success": True,
        }
        if request_id is not None:
            response["id"] = request_id
        if data is not None or include_data:
            response["data"] = data
        await self._write(response)

    async def _error(self, request_id: object, command: str, error: str) -> None:
        response: dict[str, object] = {
            "type": "response",
            "command": command,
            "success": False,
            "error": error,
        }
        if request_id is not None:
            response["id"] = request_id
        await self._write(response)

    async def _write(self, value: object) -> None:
        payload = json.dumps(_jsonable(value), ensure_ascii=False, separators=(",", ":"))
        async with self._write_lock:
            self._stdout.write(payload + "\n")
            self._stdout.flush()


async def run_rpc_session(session: CodingSession) -> None:
    """Run RPC mode for an already configured CodingSession."""
    await RpcServer(session).run()
