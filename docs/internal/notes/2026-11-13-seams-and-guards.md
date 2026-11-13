# 契约接缝与守卫收尾（2026-11-13，PR #74 之后）

本记录对应分支 `fix/seams-and-guards`。上游背景：A0–G 结构重构合并后，一次三路只读审计
指出了若干"账本与实际不符"的接缝（结论见 `2026-11-11-structure-debt-review.md` 的后续复核）。
本分支只做**能一次做完、且有守卫兜住**的项；每一项都先核对当前 HEAD 再动手，不照抄审计的
行号（审计快照落后于合并后的代码，四项 P1 在 PR #74 里已经修掉）。

## 做了什么

### 1. 动态 provider 契约搬回 provider 域（消除包级双向依赖）

`platform/providers.py`（636 行：`DynamicProvider`、`ProviderModel`、auth 策略、
transport、model snapshot）只依赖 `protocol`、`context.thinking` 与 `providers.*`，
本来就不是平台代码。它留在 `platform` 造成了一条包级双向边：

- `providers/runtime.py` → `platform.providers`（还跨包引用了私有
  `_MissingRequiredApiKeyError`）；
- `platform/providers.py` → `providers.catalog` / `providers.config.models`。

做法：

- `git mv platform/providers.py → providers/contracts.py`，单一归属；
- 14 个消费方改从归属模块导入（platform 的 api/provider_registry/runtime/__init__、
  providers/runtime、session 的 lifecycle/model_selection/provider_helpers/session、
  features 的 llama_cpp/subagents，以及测试与测试内嵌的扩展源码字符串）；
- `platform/__init__` 不再聚合 provider 契约：82 → 59 个导出、179 → 131 行。这不是新
  规则，而是平台根早已对 `providers.backends` 契约执行过的同一条规则
  （`test_platform_root_reexports_only_platform_owned_names` 现在同时约束这条边）；
- `baldric.api` **不动**：它是扩展作者的稳定公共面，按设计不承载 provider 域契约
  （与 backends 契约同一先例），因此本次没有公共契约变更、无需 bump
  `EXTENSION_API_VERSION`；
- 新增守卫边 `providers ✗→ platform`，反向（platform 消费 provider 契约）是允许方向。

### 2. 三个构造路径都遵守 `disabled_built_in_extensions`

该字段是文档化的宿主 seam（子代理子会话传 `{"mcp"}` 让 MCP 客户端不在子会话里启动）。
三条构造路径只有第一条过滤：

| 路径 | 之前 | 现在 |
|---|---|---|
| 首次 `CodingSession.load` | ✅ 走 `prepare_runtime_for_load` | 不变 |
| `/reload`、rebind | ❌ `stage_runtime_for_reload` 没有过滤参数，回落到全量注册表 | 新增必填参数并转发 `eligible_built_in_extensions(session._config)` |
| `resume` | ❌ 重建 config 时漏字段，回落到 `frozenset()` | 显式携带 |

`eligible_built_in_extensions` 改为通过模块读取注册表（不再用导入时拷贝的名字），
使过滤器和加载器永远看同一个对象（也让测试能替换成记录型注册表）。

回归测试：一个会话走 首次加载 → reload → resume，断言被禁用的内建从未运行。
**守卫有牙**已验证：把 reload 调用点或 resume 关键字改回去，对应断言各自失败。

### 3. 非交互渲染器的事件完备性守卫

TUI 有"新事件必须被投影/DOM 处理/显式 noop"的守卫，三个 print 渲染器没有。现在
`plain.py` / `json.py` / `transcript.py` 各自声明：

- `RENDERED_EVENT_TYPES`：其 `isinstance` 分支真正消费的会话事件类；
- `INTENTIONAL_NOOP`：其余每个会话事件 + 一行理由。

守卫测试（`tests/guards/test_print_event_dispatch.py`）断言精确划分、理由非空、双向真实性
（声明的 RENDERED 必须真的出现在 `isinstance` 里；真的 `isinstance` 分发不许藏在 NOOP 里）。
21 个会话事件：plain/json 各渲染 2、解释 19；transcript 渲染 9、解释 12。

**守卫立刻抓到一处真 bug**：transcript 的"闭合流式助手块/补最终换行"分支判断
`AgentEndEvent`，而 `session.prompt()` 在渲染器看到之前已把 `AgentEndEvent` 改写成
`SessionAgentEndEvent`（`session/runtime.py:432,494,567`），于是被中止的运行永远不补换行。
已改为匹配会话形态（并保留代理形态给 harness 级调用方），并有回归测试。

### 4. RPC 入口收口（所有权 + 错误面）

- **provider 泄漏**：`run_openai_rpc_mode` 先建 provider，再在 try 之外 `CodingSession.load`，
  finally 才 `aclose` provider；且 config 没设 `owns_initial_provider`，会话无权关闭它，
  load 失败就泄漏一个活着的 httpx client。现在与 print/TUI 一致：`prepare_coding_session`
  + `owns_initial_provider=True` + `adopt()`，finally 里会话存在就 `aclose()`（幂等，
  覆盖 `RpcServer.run` 异常跳过 close 的路径），否则自己关 provider。附带收益：RPC 的
  权威写入现在推迟到 adopt，不再在校验前落盘。
- **错误面**：`_run_prompt` 只捕 `(RuntimeError, ValueError)`，但它跑在 anyio task group 里，
  一个 `OSError`（磁盘满、编码失败）会取消整个 group：读循环死掉、会话不关闭、异常
  ExceptionGroup 冒到 CLI（CLI 只捕 RuntimeError/ValueError）。现在记一条 `rpc_error`
  并只结束该 prompt；报告写入本身失败时不再抛（对端已断）。
  **守卫有牙**已验证：把处理面改回去，测试以 ExceptionGroup 失败。

### 5. RPC 不再上报假的 bash/压缩状态

- `TerminalCommandResult` 之前只有 command/output/exit_code/ok/added_to_context，而 bash
  工具早已在 details 里给出 `truncated`/`cancelled`/`full_output_path`、持久化的
  `BashExecutionMessage` 也早有这三个字段——结果对象把它们丢了，于是"Showing lines 1-N of M"
  的可见截断在 wire 上被报成 `truncated: false`。现在三层贯通。
- `isCompacting` 是事件派生状态（会话没有该属性，TUI 也是从
  `CompactionStart/EndEvent` 推导）。RPC 现在在 prompt 事件流上跟踪它并上报真值。
  手动 compact 期间仍不可观测（dispatch 阻塞到结束），这是结构性的，不是隐瞒。
- `steeringMode`/`followUpMode` 仍是常量，但**当前为真**（harness 队列模式固定
  `one_at_a_time`，代码里没有任何地方设 `"all"`），已用注释说明；要上报实时值需要给
  session 增加 `queue_mode` 成员，记录在 RPC 互通计划里而不是在这里伪装。

### 6. `get_tree` 深链不再爆栈

会话条目是父子链，递归投影深度随会话增长：实测 996 条即 `RecursionError`，而 1500 条链是
受支持的会话（`tests/runtime/session/test_coding_session.py` 已有该回归）。改为显式栈的
后序遍历，树形状、字段值与子节点顺序不变，`_entry_wire` 仍对每个可见条目调用一次。
1500 条链的回归测试在旧实现下会以 RecursionError 失败。

### 7. 抑制棘轮去空气化

棘轮记录 138 条抑制，其中 118 条 `# noqa` 指向本项目**没有启用**的规则（93 `BLE001`、
19 `F401`、3 `SLF001` 等）——它们什么也压不住，永远不可能被"用上"，棘轮大部分在量空气。

- `RUF100` 加入 ruff select：无效 `# noqa` 从此是 lint 失败（这才是长期守卫）；
- 一次性清理：删除 164 条裸指令，把 117 条转成普通注释**保留理由**
  （`# noqa: BLE001 - hooks are an isolation boundary` → `# hooks are an isolation boundary`），
  部分失效的指令只摘掉死码、保留活码；
- 这次改动是机械的，因此单独成一个 commit、先 dry-run、并用 **AST 相等**校验：59 个被改
  文件的语法树在改前改后完全一致，证明只动了注释；
- 抑制基线收紧 138 → 29（16 个文件），剩下的每一条在当前规则集下都是必要的。

**刻意没做**：启用 `BLE001` 本身。启用会一次性产生 ~133 条违规（93 条原本被隐藏的 +
40 条从未标注的），需要对每个 handler 判断"收窄还是记账"，那是独立审计，不该混在注释
清理里做。`AGENTS.md` 里"94 `# noqa: BLE001`"的说法已失效，改为"`BLE001` 未启用，
理由写在普通注释里"，且总字节数仍满足 agent-guidance 棘轮（缩小 18 字节）。

## 影响面与验证

- 无公共契约变更：`baldric.api` 未动，`EXTENSION_API_VERSION` 未动，`protocol/` 未动。
- 行为变更仅三处，且都有回归测试：resume/reload 的禁用内建保持、transcript 中止运行补
  换行、RPC 失败只结束单个 prompt。其余是归属搬迁、注释清理与守卫。
- 验证：fast suite 2310 passed / 52 skipped；guards 86 passed；ruff clean（含 RUF100）；
  format clean；import-graph OK；mypy 仅 14 条已知 Windows-only 错误；suppression ratchet
  29；agent-guidance 通过；structure baseline 的每次增长都按规则 `--init` 记录了评审例外。
- 守卫自证：每个新守卫都做过"改回旧实现必红"的变异验证（见上文各项）。

## 后续（未做，建议单独排期）

1. **`BLE001` 审计**：把 ~133 处宽 except 逐条归类（可收窄的收窄、确需宽的用带理由的
   普通注释 + 记录），再决定是否启用规则。
2. **`session → platform` 可导入面**：`session/` 仍有 9 处模块级 platform import
   （lifecycle、model_selection、provider_helpers、resource_helpers、runtime、session），
   A0–G 的反转只覆盖了"构造"。需要先定白名单再上守卫，真正的搬移留给 H 之后。
3. **RPC `queue_mode`**：给 session 暴露实时队列模式，让 `steeringMode`/`followUpMode`
   不再是常量。
4. **installer 脏树检测**：`extensions update` 只比 `rev-parse HEAD`，未提交修改仍会被
   `--force` 静默覆盖，与 docstring 承诺不符。
5. **子代理 `get_subagent_result(wait=True)` 无超时**：调用方模型可能永久等待。
