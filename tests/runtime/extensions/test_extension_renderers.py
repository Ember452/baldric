"""Extension renderers (plan Task D): entry renderer, tool render resolvers,
markdown transformer.

Proves the registration/distribution contract: first entry renderer per
namespace wins; tool resolvers chain over the tool's own renderer with pi's
``next`` semantics; markdown transformers chain in load order on their declared
surfaces; raising renderers fail open (frontend never crashes).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baldric.agent import AgentToolResult
from baldric.runtime.extensions.api import (
    CustomEntryView,
    ExtensionAPI,
    MarkdownRenderContext,
    MessageRenderOptions,
)
from baldric.runtime.extensions.builtin_registry import BuiltInExtension
from baldric.runtime.extensions.runtime import ExtensionRuntime
from tests.runtime.extensions.test_extensions import _paths

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _runtime(tmp_path: Path, setup) -> ExtensionRuntime:
    runtime = ExtensionRuntime(built_in_extensions=(BuiltInExtension(name="ext", setup=setup),))
    runtime.load(_paths(tmp_path), include_resource_dirs=False)
    return runtime


def test_entry_renderer_renders_custom_entry(tmp_path: Path) -> None:
    def setup(api: ExtensionAPI) -> None:
        def render(view: CustomEntryView, options: MessageRenderOptions) -> str:
            title = view.data.get("title", "")
            extra = f" (expanded: {view.data.get('count')})" if options.expanded else ""
            return f"[b]{title}[/b]{extra}"

        api.register_entry_renderer("status-card", render)

    runtime = _runtime(tmp_path, setup)
    assert (
        runtime.render_custom_entry("status-card", {"title": "Indexed", "count": 17}, expanded=False)
        == "[b]Indexed[/b]"
    )
    assert (
        runtime.render_custom_entry("status-card", {"title": "Indexed", "count": 17}, expanded=True)
        == "[b]Indexed[/b] (expanded: 17)"
    )


def test_entry_renderer_without_registration_returns_none(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, lambda api: None)
    assert runtime.render_custom_entry("no-such", {"a": 1}, expanded=False) is None


def test_first_entry_renderer_wins_and_duplicates_are_diagnosed(tmp_path: Path) -> None:
    def first_setup(api: ExtensionAPI) -> None:
        api.register_entry_renderer("card", lambda view, options: "first")

    def second_setup(api: ExtensionAPI) -> None:
        api.register_entry_renderer("card", lambda view, options: "second")

    runtime = ExtensionRuntime(
        built_in_extensions=(
            BuiltInExtension(name="first", setup=first_setup),
            BuiltInExtension(name="second", setup=second_setup),
        )
    )
    runtime.load(_paths(tmp_path), include_resource_dirs=False)
    assert runtime.render_custom_entry("card", {}, expanded=False) == "first"
    dupes = [d for d in runtime.diagnostics if "already registered" in d.message]
    assert len(dupes) == 1


def test_tool_call_resolver_overrides_and_chains(tmp_path: Path) -> None:
    def setup(api: ExtensionAPI) -> None:
        def resolver(tool_name: str, next_call):
            if not tool_name.startswith("mcp__"):
                return next_call()
            base = next_call()
            return f"[ext]{base or tool_name}[/ext]"

        api.register_tool_renderer(render_call=resolver)

    runtime = _runtime(tmp_path, setup)
    # No tool registered named mcp__foo: tool's own renderer yields None, resolver wraps.
    assert runtime.render_tool_call_via_resolvers("mcp__foo", {}) == "[ext]mcp__foo[/ext]"
    # Non-mcp tool defers to the (absent) tool renderer -> None.
    assert runtime.render_tool_call_via_resolvers("read", {}) is None


def test_tool_result_resolver_sees_result_and_next(tmp_path: Path) -> None:
    def setup(api: ExtensionAPI) -> None:
        def resolver(tool_name: str, result: AgentToolResult, expanded: bool, next_call):
            return f"[r]{next_call() or result.text}[/r]"

        api.register_tool_renderer(render_result=resolver)

    runtime = _runtime(tmp_path, setup)
    result = AgentToolResult(content="file content")
    assert runtime.render_tool_result_via_resolvers("read", result, expanded=False) == "[r]file content[/r]"


def test_tool_resolver_failure_falls_open_to_next(tmp_path: Path) -> None:
    def setup(api: ExtensionAPI) -> None:
        def boom(tool_name: str, next_call):
            raise RuntimeError("kaboom")

        api.register_tool_renderer(render_call=boom)

    runtime = _runtime(tmp_path, setup)
    assert runtime.render_tool_call_via_resolvers("read", {}) is None
    failures = [d for d in runtime.diagnostics if "kaboom" in d.message]
    assert len(failures) == 1


def test_markdown_transformer_chains_in_load_order_on_declared_surfaces(tmp_path: Path) -> None:
    def first_setup(api: ExtensionAPI) -> None:
        api.register_markdown_transformer(lambda md, ctx: md + "+first")

    def second_setup(api: ExtensionAPI) -> None:
        # Only runs on summaries; must NOT run on the assistant surface.
        api.register_markdown_transformer(
            lambda md, ctx: md + "+summary",
            message_types=["summary"],
        )

    runtime = ExtensionRuntime(
        built_in_extensions=(
            BuiltInExtension(name="first", setup=first_setup),
            BuiltInExtension(name="second", setup=second_setup),
        )
    )
    runtime.load(_paths(tmp_path), include_resource_dirs=False)

    out = runtime.transform_markdown("md", message_type="assistant")
    assert out == "md+first"
    # `first` declared the default transcript surfaces only, so the summary
    # surface runs just the second transformer.
    assert runtime.transform_markdown("md", message_type="summary") == "md+summary"
    # default surfaces include assistant-thinking
    assert runtime.transform_markdown("md", message_type="assistant-thinking") == "md+first"


def test_markdown_transformer_failure_keeps_chain_going(tmp_path: Path) -> None:
    def boom_setup(api: ExtensionAPI) -> None:
        def boom(md: str, ctx: MarkdownRenderContext) -> str:
            raise RuntimeError("kaboom")

        api.register_markdown_transformer(boom)

    def after_setup(api: ExtensionAPI) -> None:
        api.register_markdown_transformer(lambda md, ctx: md + "+after")

    runtime = ExtensionRuntime(
        built_in_extensions=(
            BuiltInExtension(name="boom", setup=boom_setup),
            BuiltInExtension(name="after", setup=after_setup),
        )
    )
    runtime.load(_paths(tmp_path), include_resource_dirs=False)
    assert runtime.transform_markdown("md", message_type="assistant") == "md+after"
    failures = [d for d in runtime.diagnostics if "kaboom" in d.message]
    assert len(failures) == 1
