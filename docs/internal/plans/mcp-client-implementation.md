# MCP 客户端支持实施计划

> **给执行 agent：** 必需子技能：使用 superpowers:executing-plans 逐任务执行本计划（内联执行；项目所有者已要求不用子智能体）。步骤用勾选框（`- [ ]`）语法跟踪。本计划编码的是已验证的假设而非保证——下文**执行规则**一节约束每个任务，优先级高于方便性。

**目标：** 给 Baldric 一个 MCP 客户端——已配置服务器的工具成为普通 agent 工具——以 `baldric_mcp`（新顶层包）加一个薄的内置 extension 呈现，协议委托给官方 `mcp` Python SDK。

**架构：** `baldric_coding/extensions/builtins/mcp → baldric_mcp → baldric_protocol`。agent 内核永不得知 MCP 存在；MCP 工具经 extension API 进入。连接监护遵循 pi 的状态机（`connecting/connected/disconnected/needs-auth/failed/closed`，掉线惰性重连）。动态工具可见性骑在两条已验证的小接缝上：harness 每轮读 `config.tools`，system prompt 经 `refresh_system_prompt()` 重建。

**技术栈：** Python 3.12、anyio、pydantic、官方 `mcp` SDK（稳定 1.x）、pytest + anyio 插件、ruff + mypy strict。

**规格：** `dev-notes/design/mcp-client-support.md`（v2）。本计划从规格出发展开论证；执行者两份都读。规格与本计划冲突时，停下来在写代码前先调和。

## 全局约束

- 所有命令的仓库根：`D:\DEVELOP\Solis\baldric`。一切经 `uv run` 运行（自家规则）。
- Python `>=3.12`；mypy `strict`；ruff `line-length=110`、双引号、规则 `E,F,I,UP,B,SIM`；覆盖率下限 80%。
- 导入方向：`baldric_coding → baldric_mcp → baldric_protocol`。`baldric_mcp` 不得导入 `baldric_agent`、`baldric_ai`、`baldric_coding`、`textual`、`rich`；`baldric_agent`/`baldric_ai` 不得导入 `baldric_mcp`。由 `scripts/check_import_graph.py` 与 `tests/guards/test_import_boundaries.py` 强制。
- `src/baldric_mcp/` 下任何地方不得出现 Textual/Rich 导入。
- 工具名在 1.0 冻结：`mcp__<server>__<tool>`，净化为 `[A-Za-z0-9_]`，≤ 64 字符，溢出/冲突加 sha256-8 后缀。
- 配置：顶层 `mcpServers` 键（pi/Claude Desktop 兼容）；项目文件 `.baldric/mcp.json` 仅在项目受信任时加载。
- 截断：面向模型的文本上限 20 KiB，保留首尾，全文存文件且注记携带路径（pi 的规则）。
- 已知 Windows 限制不由你修：POSIX-only 模块的 14 个 mypy 错误、约 121 个跳过测试、TUI 测试偶发 flaky。不要在其他地方加平台垫片去"修"它们。
- 棘轮：`# type: ignore`/`# noqa` 计数只能缩小；结构门增长用 `--init` 记录，绝不弱化基线。
- 下面每个任务都以**验证（Verify）**步骤开始。验证步骤是强制的：写任何东西之前先读指名的代码。若某个标了 **MUST-HOLD** 的事实不成立，停下，更新规格/计划并重新评审——不要即兴（项目所有者硬规则：严禁没有想清楚就动手）。这是下限不是上限：下面的**执行规则**一节把它扩展到每个动作。
- 编辑规则（自家规则）：只用编辑器工具；绝不用脚本/sed 批量改写文件。
- 每任务质量门：触碰的文件跑 `uv run ruff check . && uv run ruff format --check .`，跑 `uv run mypy`，每次提交前跑快速套件 `uv run pytest -q --ignore=tests/coding/tui`。
- 异步测试用自家模式：模块级 `pytestmark = pytest.mark.anyio` 加返回 `"asyncio"` 的 `anyio_backend()` fixture（见 `tests/coding/extensions/test_extensions.py:55-59`）。
- 提交按任务原子化并写显式路径（`git add <path>...`），不用 `git add -A`。

## 执行规则（所有者授权，约束性）

项目所有者于 2026-11-08 制定这些规则。它们适用于本计划的每个任务、步骤、修复与偏差，优先级高于方便性。

### R1 — 计划是假设；每个动作前重新验证

本计划中的每条路径、行号、签名与行为声明都在计划撰写时验证过一次。不保证仍然成立：工作树在动，计划本身也可能就是错的。

- 每个任务开始前——以及任何触碰代码的步骤之前——重新打开指名的文件，确认该步骤依赖的事实。grep 周边区域找漂移（新调用者、改名符号、变更签名），而不是按计划的行号或记忆导航。
- 现实与计划不一致时，计划让步。停下，先调和计划/规格，再继续。严禁没有想清楚就动手。

### R2 — 动手前列全影响面（看全面）

修改任何既有文件——哪怕一行——之前，枚举其影响面并记录在任务笔记或 commit message 里：

- 两个方向：谁调用/导入该符号，以及它调用/导入什么——grep `src/`、`tests/`、`scripts/`、`website/`。
- 哪些测试与守卫（`tests/guards/`、棘轮基线）钉住当前行为、会在变更时报警。
- 行为的下游消费者：TUI、print mode、RPC、命令、session 文件/恢复、文档。
- pi 参考树在同一条接缝处做什么（见 R3）。

没有枚举影响面的变更不做。若影响面比计划假设的大，那是计划缺陷：回到 R1。

### R3 — 重要问题、bug 与设计先问 pi

每当出现重要问题、bug 或设计决策——不只是本计划预料的那些——先看 pi 怎么解决同一件事，再自己发明。pi 树在 `D:\DEVELOP\Solis\pi-main`；MCP 代码在 `pi-main/packages/mcp/` 与
`pi-main/packages/coding-agent/src/extensions/mcp/`。记录 pi 做了什么、为什么，然后适配到 Baldric 的架构——移植判断，不必然移植代码。pi 没有等价物时，在笔记里说明并从第一性原理推理。

### R4 — 允许偏差，但绝不静默

超出本计划的真正必要的工作——包括改动规格触点表之外的既有代码——是允许的。每条偏差必须：

1. 说明按原文执行的计划为何错误或不足——一条来自 R1/R2 的具体事实，不是偏好。
2. 携带 R2 的完整影响面分析。
3. 达到 R5 的质量线；偏差绝不许可更松的设计。
4. 追加到本文件末尾的**执行偏差日志**，并在 commit message 里带 `deviation:` 注记。
5. 若它改变*设计*（不只是实现路线），先向所有者报告再继续。

### R5 — 质量线：高内聚、低耦合、可维护

- `baldric_mcp` 保持自包含：config、connection、supervision 与 adaptation 各住自己的模块；`baldric_coding` 里的 extension 层保持为它们之上的薄胶水。
- 加进 agent 内核的每条接缝（`bind_live_tools`、`refresh_system_prompt`、`unregister_tool`）必须是带通用名字的通用能力——没有 MCP 专属语义泄进内核。接缝无法通用陈述时，设计就是错的：回到 R1。
- 触碰的每个文件匹配其自家风格；新模块遵循既有包约定（pydantic 模型、显式异步边界、类型化 dataclass）。
- 高级工程师读最终 diff 应当觉得没有过度设计、没有炫技。

---

### 任务 0：飞行前影响面验证（只读，无代码）

**文件：** 不新建。发现以一小节追加进
`dev-notes/design/mcp-client-support.md`（"Implementation preflight findings"），单独提交。

**接口：**
- 产出：后续每个任务依赖的已确认事实（或规格修正）。

- [x] **步骤 1：验证工具物化链（MUST-HOLD）**

读 `src/baldric_coding/session/session.py:805-870` 与
`src/baldric_agent/harness.py:55-90, 336-370`。确认：

1. `tools = _filter_tools(extension_runtime.compose_tools(base_tools), config.allowed_tool_names)`
   在 session 构造时物化一份列表（`session.py:818`）。
2. 同一个列表对象交给 `AgentHarnessConfig(tools=tools)` 与
   `build_system_prompt(tools=tools)`。
3. `AgentHarnessConfig` 是 `@dataclass(slots=True)` 带
   `tools: list[AgentTool]`（`harness.py:66-71`）——非冻结，字段可赋值。
4. `run_agent_loop(..., tools=self._config.tools, ...)` 每轮读该字段
   （`harness.py:356`），`system=self._config.system` 同理（`:352`）。

任何一条不成立就停：live-seam 设计是错的，必须先修规格再写代码。

- [x] **步骤 2：验证子 session 与 extension runtime（Task 7 门的 MUST-HOLD）**

读 `src/baldric_coding/extensions/runtime.py:1034-1080`（`compose_tools`）、
`src/baldric_coding/session/provider_helpers.py:252`（`_filter_tools`），并 grep
`src/baldric_coding/extensions/builtins/subagents/` 找子 session
构造（`CodingSession` / `CodingSessionConfig(` 用法）。判定：

- subagent 子 session 是否走同一 `CodingSession.load` 路径并加载 built-in extension？
- 若是：Task 7 的门必须是真实旗标。记录确切构造点；Task 6 增加 `CodingSessionConfig.mcp_enabled: bool = True`，subagents 子构造传 `mcp_enabled=False`。
- 若否：门是文档化的恒真函数（无旗标——YAGNI），Task 6 的配置字段变更取消。

记录结论与确切 file:line 证据。

- [x] **步骤 2b：验证重绑生命周期矩阵（Task 7 守卫的 MUST-HOLD）**

读 `src/baldric_coding/session/lifecycle.py:440-455`（reload：旧 runtime 关闭、新的 staged runtime 启动）与 `lifecycle.py:700-764` +
`lifecycle.py:925-940`（new/resume/branch：`type(session).load(...)` 带
`extension_runtime=session._extension_runtime` 于 `:740`，随后在同一 runtime 上
`emit_session_shutdown(reason)` 再 `emit_session_start(reason)`）。记录矩阵：

| 原因 | runtime 实例 | shutdown 触发 | start 触发 |
| --- | --- | --- | --- |
| startup | 全新 | 否 | 是 |
| reload | 全新（staged） | 是（旧） | 是（staged） |
| new/resume/branch | 与之前相同 | 是 | 是 |
| quit | 相同 | 是 | 否 |

**MUST-HOLD**：new/resume/branch 复用 runtime，所以朴素的
`session_start` handler 会构建第二个 supervisor。Task 7 的 handler 必须幂等（已有活动 supervisor → 仅重新同步）。另外验证并记录（读 `runtime.py:1034-1060`）`compose_tools` 在重绑时把 registry 工具重新合并进重建列表——计划绝不能加任何 re-seed 机制。单独记录既有观察：`config.tools` 非空的重绑会再次包裹已包裹的工具（`lifecycle.py:716` +
`runtime.py:1046`）——影响所有 extension，本分支不修；记给未来 issue。

- [x] **步骤 2c：验证工具执行器签名与 print/RPC 输入路径**

1. 读 `src/baldric_protocol/tools.py:64-111`：确认 `ToolExecutor` 是
   `(tool_call_id, arguments, signal, on_update) -> Awaitable[AgentToolResult]` 且 `AgentTool.execute` 转发全部四个（Task 5 的 `on_update` 映射依赖于此）。**MUST-HOLD。**
2. 读 print mode（`-p`）与 RPC mode 如何到达第一个 prompt（grep
   `run_input_hooks` 调用者于 `src/baldric_coding/`）。记录第一轮准入等待是否适用于每种模式。若有模式绕过 hook，在文档任务里记为已知限制（live 接缝仍在后续轮次送达工具）。

- [x] **步骤 3：验证 prompt 构建器输入（`refresh_system_prompt` 的 MUST-HOLD）**

读 `src/baldric_coding/context/system_prompt.py:55-90`
（`BuildSystemPromptOptions`、`build_system_prompt`）与
`src/baldric_coding/session/lifecycle.py:420-480`（重新存储 `resources.*` 字段的 reload 路径）。确认 `session.py:819-846` 使用的每个 `BuildSystemPromptOptions` 输入都能被同一作用域构建的零参闭包捕获（`config.*`、`resources.*`、`extension_runtime.*`、局部 `tools`）。
列出该作用域内不稳定的输入；这类输入必须在 Task 6 依赖闭包之前存到 session 上。

- [x] **步骤 4：验证输入 hook 接缝（第一轮准入的 MUST-HOLD）**

读 `src/baldric_coding/session/runtime.py:320-345`。确认
`run_input_hooks` 在运行开始前 await，返回 `None` 时照常继续。确认 `input` hook 收到
`InputEvent(source=...)`（`extensions/api.py:484-502`）。

- [x] **步骤 5：验证 resume/修复与未知工具行为**

读 `src/baldric_agent/harness.py:336-356`（前奏
`_append_interrupted_tool_results`）与 `src/baldric_agent/tool_history.py`。
再读 `src/baldric_agent/loop.py` 的工具解析（grep
`tool_calls`/按名查找）：记录模型调用不在 `tools` 里的名字时发生什么（预期：合成错误结果到达模型；记下确切机制）。若未知工具改为抛异常，记录之——Task 9 钉住实际存在的行为，规格的"工具不可用"承诺在 adapter 层实现（被撤回的 MCP 工具保持注册、带错误执行器），而不依赖 loop 行为。

- [x] **步骤 6：验证 BoundSession 协议面**

读 `src/baldric_coding/extensions/runtime.py` 的 `class BoundSession` 与
`bind`。确认往协议加 `refresh_system_prompt() -> None` 的位置，且 `runtime._session` 是被绑定的 session（Task 6 的 `request_system_prompt_refresh` 使用）。

- [x] **步骤 7：提交发现**

向 `dev-notes/design/mcp-client-support.md` 追加 "## Implementation preflight findings" 小节，写明每条事实与 file:line。提交：

```bash
git add dev-notes/design/mcp-client-support.md
git commit -m "docs: record MCP implementation preflight findings"
```

---

### 任务 1：依赖、包脚手架、导入守卫、SDK 钉死

**文件：**
- 修改：`pyproject.toml`（dependencies、wheel packages、mypy packages）
- 修改：`scripts/check_import_graph.py`（RULES）
- 修改：`tests/guards/test_import_boundaries.py`（相同规则）
- 新建：`src/baldric_mcp/__init__.py`
- 新建：`tests/mcp/__init__.py`、`tests/mcp/test_import_direction.py`

**接口：**
- 产出：可导入的空包 `baldric_mcp`；锁定其层位的 CI 守卫；Task 3-5 使用的已钉死 SDK API 契约。

- [x] **步骤 1：加依赖与包注册**

在 `pyproject.toml`：`dependencies` 加 `"mcp>=1.0,<2"`（aliyun 索引有货）；扩展
`[tool.hatch.build.targets.wheel] packages = [..., "src/baldric_mcp"]` 与
`[tool.mypy] packages = [..., "baldric_mcp"]`。然后 `uv sync` 并记录安装版本：

```bash
uv sync
uv run python -c "import importlib.metadata as m; print(m.version('mcp'))"
```

- [x] **步骤 2：把层锁进导入图**

`scripts/check_import_graph.py` 的 RULES 加：
`("baldric_mcp", "baldric_agent")`、`("baldric_mcp", "baldric_ai")`、
`("baldric_mcp", "baldric_coding")`、`("baldric_mcp", "textual")`、
`("baldric_mcp", "rich")`、`("baldric_agent", "baldric_mcp")`、
`("baldric_ai", "baldric_mcp")`。在 `tests/guards/test_import_boundaries.py` 镜像 RULES 的地方原样镜像这七条（先读文件；它导入 `scan_violations` 并复述规则——保持两者同步）。

- [x] **步骤 3：创建包壳**

`src/baldric_mcp/__init__.py`：

```python
"""MCP client core: configuration, connection supervision, tool adaptation.

Protocol work is delegated to the official `mcp` SDK; this package holds only
Baldric's product layer. It must not import `baldric_agent`, `baldric_ai`, or
`baldric_coding` (see scripts/check_import_graph.py).
"""

__all__: list[str] = []
```

`tests/mcp/test_import_direction.py`：断言 `importlib.import_module("baldric_mcp")` 成功的测试。导入图守卫（任务 1 步骤 2）是执行层；这里不做 `__dict__` 内省——不可靠。

- [x] **步骤 4：SDK API 钉死（Task 3-5 之前的 MUST-HOLD）**

读已安装 SDK 源码 `.venv/Lib/site-packages/mcp/`（读，不猜），记录：

1. `mcp/client/stdio/__init__.py`：`stdio_client(server)` 上下文管理器 yield 形状；`StdioServerParameters` 字段（`command`、`args`、`env`、`cwd`——确认钉住的版本是否有 `cwd`）；env 语义——传 `env` 时是原样使用还是与 `get_default_environment()` 合并？记录确切行为；无论哪种，Task 3 都显式传合并后的快照+配置 env。
2. `mcp/client/streamable_http/__init__.py`：`streamablehttp_client(url,
   headers=...)` yield 形状。
3. `mcp/client/session/__init__.py`：`ClientSession` 构造参数
   （`message_handler`？`read_timeout_seconds`？）、`initialize()` 结果字段（`instructions`）、`list_tools()`、`call_tool(name, arguments, ...)` 签名与 `CallToolResult` 字段（`content`、`isError`、`structuredContent`），以及进度通知如何呈现（ServerNotification /
   ProgressNotification 字段 `progress`、`total`、`message`）。
4. HTTP 401 在 `initialize()` 期间如何呈现（异常类型/属性）——Task 3 映射为 `needs-auth`。
5. `mcp/shared/memory.py`：供测试的内存连接 client/server helper（名字与 yield 形状）。
6. `mcp/server/fastmcp`：确认 `FastMCP(name)` + `@mcp.tool()` + `mcp.run()`
   跑 stdio 服务器（Task 9 的 fixture 使用）。

**停止规则：** 1-6 任何一条与 Task 3-5 使用的签名有实质差异，先在本计划文件里调整那些任务的代码、提交计划变更，再继续。绝不边写代码边静默适配。

- [x] **步骤 5：跑门并提交**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -q tests/mcp tests/guards
git add pyproject.toml uv.lock scripts/check_import_graph.py tests/guards/test_import_boundaries.py src/baldric_mcp/__init__.py tests/mcp/__init__.py tests/mcp/test_import_direction.py
git commit -m "feat: add baldric_mcp package scaffold with mcp SDK dependency"
```

---

### 任务 2：`baldric_mcp.config`——解析、合并、展开、写回

**文件：**
- 新建：`src/baldric_mcp/config.py`
- 修改：`src/baldric_coding/config/paths.py`（两个属性）
- 新建：`tests/mcp/test_config.py`
- 仅在需要时修改：`tests/mcp/test_import_direction.py`

**接口：**
- 产出（Task 3/4/7/8 消费）：

```python
ServerType = Literal["stdio", "http"]

@dataclass(frozen=True, slots=True)
class McpServerConfig:
    name: str
    server_type: ServerType
    source: Path | None = None      # file that defined the effective entry
    enabled: bool = True
    description: str | None = None
    timeout: float = 60.0           # seconds, per call
    command: str | None = None      # stdio
    args: tuple[str, ...] = ()      # stdio
    env: Mapping[str, str] = field(default_factory=dict)   # stdio, expanded
    cwd: str | None = None          # stdio, ~-expanded
    url: str | None = None          # http
    headers: Mapping[str, str] = field(default_factory=dict)  # http, expanded

@dataclass(frozen=True, slots=True)
class McpConfigDiagnostic:
    path: str
    name: str            # server name, or "" for file-level problems
    message: str

@dataclass(frozen=True, slots=True)
class McpConfigLoadResult:
    servers: tuple[McpServerConfig, ...]
    diagnostics: tuple[McpConfigDiagnostic, ...]

def load_mcp_config(
    user_path: Path | None,
    project_path: Path | None,
    environment: Mapping[str, str],
) -> McpConfigLoadResult: ...

def set_server_enabled(path: Path, name: str, enabled: bool) -> None: ...
```

`paths.py` 增项（跟随既有 property 风格）：

```python
@property
def user_mcp_config_path(self) -> Path:
    """Return the user-level MCP server config path."""
    return self.home / "mcp.json"

def project_mcp_config_path(self, cwd: Path) -> Path:
    """Return the project-local MCP server config path."""
    return self.project_baldric_dir(cwd) / "mcp.json"
```

- [x] **步骤 1：写失败测试（见下方测试清单）**

`tests/mcp/test_config.py` 的测试用例（每个一个小函数；在 `tmp_path` 下构建 JSON
文件）：

1. stdio 条目解析：`command`/`args`/`env`/`cwd` → `server_type="stdio"`，默认 `enabled=True`、`timeout=60.0`。
2. http 条目解析：`url`/`headers` → `server_type="http"`。
3. 显式 `type` 必须与字段一致：`{"type": "http", "command": "x"}` → 诊断、条目被拒；`{"type": "stdio", "command": "x"}` 通过。
4. 同时有 `command` 与 `url` → 诊断；两者皆无（且非覆盖条目）→ 诊断。
5. 未知字段产生警告诊断，条目仍加载。
6. `env`/`headers`/`command` 里的 `${VAR}` 展开只用注入的环境；无法解析的 `${MISSING}` → 诊断且条目以 `enabled=False` 加载。
7. `~` 与 `~/x`（`~\x` 语义经同一 helper）在 `command`/`cwd` 中展开；普通路径不动。
8. 同名项目条目替换用户条目；`source` 指向项目文件。
9. 项目覆盖条目（仅 `{"enabled": false}`，无 command/url/type）合并到用户条目，保留其 command/args；带任何其他键的覆盖 → 诊断；没有用户基底的覆盖 → 诊断。
10. 命名空间冲突：用户配置定义 `a-b` 与 `a_b` → 两者都被拒并诊断（`_namespace` 冲突）。
11. 畸形 JSON / 非对象文件 → 文件级诊断，不抛异常。
12. `set_server_enabled(path, "x", False)` 写 `"enabled": false`，保留既有缩进与无关顶层键；
    完整条目上 `set_server_enabled(path, "x", True)` 移除该键，覆盖条目上写 `enabled: true`。
    往返：写后 `load_mcp_config` 反映变更。
13. 文件中禁用的服务器出现在 `result.servers` 且 `enabled=False`
    （`/mcp on` 才能找到它们）。

- [x] **步骤 2：运行并看它们失败**

运行：`uv run pytest -q tests/mcp/test_config.py`
预期：FAIL——`ModuleNotFoundError: No module named 'baldric_mcp.config'`
（或那些名字的导入错误）。

- [x] **步骤 3：实现 `config.py`**

按上述接口实现。规则移植自 pi
（`pi-main/packages/coding-agent/src/extensions/mcp/config.ts`、
`pi-main/packages/mcp/src/naming.ts`）：

- 用 `Path.read_text(encoding="utf-8-sig")` 读取（BOM 安全，pi 的 `stripBom`）。
- 顶层必须是对象；`mcpServers` 可选对象；顶层未知键 → 警告诊断（向前兼容）。
- 命名空间检查：`f"mcp__{name.replace('-', '_')}"` —— 共享命名空间的两个服务器都被拒。
- `${VAR}` 展开用正则 `\$\{([A-Za-z_][A-Za-z0-9_]*)\}` 对照注入的 `environment`；无法解析 → 诊断 + `enabled=False`。
- `~` 展开 helper 处理 `~`、`~/…`、`~\…`。
- 项目覆盖 = 没有 `command`/`url`/`type` 的条目；只允许 `enabled`；经 `dataclasses.replace(base, enabled=..., source=project_path)` 合并。
- `set_server_enabled`：读 → 解析 → 定位条目 → 改动 → 按检测到的缩进写回（`re.search(r"^([ \t]+)\S", text, re.M)` 回退 `"  "`），保留无关内容与尾部换行（移植 pi 的
  `editMcpServers`）。完整条目 `enabled=True` 删除键，覆盖条目写入键。

- [x] **步骤 4：加两个 `paths.py` 属性（代码见上方接口）**

- [x] **步骤 5：跑测试、静态门、提交**

```bash
uv run pytest -q tests/mcp/test_config.py
uv run ruff check src/baldric_mcp src/baldric_coding/config/paths.py tests/mcp && uv run ruff format --check src/baldric_mcp src/baldric_coding/config/paths.py tests/mcp
uv run mypy
git add src/baldric_mcp/config.py src/baldric_coding/config/paths.py tests/mcp/test_config.py
git commit -m "feat: MCP server config parsing, merge, expansion, and write-back"
```

---

### 任务 3：`baldric_mcp.client`——每服务器一条受监护连接

**文件：**
- 新建：`src/baldric_mcp/client.py`
- 新建：`tests/mcp/test_client.py`

**接口：**
- 消费：`McpServerConfig`（任务 2）；任务 1 步骤 4 钉死的 SDK API。
- 产出（Task 4/5/9 消费）：

```python
McpConnectionState = Literal[
    "connecting", "connected", "disconnected", "needs-auth", "failed", "closed"
]

@dataclass(frozen=True, slots=True)
class McpToolInfo:
    name: str
    description: str
    title: str | None
    input_schema: Mapping[str, JSONValue]

@dataclass(frozen=True, slots=True)
class McpContentBlock:
    text: str | None = None
    image_data: str | None = None    # base64 as sent by the server
    image_mime: str | None = None

@dataclass(frozen=True, slots=True)
class McpToolResultData:
    blocks: tuple[McpContentBlock, ...]
    is_error: bool

class McpTransport(Protocol):
    """Async context manager yielding (read_stream, write_stream)."""

class TransportFactory = Callable[[McpServerConfig, Mapping[str, str]], McpTransport]

def default_transport(config: McpServerConfig, environment: Mapping[str, str]) -> McpTransport: ...

class McpToolUnavailable(RuntimeError): ...

class McpServerConnection:
    def __init__(
        self,
        config: McpServerConfig,
        *,
        environment: Mapping[str, str],
        transport_factory: TransportFactory = default_transport,
        clock: Callable[[], float] = time.monotonic,
        retry_delays: Sequence[float] = (1.0, 3.0),
    ) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def state(self) -> McpConnectionState: ...
    @property
    def error(self) -> str | None: ...
    tools: tuple[McpToolInfo, ...]          # () until connected
    instructions: str | None                # from initialize()
    async def connect(self) -> bool         # True on connected; False on failed
    async def call_tool(
        self, tool: str, arguments: Mapping[str, JSONValue], *,
        on_progress: Callable[[str], None] | None = None,
    ) -> McpToolResultData                  # lazy reconnect when disconnected
    async def close(self) -> None
```

- [x] **步骤 1：写失败测试**

`tests/mcp/test_client.py`（自家 anyio 模式）。用脚本化的 fake
transport factory——一个带 `__aenter__`/`__aexit__` 的对象，yield
`(fake_read, fake_write)`，且可额外注入 fake `ClientSession`：让构造器接受
`session_factory: Callable[[Any, Any], Any] = _sdk_session_factory`，测试注入带脚本化 `initialize()`、`list_tools()`、
`call_tool()` 结果的 fake session，完全不碰 SDK。用例：

1. 成功连接：状态 `connected`，`tools` 由 `list_tools()` 填充，`instructions` 从 `initialize()` 结果捕获。
2. 瞬时失败后成功：第一次 `initialize()` 抛 `TimeoutError` 类 → 重试延迟后第二次成功（注入即时推进的 `clock` 与微小 `retry_delays=(0.0, 0.0)`）；状态 `connected`；恰好 2 次尝试。
3. 预算耗尽：所有尝试都抛瞬时 → 状态 `failed`、`connect()` 返回 False、`error` 带最后一条消息。
4. 非瞬时失败（如 `ValueError`）→ 立即 `failed`，1 次尝试。
5. HTTP 401 → 状态 `needs-auth`，不重试（fake 抛任务 1 步骤 4 第 4 条钉死的异常类型；SDK 不带状态码时 fake 抛 `McpNeedsAuthError`——在 `client.py` 定义该哨兵并让
   `default_transport` 的错误路径抛它；以任务 1 的发现为准）。
6. 惰性重连：connected → 掉线（fake session 的 `call_tool` 抛一次连接类错误）→ 状态 `disconnected`；下一次 `call_tool`
   重连（session_factory 记录第二次连接）并返回结果。
7. `failed`/`needs-auth`/`closed` 时调用 → `McpToolUnavailable`。
8. 调用超时：fake `call_tool` 睡眠；配置 `timeout=0.05`；看门狗取消；结果为带超时消息的 `McpToolUnavailable`；状态保持
   `connected`（超时是单次调用的，不是连接故障）。
9. 进度：fake session 经钉死的机制发出进度 →
   `on_progress` 收到文本且期限重置（fake clock：第一次进度移动期限；看门狗用注入 `clock`）。
10. 结果映射：文本块 → `McpContentBlock(text=...)`；图片块 →
    `image_data`/`image_mime`；空内容 + `structuredContent` → 一条 JSON 文本块；`isError=True` → `is_error=True`。
11. `close()` → 状态 `closed`；退出 transport 上下文（fake 记录退出）。
12. （已删——钉住的 SDK 经 `stdio_client` 内的
    `get_windows_executable_command` 自行解析 Windows `.cmd`/`.bat`/`.exe` shim；计划中的 `_resolve_windows_command` helper 冗余，已删除。
    stdio 工厂测试改为断言 `config.command` 原样到达
    `StdioServerParameters`。）

- [x] **步骤 2：运行并看它们失败**

运行：`uv run pytest -q tests/mcp/test_client.py`
预期：FAIL（模块缺失）。

- [x] **步骤 3：实现 `client.py`**

关键实现决策（注明处移植自 pi 的
`packages/coding-agent/src/extensions/mcp/runtime.ts`）：

- transport 生命周期经 `contextlib.AsyncExitStack`：连接时
  `stack.enter_async_context(transport_factory(...))`，然后
  `stack.enter_async_context(ClientSession(read, write, ...))`，然后
  `await session.initialize()`。`close()`/失败 teardown 时：
  `await stack.aclose()`（绝不向调用者抛异常）。
- 初始连接重试：次数 = `1 + len(retry_delays)`；只重试
  瞬时错误（pi 的 `isTransientError`：HTTP 408/429/5xx-除-501 与连接类异常——按任务 1 的发现映射到 SDK 实际异常类型；401 → `needs-auth` 不重试）。尝试之间
  `await anyio.sleep(delay)`。
- 单调用期限看门狗（进度重置它）：

```python
async def _call_with_deadline(self, coro_factory, on_progress):
    box: dict[str, object] = {}
    deadline = self._clock() + self._config.timeout
    with anyio.CancelScope() as scope:
        async def watchdog() -> None:
            while True:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    scope.cancel()
                    return
                await anyio.sleep(min(remaining, 0.25))
        async def run() -> None:
            box["result"] = await coro_factory()
        async with anyio.create_task_group() as tg:
            tg.start_soon(watchdog)
            tg.start_soon(run)
    if "result" not in box:
        raise McpToolUnavailable(f"MCP tool call timed out after {self._config.timeout:g}s")
    return box["result"]
```

进度通知经 `call_tool` 的 `progress_callback` 到达
（SDK 1.30.0：`await callback(progress, total, message)`，按请求的 progress token 匹配——`mcp/shared/session.py:409-420`）：映射到
`on_update` 并推迟期限——用一个小的可变 holder 共享期限，回调与看门狗都闭包引用它。加固注记：mypy strict 下 `box["result"]`
需要显式 `cast(object, ...)` 式收窄；超时后 SDK 仍可能送达迟到响应——按请求 id 丢弃，无害；在取消点留一行注释说明，避免未来读者"修"它。`call_tool`
也可能抛（output-schema 校验、内部 `list_tools` 刷新）：executor 逐调用捕获异常并转成错误结果
（任务 5 的回退文本）。

- 惰性重连（pi 的 `disconnected` 语义）：`self._state == "disconnected"` 时
  `call_tool` 执行一次 `connect()`；失败抛
  `McpToolUnavailable(self._error or ...)`。
- `default_transport`：http →
  `streamable_http_client(config.url, http_client=create_mcp_http_client(headers=dict(config.headers)))`
  （SDK 1.30.0 把 `streamablehttp_client` 改名为 `streamable_http_client` 并把 headers/超时移到 httpx 客户端；旧名已弃用——用新名；yield 是 `(read_stream, write_stream, get_session_id)`）；
  stdio → 原样传 `config.command`（SDK 自行解析 Windows shim——见测试 12），然后
  `stdio_client(StdioServerParameters(command=..., args=list(config.args),
  env={**environment, **config.env}, cwd=config.cwd))`（钉住的 SDK 有 `cwd`；SDK 把传入 env 合并在 `get_default_environment()` 之上，完整快照盖过那些默认；yield 是
  `(read_stream, write_stream)`）。
- stderr 捕获：SDK 接缝是 `stdio_client(server, errlog=<TextIO>)`——
  构造 kwarg 是 `stderr_sink: TextIO | None = None`（任务 10 打开日志文件传入）。HTTP transport 没有 stderr。
- `initialize()` 期间的 HTTP 401 表现为 `httpx.HTTPStatusError`
  （POST handler 里的 `response.raise_for_status()`，`streamable_http.py:381`），
  可能被包进 anyio `ExceptionGroup`；`connect()` 解包组并把状态 401 映射为 `needs-auth`。

- [x] **步骤 4：跑测试、门、提交**

```bash
uv run pytest -q tests/mcp/test_client.py
uv run ruff check src/baldric_mcp && uv run ruff format --check src/baldric_mcp && uv run mypy
git add src/baldric_mcp/client.py tests/mcp/test_client.py
git commit -m "feat: supervised MCP server connection with lazy reconnect"
```

---

### 任务 4：`baldric_mcp.supervisor`——全部连接的所有权

**文件：**
- 新建：`src/baldric_mcp/supervisor.py`
- 新建：`tests/mcp/test_supervisor.py`

**接口：**
- 消费：`McpServerConnection`（任务 3）、`McpServerConfig`（任务 2）。
- 产出（Task 7/8 消费）：

```python
@dataclass(frozen=True, slots=True)
class McpServerStatus:
    name: str
    state: McpConnectionState
    tool_count: int
    error: str | None

class McpSupervisor:
    def __init__(
        self,
        configs: Sequence[McpServerConfig],
        *,
        environment: Mapping[str, str],
        connection_factory: Callable[[McpServerConfig], McpServerConnection] | None = None,
        wait_ready_cap: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None: ...
    def statuses(self) -> tuple[McpServerStatus, ...]
    def any_connecting(self) -> bool
    def tool_names(self, server: str) -> tuple[McpToolInfo, ...]   # () when absent
    def instructions(self, server: str) -> str | None
    def on_change(self, callback: Callable[[], None]) -> None      # last wins
    async def start(self) -> None        # connect all enabled servers concurrently
    async def wait_ready(self, timeout: float = 10.0) -> None   # capped by wait_ready_cap
    async def call_tool(self, server: str, tool: str, arguments: Mapping[str, JSONValue], *, on_progress: Callable[[str], None] | None = None) -> McpToolResultData
    async def restart(self, name: str, config: McpServerConfig) -> None   # close old, connect new
    async def set_enabled(self, name: str, enabled: bool, config: McpServerConfig | None) -> None
    async def shutdown(self) -> None
```

supervisor 从不读配置文件或路径（低耦合）：`restart` 与
`set_enabled(..., config)` 从 extension 层接收重读的配置。

- [x] **步骤 1：写失败测试**（`tests/mcp/test_supervisor.py`，只用 fake
  连接——无 SDK）：start 并发连接所有已启用服务器并忽略禁用的；`wait_ready` 在没有连接中时立即返回、有连接保持 `connecting` 时以注入 clock 封顶 `wait_ready_cap`；`on_change` 在连接成功/失败/set_enabled/restart 时触发；
  `call_tool` 路由到正确连接，未知服务器/工具或禁用服务器抛 `McpToolUnavailable`；`set_enabled(False)` 关闭连接且其工具从 `statuses()` 消失；`set_enabled(True,
  config)` 用提供的配置连接；`restart` 替换连接；`shutdown` 关闭全部且后续 `call_tool` 抛错。
- [x] **步骤 2：运行并看它们失败。**
- [x] **步骤 3：实现。** 连接经 `connection_factory` 创建（默认用构造器的 environment 构建真实 `McpServerConnection`）。`start` 用 `anyio.create_task_group` 并发连接每个启用的
  server；单连接失败记录在连接自身（`failed`/`needs-auth` 状态），绝不从 `start` 抛出。
  `wait_ready`：`deadline = min(timeout, self._wait_ready_cap)`；轮询
  `anyio.sleep(0.05)` 直到 `not any_connecting()` 或期限过——永不抛。`on_change` 在任何影响状态的操作后（同步）触发。
- [x] **步骤 4：跑测试、门、提交**

```bash
uv run pytest -q tests/mcp/test_supervisor.py
uv run ruff check src/baldric_mcp && uv run ruff format --check src/baldric_mcp && uv run mypy
git add src/baldric_mcp/supervisor.py tests/mcp/test_supervisor.py
git commit -m "feat: MCP connection supervisor with bounded first-turn wait"
```

---

### 任务 5：`baldric_mcp.adapter`——命名、schema、结果转换

**文件：**
- 新建：`src/baldric_mcp/adapter.py`
- 新建：`tests/mcp/test_adapter.py`

**接口：**
- 消费：`McpToolInfo`、`McpToolResultData`（任务 3）、`AgentTool`/
  `AgentToolResult`/`TextContent`/`ImageContent`（`baldric_protocol.tools`、
  `baldric_protocol.messages`）。
- 产出（Task 7 消费）：

```python
TOOL_NAME_MAX = 64
TEXT_LIMIT = 20 * 1024

def create_mcp_tool_name(
    server: str, tool: str, is_taken: Callable[[str], bool] = lambda _name: False
) -> str: ...

def normalize_input_schema(schema: Mapping[str, JSONValue] | None) -> dict[str, JSONValue]: ...

OutputSaver = Callable[[str, str], str]   # (full_text, suffix) -> saved file path

McpToolCaller = Callable[..., Awaitable[McpToolResultData]]
# call signature: await call(arguments, on_progress=...) -> McpToolResultData

def mcp_tool_to_agent_tool(
    server: str,
    info: McpToolInfo,
    call: McpToolCaller,
    *,
    output_saver: OutputSaver | None = None,
) -> AgentTool: ...

def convert_result(
    server: str, tool: str, data: McpToolResultData, *, output_saver: OutputSaver | None = None
) -> AgentToolResult: ...
```

- [x] **步骤 1：写失败测试。** 命名表测（精确移植 pi 的
  `naming.ts`——测试断言：普通用例 `mcp__docs__search`；
  `my-server`/`do.thing` 净化为 `mcp__my_server__do_thing`；64 字符
  上限加 `_` + 对 `server\0tool` 的 8 位 hex sha256 后缀；同一服务器内
  `a-b`/`a_b` 工具冲突）。schema 测试（缺失/`{}`/非对象
  schema → `{"type": "object", "properties": {}}`；带 properties 的对象保留；
  非 dict schema → 同样的空对象回退）。转换测试：文本拼接；
  图片 → 占位文本 `[image: image/png, N bytes]`（MVP——loop 的
  provider 对工具结果图片的序列化未验证）；`isError` →
  `is_error=True`；空错误内容补 `"MCP tool <server>/<tool>
  returned an error"`；>20 KiB 文本配 fake saver → 全文保存（路径在注记里），保留首尾；>20 KiB 无 saver → 截断加注记，不崩溃。`AgentTool` 形状：`name` 经
  `create_mcp_tool_name`，`label =
  f"{server}/{info.name}"`，描述回退链
  `description.strip() or title or f"MCP tool {info.name} from server
  {server}"`，`parameters=normalize_input_schema(...)`，executor 把
  `on_progress` 映射为 `on_update(AgentToolResult(content=[TextContent(text=...)]))` 并接受 `signal` 而不使用它（docstring：单调用超时住在连接里）。
- [x] **步骤 2：运行并看它们失败。**
- [x] **步骤 3：实现** —— `create_mcp_tool_name` 是
  `pi-main/packages/mcp/src/naming.ts` 的逐行移植（`str.replace` → `re.sub(r"[^A-Za-z0-9_]",
  "_", name)`、`hashlib.sha256(f"{server}\0{tool}".encode()).hexdigest()[:8]`）。
  `convert_result` 拼接文本块、以占位符替换图片块、应用 20 KiB 截断（保留首尾两半）并在提供时调用 `output_saver`。
- [x] **步骤 4：跑测试、门、提交**

```bash
uv run pytest -q tests/mcp/test_adapter.py
uv run ruff check src/baldric_mcp && uv run ruff format --check src/baldric_mcp && uv run mypy
git add src/baldric_mcp/adapter.py tests/mcp/test_adapter.py
git commit -m "feat: MCP tool adapter with ecosystem tool naming and result conversion"
```

---

### 任务 6：agent 接缝——活动工具列表、注销、prompt 刷新

**文件：**
- 修改：`src/baldric_agent/harness.py`（`update_system_prompt`）
- 修改：`src/baldric_coding/extensions/runtime.py`（`bind_live_tools`、
  `unregister_tool`、`request_system_prompt_refresh`）
- 修改：`src/baldric_coding/extensions/api.py`（`unregister_tool`、
  `refresh_system_prompt`）
- 修改：`src/baldric_coding/session/session.py`（bind + builder 闭包 +
  `refresh_system_prompt`）
- 仅当任务 0 步骤 3 发现有 prompt 输入不能跨 reload 保留时修改：`src/baldric_coding/session/lifecycle.py`
- 新建：`tests/agent/test_harness_system_prompt.py`
- 新建：`tests/coding/extensions/test_live_tools.py`
- 新建：`tests/coding/session/test_refresh_system_prompt.py`（放在既有 session 测试旁——先核实目录，调整路径）

**接口：**
- 消费：任务 0 步骤 1/3/6 验证的链条。
- 产出（Task 7/8 消费）：

```python
# harness.py
class AgentHarness:
    def update_system_prompt(self, system: str) -> None:
        """Replace the system prompt for subsequent runs (per-run read contract)."""

# runtime.py
class ExtensionRuntime:
    def bind_live_tools(self, tools: list[AgentTool], allowed: frozenset[str] | None) -> None: ...
    def request_system_prompt_refresh(self) -> None: ...
    # register_tool/unregister_tool now also mutate the bound live list

# api.py
class ExtensionAPI:
    def unregister_tool(self, name: str) -> None: ...       # source-owned removal
    def refresh_system_prompt(self) -> None: ...            # delegates to bound session

# session.py
class CodingSession:
    def refresh_system_prompt(self) -> None: ...
```

- [x] **步骤 1：验证（依任务 0 发现）并复述触点**

编辑器开着重读确切区域：`session.py:805-870`、
`runtime.py:1034-1080` + `register_tool`（`:544-563`）+ `BoundSession`、
`api.py:1172-1180`（`register_tool`）。确认任务 0 的飞行前发现在本分支仍成立（它们在 `main` 上验证过；一次合并可能移动了行）。**MUST-HOLD**：同一列表对象同时流向 harness 与
`build_system_prompt`。

- [x] **步骤 2：写失败测试**

1. `tests/agent/test_harness_system_prompt.py`：用 `tests/agent/` 里既有的 fake
   provider helper（先读它们），断言 `harness.update_system_prompt("NEW")` 之后的运行发送 `NEW` 作为 system prompt，之前是旧 prompt。
2. `tests/coding/extensions/test_live_tools.py`：构建 runtime（模式照
   `tests/coding/extensions/test_extensions.py`），绑定一个列表，经 `ExtensionAPI.register_tool` 注册工具 → 绑定列表多出该对象；
   `unregister_tool` 移除它；注册 `allowed` 之外的名字（`allowed` 非 None 时）被忽略并诊断；注册重名不重复添加。
3. `tests/coding/session/test_refresh_system_prompt.py`：构建 session（模式照既有 session 测试——fake provider），捕获 fake provider 收到的 system
   prompt；经 extension API 注册一个 prompt 区块，调用 `session.refresh_system_prompt()`；下一次运行的 system prompt 含该区块。另外：带显式
   `config.system` 构建的 session 中 `refresh_system_prompt()` 是 no-op。

- [x] **步骤 3：运行并看它们失败。**

- [x] **步骤 4：实现。**

`harness.py`：

```python
def update_system_prompt(self, system: str) -> None:
    """Replace the system prompt used by subsequent runs.

    The run path reads ``config.system`` per run, so the next prompt picks
    this up without touching the durable history.
    """
    if not system:
        raise ValueError("system prompt must be a non-empty string")
    self._config.system = system
```

`runtime.py` —— 字段 `self._live_tools: list[AgentTool] | None = None` 与
`self._live_allowed: frozenset[str] | None = None`：

```python
def bind_live_tools(self, tools: list[AgentTool], allowed: frozenset[str] | None) -> None:
    """Bind the session's materialized tool list for live registration.

    The bound object is the same list handed to the agent harness, which
    reads it per run; register/unregister keep registry and list in step.
    Re-binding on session rebind (resume/new/branch) replaces the previous
    list, mirroring set_ui_bridge.
    """
    self._live_tools = tools
    self._live_allowed = allowed
```

`register_tool` 在重复检查之后、插入之前增加：

```python
if self._live_tools is not None and self._live_allowed is not None and tool.name not in self._live_allowed:
    self._load_diagnostics.append(ResourceDiagnostic(
        kind="extension", name=extension_name,
        message=f"tool `{tool.name}` is not in allowed_tool_names; ignoring",
    ))
    return
...
if self._live_tools is not None:
    self._live_tools.append(tool)
```

`unregister_tool(source_id, extension_name, name)`：仅当
`registered.source_id == source_id` 时移除 registry 条目（否则静默 no-op），并按身份从活动列表移除同一对象。`bind`（session 重绑）
保持活动绑定连贯：`retire`/`_remove_registrations` 时同样把被移除的工具从活动列表丢弃。扩展 `BoundSession` 协议加
`refresh_system_prompt() -> None`；`request_system_prompt_refresh()` 在被绑定 session 存在时调用它。

`api.py`：`unregister_tool(name)` 先断言世代再委托
`self._runtime.unregister_tool(self._source_id, self._extension_name, name)`；
`refresh_system_prompt()` 先断言世代再
`self._runtime.request_system_prompt_refresh()`。

`session.py`：在 `tools = _filter_tools(...)`（约 818 行）之后插入
`extension_runtime.bind_live_tools(tools, config.allowed_tool_names)`。把既有
`build_system_prompt(...)` 调用包进零参闭包
`def _build_system_prompt() -> str: return build_system_prompt(BuildSystemPromptOptions(...))`
，参数完全一致（任务 0 步骤 3 的清单），先调用一次得
`system`，并把 builder 存到 session：
`system_builder=None if config.system is not None else _build_system_prompt`
传入 `cls(...)` 并保存为 `self._system_prompt_builder`。增加：

```python
def refresh_system_prompt(self) -> None:
    """Rebuild the system prompt from current registries (extension seam)."""
    if self._system_prompt_builder is None:
        return
    self._harness.update_system_prompt(self._system_prompt_builder())
```

- [x] **步骤 5：跑完整快速套件（横切变更）、门、提交**

```bash
uv run pytest -q --ignore=tests/coding/tui
uv run ruff check . && uv run ruff format --check . && uv run mypy
git add src/baldric_agent/harness.py src/baldric_coding/extensions/runtime.py src/baldric_coding/extensions/api.py src/baldric_coding/session/session.py tests/agent/test_harness_system_prompt.py tests/coding/extensions/test_live_tools.py tests/coding/session/test_refresh_system_prompt.py
git commit -m "feat: live tool registration and system-prompt refresh seams"
```

---

### 任务 7：内置 extension A——启动、信任门、动态注册

**文件：**
- 新建：`src/baldric_coding/extensions/builtins/mcp/__init__.py`
- 新建：`src/baldric_coding/extensions/builtins/mcp/extension.py`
- 修改：`src/baldric_coding/extensions/builtin_registry.py`
- 仅当任务 0 步骤 2 判定需要 `mcp_enabled` 旗标时修改：`src/baldric_coding/session/session.py`（child 会加载 built-in）：加字段并在 subagents 子构造点传 `mcp_enabled=False`
- 新建：`tests/coding/extensions/test_mcp_extension.py`

**接口：**
- 消费：任务 2/4/5 产出；`BuiltInExtensionContext`（paths、
  environment）；`ExtensionAPI`。
- 产出：注册的内置 `mcp`；供测试的模块级 factory hook：

```python
# extension.py
API_VERSION = EXTENSION_API_VERSION
CAPABILITIES = ExtensionCapabilities(tools=True, hooks=True)

def setup(baldric: ExtensionAPI, context: BuiltInExtensionContext | None = None) -> None: ...

def _session_wants_mcp(api: ExtensionAPI) -> bool:
    """MVP gate: top-level sessions only (see spec 'Child sessions')."""

_supervisor_factory: Callable[[Sequence[McpServerConfig], Mapping[str, str]], McpSupervisor]
# module-level, monkeypatched by tests; default builds McpSupervisor
```

- [x] **步骤 1：验证（MUST-HOLD）**——重读 `builtin_registry.py`（同步
  setup 契约、`setup_with_context`），确认任务 0 步骤 2 的子
  session 决定，确认任务 0 步骤 2b 的生命周期矩阵在本分支仍成立。**修正后的矩阵（任务 6 执行发现）**：`load`
  总是 stage 全新 runtime（`session.py:643-670`："never reuse
  source-project code across replacement trust boundaries"；
  `config.extension_runtime` 只把凭据带进新 runtime）。
  new/resume/branch 时旧 runtime 收到 `session_shutdown`，新
  runtime 的全新 extension 实例收到 `session_start`，然后旧
  runtime 退役。每个 extension 实例因此每世代至多启动一次；下面的守卫作为纵深防御保留（宿主可能在同一 runtime 上重发
  `session_start`），registry 在新世代自然重新填充——不要 re-seed。若选择了旗标分支，还要按任务 0 记录的 file:line 核对
  `CodingSessionConfig` 字段位置与 child 构造点。

- [x] **步骤 2：写失败测试**（`tests/coding/extensions/test_mcp_extension.py`，
  自家 anyio 模式，fake supervisor 经 `monkeypatch.setattr` 注入模块级工厂）：

1. 无配置文件 → 不建 supervisor、无工具、无诊断。
2. 用户配置带一个 stdio 服务器、项目不受信任 + 项目文件
   存在 → 项目服务器被忽略，恰好一条提到 "not trusted" 的诊断；用户服务器启动（fake supervisor 启动）。
3. 项目受信任 → 两个服务器都启动；fake supervisor 报告一台已连接服务器带两条 `McpToolInfo` 后，extension 注册了两个名字遵循 `mcp__<server>__<tool>` 的工具；活动列表（经任务 6 绑定，用真实 runtime + fake provider 构建的 session 断言）包含它们。
4. 服务器转为 `failed` → 其工具从活动列表撤回（经 `unregister_tool`）。
5. `session_shutdown(<任何原因>)` → fake supervisor 的 `shutdown` 被 await
   （修正矩阵：每个关闭原因都先于该世代退役，所以 supervisor 总是被关闭；在 new/resume/branch 上保留连接会让服务器进程变孤儿）。
6. **子代理门（修正机制，偏差 D3）**：门在组合层——
   `CodingSessionConfig.disabled_built_in_extensions`
   在 `load` 里过滤内置 registry，subagents 子构造传
   `frozenset({"mcp"})`，extension 在 child 里根本不加载（无 supervisor、无工具、无 `/mcp` 命令）。
7. **启动守卫（纵深防御）**：同一 runtime 上触发两次 `session_start` → fake supervisor 的 `start` 恰好被调一次（没有第二个 supervisor），supervisor 身份不变，第二次 start 前注册的工具仍在，且没有重复注册诊断。（每世代全新 runtime 已让重绑时的双重启动不可能；这里钉住世代内守卫。）
8. **不处理 `tools/list_changed`**：连接后加工具的服务器保持连接时的工具集（规格非目标）——extension 不为该通知注册 handler，行为被断言为"工具数不变"。

- [x] **步骤 3：运行并看它们失败。**

- [x] **步骤 4：实现 `extension.py`。** 同步 `setup` 存 context，然后：

```python
baldric.on("session_start")(self._on_session_start)     # async handler
baldric.on("session_shutdown")(self._on_session_shutdown)
baldric.on("input")(self._on_input)                     # Task 8 wires the body
baldric.register_command("mcp", self._mcp_command, ...) # Task 8 wires the body
```

`_on_session_start`：**先做幂等启动守卫**（防同一 runtime 上重复的
`session_start`；修正后的任务 0 步骤 2b 矩阵每世代 stage 全新 runtime，所以每个实例通常只启动一次）：
若
`self._supervisor is not None` 且未关闭 → 调 `self._sync()` 并返回（registry 已持有工具且 `compose_tools` 会重新合并——不要 re-seed、不要盲目重新注册；`_registered` map 去重）。否则：
门 → `load_mcp_config(user_path=context.paths.user_mcp_config_path, project_path=context.paths.project_mcp_config_path(api.context.cwd) if api.context.project_trusted else None, environment=context.environment)` → 诊断经 `api.notify(..., "warning")` → 构建启用列表 → 若有，`_supervisor = _supervisor_factory(enabled, context.environment)`，`on_change(self._sync)`，然后
`asyncio.get_running_loop().create_task(self._supervisor.start())`（自家模式，
`subagents/extension.py:387`）。`_sync` 注册已连接服务器的工具：对每条已连接连接，跳过 `self._registered` 里已有的名字；构建调用闭包
`async def call(arguments, *, on_progress=None): return await self._supervisor.call_tool(server, info.name, arguments, on_progress=on_progress)`
并注册 `api.register_tool(mcp_tool_to_agent_tool(server, info, call))`；
`failed`/`needs-auth` 时经 `api.unregister_tool(name)` 撤回。若可见状态没变（同一工具名集合与同一区块正文），`_sync` 是 no-op——每次真实变化都重建 system prompt 并使 provider 前缀缓存失效，所以设计上必须避免无谓抖动。
`_on_session_shutdown`：无论原因都 `await supervisor.shutdown()`——
修正后的任务 0 步骤 2b 矩阵在每次 shutdown 后退役该世代，保留连接会让服务器进程变孤儿。
注册 `builtin_registry.py` 条目：`BuiltInExtension(name="mcp",
setup=_mcp_setup, hidden=True, setup_with_context=_mcp_setup_with_context)`
，懒导入镜像 llama.cpp 模式。

- [x] **步骤 5：跑测试、门、提交**

```bash
uv run pytest -q tests/coding/extensions/test_mcp_extension.py
uv run ruff check . && uv run ruff format --check . && uv run mypy
git add src/baldric_coding/extensions/builtins/mcp src/baldric_coding/extensions/builtin_registry.py tests/coding/extensions/test_mcp_extension.py
git commit -m "feat: MCP built-in extension with trust gating and live registration"
```

---

### 任务 8：内置 extension B——第一轮等待、prompt 区块、`/mcp`

**文件：**
- 修改：`src/baldric_coding/extensions/builtins/mcp/extension.py`
- 修改：`tests/coding/extensions/test_mcp_extension.py`

**接口：**
- 消费：`supervisor.wait_ready/any_connecting/statuses/restart/set_enabled`
  （任务 4）、`set_server_enabled`/`load_mcp_config`（任务 2）、
  `api.refresh_system_prompt`/`add_prompt_section`（任务 6）。

- [x] **步骤 1：写失败测试**（fake supervisor + 真实 runtime）：

1. 服务器 `connecting` 时的第一次 `input` → handler 恰好一次 await
   `wait_ready(timeout=10.0)`（fake 记录）；第二次 input 不再等待；没有连接中服务器时不等待。
2. 工具落定后，恰好注册一个标题为 "MCP servers" 的 prompt 区块
   （`add_prompt_section`）且调用过 `refresh_system_prompt`；
   区块正文逐服务器列 `- name (stdio, 2 tools): description-or-instructions 首行`，单服务器上限 200 字符、总量 1200；没有 description/instructions 的服务器只渲染 `name (stdio, N tools)`。
3. `/mcp` 无参数按服务器各返回一行
   `name  state  transport  N tools`（failed 时加 `: first error line`）。
4. `/mcp off <name>`：调 `set_server_enabled(source_path, name, False)`
   （断言 tmp_path 配置）与 `supervisor.set_enabled(name, False, None)`；
   未知名字 → 消息；`/mcp on <name>` 重读配置并调
   `set_enabled(name, True, fresh_config)`；`/mcp restart <name>` 调
   `supervisor.restart(name, fresh_config)`。
5. 同步命令 handler 的异步工作被调度到运行中的循环（在 await 一个 tick 后经记录的 fake 调用断言）。

- [x] **步骤 2：运行并看它们失败。**

- [x] **步骤 3：实现。** `_on_input`（async）：若 `self._admitted` 或
  supervisor 为 None 或 `not any_connecting()` → 返回 `None`；置
  `self._admitted = True`；`await wait_ready(timeout=10.0)`；返回 `None`。
  `_sync`（已由 `on_change` 调用）：重算区块正文并调
  `add_prompt_section` + `api.refresh_system_prompt()`（仅当至少配置了一个启用服务器）。`_mcp_command`（同步）：解析参数；restart/on/off
  都调度
  `asyncio.get_running_loop().create_task(self._apply_toggle(...))`；
  toggle 按与启动相同的信任规则重读配置，经
  `set_server_enabled` 持久化（pi 的 `/mcp` 持久化语义移植）。

- [x] **步骤 4：跑测试、门、提交**

```bash
uv run pytest -q tests/coding/extensions/test_mcp_extension.py
uv run ruff check . && uv run ruff format --check . && uv run mypy
git add src/baldric_coding/extensions/builtins/mcp/extension.py tests/coding/extensions/test_mcp_extension.py
git commit -m "feat: MCP first-turn admission, servers prompt section, /mcp command"
```

---

### 任务 9：真实进程集成测试 + resume 回归

**文件：**
- 新建：`tests/helpers/mcp_stdio_fixture.py`
- 新建：`tests/mcp/test_integration_stdio.py`
- 新建：`tests/coding/session/test_mcp_resume_repair.py`（路径在
  任务 6 步骤 2 验证）

**接口：**
- 消费：以上全部；既有的 fake-provider session 测试 helper。

- [x] **步骤 1：写 fixture 服务器**

`tests/helpers/mcp_stdio_fixture.py`：

```python
"""A tiny stdio MCP server used by integration tests: one `echo` tool."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fixture")

@mcp.tool()
def echo(text: str) -> str:
    """Echo the text back."""
    return text

if __name__ == "__main__":
    mcp.run()
```

（对照任务 1 步骤 4 第 6 条确认；按钉住的 SDK 调整导入路径。）

- [x] **步骤 2：写集成测试**（`tests/mcp/test_integration_stdio.py`，
  anyio，余量放宽——套件级 `--timeout=120` 是兜底）：

构建 `McpServerConfig(name="fixture", server_type="stdio",
command=sys.executable, args=(str(HELPER_PATH),), timeout=30.0)`；用 `environment=os.environ` 快照构建真实
`McpSupervisor`；`await
supervisor.start()`；断言一条 `connected` 状态带恰好一个工具；
`call_tool("fixture", "echo", {"text": "hi"})` 返回文本 `"hi"`；
`await supervisor.shutdown()` 不留残留子进程（经
`statuses()` 状态 `closed` 断言）。标记它以便 POSIX CI 在进程启动 flaky 时排除？不——子进程启动是跨平台的；
不加 skip（自家规则禁止弱化）。

- [x] **步骤 3：写 resume 回归测试**

用 session 测试 helper（fake provider）：构造含 assistant `ToolCall`
（名为 `mcp__gone__server__tool`、无结果）的初始消息，跑一条 prompt，断言 provider 的请求含该调用的合成
工具结果（机制：harness 前奏
`_append_interrupted_tool_results`——任务 0 步骤 5 的记录行为；若
loop 路径对未知名调用的处理不同，用注释点名机制钉住那个观察到的
行为——绝不断言代码没有做的事）。

- [x] **步骤 4：运行、门、提交**

```bash
uv run pytest -q tests/mcp/test_integration_stdio.py tests/coding/session/test_mcp_resume_repair.py
uv run ruff check . && uv run ruff format --check . && uv run mypy
git add tests/helpers/mcp_stdio_fixture.py tests/mcp/test_integration_stdio.py tests/coding/session/test_mcp_resume_repair.py
git commit -m "test: MCP stdio integration and resume repair regression"
```

---

### 任务 10：打磨——stderr 日志、输出保存器、看门狗时钟测试

**文件：**
- 修改：`src/baldric_coding/extensions/builtins/mcp/extension.py`
- 仅当任务 1 的 stderr 发现允许接线时修改：`src/baldric_mcp/client.py`
- 修改：`tests/coding/extensions/test_mcp_extension.py`

- [x] **步骤 1：验证**——读 `src/baldric_coding/tools/truncate.py` 与
  `src/baldric_coding/tools/output_accumulator.py`（以及 bash 工具的
  输出文件路径约定），找到保存完整工具输出的自家 helper 及其目标目录约定。复用它；不发明平行约定。

- [x] **步骤 2：写失败测试**：extension 向 `mcp_tool_to_agent_tool` 传一个
  `output_saver`，写到自家输出位置之下并返回路径（基于 tmp_path，断言文件内容）；截断注记携带该路径。若任务 1 的 SDK 发现暴露了 stderr 管道：client 测试断言尾部落入 sink。

- [x] **步骤 3：实现**——在 extension 的
  `mcp_tool_to_agent_tool(...)` 调用接上 `output_saver`；接上 `stderr_sink`：打开
  `paths.logs_dir / "mcp" / f"{server}.log"`（追加模式，创建父目录）并作为 `stdio_client(server, errlog=...)` 传入；http 服务器给 `None`
  （无 stderr）；接缝就地文档化。

- [x] **步骤 4：运行、门、提交**

```bash
uv run pytest -q tests/coding/extensions/test_mcp_extension.py tests/mcp
uv run ruff check . && uv run ruff format --check . && uv run mypy
git add -u
git commit -m "feat: MCP output saving and stdio stderr logging"
```

（仅当文件集恰为上述四个时才用 `git add -u`——否则显式列路径。）

---

### 任务 11：文档与全量门

**文件：**
- 新建：`website/content/guides/mcp.md`（从既有指南核实 guides 目录与
  frontmatter 约定，例如 providers 指南）
- 修改：注册指南的文档导航/索引文件（经
  `website/` 配置找；编辑前核实）
- 新建：`dev-notes/journal/` 条目——若那是自家日志位置；核实既有构建日志的位置（`dev-notes/`）并遵循

- [x] **步骤 1：写用户指南**：MCP 是什么、`mcp.json`（用户 +
  项目、信任门）、`/mcp` 用法、`enabled`/`timeout`/`description`/`type`
  字段、`${ENV}` 展开、工具命名 `mcp__<server>__<tool>`、状态与
  惰性重连，以及已知代价/限制：工具抖动重建 system prompt（provider 前缀缓存失效——接受，用
  `_sync` no-op 规则最小化）、无 OAuth、无 resources/prompts、无 `list_changed`、绕过 `input` hook 的模式从第二轮起拿到工具（镜像
  规格非目标与任务 0 步骤 2c 发现）。
- [x] **步骤 2：写 dev-notes 日志条目**（加了什么、为什么、如何对应 pi 的设计、怎么测试），遵循仓库文档期望。
- [x] **步骤 3：跑每个门（横切变更 ⇒ 全量套件）：**

```bash
uv run pytest -q
uv run pytest --cov
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run python scripts/check_import_graph.py
uv run python scripts/check_structure.py
uv run python scripts/check_suppressions.py
uv run python scripts/check_agent_guidance.py
```

若 `check_structure.py` 标记 `session.py` 增长，按自家规则用 `--init` 记录在单独提交 `chore: record structure growth for mcp seams` 里。覆盖率必须保持 ≥ 80%。

- [x] **步骤 4：提交文档**

```bash
git add website/content/guides/mcp.md <nav-file> <journal-entry>
git commit -m "docs: MCP servers guide and build journal"
```

---

## 最终验证清单（宣布完成之前）

- [x] 所有任务的勾选框已勾；每条 MUST-HOLD 验证记录在飞行前发现小节。
- [x] `uv run pytest -q` 本地全绿（2884 通过、126 跳过；
  Windows 跳过是预期且有文档）。
- [x] 九个门全绿（任务 11 步骤 3；一个 TUI 偶发按 AGENTS.md 重跑通过）。
- [x] 手动冒烟（可选但推荐）：由真实进程 stdio 集成测试覆盖（supervisor 启动 FastMCP 服务器、调用其工具、干净关闭）。
- [x] 分支 diff 不含规格触点表之外的任何东西（飞行前发现与文档除外）——每条例外都记入**执行偏差日志**，附影响分析与 `deviation:`
  提交注记。
- [x] 规格与计划仍描述实际构建的东西（执行规则 R1 发现的任何漂移都被调和，而不是绕过）。

## 执行偏差日志

执行期按执行规则 R4 追加。每条偏差一项；空小节表示计划按原文执行。条目格式：

- **D1 — 采纳必须转移 prompt builder**（任务 6，2026-11-08）：
  `lifecycle.py` 的 `_adopt_replacement` 在计划触点表之外，但它从替换中拷贝 `session._harness` 时没有带新的
  `_system_prompt_builder`；resume/new 会用采纳前的闭包重建 prompt。在 session.py 内修复
  （`_adopt_system_prompt_builder`）以尊重 session-state 写
  棘轮；lifecycle 只调用方法。影响面已核：三个采纳调用者（new/resume/reload 采纳）、写棘轮
  （tests/guards）、钉住采纳字段拷贝的 session 测试。
  设计变更？否（接缝按设计工作；这是补一个转移缺口）。提交：任务 6 的 feat 提交。
- **D2 — 结构基线增长用 --init 记录**（任务 6，2026-11-08）：接缝触碰的五个文件本就超过 400
  行限且有登记例外（`harness.py` 467→477、`api.py`
  1340→1350、`runtime.py` 1393→1454、`lifecycle.py` 1187→1191、
  `session.py` 2011→2031；`load` 的最长函数 54→56 语句）。增长恰好是计划要求的接缝行加修正后的
  `_connect_quietly`/`unregister_tool`。逐行评审 diff，每条新增行都可追溯到触点表或偏差 D1。
  提交：任务 6 的 feat 提交。
- **D3 — 子代理门移到组合层**（任务 7，2026-11-08）：计划中的
  `CodingSessionConfig.mcp_enabled: bool = True` + `_session_wants_mcp`
  没有读取机制：`ExtensionContext` 不暴露 session 配置，往 `BoundSession` 协议加 MCP 命名成员会把 MCP
  语义泄进内核（R5）。替换为 session config 上的
  `disabled_built_in_extensions: frozenset[str]` 加 `load` 中的内置 registry 过滤
  （`_eligible_built_in_extensions`），镜像既有 `extensions_enabled` 先例；subagents 子构造传 `frozenset({"mcp"})`。extension 在 child 里永不加载，因此无 supervisor、无工具、无 `/mcp` 命令。设计变更？否（同一产品决策，不同接缝）。提交：任务 7 的。
- **D4 — session_shutdown 总是关闭 supervisor**（任务 7，2026-11-08）：计划在 new/resume/branch 上保留连接，这源于错误的共享 runtime 矩阵。修正为每世代全新 runtime 的矩阵后，每个关闭原因都先于该世代退役，保留连接会让服务器进程变孤儿。影响面：`runtime._emit_lifecycle`（每个原因都在退场 runtime 上触发关闭）、`retire()` 语义。设计变更？矩阵层面是——由已提交的矩阵修正
  （674e3fc）与规格更新覆盖。
- **D5 — 结构基线增长用 --init 记录**（任务 7，2026-11-08）：`session.py` 2037→2064（config 字段 + registry 过滤
  helper）、`subagents/extension.py` 1620→1624（child 门参数）。每条新增行都可追溯到 D3。提交：任务 7 的 feat 提交。
- **D8 — "自家输出位置"就是临时文件约定**（任务 10，2026-11-08）：计划假设有托管输出目录；自家约定（bash 工具）是带工具专属前缀的 `tempfile.NamedTemporaryFile(delete=False)`。helper 移到
  `tools.output_accumulator.write_temp_output(output, *, prefix, suffix)`
  （bash 委托不变），MCP saver 用前缀
  `baldric-mcp-`。影响面：bash 工具输出路径（不变）、其测试（通过）。设计变更？否。
- **D6 — 带标题 prompt 区块按来源 upsert**（任务 8，2026-11-08）：
  `register_prompt_section` 原来无条件追加，但 MCP 区块正文随服务器状态变化会堆叠重复。同一来源的带标题区块现在替换同标题条目；无标题区块保持追加语义。影响面：所有既有
  `add_prompt_section` 用户只注册一次不同标题（grep
  src/tests/examples/website——没有钉住重复追加行为）。设计
  变更？否（使计划中的区块刷新成为可能）。
- **D7 — supervisor 也接收禁用服务器**（任务 8，2026-11-08）：计划只启动启用服务器，当所有服务器以禁用状态启动时 `/mcp on`
  没有 supervisor 可用。依据规格自己的规则（pi：禁用服务器要列出"以便可以再次启用"）与任务 4 的语义（start 只连接启用的）。prompt
  区块只列启用服务器。设计变更？否（补全计划中的 /mcp on 流程）。
- **D9 — 动态注册工具经 hook 包装**（评审后，2026-11-08）：活动接缝追加的是裸工具，`tool_call`/
  `tool_result` hook（与拦截门）从未覆盖 MCP 工具，不像
  `compose_tools` 的输出。`register_tool` 现在经 `_wrap_tool` 包装并在 `_live_wrapped` 跟踪包装；注销/来源移除按身份丢弃包装。这改变了任务 6 钉住的"裸追加"语义——测试现在钉管线一致的行为。设计变更？否
  （pi 的管线承诺被显式化；计划从未承诺裸）。未加豁免。
- **D10 — stderr sink 每次连接尝试打开**（评审后，2026-11-08）：连接在构造时捕获了一个 sink 实例且
  `_teardown` 会关闭它，惰性重连把已关闭文件交给 SDK，真实重连路径是坏的（测试缺口：只覆盖了 close()）。连接改为接收 sink 工厂，每次连接尝试开新句柄，teardown 关当前；回归测试覆盖掉线→重连。
- **D11 — adapter 接受冲突解析后的工具名**（评审后，2026-11-08）：只在 extension 传 `is_taken` 不够——
  `mcp_tool_to_agent_tool` 内部重算名字时不知道 taken 集，净化名冲突仍落在第一个名字上并被 registry 的重复检查丢弃。adapter 现在接收 `name=`，extension 传解析后的名字；回归测试覆盖两个工具净化到同一基名的情况。
