# MCP 客户端支持（baldric_mcp 包 + 内置 extension）

状态：已批准设计 v2（已纳入外部评审），实施计划待定。

Baldric 获得 MCP（Model Context Protocol）**客户端**：用户配置 MCP
服务器，Baldric 连接它们，其工具成为普通 agent 工具。协议委托给官方 `mcp` Python SDK
（modelcontextprotocol/python-sdk）；Baldric 只写它周围的产品层：
配置、信任门、连接监护、工具适配与
`/mcp` 命令。

形状镜像 Pi 自己的：独立协议包加编码应用里的薄内置
extension。agent 内核永不得知 MCP 的存在。

## 目标

- 成熟的终端编码 agent 必须接纳 MCP 生态：用户已经在跑 MCP 服务器（浏览器、数据库、issue 跟踪器、内部 API），并期待 agent 复用它们。
- 工具名稳定性、配置格式与信任行为必须在 1.0 前冻结：第一个真实用户出现那天起它们就是向后兼容承诺。冻结的名字遵循生态约定，而非自创。
- 分层架构保持：`baldric_agent`/`baldric_ai` 不获得 MCP 感知；MCP 是经 extension API 到达的工具来源。

## 非目标（显式 MVP 边界）

- **远程服务器 OAuth。** MVP 只经 headers/commands 里的 `${ENV}` 展开认证。HTTP 401 表现为 `needs-auth` 状态。
- **MCP 服务器模式**（把 Baldric 本身暴露给其他 agent）。
- **resources / prompts / sampling。** 只有工具。
- **延迟工具加载**（pi 的 `tool_search`/codemode）。MVP 用每服务器的启用/禁用管理 token 预算。`mcp__<server>__` 命名正是为了让未来的命名空间/延迟层无需改名即可插入。
- **`list_changed` 通知。** session 中途增删工具的服务器保持连接时的工具集，直到 `/mcp restart`。
- **工具注解**（`readOnlyHint`、`destructiveHint`……）。Baldric 的
  `AgentTool` 没有注解字段；以后把 hint 并进描述。
- **项目配置变更热重载。** 配置在 session 启动时读取；
  `/mcp restart` 重读。

## 架构

```text
baldric_coding/extensions/builtins/mcp/   thin extension: config load, trust gate,
        │ depends on                       live tool registration, /mcp, prompt section
baldric_mcp (NEW top-level package)        client core: config, supervisor,
        │ depends on                       adapter (protocol delegated to `mcp` SDK)
baldric_protocol                           conversion target: AgentTool / AgentToolResult
```

依赖方向：`baldric_coding → baldric_mcp → baldric_protocol`。
`baldric_mcp` 不得导入 `baldric_agent`、`baldric_ai`、`baldric_coding`、
`textual`、`rich`。`baldric_agent`/`baldric_ai` 不得导入
`baldric_mcp`。`mcp` SDK 依赖只存在于 `baldric_mcp`。

SDK 建在 anyio + httpx + pydantic 之上——三者都已是 Baldric
依赖。实现时锁定稳定的 `mcp` 1.x 线（2.0 处于 pre-release；不采纳）。

包拆分有第二个消费者撑腰：`AgentHarness` 的库用户与未来的 MCP 服务器模式原样复用 `baldric_mcp`。

## 包：`baldric_mcp`

### `config.py`

- `McpServerConfig` — 冻结 dataclass。共享字段：`name`、`enabled`、
  `description`（进入 prompt 区块）、`timeout`（单次调用，**秒**，
  默认 60；进度通知重置期限，与 pi 一致）、可选
  `type`（`"stdio"` | `"http"`）。粘贴兼容优先：缺失时 `type` 从 `command`（stdio）或 `url`（http）推断；存在时必须与条目字段一致，不一致被拒绝。stdio：
  `command`/`args`/`env`/`cwd`；http：`url`/`headers`。
- `load_mcp_config(user_path, project_path) -> McpConfigLoadResult` — 先用户级再项目级合并；同名项目条目覆盖
  用户条目。校验问题成为诊断；坏条目绝不拆掉 session。会坍缩到同一 `mcp__<server>` 命名空间的服务器名（仅 `-` 与 `_` 之差）被拒绝，同 pi。
- `${VAR}` 展开只用注入的环境快照，绝不直接读
  `os.environ`。无法解析的变量是诊断；条目保持禁用。
- **子环境（stdio）：** 快照 + 配置 `env` 合并，配置获胜。既定语义：许多服务器假设完整环境（PATH、HOME）；
  只传配置 `env` 会破坏它们。
- `~` 与 `~/…`（Windows 上还有 `~\…`）在 `command`、`args`、`cwd` 中展开。

### `client.py`

- `McpServerConnection` — 包裹 SDK session 的一条服务器连接。
  状态机采纳自 pi：
  `connecting | connected | disconnected | needs-auth | failed | closed`。
  - `disconnected`：连接在 session 中途掉线（stdio 服务器退出、
    HTTP socket 断了）。工具保持注册；下一次调用尝试惰性
    重连。掉线没有后台重试循环。
  - `failed`：连接期重试耗尽。工具被撤回；`/mcp
    restart` 可复活。
  - `needs-auth`：没有可用凭据的 HTTP 401。工具撤回；
    通知建议配置 header/env。
- 初始连接：只对**瞬时**错误（HTTP 408、
  429、5xx 除 501、连接类错误）有界重试，3 次，1 秒后 3 秒
  退避。
- 来自配置的单调用超时（`timeout` 秒，默认 60）；进度
  通知重置期限。
- stdio 服务器：child stderr 捕获到 `~/.baldric/logs/mcp/<server>.log`；
  连接失败时 stderr 尾部并入所报错误。
- 暴露 `instructions`（`initialize` 结果字段）与工具列表。

### `supervisor.py`

- `McpSupervisor` — 拥有全部连接。`start(configs)`（非阻塞：
  连接作为后台任务运行）、`wait_ready(timeout)`（没有已配置服务器仍处于 `connecting` 时完成）、工具集变化回调、
  `restart(name)`（重读配置）、`set_enabled(name, bool)`、`shutdown()`。
- `wait_ready` 无论参数一律上限 10 秒，同 pi 的第一轮
  准入。

### `adapter.py`

纯转换层，完全可单测。规则（在适用处移植 pi 的 `tools.ts`
决策）：

- **命名：** `mcp__<server>__<tool>` —— 生态约定（pi、Codex、
  Claude Code）。`[A-Za-z0-9_]` 之外一律净化为 `_`；上限 64
  字符；溢出或净化冲突时追加 `_` + 对 `server\0tool` 的 sha256 前 8 位十六进制。**随 1.0 冻结** —— 工具名活在 session
  JSONL 历史里。
- **label：** 渲染器用 `"<server>/<tool>"`。
- **描述回退链：** `tool.description.strip() || tool.title ||
  "MCP tool <tool> from server <server>"`。
- **schema：** 归一化为 `type: object` 且含 `properties`；空
  schema 变为 `{"type": "object", "properties": {}}`。
- **结果：** 文本块 → `TextContent`；图片块 → 活动模型支持图片工具结果时用 `ImageContent`，否则占位行；
  resource 块 → 占位文本。`isError` → `AgentToolResult.is_error`；
  无文本的 `isError` 结果得到 `"MCP tool <server>/<tool> returned
  an error"`。
- **进度：** MCP 进度通知映射到执行器的 `on_update` 部分结果（`progress/total/message` 作为文本）——Baldric 的
  `AgentTool.execute` 已携带该回调。
- **截断：** 上限跟随 pi 身经百战的路线：超过 20 KiB 的面向模型文本保留首尾、中段截断，全文
  存入输出文件，截断注记指明路径。自家模式
  （`baldric_coding/tools/truncate.py`）在 extension 层实现；`baldric_mcp` 本身保持 import 干净，返回全文加尺寸度量。

## 内置 extension：`baldric_coding/extensions/builtins/mcp/`

- 在 `builtin_registry.py` 注册为 `name="mcp"`、`hidden=True`、
  `setup_with_context`（paths + 环境快照）。能力：
  `ExtensionCapabilities(tools=True, hooks=True)` —— 绝不 Textual。
- **生命周期。** 同步 `setup()` 加载配置（用户 + 项目，项目仅在
  `api.context.project_trusted` 时；否则一条诊断）并注册
  handler。异步 `session_start` handler 非阻塞启动 supervisor（后台连接任务——自家模式：
  `asyncio.get_running_loop().create_task`）。每个运行世代 stage 全新的 extension 实例（修正后的 Task 0 Step 2b 矩阵：`load`
  总是 stage 新 runtime），因此 `session_start` 通常每世代恰好启动一个
  supervisor；幂等守卫在宿主真的在同一 runtime 上重发 `session_start` 时改为重新同步而非重启。在
  `session_shutdown` 时 supervisor **总是**被关闭：每个关闭原因都先于该世代退役，保留连接会让服务器进程变孤儿。
- **第一轮准入。** 异步 `input` hook（session 运行路径在运行开始前 await）在任何服务器仍在连接时每 session **一次** await `supervisor.wait_ready()`；上限 10 秒，然后照常继续。TUI 启动永不延迟；第一条消息只是稍等，让新服务器的工具真正可调用。
- **活动工具注册。** session 把物化的工具列表绑进 runtime（`bind_live_tools`）；`register_tool`/`unregister_tool`
  同时改动 registry 与该活动列表。工具随服务器就绪出现，随 `failed`/`needs-auth`/`/mcp off` 消失。被
  `allowed_tool_names` 过滤拒绝的注册带诊断忽略。
- **`mcp_servers` prompt 区块。** 第一次 `wait_ready` 落定后（或服务器状态变化时），extension 注册一个 prompt 区块：每个已启用服务器
  `name — 配置 description 或服务器 instructions 的第一行`（按服务器与总量设上限）。经 session 的
  `refresh_system_prompt()` 接缝渲染；没有 instructions 的服务器只贡献
  名字与工具数。
- **子 session。** subagent 子 session 在 MVP 中不获得 MCP——每个 child 各起服务器进程是浪费。门在组合层而非 extension 层：`CodingSessionConfig` 增加
  `disabled_built_in_extensions: frozenset[str]`，session 用它过滤
  built-in registry，`mcp` built-in 在 child 里根本不加载。这镜像既有的 `extensions_enabled` 先例，让
  `ExtensionContext` 不含 MCP 专属字段；以后给 child 启用 MCP 是 child 构造点的一行改动。
- **`/mcp` 命令**（同步 handler；异步工作调度到循环上）：
  无参数列出服务器（名字、状态、transport、工具数、首行错误）；`/mcp restart <name>` 重读配置并重连；`/mcp off
  <name>` 关闭连接、撤回其工具，并把
  `enabled: false` 写回定义该服务器的文件（保留缩进与
  无关内容，同 pi 的 `mcp.json` 写回）；`/mcp on
  <name>` 重连并以同样方式清除标志。
- 服务器状态变化经 `ui.notify` 呈现；无 UI 组件。

## 配置格式

用户：`~/.baldric/mcp.json`；项目：`<cwd>/.baldric/mcp.json`。顶层键
`mcpServers` —— 与 pi 和 Claude Desktop 兼容，既有配置可以直接粘贴：

```json
{
  "mcpServers": {
    "github": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "${GITHUB_TOKEN}" },
      "timeout": 60
    },
    "docs": {
      "type": "http",
      "url": "https://example.com/mcp",
      "headers": { "Authorization": "Bearer ${DOCS_TOKEN}" }
    }
  }
}
```

每服务器可选 `enabled`（默认 true）与 `description`。未知
字段警告但容忍；未知 `type` 被拒绝。

**信任门：** 项目级文件只在
`api.context.project_trusted` 为真时加载；否则一条诊断。信任一个项目意味着允许它启动进程——与项目 extension 和 bash 同一信任级。

## resume、分支与缺失工具

工具名写入持久 JSONL 历史。resume/分支时：

- 悬空 tool call（有 assistant 调用无结果）由 harness 既有的 `_append_interrupted_tool_results` 前奏修复——合成结果，不崩溃。回归测试用 MCP 工具名钉住这一点。
- 对 `failed`/`needs-auth`/已禁用服务器的 MCP 工具调用返回合成的"工具不可用"错误结果；它绝不作为异常进入运行。

## 安全与失败语义

- MVP 只用 env/header 认证；token 从环境快照展开，绝不记录日志。
- Windows 命令解析：小的确定性 helper 在 PATH 上探测 `npx` →
  `npx.cmd`/`npx.exe`（pi 上游恰好需要这个）。
- 无界重生禁止：连接重试有界；session 中途掉线只在下次调用时惰性重连。

## 既有代码触点（授权修改）

每处变更都可追溯到本设计；相邻之物一概"不改进"：

| 文件 | 变更 |
| --- | --- |
| `pyproject.toml` | 加 `mcp>=1.x` 依赖；把 `src/baldric_mcp` 加进 wheel packages 与 mypy packages |
| `scripts/check_import_graph.py` + `tests/guards/test_import_boundaries.py` | `baldric_mcp` 不得导入 agent/ai/coding/textual/rich；agent/ai 不得导入 `baldric_mcp` |
| `src/baldric_coding/config/paths.py` | 加 `user_mcp_config_path` 与 `project_mcp_config_path(cwd)` |
| `src/baldric_coding/extensions/runtime.py` | 加 `bind_live_tools(list)`；`register_tool`/`unregister_tool` 同步改动绑定的活动列表 |
| `src/baldric_coding/extensions/api.py` | 加 `unregister_tool(name)`（来源拥有的移除，世代守卫） |
| `src/baldric_coding/session/session.py` | 把组合后的工具列表绑进 runtime；加 `refresh_system_prompt()`，从当前 registry 重跑既有构建器 |
| `src/baldric_agent/harness.py` | 加 `update_system_prompt(str)`（`AgentHarnessConfig` 是非冻结 slots dataclass，运行路径每轮读 `config.system`；该方法赋值字段） |
| `src/baldric_coding/extensions/builtin_registry.py` | 声明 `mcp` 内置 extension |

若结构棘轮标记 `session.py` 增长，按自家规则用 `--init` 记录，而不是在同一变更里拆分。

## 测试策略

- supervisor/client 生命周期测试用脚本化 fake 连接，必要时用
  SDK 的内存 client/server 对——确定性，集成测试之外不碰真实子进程。
- 一到两个集成测试从 `tests/helpers/` spawn 真实的 fixture stdio MCP 服务器（spawn、列工具、调工具、退出）。
- 单测：配置解析/合并/展开/信任门/命名空间冲突；adapter
  命名（净化、64 上限、哈希后缀）、schema 归一化、结果
  转换、`is_error` 回退文本；活动工具列表接缝（bind 后注册的工具出现在下一次运行的工具列表——fake provider）。
- 回归：带悬空 `mcp__…` 调用的 resume 产生合成结果；
  调用被撤回工具得到"工具不可用"。
- Windows 命令解析 helper 用表驱动测试。

## 阶段（实施计划的输入）

1. `baldric_mcp.config` + `BaldricPaths` 增项 + 配置测试。
2. 基于 SDK 的 `baldric_mcp.client` + `supervisor`（内存对测试）。
3. `baldric_mcp.adapter`（+ 测试）。
4. agent 接缝：`bind_live_tools`、`unregister_tool`、
   `refresh_system_prompt`、`update_system_prompt`（+ 证明 loop 看到变更的测试）。
5. extension 接线：内置注册、信任门、动态注册、
   `input` 第一轮等待、`mcp_servers` 区块、`/mcp`、shutdown/reload
   生命周期（+ fake-supervisor 测试 + fixture 集成测试）。
6. 打磨：Windows 命令解析、stderr 日志、带完整输出文件的截断（+ 测试）。
7. 文档：`website/content/` MCP 指南、`dev-notes/` 构建日志、棘轮
   检查全绿。

## 有意推迟（MVP 之后）

OAuth 流程、MCP 服务器模式、resources/prompts/sampling、延迟工具
加载（`tool_search`/codemode）、`list_changed` 处理、工具注解、
配置热重载、为不支持图片的模型直出 `ImageContent` 工具结果、子 session MCP 共享、配置值里的 `!command` shell 替换（pi 的 `resolve-config-value.ts` 支持它；解析配置时跑 shell 是本 MVP 刻意排除的面——`${VAR}` 覆盖凭据场景）。

## 实施飞行前发现

记录于 2026-11-08，在 `feat/mcp-client` 上执行 `plans/mcp-client-implementation.md` 的 Task 0。每条计划的 MUST-HOLD 都对照工作树重新验证（下文行号是当天的，不是计划的）。

### 工具物化链（MUST-HOLD — 成立）

1. `session.py:818` 只物化一次：
   `tools = _filter_tools(extension_runtime.compose_tools(base_tools), config.allowed_tool_names)`；
   `base_tools` 是 `config.tools` 或全新编码工具（`session.py:808-817`）。
2. 同一个局部 `tools` 传给 `build_system_prompt(tools=tools)`
   （`session.py:825`）与 `AgentHarnessConfig(tools=tools)`（`session.py:852`）。
3. `AgentHarnessConfig` 是 `@dataclass(slots=True)`，**非冻结**：
   `tools: list[AgentTool] = field(default_factory=list)`（`harness.py:66-71`）。
   字段赋值是既有模式——subagents 隔离 child 的收窄就写
   `session._harness.config.tools = [...]`
   （`extensions/builtins/subagents/extension.py:761-763`）。
4. `_run` 每轮读 `tools=self._config.tools`（`harness.py:356`）与
   `system=self._config.system`（`harness.py:352`）。

### 子 session（门的 MUST-HOLD — 需要旗标）

subagent child 经 `CodingSession.load(CodingSessionConfig(...))` 构造
且不传 `extension_runtime`（`extensions/builtins/subagents/extension.py:695-743`）
——每个 child 得到**全新** runtime，built-in 原生加载（"Children
load extensions natively (pi parity)"，`extension.py:731-737`；
`extensions_enabled=not run.requested_isolated`，`:737`）。因此门是组合层的真实旗标：`CodingSessionConfig.disabled_built_in_extensions:
frozenset[str]`（session 过滤内置 registry），child 构造传 `frozenset({"mcp"})`。隔离 child 另外会在加载后把
`config.tools` 收窄为核心名字（`extension.py:753-763`）。

### 重绑生命周期矩阵（守卫的 MUST-HOLD — Task 6 中修正）

初始验证正确读了 `lifecycle.py`，但漏了 `load` 对它接手的 runtime 做什么。`session.py:643-670` 一锤定音：runtime 是 cwd 绑定的且可能持有项目注册，所以 **`load` 总是为目标快照 stage 全新 runtime**
（"never reuse source-project code across replacement trust boundaries"）；
`config.extension_runtime`（`lifecycle.py:740`、`:899`）只把
凭据/环境带进新世代。

| 原因 | runtime 实例 | 证据 |
| --- | --- | --- |
| startup | 全新 | session 构造 |
| reload | 全新 staged runtime | 关闭旧 → 绑定 staged → 启动 staged（`lifecycle.py:446-451`）；资源重新存储（`:459-474`） |
| new/resume/branch | **替换用全新 runtime** | 旧 runtime `emit_session_shutdown`（`lifecycle.py:935`）→ 替换的全新 runtime `emit_session_start`（`:937`）→ `old_runtime.retire()`（`:946`）；全新 runtime 重绑到幸存的 session 门面（`:998`） |
| quit | 同一 runtime | 仅 shutdown |

对 extension 的推论：每个 extension **实例**（每个 runtime 世代一个）全新收到 `setup`，每世代至多启动一次 supervisor；退场世代的 `session_shutdown` 关闭其 supervisor。幂等 `session_start` 守卫作为纵深防御保留，registry 在新世代自然重新填充（无需 re-seed）。
既有问题记录给未来 issue，**不在本分支修**：
`config.tools` 非空的重绑会再次包裹已包裹的工具
（`lifecycle.py:716` 传旧列表；`runtime.py:1046` 无条件包裹）。活动工具接缝的相关注意事项：subagents
隔离 child 收窄是**替换** `session._harness.config.tools`
（`subagents/extension.py:761-763`），会脱离 runtime 在 load 时绑定的列表；MCP child 被门挡住（child 的禁用 built-in
排除 `mcp`），所以 MCP
extension 永不注册进被收窄的列表，但未来的活动列表用户必须在收窄后重新绑定。

### 工具执行器签名与输入路径（MUST-HOLD — 成立）

`ToolExecutor` 是 `(tool_call_id, arguments, signal, on_update) ->
Awaitable[AgentToolResult]`（`baldric_protocol/tools.py:64-73`）；`AgentTool.execute`
转发全部四个（`:103-111`）。Task 5 的 `on_update` → 进度映射成立。

每一轮都经 `CodingSession` 的 `prompt()` 进入——唯一的
`run_input_hooks` await 在 `session/runtime.py:335`，先于展开与运行
（`:338-353`）。调用者：print/JSON（`cli.py:1505`）、RPC 服务器
（`modes/rpc/server.py:124`）、TUI（`tui/app.py:2509`、`:2530`）、subagent child
运行（`subagents/extension.py:414`、`:772`），以及 extension
`send_user_message` 包装（`session.py:1839`）。因此 MCP 第一轮准入等待适用于每种模式；不存在绕过路径，也不需要已知限制注记。

### prompt 构建器闭包（MUST-HOLD — 成立）

`BuildSystemPromptOptions`（`context/system_prompt.py:54-68`）与
`build_system_prompt(options)` 是纯函数（`:71-73`）。`session.py:819-846` 使用的每个输入要么是 `config` 字段、session 存储的资源
字段（`session.py:865-872`）、`extension_runtime` 属性，要么是局部
`tools` 列表。reload 会重新存储全部（`lifecycle.py:459-474`）。
`current_date` 保持默认（`date.today()`），与 reload 重建相同。在 `load` 作用域构建的零参闭包可以捕获 session 与局部
`tools`——没有不稳定输入，Task 6 之前也没有额外要存储的东西。

### 输入 hook 接缝（MUST-HOLD — 成立）

`run_input_hooks` 在运行开始前 await
（`session/runtime.py:335`）；`handled` 短路该轮，否则
`content = input_outcome.text`（`:338-342`）。`input` hook 载荷是
`InputEvent(text, source, streaming_behavior)`，其中
`source: Literal["interactive", "extension"]`
（`extensions/api.py:484-502`）。

### resume 修复与未知工具（成立）

`_run` 在 loop 之前修复悬空 tool call
（`harness.py:346-348` → `_append_interrupted_tool_results`，`:466-467`）：为每个未应答调用 id 追加
`ToolResultMessage(text="Tool call interrupted by user",
is_error=True)`（`tool_history.py:17-44`）。未知工具名经 `tools.get(call.name)` 解析，产出合成的
`error_result("Tool <name> not found")`，作为错误工具结果到达模型——不抛异常（`baldric_agent/tool_calls.py:64-67`）。Task 9
钉住这一点；adapter 层"工具不可用"承诺保持原样。

### BoundSession 协议（已验证）

`BoundSession` 覆盖 `extensions/runtime.py:115-189`（属性，然后到 `set_inference_provider` 结束的 mutator，`:189`）；`bind` 在 `:803`；
`_session: BoundSession | None` 在 `:312`。`refresh_system_prompt() -> None`
尚不存在，将加入协议与 `CodingSession`。

### 对计划的修正

- 生命周期矩阵的 `branch` 行描述的行为尚不存在（被 adopt 字面量接受，从未调用）。设计不变：幂等守卫无论如何都覆盖未来实现。
- 计划的"若有模式绕过 hook，记为已知限制"应急项收敛为"没有模式绕过它"——无需记录。

### SDK API 钉死（已安装 `mcp` 1.30.0，Task 1 Step 4）

记录于此，让 Task 3-5 从事实出发而不是计划的假设。HTTP
transport 的差异触发了计划的 STOP RULE；在任何 Task 3 代码之前计划已修订并提交。

1. **stdio**（`mcp/client/stdio/__init__.py`）：`StdioServerParameters(command,
   args=[], env=None, cwd=None, encoding="utf-8", encoding_error_handler="strict")`
   —— `cwd` 存在（`:86`）。`stdio_client(server, errlog: TextIO = sys.stderr)`
   yield `(read_stream, write_stream)`（`:189`）。env 语义（`:127`）：
   传 env 时为 `{**get_default_environment(), **server.env}`——合并在 SDK 安全继承的默认之上，传入的 env 获胜。Windows 命令
   解析已内建（`get_windows_executable_command`，
   `mcp/os/win32/utilities.py:36-65`，`shutil.which` + `.cmd/.bat/.exe/.ps1`
   探测）并自动在 `stdio_client` 内运行（`:229-230`）——计划自带的 `_resolve_windows_command` 冗余，已删除。
   关闭内建于 context manager（close stdin → 等 2s →
   终止进程树；Windows 用 kill-on-close Job Object）。
2. **HTTP**（`mcp/client/streamable_http.py`）：`streamablehttp_client` 已
   弃用（`:709-711`）。用
   `streamable_http_client(url, *, http_client=None, terminate_on_close=True)`；
   headers/超时/认证经 `create_mcp_http_client(headers=..., timeout=...)` 配在 httpx 客户端上，作为 `http_client` 传入。
   yield `(read_stream, write_stream, get_session_id)`（`:695-699`）。
3. **ClientSession**（`mcp/client/session.py`）：`ClientSession(read_stream,
   write_stream, read_timeout_seconds: timedelta | None = None,
   sampling_callback, elicitation_callback, list_roots_callback,
   logging_callback, message_handler, client_info, ...)`（`:122-136`）。
   `initialize() -> InitializeResult` 在不支持的协议版本上抛 `RuntimeError`（`:202-203`）；`InitializeResult.instructions: str | None`
   存在（`types.py:698`）。`list_tools() -> ListToolsResult`（`.tools`）。
   `call_tool(name, arguments=None, read_timeout_seconds=None,
   progress_callback=None, *, meta=None) -> CallToolResult`（`:386-394`）；
   `CallToolResult(content, isError, structuredContent)`（`types.py:1363-1367`）。
   注意：`call_tool` 可能抛——成功结果上的 output-schema 校验
   （`:412-413`，`RuntimeError` 在 `:435/:443/:448`）与内部
   `list_tools` 刷新（`:419-421`）。adapter 逐调用捕获异常。
4. **进度**：`progress_callback` 以
   `await callback(progress, total, message)`（位置三元组）调用，按请求的 progress token 匹配（`mcp/shared/session.py:409-420`）。
5. **HTTP 401**：POST handler 调 `response.raise_for_status()`
   （`streamable_http.py:381`），因此 `initialize()` 期间的 401 表现为
   `httpx.HTTPStatusError`（`.response.status_code == 401`），可能被 transport 任务组包进 anyio `ExceptionGroup`。`connect()`
   解包组并把 401 映射为 `needs-auth`。
6. **测试 helper**：`mcp/shared/memory.py` 提供
   `create_client_server_memory_streams()`（yield `(client_streams,
   server_streams)`）与 `create_connected_server_and_client_session(server:
   Server | FastMCP, read_timeout_seconds=..., ...) -> AsyncGenerator[ClientSession]`
   （yield 已初始化 session；FastMCP 经 `_mcp_server` 解包）。
   **FastMCP**（`mcp/server/fastmcp/server.py`）：`FastMCP(name)`（`:157`）、
   `@mcp.tool()`（`:462`）、`mcp.run(transport="stdio")` 是同步的且默认 stdio（`:295-312`）。
