# TUI 视觉系统重构 Implementation Plan（第一批：L1 + L2）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立分层主题 token 体系（opencode schema 数据层 + `TuiTheme` 双层投影），并把它用在消息卡片、工具行、diff 高亮、状态行上，让对话区从"黑底白字"变成"有层级、有卡片、有 diff 高亮的终端工作台"。

**Architecture:** 数据层用 opencode 的嵌套 schema（hue 色阶 + text/background/diff/syntax/markdown），代码层新增 `ThemeTokens` 分层视图，同时从同一份 schema 投影出**保持原样的** `TuiTheme`（扩展契约零破坏）。组件层只读 `ThemeTokens`；`TuiTheme` 与 `theme_css_variables()` 的输出必须与现状逐字段相等。

**Tech Stack:** Python 3.12 / Textual 8.2.8 / Rich 15 / pytest / ruff / mypy

**Spec:** `docs/superpowers/specs/2026-11-08-tui-visual-system-design.md`

---

## 开工前的四条硬要求（用户指定，优先级高于本文档）

> 这几条写在计划最前面，因为它们是**执行纪律**，不是建议。

1. **本文档不是铁律。** 动手写任何代码前，必须**去代码里核实**本任务列出的每个文件、每个签名、每个行号。本文档的行号和数值是 2026-11-08 的实测值，执行时可能已漂移——**以代码为准，不以本文档为准**。核实后发现本文档写错，**先改本文档，再写代码**（并在 commit message 里说明改了哪条）。

2. **没有想清楚就不动手。** 每个任务开始前写清三件事：① 这次改动会影响哪些调用点（`git grep` 出具体清单，不是"大概"）；② 可能引入哪些 bug（列出至少 3 条具体场景，比如"空 diff 会怎样""CJK 宽度会不会崩""灰度终端会不会掉色"）；③ 怎么验证（不只是跑测试，还要有能证伪的手工/自动检查）。**三条缺一条就不要开始写代码。**

3. **代码质量要求：高内聚低耦合。** 具体到本计划：新逻辑放进 `ThemeTokens` / `rendering/` 的纯函数，**不要往 `app.py`（4589 行）里堆**；组件只消费 token，不在渲染代码里硬编码颜色；每个新模块有单一职责，能被单独测试。

4. **遇到问题先去 pi / opencode 找答案。** 本计划给出的常量、配色、文案都标了来源（`pi:` / `opencode:`）。实现时若遇到本文档没覆盖的细节（截断文案、折叠交互、状态色优先级），**先去 `pi-main/` 和 `opencode-dev/` 读它们怎么做的**，不要自己发明。找到的做法要写进代码注释（注明来源文件）。

5. **可以改现有烂代码，但必须先核查。** 如果实现过程中发现现有代码有问题、写死得不好、对后续维护不友好（例如本计划已知的三处：工具失败靠 `startswith("✗")` 判断、预览预算所有工具共用一个常量、`extensions` 侧栏分区重复），**允许修改**，但必须：① 先写清"为什么这是问题"；② 评估影响面（谁在依赖这个行为）；③ 单独一个 commit，不与功能改动混在一起；④ 在 commit message 里说明原行为与新行为的差异。

---

## Global Constraints（每个任务都隐含适用）

- **不得改变 `TuiTheme` 的公开字段形状**：`dataclasses.fields(TuiTheme)` 的字段名集合必须与开工前**完全相同**（当前 35 个，其中 31 个 color 字段）。`TuiRoleStyle` 必须仍是 `border`/`body` 两个字段。
- **不得改变 `theme_css_variables()` 的键集合**：当前 32 个（25 个 `baldric-*` + 7 个 `footer-*`）。可以新增，**不得删除或重命名**。
- **不得让 `rendering/` 引入 Textual**：`uv run python scripts/check_import_graph.py` 必须始终 OK。`baldric_protocol` / `baldric_mcp` 不得被 `baldric_coding` 以外扩展、也不得引用 Textual/rich。
- **配色/常量来源优先抄 pi / opencode，不自己发明**。每个自定值必须在代码注释里写明"为什么两家都不能直接用"。
- **Python >= 3.12**；类型标注齐全（`mypy --strict` 在 Linux CI 跑）。
- **测试用 `pytest` 风格，测试文件放 `tests/coding/<topic>/`**，与现有目录一致（渲染类放 `tests/coding/rendering/`，TUI 放 `tests/coding/tui/`）。
- **每个 commit 只做一件事**；提交前跑 `uv run ruff check . && uv run ruff format --check . && uv run mypy`（Windows 上 mypy 会有 14 个已知 fcntl 噪音，不算新增）。

---

## 文件结构（本批要动的文件与职责）

**新增**

| 文件 | 职责 |
|---|---|
| `src/baldric_coding/rendering/theme_schema.py` | ① 解析 opencode 风格 schema（含 `$hue.*` / `$background.*` 引用解析）；② `ThemeTokens` dataclass（分层视图）；③ `build_tokens(schema) -> ThemeTokens`；④ `project_to_tui_theme(schema) -> TuiTheme`（投影出旧的扁平视图） |
| `src/baldric_coding/rendering/tool_preview.py` | 按工具名返回预览预算（bash/read/edit-write/其它），从 `state.py` 抽出，供渲染与 state 共用 |
| `tests/coding/rendering/test_theme_schema.py` | schema 解析、引用解析、`ThemeTokens` 构建、投影等价 |
| `tests/coding/rendering/test_tool_preview.py` | 分级预算的分派规则 |
| `src/baldric_coding/rendering/themes/opencode-dark.json` | 第 4 套主题（全量照搬 opencode） |
| `src/baldric_coding/rendering/themes/pi-dark.json` | 第 5 套主题（pi dark.json → hex） |

**修改**

| 文件 | 改什么 |
|---|---|
| `src/baldric_coding/rendering/themes/__init__.py`（446 行） | `parse_tui_theme_json()` 双格式兼容；`_load_builtin_theme` 走新 schema；`BUILTIN_TUI_THEME_NAMES` 扩到 5 |
| `src/baldric_coding/rendering/diffs.py` | `_line_text` / `_render_single_line` 加整行底色（读 `ThemeTokens`，但为了不破坏签名，颜色从 `TuiTheme` 的现有字段+新增 token 均可选） |
| `src/baldric_coding/tui/state.py` | 预览常量改为按工具名分派（调 `tool_preview.py`） |
| `src/baldric_coding/tui/widgets/core.py` | `TranscriptMessageWidget` 卡片底色；工具行右侧 `+N −M · 4.2s` |
| `src/baldric_coding/tui/app.py` | prompt 边框随 thinking 等级；侧栏默认收起 + `Ctrl+B`；状态行合并一行 |
| `tests/coding/tui/test_tui_themes.py`（408 行） | 扩到 5 套主题 + 双格式兼容 |

---

## Task 1: 主题 schema 解析器（纯函数，无 UI 依赖）

**Files:**
- Create: `src/baldric_coding/rendering/theme_schema.py`
- Test: `tests/coding/rendering/test_theme_schema.py`

**Interfaces:**
- Produces:
  - `resolve_references(data: object) -> dict[str, object]`：把 `"$hue.gray.200"` / `"$background.raised.base"` 解析成实际 hex。
  - `ThemeTokens`（frozen dataclass，字段见下）
  - `build_tokens(schema: dict[str, object]) -> ThemeTokens`

- [ ] **Step 1: 先读现状，写下影响面与风险（不写代码）**

Run:
```bash
cd baldric
wc -l src/baldric_coding/rendering/themes/__init__.py
sed -n '218,240p' src/baldric_coding/rendering/themes/__init__.py   # 看 _substitute_vars 现有实现
git grep -n "_substitute_vars" -- src
```
在任务日志里写下：
- `_substitute_vars` 现在只做 `$var` 单级替换，本任务要扩成 `$a.b.c` 多级——**列出所有调用点**，确认扩展不破坏现有单级用法。
- 三个可能 bug：① `$` 开头但路径不存在的引用（要报清晰错误，不能静默成空）；② 循环引用（`$a` → `$b` → `$a`，要检测并报错）；③ 非 ASCII 路径键。

- [ ] **Step 2: 写失败测试**

```python
# tests/coding/rendering/test_theme_schema.py
from baldric_coding.rendering.theme_schema import build_tokens, resolve_references


def test_resolve_hue_reference() -> None:
    data = {
        "hue": {"gray": {"200": "#eeeeee", "900": "#141414"}},
        "text": {"base": "$hue.gray.200"},
    }
    resolved = resolve_references(data)
    assert resolved["text"]["base"] == "#eeeeee"


def test_resolve_nested_background_reference() -> None:
    data = {
        "hue": {"gray": {"800": "#1e1e1e"}},
        "background": {"base": "#0a0a0a", "raised": {"base": "$hue.gray.800"}},
        "roles": {"user": {"body": "on $background.raised.base"}},
    }
    resolved = resolve_references(data)
    assert resolved["background"]["raised"]["base"] == "#1e1e1e"
    assert resolved["roles"]["user"]["body"] == "on #1e1e1e"


def test_unresolved_reference_raises() -> None:
    data = {"text": {"base": "$hue.nope.100"}}
    try:
        resolve_references(data)
    except KeyError as exc:
        assert "hue.nope.100" in str(exc)
    else:
        raise AssertionError("expected KeyError")


def test_cycle_raises() -> None:
    data = {"a": "$b", "b": "$a"}
    try:
        resolve_references(data)
    except ValueError as exc:
        assert "cycle" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError")


def test_build_tokens_exposes_layering() -> None:
    schema = {
        "hue": {"gray": {"800": "#1e1e1e", "900": "#0a0a0a"}},
        "text": {"base": "#eeeeee", "muted": "#808080"},
        "background": {"base": "$hue.gray.900", "raised": {"base": "$hue.gray.800"}},
        "diff": {"background": {"added": "#20303b"}},
    }
    tokens = build_tokens(schema)
    assert tokens.text_base == "#eeeeee"
    assert tokens.surface_base == "#0a0a0a"
    assert tokens.surface_raised == "#1e1e1e"
    assert tokens.diff_added_bg == "#20303b"
```

- [ ] **Step 3: 跑测试确认失败**

Run: `uv run pytest tests/coding/rendering/test_theme_schema.py -v`
Expected: FAIL，`ModuleNotFoundError: baldric_coding.rendering.theme_schema`

- [ ] **Step 4: 写最小实现**

```python
# src/baldric_coding/rendering/theme_schema.py
"""Parse an opencode-shaped theme schema into flat tokens.

The data layer is nested (``hue.gray.200``, ``background.raised.base``) so a
theme can express layering; consumers get a flat ``ThemeTokens`` because the
renderers only ever want "the raised surface colour", not the path to it.

Reference syntax follows opencode's theme files: a string that is exactly
``$a.b.c`` resolves through the document. Sources:
  opencode-dev/packages/tui/src/theme/resolve.ts
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_REFERENCE_PREFIX = "$"


def _lookup(document: Any, path: str) -> Any:
    node = document
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"unresolved theme reference: ${path}")
        node = node[part]
    return node


def resolve_references(data: object) -> dict[str, Any]:
    """Return a deep copy with every ``$a.b.c`` string replaced by its value."""
    resolved = _resolve(data, root=data, seen=())
    if not isinstance(resolved, dict):
        raise TypeError("theme document must be an object")
    return resolved


def _resolve(node: Any, *, root: object, seen: tuple[str, ...]) -> Any:
    if isinstance(node, dict):
        return {key: _resolve(value, root=root, seen=seen) for key, value in node.items()}
    if isinstance(node, list):
        return [_resolve(item, root=root, seen=seen) for item in node]
    if isinstance(node, str) and node.startswith(_REFERENCE_PREFIX) and "." in node:
        path = node[len(_REFERENCE_PREFIX) :]
        if path in seen:
            raise ValueError(f"cycle in theme references: {' -> '.join(seen + (path,))}")
        target = _lookup(root, path)
        return _resolve(target, root=root, seen=seen + (path,))
    return node


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    """Flat, layered view of a theme for component code.

    Only fields the first batch actually uses are defined here; later batches
    append fields (never rename) so consumers stay stable.
    """

    name: str
    dark: bool
    # text
    text_base: str
    text_muted: str
    text_faint: str
    text_thinking: str
    # surfaces (the layering the flat TuiTheme could not express)
    surface_base: str
    surface_raised: str
    surface_high: str
    surface_max: str
    # accents and status
    accent: str
    success: str
    error: str
    # diff
    diff_added_bg: str
    diff_removed_bg: str
    diff_added_text: str
    diff_removed_text: str
    diff_context_bg: str
    diff_line_number_text: str
    # role backgrounds (None means "no card background")
    role_user_bg: str | None
    role_tool_pending_bg: str | None
    role_tool_success_bg: str | None
    role_tool_error_bg: str | None


def _get(document: dict[str, Any], *path: str, default: str = "#000000") -> str:
    node: Any = document
    for part in path:
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node if isinstance(node, str) else default


def build_tokens(schema: dict[str, Any]) -> ThemeTokens:
    """Build the component-facing token view from a resolved schema."""
    resolved = resolve_references(schema)
    roles = resolved.get("roles", {})
    return ThemeTokens(
        name=str(resolved.get("name", "unnamed")),
        dark=bool(resolved.get("appearance", "dark") == "dark"),
        text_base=_get(resolved, "text", "base", default="#d8dee9"),
        text_muted=_get(resolved, "text", "muted", default="#808080"),
        text_faint=_get(resolved, "text", "faint", default="#4c4c4c"),
        text_thinking=_get(resolved, "text", "thinking", default="#9ca3af"),
        surface_base=_get(resolved, "background", "base"),
        surface_raised=_get(resolved, "background", "raised", "base"),
        surface_high=_get(resolved, "background", "raised", "high"),
        surface_max=_get(resolved, "background", "raised", "max"),
        accent=_get(resolved, "hue", "accent", "200", default="#a7f3f0"),
        success=_get(resolved, "hue", "green", "200", default="#9cffb1"),
        error=_get(resolved, "hue", "red", "200", default="#ff4f4f"),
        diff_added_bg=_get(resolved, "diff", "background", "added"),
        diff_removed_bg=_get(resolved, "diff", "background", "removed"),
        diff_added_text=_get(resolved, "diff", "text", "added"),
        diff_removed_text=_get(resolved, "diff", "text", "removed"),
        diff_context_bg=_get(resolved, "diff", "background", "context"),
        diff_line_number_text=_get(resolved, "diff", "lineNumber", "text"),
        role_user_bg=_optional(roles, "user", "background"),
        role_tool_pending_bg=_optional(roles, "tool_pending", "background"),
        role_tool_success_bg=_optional(roles, "tool_success", "background"),
        role_tool_error_bg=_optional(roles, "tool_error", "background"),
    )


def _optional(roles: Any, role: str, key: str) -> str | None:
    if not isinstance(roles, dict) or role not in roles:
        return None
    node = roles[role]
    if not isinstance(node, dict):
        return None
    value = node.get(key)
    return value if isinstance(value, str) and value else None
```

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/coding/rendering/test_theme_schema.py -v`
Expected: 5 passed

- [ ] **Step 6: 静态检查并提交**

```bash
uv run ruff check . && uv run ruff format --check . && uv run python scripts/check_import_graph.py
git add src/baldric_coding/rendering/theme_schema.py tests/coding/rendering/test_theme_schema.py
git commit -m "feat(rendering): opencode-shaped theme schema parser and flat ThemeTokens"
```

---

## Task 2: 从 schema 投影出 TuiTheme（零破坏等价）

**Files:**
- Modify: `src/baldric_coding/rendering/theme_schema.py`
- Test: `tests/coding/rendering/test_theme_schema.py`

**Interfaces:**
- Consumes: `resolve_references`（Task 1）
- Produces: `project_to_tui_theme(schema: dict[str, object]) -> TuiTheme`

> **本任务是"参数照抄不发明"的机械保证。** 它必须能把现有 3 套主题的 JSON
> 投影成与现状**逐字段相等**的 `TuiTheme`；不相等就是投影写错了，不是"可以接受的差异"。

- [ ] **Step 1: 影响面与风险核实**

```bash
sed -n '40,80p' src/baldric_coding/rendering/themes/__init__.py   # TuiTheme 全字段
uv run python -c "import dataclasses,sys; sys.path.insert(0,'.'); from baldric_coding.tui.config import TuiTheme; print([f.name for f in dataclasses.fields(TuiTheme)])"
```
写下：投影必须覆盖 **31 个 color 字段 + 10 个 role**；可能 bug：① 某个 color 字段在 schema 里没有来源（要 fallback 到现主题该字段的值，不能瞎猜）；② role body 是 `"fg on bg"` 富样式串，投影时不能把 `on` 当路径解析；③ `syntax_theme` 不是颜色，要原样传。

- [ ] **Step 2: 写失败测试（用真实现有主题做等价基准）**

```python
# 追加到 tests/coding/rendering/test_theme_schema.py
from json import dumps
from pathlib import Path

from baldric_coding.rendering.theme_schema import project_to_tui_theme
from baldric_coding.rendering.themes import BALDRIC_DARK_THEME, THEME_COLOR_FIELDS

THEMES_DIR = Path(__file__).resolve().parents[3] / "src/baldric_coding/rendering/themes"


def test_projection_matches_the_current_dark_theme_field_by_field() -> None:
    schema = __import__("json").loads((THEMES_DIR / "baldric-dark.json").read_text(encoding="utf-8"))
    projected = project_to_tui_theme(schema)
    for field_name in THEME_COLOR_FIELDS:
        assert getattr(projected, field_name) == getattr(BALDRIC_DARK_THEME, field_name), field_name
    assert projected.role_styles == BALDRIC_DARK_THEME.role_styles
    assert projected.syntax_theme == BALDRIC_DARK_THEME.syntax_theme
```

- [ ] **Step 3: 跑测试确认失败**

Run: `uv run pytest tests/coding/rendering/test_theme_schema.py::test_projection_matches_the_current_dark_theme_field_by_field -v`
Expected: FAIL（`project_to_tui_theme` 不存在）

- [ ] **Step 4: 实现投影**

在 `theme_schema.py` 追加：

```python
def project_to_tui_theme(schema: dict[str, Any]) -> TuiTheme:
    """Project a layered schema onto the flat, frozen TuiTheme contract.

    The flat view is what third-party extension factories receive
    (``Callable[[TuiTheme], Widget]`` in extensions/api.py), so its field
    semantics must not change: same names, same meaning, same role shape.
    Every colour here comes from the schema; a missing source falls back to
    the field's current default so a partial theme never crashes the TUI.
    """
    from baldric_coding.rendering.themes import TuiTheme, TuiRoleStyle

    resolved = resolve_references(schema)
    colors = resolved.get("colors", {})  # old flat format passthrough
    roles_raw = resolved.get("roles", {})

    def color(field: str) -> str:
        if isinstance(colors, dict) and isinstance(colors.get(field), str):
            return colors[field]
        # New schema: derive the flat field from its layered token.
        return _FLAT_FIELD_SOURCE.get(field, lambda r: _get(r, "background", "base"))(resolved)

    role_styles = {
        name: TuiRoleStyle(
            border=str(spec.get("border", color("border"))),
            body=str(spec.get("body", "")),
        )
        for name, spec in roles_raw.items()
        if isinstance(spec, dict)
    }
    return TuiTheme(
        name=str(resolved.get("name", "unnamed")),
        dark=bool(resolved.get("appearance", "dark") == "dark"),
        syntax_theme=str(resolved.get("syntax_theme", "ansi_dark")),
        role_styles=role_styles,
        **{field: color(field) for field in THEME_COLOR_FIELDS},
    )
```

同时定义 `_FLAT_FIELD_SOURCE`（31 个字段到 schema 路径的映射）。**注意：Step 1 会告诉你现有 3 套主题 JSON 是旧 flat 格式（有 `colors`/`roles`），所以 `colors` passthrough 分支就能让等价测试通过**；新 schema 分支用来服务第 4/5 套主题（Task 3）。这个双分支是**故意的**，注释里要写清。

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/coding/rendering/test_theme_schema.py -v`
Expected: 全 passed，且 `theme_css_variables(BALDRIC_DARK_THEME)` 与投影后主题的变量字典相等（补一条断言）。

- [ ] **Step 6: 提交**

```bash
git add -u && git commit -m "feat(rendering): project a layered schema onto the flat TuiTheme contract"
```

---

## Task 3: 5 套主题落地（含两套致敬皮肤）

**Files:**
- Modify: `src/baldric_coding/rendering/themes/__init__.py`
- Create: `src/baldric_coding/rendering/themes/opencode-dark.json`
- Create: `src/baldric_coding/rendering/themes/pi-dark.json`
- Test: `tests/coding/tui/test_tui_themes.py`

**Interfaces:**
- Consumes: `project_to_tui_theme`（Task 2）
- Produces: `BUILTIN_TUI_THEME_NAMES == ("baldric-dark", "baldric-light", "high-contrast", "opencode-dark", "pi-dark")`

- [ ] **Step 1: 核实参数来源与风险**

```bash
# opencode 真实值（不改一个 hex）
cd .. && python -c "import json; d=json.load(open('opencode-dev/packages/tui/src/theme/assets/v2/opencode.json')); print(json.dumps(d['base']['background'], indent=1)); print(json.dumps(d['base']['diff'], indent=1))"
# pi 真实值
cat pi-main/packages/coding-agent/src/modes/interactive/theme/dark.json
```
写下：① pi 用 `okhsl(...)`，**必须转换**成 hex（opencode 的 `color.ts` 有 okhsl→rgb 实现，`pi-main/packages/tui/src/oklab.ts` 也有，抄公式）；② 转换函数要有单测，误差容忍 ±1/255；③ 风险：opencode 主题缺 `roles`（它按 design 命名，不按角色），要补一层 role 映射。

- [ ] **Step 2: 写失败测试**

```python
# 追加到 tests/coding/tui/test_tui_themes.py
def test_five_builtin_themes_are_registered() -> None:
    assert BUILTIN_TUI_THEME_NAMES == (
        "baldric-dark",
        "baldric-light",
        "high-contrast",
        "opencode-dark",
        "pi-dark",
    )


def test_each_builtin_theme_loads_and_has_all_fields() -> None:
    for name in BUILTIN_TUI_THEME_NAMES:
        theme = get_tui_theme(name)
        for field_name in THEME_COLOR_FIELDS:
            assert getattr(theme, field_name), (name, field_name)
        assert set(theme.role_styles) == set(TRANSCRIPT_ROLES), name
```

- [ ] **Step 3: 跑测试确认失败**

Run: `uv run pytest tests/coding/tui/test_tui_themes.py::test_five_builtin_themes_are_registered -v`
Expected: FAIL（当前只有 3 套）

- [ ] **Step 4: 落地两套新主题 + okhsl 转换**

```python
# 追加到 theme_schema.py
def okhsl_to_hex(okhsl: str) -> str:
    """Convert ``okhsl(h s% l%)`` to ``#rrggbb``.

    Ported from pi-main/packages/tui/src/oklab.ts (okhslToRgb) and
    opencode-dev/packages/tui/src/theme/color.ts. Both agree on the pipeline;
    this is a straight port, not a re-derivation.
    """
    raise NotImplementedError("port okhslToRgb from pi-main/packages/tui/src/oklab.ts")
```
> 实现时**照抄** `oklab.ts` 里的 `okhslToRgb` 数学，不要自己推导。写 4 条单测（黑/白/中灰/红）比对已知值。

`opencode-dark.json`：把 `opencode.json` 的 `base` 段整体搬过来（`hue`/`text`/`background`/`border`/`diff`/`syntax`/`markdown`），补一层 `roles`（映射规则写在文件里注释不了，所以写进 `dev-notes/`）。
`pi-dark.json`：把 `pi dark.json` 的 `colors` 表转成我们的 schema，`okhsl` 全部转 hex。

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/coding/tui/test_tui_themes.py -v`
Expected: 全 passed（含原有 408 行的断言）

- [ ] **Step 6: 提交**

```bash
git add -u && git commit -m "feat(theme): add opencode-dark and pi-dark, five builtin themes total"
```

---

## Task 4: 工具行分级预览预算（按工具名分派）

**Files:**
- Create: `src/baldric_coding/rendering/tool_preview.py`
- Modify: `src/baldric_coding/tui/state.py:44-49, 930, 937, 960, 981`
- Test: `tests/coding/rendering/test_tool_preview.py`

**Interfaces:**
- Produces: `preview_budget(tool_name: str) -> int | None`（`None` 表示不截断）

> **这是用户 D2 的核心，也是"允许改烂代码"的第一处。** 现状是所有工具共用一个
> `TOOL_RESULT_PREVIEW_LINES = 8`，`edit`/`write` 的 patch 用另一个 32。D2 要求
> bash 5 / read 10 / edit·write 全量。**改法必须是"按工具名分派"，不是调数字。**

- [ ] **Step 1: 影响面与风险核实（必做）**

```bash
git grep -n "TOOL_RESULT_PREVIEW_LINES\|TOOL_PATCH_PREVIEW_LINES\|TERMINAL_COMMAND_OUTPUT_PREVIEW_LINES" -- src tests
sed -n '920,1000p' src/baldric_coding/tui/state.py
git grep -n "format_tool_result_block" -- src tests
```
写下：
- 所有调用点清单（`state.py` 内部 + 测试）。
- **三个具体 bug 场景**：① 现有测试断言了"8 行预览"，改分级后会红——要确认是**行为有意变更**还是**测试该改**；② `read` 结果第 11 行开始被截，`(N earlier lines)` 的 N 是否还在；③ `write` 新建文件没有 patch（`old_content=None` 时），分级分支会不会 KeyError。
- **来源标注**：`pi: bash.ts BASH_PREVIEW_LINES = 5`、`pi: read.ts renderers maxLines = 10`（未展开时）、`pi: renderer.ts CODE_PREVIEW_LINES = 10`。三个都在 `pi-main/packages/coding-agent/src/core/tools/`。

- [ ] **Step 2: 写失败测试**

```python
# tests/coding/rendering/test_tool_preview.py
from baldric_coding.rendering.tool_preview import preview_budget


def test_bash_shows_five_lines() -> None:
    assert preview_budget("bash") == 5


def test_read_shows_ten_lines() -> None:
    assert preview_budget("read") == 10


def test_edit_and_write_are_not_truncated() -> None:
    assert preview_budget("edit") is None
    assert preview_budget("write") is None


def test_unknown_tool_falls_back_to_a_bounded_preview() -> None:
    assert preview_budget("some_new_tool") == 10


def test_terminal_command_output_keeps_its_own_large_budget() -> None:
    # BashExecutionMessage is distinct from a tool call; see state.py.
    assert preview_budget("__terminal__") == 120
```

- [ ] **Step 3: 跑测试确认失败**

Run: `uv run pytest tests/coding/rendering/test_tool_preview.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 4: 实现**

```python
# src/baldric_coding/rendering/tool_preview.py
"""Per-tool preview budgets for collapsed tool rows.

One constant for every tool was wrong: a bash log wants the tail, a read wants
the head, and an edit patch must never be cut (the patch IS the thing the user
needs to review). Values copied from pi:
  pi-main/packages/coding-agent/src/core/tools/bash.ts   (BASH_PREVIEW_LINES = 5)
  pi-main/packages/coding-agent/src/core/tools/renderers/read.ts (10 unexpanded)
  pi-main/packages/coding-agent/src/core/tools/renderer.ts (CODE_PREVIEW_LINES = 10)
"""

from __future__ import annotations

BASH_PREVIEW_LINES = 5
READ_PREVIEW_LINES = 10
DEFAULT_PREVIEW_LINES = 10
TERMINAL_COMMAND_PREVIEW_LINES = 120

_NO_TRUNCATION_TOOLS = frozenset({"edit", "write"})
_PREVIEW_BY_TOOL = {"bash": BASH_PREVIEW_LINES, "read": READ_PREVIEW_LINES}


def preview_budget(tool_name: str) -> int | None:
    """Return the collapsed preview line budget, or None to show everything."""
    if tool_name == "__terminal__":
        return TERMINAL_COMMAND_PREVIEW_LINES
    if tool_name in _NO_TRUNCATION_TOOLS:
        return None
    return _PREVIEW_BY_TOOL.get(tool_name, DEFAULT_PREVIEW_LINES)
```

`state.py` 改动：把 `format_tool_result_block` 里三处硬编码常量换成 `preview_budget(name)`；
`full=True` 时仍返回全文（现有语义不变）。**注意** `_preview_text(max_lines=...)` 需要一个
"不截断"表示——`None` 时直接返回全文，要在函数签名里加 `max_lines: int | None`。

- [ ] **Step 5: 跑测试**

Run: `uv run pytest tests/coding/rendering/test_tool_preview.py tests/coding/tui/test_tui_full_output.py tests/coding/tools -v`
Expected: 全 passed。**如果有旧测试断言"8 行预览"，那是行为有意变更**——按仓库 Hard Rule，**改断言并在 commit message 里说明 "behavior intentionally changed: per-tool preview budgets"**，不许加 skip 或放宽。

- [ ] **Step 6: 提交**

```bash
git add -u && git commit -m "feat(tool-preview): per-tool collapsed preview budgets (bash 5 / read 10 / edit-write full)

Behavior intentionally changed: tool result previews no longer share one
8-line budget. Verified against pi's per-renderer constants."
```

---

## Task 5: 消息卡片底色（TranscriptMessageWidget）

**Files:**
- Modify: `src/baldric_coding/tui/widgets/core.py:219-300`（`TranscriptMessageWidget`）、`_chat_item_role_style`
- Modify: `src/baldric_coding/rendering/themes/baldric-dark.json`（新增 `roles.user.background` 等）
- Test: `tests/coding/tui/test_tui_app.py`

**Interfaces:**
- Consumes: `ThemeTokens.role_user_bg / role_tool_pending_bg / role_tool_success_bg / role_tool_error_bg`（Task 1）
- Produces: 卡片底色；`TranscriptMessageWidget` 继续接受 `theme: TuiTheme`（**签名不变**）

- [ ] **Step 1: 影响面与风险核实（必做）**

```bash
sed -n '219,300p' src/baldric_coding/tui/widgets/core.py
git grep -n "_BORDERLESS_TRANSCRIPT_ROLES" -- src
git grep -n "styles.background" -- src/baldric_coding/tui/widgets/core.py
```
写下：
- `_BORDERLESS_TRANSCRIPT_ROLES = {"assistant", "thinking"}` —— **这两类故意不设背景**，改动不能把它们一起染色。
- **三个 bug 场景**：① user 角色已有 `self.styles.padding = (1, 0)`（:284）叠背景会不会挤掉边距；② 灰度终端（`TERM=vt100`）下 `#1e1e1e` 与 `#0a0a0a` 可能同色，卡片不可见——需要**只用色相差**或加深；③ `role_styles` 字典里没有 `tool_success` 这个 key（当前没有），加字段要**同时**保证 `TRANSCRIPT_ROLES` 不变（它是 `ChatItemRole` 的单一真相），所以 tool 三态底色**不能**通过新增 role 名实现，要通过 `roles.tool` 的子键。
- **接口决策**：`TranscriptMessageWidget` 拿的是 `TuiTheme`，拿不到 `ThemeTokens`。两条路：① 给 `TuiTheme` 加字段（违反"字段集合不变"）；② 让 `TuiTheme.role_styles["tool"]` 的 body 里带背景（现有机制已支持 `"fg on bg"`）。**选 ②**，因为它零接口变更。

- [ ] **Step 2: 写失败测试**

```python
# 追加到 tests/coding/tui/test_tui_app.py
def test_user_message_has_a_card_background() -> None:
    from baldric_coding.rendering.themes import BALDRIC_DARK_THEME
    from baldric_coding.tui.state import ChatItem

    item = ChatItem(role="user", text="hello")
    widget = TranscriptMessageWidget(item, theme=BALDRIC_DARK_THEME, show_tool_results=False)
    assert widget.styles.background is not None


def test_assistant_message_has_no_card_background() -> None:
    from baldric_coding.rendering.themes import BALDRIC_DARK_THEME
    from baldric_coding.tui.state import ChatItem

    item = ChatItem(role="assistant", text="hi")
    widget = TranscriptMessageWidget(item, theme=BALDRIC_DARK_THEME, show_tool_results=False)
    assert widget.styles.background in (None, Color.parse("transparent"))
```

- [ ] **Step 3-5: 红 → 实现 → 绿**

实现要点：在 `baldric-dark.json` 的 `roles.user.body` 从 `"#d8dee9 on #101419"` 改为更可见的
`"#d8dee9 on #1e2430"`（**值抄 opencode `background.raised.base` 的亮度级**，注释标来源）；
`roles.tool` 保持无背景（pending 用 `border` 表达状态）。**不要动 `_BORDERLESS_TRANSCRIPT_ROLES`。**

- [ ] **Step 6: 提交**

```bash
git add -u && git commit -m "feat(tui): give user messages a visible card surface"
```

---

## Task 6: diff 整行底色（"回复高亮"）

**Files:**
- Modify: `src/baldric_coding/rendering/diffs.py:221-237`（`_line_text`）、`:210-218`（`_render_single_line`）
- Modify: `src/baldric_coding/rendering/themes/baldric-dark.json`（新增 `diff` 段）
- Test: `tests/coding/rendering/test_diffs.py`

**Interfaces:**
- Consumes: `ThemeTokens.diff_added_bg / diff_removed_bg / ...`（Task 1）
- Produces: `render_patch()` 返回的 `Text` 每行带背景；**签名不变**

- [ ] **Step 1: 影响面与风险核实**

```bash
sed -n '150,240p' src/baldric_coding/rendering/diffs.py
git grep -n "render_patch\|_line_text" -- src tests
python - <<'PY'
# 确认 Rich Text 支持 style 背景如何与现有 stylize 共存
from rich.text import Text
t = Text("-x")
t.stylize("on #20303b", 0, 2)
t.stylize("bold #4fd6be", 1, 2)
print(t.spans)
PY
```
写下：① `_GUTTER_OFFSET` 是手算的（`2*4+2`），加背景**不能**破坏词级高亮的偏移；② 三个 bug 场景：空 patch（`render_patch` 返回 None）、内容以 `--` 开头的行（Task 前已修过 hunk 计数判定，要确认底色不影响它）、超长行折行时背景断不断；③ **来源**：`opencode-dev/packages/tui/src/theme/assets/v2/opencode.json` 的 `base.diff`（added `#4fd6be`/removed `#c53b53`，bg `#20303b`/`#37222c`，lineNumber `#8f8f8f`）。

- [ ] **Step 2: 写失败测试**

```python
def test_added_line_has_a_background() -> None:
    from baldric_coding.rendering.diffs import render_patch
    from baldric_coding.rendering.themes import BALDRIC_DARK_THEME
    from rich.console import Console
    from io import StringIO

    patch = "--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new\n"
    console = Console(record=True, width=80, color_system="truecolor", file=StringIO())
    console.print(render_patch(patch, theme=BALDRIC_DARK_THEME))
    out = console.export_text(styles=True)
    assert "48;2;32;48;59" in out or "on #20303b" in out  # added bg present
```

- [ ] **Step 3-5: 红 → 实现 → 绿**

实现：`_line_text` 里给整行 `Text` 先 `stylize(f"on {bg}", 0, len(text))`，再叠加词级 `bold`
（顺序很重要：**背景先铺，强调后加**，否则强调会覆盖背景）。`render_patch` 增加可选参数
`tokens: ThemeTokens | None = None`，为 `None` 时保持现有行为（**向后兼容**）。

- [ ] **Step 6: 提交**

```bash
git add -u && git commit -m "feat(diff): row backgrounds for added/removed lines (opencode palette)"
```

---

## Task 7: 状态行合并 + prompt 边框随 thinking 等级

**Files:**
- Modify: `src/baldric_coding/tui/app.py`（`#compact-session-info`、`#prompt` CSS、`_refresh`）
- Test: `tests/coding/tui/test_tui_app.py`

- [ ] **Step 1: 核实**

```bash
git grep -n "compact-session-info\|render_compact_session_info" -- src
sed -n '738,760p' src/baldric_coding/tui/app.py
git grep -n "thinkingOff\|thinking_levels\|available_thinking_levels" -- src/baldric_coding | head
```
写下：① 状态行数据来自 `session.session_stats`，**不许新增查询**；② prompt 边框色要能随
`thinking` 等级变，现有 `prompt_border` 是单值，**怎么传等级色**（方案：在 `_refresh` 里按
`state.thinking_level` 从 `theme.role_styles["thinking"].border` 派生，或新增 token）；
③ 三个 bug：窄终端（<80 列）状态行会折行、`thinking` 等级未知时的 fallback、CJK 字符宽度。

- [ ] **Step 2-5: 红 → 实现 → 绿**

测试断言：状态行包含 `cwd`、`model`、`context` 百分比、`cost` 四个字段（用 `Console.record`）。

- [ ] **Step 6: 提交**

```bash
git add -u && git commit -m "feat(tui): single-line status bar and thinking-tinted prompt border"
```

---

## Task 8: 侧栏默认收起 + Ctrl+B

**Files:**
- Modify: `src/baldric_coding/tui/app.py:360`（`SIDEBAR_MIN_WIDTH` 附近）、CSS、`BINDINGS`、`_update_responsive_layout:3790`
- Test: `tests/coding/tui/test_tui_app.py`

- [ ] **Step 1: 核实**

```bash
sed -n '355,370p' src/baldric_coding/tui/app.py
sed -n '3785,3805p' src/baldric_coding/tui/app.py
git grep -n "TOGGLE_SIDEBAR\|_toggle_sidebar_visibility\|ctrl+b" -- src
```
写下：① 现在侧栏是**响应式**（宽度 ≥96 自动显示），改成"默认收起"会改变**所有用户的默认观感**——
确认这是用户 D6 明确要的；② 三个 bug：宽屏用户第一次启动会以为侧栏消失了（需要一次性提示？）、
`_sidebar_visibility_override` 与响应式的优先级、`Ctrl+B` 与现有键位冲突。
③ **注意 `extensions` 分区在 `sidebar.py` 出现两次（:211 和 :355）**——这是本计划标记的"烂代码"之一，
本任务**只做默认收起，不顺手改**；要改单独开 task（见 Task 8b）。

- [ ] **Step 2-5: 红 → 实现 → 绿**

测试：`app.run_test(size=(120,40))` 断言初始 `"-hide-sidebar"` 类存在；`pilot.press("ctrl+b")` 后消失。

- [ ] **Step 6: 提交**

```bash
git add -u && git commit -m "feat(tui): sidebar starts collapsed; Ctrl+B toggles it"
```

### Task 8b（可选，必须先问）：澄清侧栏 `extensions` 分区重复

若 Task 8 的 Step 1 核实发现 `sidebar.py:211` 与 `:355` 确实渲染两次 `extensions`，
**先单独提一个 issue / 问用户**，不要在本批顺手修——它属于"现有烂代码"，按开工前第 5 条要
"单独核查、单独 commit、说明原行为"。

---

## Task 9: 截图对比 + 人工验收（第一批收口）

**Files:**
- Create: `dev-notes/architecture/tui-visual-batch1-acceptance.md`（记录截图与结论）
- 不改代码

- [ ] **Step 1: 出图**

用 headless `app.export_screenshot()`（现有 Textual API）出 4 张：
① 对话页（含 user 卡片、edit diff、bash 输出、thinking 折叠）② 会话选择器 ③ 模型选择器 ④ `baldric-light` 主题。
**注意**：截图前 `del os.environ["NO_COLOR"]`（本项目 CI/某些 shell 带 `NO_COLOR=1`，会导致截图全灰，之前踩过）。

- [ ] **Step 2: 与参照并排对比**

把 `opencode-dev/packages/tui/src/theme/assets/` 与 `pi-main/.../docs/images/interactive-mode.png` 作为参照，
逐项打勾：卡片可见 / diff 有底色 / 工具行有耗时 / 状态行一行 / 侧栏默认收起。

- [ ] **Step 3: 全量闸门**

```bash
uv run pytest -q --ignore=tests/coding/tui   # 快速套件
uv run pytest -q tests/coding/tui            # TUI 套件（Windows 可能 flaky，重跑一次）
uv run ruff check . && uv run ruff format --check .
uv run python scripts/check_import_graph.py
uv run python scripts/check_structure.py
uv run python scripts/check_suppressions.py
```
Expected: 全绿（mypy 只剩 14 个已知 fcntl 噪音）。

- [ ] **Step 4: 写验收记录并提交**

```bash
git add dev-notes/architecture/tui-visual-batch1-acceptance.md
git commit -m "docs: batch-1 visual acceptance record with screenshot comparison"
```

---

## 自检（写完后自查，已执行）

**1. Spec 覆盖检查**

| Spec 章节 | 对应 Task |
|---|---|
| §4.1/4.2 schema 结构 + 5 套主题 | Task 1, 3 |
| §4.3 兼容与校验（双格式） | Task 2（`colors` passthrough） |
| §5.0 数据来源 | Task 4, 5（用 `ChatItem` 字段） |
| §5.1 消息卡片 | Task 5 |
| §5.2 工具行分级预算 + 计时 | Task 4（预算）+ Task 5 附录（计时在 `+N −M · 4.2s`） |
| §5.3 diff 高亮 | Task 6 |
| §5.4 输入区 + 状态行 | Task 7 |
| §5.5 侧栏默认收起 | Task 8 |
| §9 验收标准 | Task 9 |
| §13 v1.0 迁移路线 | 不属第一批（v0.3.x 期间准备，见 spec §13.4） |

> **缺口（有意留到第二批）**：§5.2 的"计时行 `4.2s`"完整实现依赖工具行右侧布局，本批只在
> Task 5 里给出 `started_at` 的取数位置；完整渲染放第二批（spec §6 L3）。

**2. 占位符扫描**：本计划唯一的 `NotImplementedError` 在 Task 3 的 `okhsl_to_hex`——**这是有意的**，
因为该函数必须**照抄** `pi-main/packages/tui/src/oklab.ts` 的数学（要求第 4 条：先参考实现，不自己写）。
执行者必须读那个文件后填充，并写 4 条比对单测。除此之外无 TBD/TODO。

**3. 类型一致性**：`ThemeTokens` 字段在 Task 1 定义、Task 5/6 消费，名称一致
（`role_user_bg` / `diff_added_bg` / `surface_raised`）。`preview_budget` 在 Task 4 定义并自用。
`project_to_tui_theme` 在 Task 2 定义、Task 3 消费。

---

## 执行方式

计划完成，已保存到 `docs/superpowers/plans/2026-11-08-tui-visual-batch1.md`。两种执行方式：

1. **子代理驱动（推荐）**：每个 Task 派一个新 subagent，任务间我来 review，迭代快、上下文干净。
2. **本会话内联执行**：在当前会话里按 executing-plans 批量执行，带检查点。

选哪种？
