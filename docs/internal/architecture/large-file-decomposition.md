# 大文件拆解：拆了什么，刻意没拆什么

**状态：** TUI 与 session 拆解完成（2026-11-06）。

本笔记记录大模块的逻辑现在住在哪里、塑造拆分的约束，以及刻意保持完整的单元——让未来变更从有依据的立场出发，而不是重新发现同样的边界。

## 模式：模块函数之上的类型化门面

`CodingSession` 与 `BaldricTuiApp` 按设计就很宽。项目既有约定
（`session/runtime.py`、`session/tree_helpers.py`……）是：

- **真正的逻辑住在模块级函数里**，全类型化；
- **类保留薄成员**，签名与 docstring 不变，调用点永不改。

这对类型安全很重要。在 mixin 里把 `self` 类型化为具体类会被 mypy 拒绝：

```text
The erased type of self "…CodingSession" is not a supertype of its class "…Mixin"
```

唯一 mixin 兼容的选项是 `self: Any`——恰好在最需要 `--strict` 的代码上静默关闭它。所以：

- **核心逻辑 → 接收 `session: CodingSession` 的模块函数**（完整检查）；
- **呈现胶水 → 带 `Any` 的 mixin**（TUI picker/reconcile；函数体是 screen 编排，不是算法）。

## 抽出了什么

| 区域 | 之前 | 之后 | 新家 |
| --- | --- | --- | --- |
| `tui/app.py` | 5782 | **4472** | `tui/pickers.py`（model/theme）、`tui/session_pickers.py`（session/tree/skill/login）、`tui/extension_components.py`（slot/侧栏/主视图 reconcile 及其 handle/桥类），加中立的 `tui/session_records.py`、`tui/text_utils.py`、`tui/login_providers.py` |
| `session/session.py` | 2232 | **1931** | `session/model_runtime.py`（HF 路由 failover、header 驱动路由、运行时 provider 构建/激活/刷新、模型限制、成本计价）、`session/branching.py`（分支/树/标签 + `TREE_RUNNING_MESSAGE` 与两个树 dataclass，再导出） |

（基线行数来自 `structure-baseline.json`。）

## 拆分中发现的约束

1. **Textual 只从具体类的 `__dict__` 注册 `@on(...)` handler。** 挪进 mixin 的装饰 handler 永不触发——侧栏测试抓到了它。`on_sidebar_file_open_requested` 因此留在 `BaldricTuiApp`。
2. **`tui/screens/login.py` 经 `_app_module().get_oauth_provider(name)` 解析 OAuth**
   （`screens/sidebar.py` 对其写 helper 同理）。那些名字必须保持可从 `baldric_coding.tui.app` 导入，否则每个没有显式登录闭包的 OAuth 登录会在**worker 内部**抛 `AttributeError`——用户看不见，只有缺失的 screen 暴露它。
3. **`monkeypatch` 目标随代码移动。** patch `tui_app.<name>` 的测试在消费者移动后失效；每个 patch 现在指向真正调用该名字的模块。
4. **名字冲突。** `session/compaction/` 已是包；新的 `session/compaction.py` 会被它遮蔽。新 session 模块住在它旁边，不占包名。

## 刻意保持完整

以下每项都评估过并保持原样。只在陈述的触发条件出现时重访。

| 单元 | 大小 | 为什么不拆 |
| --- | --- | --- |
| `CodingSession.load()` | 297 行、47 条顶层语句 | 一条线性构造流程，各阶段共享约 12 个局部变量（`config`、`state`、`entries`、`pending_initial_entries`、`extension_runtime`、`resource_paths`、`resources`、`summary`、`trust_resolution`…）。拆分意味着 8 个各带 10+ 参数的函数，或一个新的可变 context 对象——都在信任/持久化顺序（最易出错处）周围加间接层。**触发：** 某个变更需要单独测试或复用一个阶段。 |
| `CodingSession.__init__()` | 80 行、51 条语句 | 纯字段赋值（60+ 状态字段）。没有逻辑可抽；移动赋值只是搬家，还有静默丢一条的风险。**触发：** 字段分组到足以有第二个状态对象。 |
| `session/lifecycle.reload()` | 216 行 | 已是模块函数；与 `load()` 相同的共享局部变量论证。**触发：** reload 各步骤分歧到可独立测试。 |
| `tui/app.py` 其余 | 4472 行、61 语句热点 | 剩余成员是应用生命周期、prompt/运行路径、事件 handler 与渲染胶水——正是"应用本身"的部分。被抽出的家族是有干净接缝的那些。**触发：** 出现新的内聚家族，或 Textual 适配器边界移动。 |
| `session/export/html.render_session_html()` | 1005 行但只有 24 条语句 | 实测而非假设：文件 59% 是字符串字面量，该函数是一个带插值的 11,316 字符 HTML/CSS/JS 模板。它是模板产物不是逻辑；结构棘轮已经给它打了低分。**触发：** 模板长出属于独立文档的区块。 |

`compaction` 原型化后**被回退**：那些方法已经是对
`session/runtime.py` 的纯委托，抽取只是加了一个模块和一层，没移走任何逻辑。

## 守卫

- `scripts/check_structure.py` —— 文件大小、函数语句、扇出；经 `--init` 记录已评审的增长。
- `scripts/check_suppressions.py` —— `# type: ignore` / `# noqa` 只能缩小。
- `scripts/check_agent_guidance.py` —— 指令文件（`AGENTS.md`/`CLAUDE.md`）
  只能缩小；**架构笔记属于 `dev-notes/`，不属于那里。**
- `tests/coding/tui/test_picker_extraction.py` —— picker/reconcile 方法来自
  mixin，绝不在应用上重定义。
- `tests/coding/session/test_session_module_layout.py` —— session 类保持
  纯门面（无 mixin 基类），树类型单源并再导出，模块函数支撑类成员。

## 验证此处的未来变更

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run python scripts/check_structure.py
uv run python scripts/check_suppressions.py
uv run python scripts/check_agent_guidance.py
uv run python scripts/check_import_graph.py
uv run pytest -q tests/coding/tui/test_picker_extraction.py tests/coding/session/test_session_module_layout.py
```

完整 TUI 套件在 Windows 上偶发 flaky（asyncio 后端）；在 Linux CI 上跑，Windows 上单独运行 `tests/coding/tui/test_tui_app.py` 及其他模块。
