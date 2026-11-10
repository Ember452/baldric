# Extension Surface Parity — 参照 Pi 的可扩展性演进计划

Status: **PLAN ONLY**（不改代码）。动手前必须重新扫描确认（见 §0）。
参照对象：`pi-main/packages/coding-agent/docs/extensions.md`（2597 行）+ `pi-main/packages/agent`。
目标对象：`baldric`（`src/baldric/{protocol,ai,agent,runtime,mcp}`）。
日期：2026-11-10。作者：Lead（AI）。

---

## 0. 这份计划的性质与铁律（每次动手前必读）

这是一份**参照计划，不是施工图**。随时间、随代码演进会失真。因此：

- **动手前必须重扫**：每个 Task 开工前，按该 Task 的"扫描清单"重新 `grep`/读源码，
  确认计划里描述的文件、行号、符号、引用仍成立；不成立就以现场为准修订计划。
- **计划允许偏离**：如果现场发现更优解或计划有误，**以现场为准**，并在动手前的
  说明里写清"偏离了什么、为什么"。
- **允许计划之外的必要改动**：如果实现某个把手必然要动一处计划没写到的代码（例如
  一个隐藏的 import 环、一个必须加的 protocol 字段），**允许做**，但前提是：
  1. 先完成"影响面评估"（见 §5 的强制清单）；
  2. 在提交信息 / dev-note 里说明这处越界的必要性与影响面；
  3. 全门禁 + 完整测试通过。
- **禁止不看全面就动手**：任何改动前，必须查清"这个词/符号/文件被谁用、被谁引用、
  改动会影响哪些层"。用 `git grep` + import-graph + 测试面三维确认。
- **质量红线**：高内聚低耦合；一个模块一个职责；不为单点用途造抽象；不复制粘贴；
  不新增 `# type: ignore`/`# noqa`（抑制棘轮只降不升）；改完 `ruff/mypy/ratchet/完整 pytest` 全绿。

---

## 1. 结论先行：差距的本质

**不是权限模型的问题，是"把手宽度"的问题。** Pi 的自由度来自两个乘数：

> **自由度 = 把手宽度（谁都能拿到活对象去改） × 可回放性（每次改动都落进事件源日志，可重放/回退）**

baldric 的 `EXTENSION_API_VERSION=1` + `capabilities` 是"**声明依赖**"的保守哲学，
Pi 是"**宽把手 + 回放兜底**"的开放哲学。两者不是同一个东西的早期/后期版本。
**caps 不是障碍，但也不是通往 Pi 自由度的路；追赶 Pi 需要真的把活把手造出来。**

前提条件——**事件源可回放**——baldric **基本已具备**（session JSONL 是事件源、
`append_entry` 已在跑、protocol 有 `replay` 语义）。这是最重要的好消息：不用先补地基。

**第三个乘数（本计划修订后加入）：hook 组合语义。** 宽把手一旦放进"多个扩展同时拦截"
的场景，若没有定义顺序/隔离/聚合/谁赢，宽把手就成了"未定义行为"。Pi 有专门的
Handler Composition 一节；baldric 现状（`runtime.py:1334 emit_event` + 各处
`except: isolation boundary`）**只有"吞异常"，没有顺序/聚合/谁赢的契约**。所以：

> **自由度 = 把手宽度 × 可回放性 × 组合语义确定性**

三条缺一不可。Task 0 就是先把第三个乘数定死，否则 A/B 造出的是一批"语义未定义的 API"。

---

## 2. 现状精确对照（2026-11-10 扫描结果，务必复核）

### 2.1 事件层级（Pi 4 级 vs baldric）

Pi 的事件（`docs/extensions.md` 实测 **41 个**，按层级）。注：本地 checkout 该文件为
**2597 行**，上游已涨到约 **3365 行**（事件可能仍在增）——差异本身印证 §0"随时间失真、
动手前重扫"的必要性；下表按本地实测 41 事件，动手前须以当时的 docs 为准。

| 层级 | Pi 事件 | baldric 现状 |
| --- | --- | --- |
| **输入级** | `input`, `user_bash`, `ui_prompt_start/end` | ✅ `input`；❌ `user_bash`、`ui_prompt_*` |
| **会话结构级** | `session_start/shutdown`, `session_before_switch/fork/compact/tree`, `session_compact(_failed)`, `session_tree`, `session_info_changed`, `resources_discover` | ⚠️ 有 `session_start/shutdown`、`session_info_changed`；❌ 全部 `before_*` 否决点、`session_compact(_failed)`、`session_tree`、`resources_discover` |
| **agent/turn/message/tool 级** | `before_agent_start`, `agent_start/before_settle/settled/end`, `turn_start/end`, `message_start/update/end`, `tool_call`, `tool_execution_start/update/end`, `tool_result`, `model_select`, `thinking_level_select`, `project_trust` | ⚠️ 内核事件 11 个（`AgentStart/TurnStart/MessageStart/RetryAttempt/MessageUpdate/MessageEnd/ToolExecution*/AgentEnd`）；扩展层 `AGENT_EVENT_TYPES` 18 种 + `LIFECYCLE` 6 种，含 `input/tool_call/tool_result/project_trust/session_start/shutdown`。❌ `before_agent_start`（改 system prompt 的时机）、`model_select`、`thinking_level_select`、`agent_before_settle` |
| **provider 级** | `context`, `context_with_system`, `before_provider_headers`, `before_provider_request`, `after_provider_response`, `provider_stream_event`, `cache_warming_decision` | ❌ **整层缺失**（最重要差距）。`ai` 层只有 `env.RuntimeResponseHeadersObserver`（只读响应头）与内部 `_provider_events` |

### 2.2 活把手（Pi `pi.*` / `ctx.*` vs baldric `ExtensionAPI`）

Pi 的 `pi.*`：`setActiveTools`, `registerTool`, `setModel`, `setThinkingLevel`,
`registerProvider`, `registerVirtualModel`, `registerMcpServer`, `appendEntry`,
`registerFlag`, `registerShortcut`。
Pi 的 `ctx.*`：`fork`, `navigateTree`, `switchSession`, `newSession`, `compact`,
`getSystemPrompt`, `getContextUsage`, `executeTool`, `abort`, `reload`, `shutdown`,
`waitForIdle`, `hasPendingMessages`, `isIdle`, `isProjectTrusted`, `sendUserMessage`, …

baldric `ExtensionAPI` **已有**（实测）：`register_tool`, `unregister_tool`,
`register_provider`, `update_provider`, `register_local_backend`, `register_command`,
`add_prompt_guideline`, `add_prompt_section`, `on`, `send_user_message`,
`send_custom_message`, `register_message_renderer`, `append_entry`, `set_label`,
`set_inference_provider`, `refresh_system_prompt`，以及 UI 组件缝
（`set_slot_widget`/`open_main_view`/`register_key_interceptor`/sidebar）。

**关键差异**：baldric 的扩展**能加**（register）但**不能"改结构"**——没有覆盖内建工具、
没有 `set_active_tools` 动态开关、没有 `ctx.session_manager`（改会话树/分支/切换）、
没有 compaction 接管、没有 per-type 的 entry/tool/markdown renderer。

### 2.3 好消息（底子已有的）

- protocol 已有 `CustomEntry / CustomMessageEntry / LabelEntry` 三类一等 entry（`entries.py:58/116/140`）。
- `append_entry(namespace, data)` 已实现且 subagents 扩展在用（`api.py:1324`）。
- `register_message_renderer` 已有（`api.py:1283`）；缺 `register_entry_renderer` /
  `register_tool_renderer`(按工具名定制) / `register_markdown_transformer`。
- `components` 能力缝已把 Textual 做成"可选契约"，方向正确。
- session 事件源 + `append_entry` 落盘 + protocol `replay` —— **可回放前提基本具备**。

---

## 3. 分层落点判据（先定层，再动手）

三层责任边界（来自各 AGENTS.md，且有 import-graph 强制）：

- `baldric.agent`（内核，9 文件 ~1500 行）：纯循环 + 事件 + 工具编排，**不得依赖 provider
  实现/frontend/文件系统**。
- `baldric.protocol`（契约，~1100 行）：wire 类型、entry 形状、provider 端口，只依赖 pydantic。
- `baldric.ai`（provider 适配）：只依赖 protocol 契约面。
- `baldric.runtime`（宿主，~5.7 万行）：session 编排、extensions、TUI、CLI、config。

**判据（每个 Task 必答）**：
1. 这个能力是"纯循环行为"吗？→ 内核；否则 → runtime。
2. 是"wire 形状 / 契约"吗？→ protocol；否则 → runtime。
3. 是"provider 请求/响应处理"吗？→ ai；否则 → runtime。
4. 只有 runtime 一层能同时看到 session + tools + providers + frontend —— **绝大多数活把手属 runtime**。

**内核是否要动？** 默认不动。**唯一可能要动内核的缝**是 provider 级事件——但优先方案
是把它做成 `ai` 层的 provider **装饰器/包装**（agent 无感）。只有"必须让 agent 在请求前
看到 hook 结果"时才考虑内核加一个 `before_request` 参数（届时按 §5 全量评估）。

---

## 4. 任务清单（按依赖排序，每项含"扫描清单 / 落点 / 影响面 / 验收"）

> 顺序原则：**先定 hook 组合契约（语义基座）→ 再扩事件覆盖率（低风险、纯增量）→ 再补活把手
> （要评估影响面）→ 最后升版本**。每项可独立成 PR、独立全门禁验证。
> **任何一项开工前重扫，确认不成立就改计划。**

### Task 0 — Hook Composition 契约（A/B 的前置，纯设计 + dev-note，零运行时风险）

这是全计划**最容易被忽略、最难事后补**的一条：多个扩展同时要在同一个缝上拦截时，
**顺序 / 错误隔离 / 结果聚合 / 谁赢**必须现在就版本化定死，否则 v2 交付的是一个
"语义未定义"的 API。**A（provider 5 缝）与 B（结构否决）必须共用这一套规则，不得各自定义。**

- **扫描清单（动手前）**：`runtime/extensions/runtime.py` 的 `emit_event`（实测 `:1334`）
  与各 handler 调用点的 `except Exception ... # extensions are an isolation boundary`
  （实测 493/1257/1320/1344 行）——确认现状是"只有吞异常，没有顺序/聚合契约"。
  `api.py` 的 `on(...)` 注册与 handler 存储结构。
- **要定死的 4 条规则（写进 `dev-notes/architecture/hook-composition.md`，作为 v2 合同一部分）**：
  1. **顺序**：handler 按注册顺序（扩展加载顺序 + 扩展内注册顺序）确定性执行；顺序可观测、可测试。
  2. **错误隔离**：单个 handler 抛异常 = 该 handler 本次失败、记诊断，**不影响其它 handler**、
     不中断运行；失败语义（fail-open 还是 fail-closed）**按缝分级**——安全缝（trust/tool 拦截）
     fail-closed，纯观测/渲染缝 fail-open。禁止"抛异常即静默改变全局结果"。
  3. **聚合**：区分两类缝，**不得混用**——
     - **transform 链**（`input`/`context`/`message_end`/`tool_result`/`before_provider_request`）：
     后者收到前者的返回值，**链式**传递；
     - **mutate in-place**（`before_provider_headers.headers` 这类）：后者看到前者就地改过的同一对象。
     一个缝**只能是链式或就地之一**，在契约表里逐缝标注，代码里用类型强制（链式缝返回新值、
     就地缝无返回）。
  4. **谁赢（终止型结果）**：`block`/`cancel`/`handled` 这类"门"是**短路**——第一个返回门结果
     的 handler 结束该缝，后续 handler 不再运行该操作；对"last override 型"（如暖缓存决策）
     则是**最后一个有效返回者赢**。逐缝在契约表里标注属"首个短路"还是"末个胜出"。
- **落点**：先只写 **`dev-notes/architecture/hook-composition.md`**（契约表：每个缝一行，
  标注 `链式/就地` + `fail-open/fail-closed` + `首个短路/末个胜出`）+ 一个**极小的 fake 测试**
  证明现有 `emit_event` 至少满足"顺序 + 隔离"两件。**不改运行时代码**（真正实现随 A/B 落地）。
- **影响面**：纯文档 + 一个测试，零运行时风险；但**A/B 的实现必须引用这张表**。
- **验收**：契约表覆盖 A 的 5 缝 + B 的结构否决缝；有一张"同一事件两个扩展都 block"的
  确定性行为说明；`dev-notes` 里明确"v2 的每个新缝都要在这张表加一行，否则不合规"。
- **为什么独立成 Task 而不并入 A**：组合语义是 A 与 B 的**公共前置**，塞进 A 会导致 B 重复
  定义或漂移。这是本项目"高内聚低耦合"在契约层面的直接体现。

### Task A — provider 级事件缝（最高价值、最大差距）

- **扫描清单**：`ai/*.py` 每个 adapter 的 `stream_response` 里 headers/payload 构造点
  （如 `anthropic.py:161-183`）；`ai/env.py` 的 `RuntimeResponseHeadersObserver`；
  `agent/assistant_stream.py` 与 `provider.stream_response` 的调用边界；
  `protocol/provider.py` 的 `ModelProvider` 协议。
- **落点**：优先做在 **`baldric.ai`**——给 `ModelProvider` 加一个**可选的 provider 装饰器**
  `HookableProvider`（组合而非继承），包住真实 provider，暴露 5 个缝：
  `context`（改上下文消息）、`before_request`（改 headers/payload 副本）、
  `after_response`（读 status/headers，流消费前）、`stream_event`（观察解析后的流事件）、
  `cache_warming_decision`（暖缓存决策）。**agent 内核零改动**（它只看到 `ModelProvider`）。
- **protocol 是否动**：只有在需要"请求体类型"进契约时，加一个**只读** `ProviderRequestView`
  到 protocol；否则用 `Mapping`/`JSONValue`，不动 protocol。
- **影响面**：`ModelProvider` 协议是 `ai` 层唯一出口，被 `runtime/providers/runtime.py`
  构造、`agent` 消费、所有 adapter 实现。**新增装饰器是"加"不是"改"**，风险低；但要确认
  没有 adapter 直接依赖具体 provider 类型而绕过协议。
- **验收**：一个 fake extension 能改 header、能替换 payload、能读到流事件；现有全部 adapter
  测试绿；`import-graph: OK`；agent 内核零 diff。**外加两条硬验收**：
  - **空钩子零变化**：未注册任何钩子时，`HookableProvider` 包装前后的最终请求字节序列
    与响应行为**完全一致**（用 golden 对比，证明"透明包装"）。
  - **缓存指纹有定义**：`before_request` 改写 payload 会使 provider 侧 prompt-cache 前缀
    失效（Pi 用前缀指纹感知）。因此契约里必须写明：改写后的 payload 参与缓存键/前缀指纹
    的重新计算，**不得让扩展"以为缓存还在、其实已失效"**；验收含一条"改写后缓存语义可解释"
    的测试（可用 adapter 的 cache_control/fingerprint 断言）。
- **参照而非法复制**：Pi 用 `pi.on("before_provider_*")` 回调；我们用 `HookableProvider` 组合，
  不把 provider 逻辑塞进 agent。

### Task B — 会话结构级否决点（before_compact / fork / switch / tree）

- **扫描清单**：`runtime/session/{compaction,session,branching,lifecycle,runtime}.py` 中
  压缩、fork、switch、tree 导航的真实入口函数；现有 `compaction_start` 事件在哪产生、
  有没有"先问再执行"的位置。
- **落点**：**`runtime.session`**。在每个结构操作**执行前**加一个"可否决/可改写"的 hook 槽，
  由 `ExtensionRuntime` 分发；hook 返回 `block | transform`。压缩（`before_compact`）
  优先——因为它最常被扩展接管（Pi 的 `custom-compaction.ts` 是标准用例）。
- **压缩按触发源分级（关键，防死循环）**：
  - **manual / threshold 压缩**：扩展可 `block`（取消）或 `replace`（自定义摘要）。
  - **overflow 压缩**：扩展**只允许 `observe` 或 `replace`，禁止 `block`**。返回 `block`
    = 契约违规，host 报错给该扩展作者、并**强制执行默认压缩**（显式失败 + 默认行为兜底，
    不是静默 fallback）。理由：模型反复 overflow + 扩展否决 = 无限重试死循环。
- **影响面**：session 是全仓最热的模块（1.1 万行），任何插入点都要确认不破坏
  "durable history append-only" 契约（AGENTS.md 硬规则）。**先在压缩这一条打样**，
  验证模式无副作用后再推广到 fork/switch/tree。
- **验收**：扩展能取消一次 **manual** 压缩并给自定义摘要；**overflow 路径下扩展 block 被拒且
  默认压缩执行**；被取消时事件序列完整；durable 日志可回放；无死循环（overflow 连发测试）。

### Task C — 活把手：动态工具面（setActiveTools / 覆盖内建工具）

- **扫描清单**：`runtime/extensions/runtime.py` 的工具注册表（`register_tool:564`、
  `unregister_tool:598`）；`agent.harness` 每次 turn 取 tools 的路径；
  `compose_tools` / `_filter_tools`（provider_helpers）；哪些内建工具名是硬编码。
- **落点**：**runtime.extensions + agent.harness 的"取工具集"接口**。新增
  `set_active_tools(...)`（按名字开关一组工具）和 `register_tool(..., override=True)`
  （覆盖同名内建工具）。**是否动内核**：如果 harness 已有"每次 turn 重新解析 tools"的缝，
  只需 runtime 侧维护集合；否则需在 harness 加一个"tools provider 回调"——**这是可能要碰
  内核的最小点，届时按 §5 全量评估**。
- **影响面**：工具集被 agent、session、TUI 三处消费；覆盖内建工具会影响安全边界（内建
  bash/read/write 是信任模型的一部分）——覆盖必须在 trust 边界内有声明。
- **验收**：扩展能关掉某个工具、能用替身覆盖某内建工具；被覆盖的工具调用走替身且 trust
  仍生效。**外加**：`ctx.execute_tool(name, args)`（Pi `ctx.executeTool`，扩展调用其它工具
  的把手，docs:1165/2758 明列）——与动态工具面同属"工具可达性"语义，放在本 Task 一起设计
  与验收（一个 fake 扩展能调用另一个已注册工具并拿到结果；被禁用的工具不可经此通道调用）。
- **归属说明**：`ctx.execute_tool` 也可作为 Task E 的验收项（它依赖 session 的工具执行环境），
  但**优先在 Task C 落最小可用版**（只要求调用已注册工具），Task E 再补"经 session 环境执行"。

### Task D — 三类 renderer（entry / tool / markdown transformer）

- **扫描清单**：`api.py:1283` 的 `register_message_renderer` 实现；`rendering/` 里
  message/tool/entry 的渲染分发点；`protocol/session/entries.py` 三类 entry 的字段；
  `tui/adapter.py` 里 CustomMessageMarkup / ToolCallMarkup / ToolResultMarkup 的解析器。
- **落点**：**runtime.extensions（注册）+ runtime.rendering（解析）**。补齐：
  `register_entry_renderer(customType, fn)`、`register_tool_renderer(toolName, fn)`、
  `register_markdown_transformer(fn)`。**protocol 大概率不动**（entry 已有 `details: JSONValue`）。
- **影响面**：渲染分发是 TUI 热路径；新增解析器要保证"失败降级到默认"，不抛进 frontend
  （沿用现有 `CustomMessageMarkup` 的"吞错"约定）。
- **验收**：扩展能给自己的 `append_entry` 类型挂渲染器，重启后仍渲染正确。

### Task E — `ctx.session_manager` 活把手（改会话树：fork / navigate / switch / compact）

- **扫描清单**：`runtime/session/session.py` 的公共方法（fork/navigate/switch/compact/load）；
  `SessionManager`（`session/manager.py`）；扩展拿到的是不是只读快照；
  durable 契约（每次 mutation 必须过 storage 事件源）。
- **落点**：**runtime.extensions.api 的 `context`** 暴露一个**受控的** `session_manager`
  句柄；所有 mutation 走既有 session 的公共方法（不新开旁路），保证每条改动都落进事件源。
- **依赖**：**排在 Task B 之后**（结构级 hook 先建立"每次结构操作都过钩子"的模式），
  且**强烈建议在服务化/审计（见项目 kernel 阶段6 产品化 guard）之后**——Pi 敢交活把手的
  前提是"每次 mutation 都过审计日志"，baldric 应先有可信的 mutation 审计再放开。
- **影响面**：最大。session 是最高耦合模块；活把手一旦放开，扩展可能制造非法树状态。
  **必须伴随**：mutation 前校验 + durable 事件源 + guard（禁止扩展绕过 protocol 直连内部）。
- **验收**：扩展能 fork/切换/压缩，重启后树状态一致；非法操作被拒且日志可回放。

### Task F — 小缺口（低优先级、可随时补）

- `user_bash`（`!` 命令拦截）、`register_shortcut`、`register_flag`、
  `before_agent_start`（改 system prompt 的标准时机）。落点均在 runtime。
- **归属补齐（原 §2.1/§2.2 已列但未挂任务的事件与把手）**：
  - 事件 `model_select` / `thinking_level_select`（Pi 明列）→ 本 Task；
  - 把手 `set_model` / `set_thinking_level`（Pi `pi.*` 明列）→ 本 Task（与上面两个 select
    事件成对：一个是"通知已选"，一个是"主动设置"）。
- **验收**：各自有最小用例；`set_model`/`set_thinking_level` 改动后下一请求生效且事件
  （`model_select`/`thinking_level_select`）被投递；不破坏现有 input/trust 流程。

### Task G — `EXTENSION_API_VERSION` 1 → 2

- **触发条件**：Task A–E 里凡**改变扩展可见契约**的（新 hook 名、新 API 方法、新 entry 字段、
  新 renderer 类型）落定后，才升版本。
- **做法**：升 `EXTENSION_API_VERSION`，写迁移说明（旧扩展声明 v1 仍按 v1 语义加载或明确拒绝），
  更新 `dev-notes/architecture/phase-21-extensions.md`、`website/content/guides/extensions.md`、
  bundled `data/docs/extensions.md`。
- **capabilities 按域映射（关键，防 caps 沦为摆设）**：每个新增的 hook / API / renderer **必须**
  落到 `ExtensionCapabilities` 的某个**域**上——`provider_hooks` / `session_structure_hooks` /
  `renderers` / `dynamic_tools` / `session_handle` 等（**按域分组，不逐 hook 一个布尔**，否则字段爆炸）。
  语义：v1（或未声明该域）的扩展 → **该域的所有钩子不注册、事件不投递**（默认拒绝，不是默认放行）。
  这样 caps 与宽把手不会脱节：宽把手只在扩展**显式声明要这个域**时才生效。
- **验收**：v1 扩展行为不变或明确报错；**未声明某域的扩展调用该域新缝返回"未授权"而非静默生效**；
  文档三处同步；`dev-notes/hook-composition.md` 的契约表与 caps 域表一一对应（每个缝标注所属域）。

---

## 5. 强制影响面评估清单（每个 Task 动手前逐条过，缺一不可）

对每个要改的符号/文件，回答：

1. **谁引用它**：`git grep -n "<symbol>"` 全仓结果，按 `src/` / `tests/` / `docs` 分类；
   每个引用点是否受影响。
2. **哪层依赖它**：`scripts/check_import_graph.py` 的 RULES 是否覆盖；改动是否越层。
3. **测试面**：哪些测试文件导入/断言它（尤其 `tests/guards/` 的契约测试、
   `test_public_surface.py` 的 139 符号冻结、`test_public_api_contract.py`）。
   **公共 API 面变化必须同步更新契约测试并说明。**
4. **durable 契约**：改动是否触碰 session 事件源 / append-only / replay？若触碰，必须证明可回放。
5. **棘轮**：`check_structure / check_suppressions / check_agent_guidance` 会不会涨？
   涨了要么拆、要么 `--init` 记录并评审。
6. **TUI 边界**：改动是否把 Textual 拉进不该有它的层？`components` 能力缝是否仍可选？
7. **回滚性**：这个改动能不能独立回滚（一个 PR 一个语义）？

**未完成上述评估，禁止动手。**

---

## 6. 质量与可维护性守则（贯穿每个 Task）

- **高内聚**：provider 钩子全在 `ai` 的 HookableProvider；session 结构钩子全在 `runtime.session`
  的一个钩子分发点；renderer 全在 `runtime.rendering`。不把钩子逻辑散到各处。
- **低耦合**：hook 用 `Protocol`/`Callable` 定义在边界模块；实现方（扩展）只依赖窄接口。
  agent 内核不 import runtime；runtime 不 import 具体 adapter 实现（走协议）。
- **参照 Pi 不照搬**：Pi 用 TS 的 `pi.on(event)` + declaration merging + `ctx` 大对象；
  Python 侧用**协议 + 组合 + dataclass 事件**表达同一意图，不照抄 `ctx` 巨对象（避免 god object）。
- **一次一个语义**：每个 Task 一个 PR、一个原子提交、完整门禁。
- **可测试**：每个钩子用 fake extension 覆盖正/负/降级三条路径。

---

## 7. 建议的执行顺序与理由

0. **Task 0（Hook 组合契约）** → **最先**。纯文档 + 极小测试、零运行时风险，但锁定 v2 全部
   钩子的语义基座；A/B 实现必须引用它。
1. **A（provider 缝）** → 差距最大、风险最低（纯增量、内核不动）。
2. **D（renderer 三类）** → 纯增量、用户可见价值高、依赖小。
3. **B（会话结构否决）先做压缩一条** → 建立"结构操作过钩子"的模式，验证 durable 无副作用。
4. **C（动态工具面 + execute_tool）** → 评估可能碰内核的点；安全边界要设计。
5. **F（小缺口 + model/thinking select/set）** → 随时可插空做。
6. **E（session_manager 活把手）** → 最后，且应在可信 mutation 审计/产品化 guard 之后。
7. **G（升 v2 + caps 按域映射）** → 上述契约落定后收口。

**不要为"自由度"造新阶段**：全部挂进项目既有的 `phase-21 extensions` 续做 +
`kernel 阶段6（产品化 guard）`。计划文档本身零代码。

---

## 8. 本计划明确不做 / 需另议

- **不照搬 `ctx` 巨对象**（Pi 的 `ctx` 是 TS 便利产物；Python 用分域句柄更好维护）。
- **不在本轮做工具并行执行**（baldric 有 `test_harness_rejects_parallel_tools`，是有意识取舍，
  与扩展自由度正交）。
- **不为了"能力数量"堆 API**：只造真实用例需要的把手（Pi 的每个事件都有 example 支撑，
  baldric 也应"有真实扩展用到才加"）。
- **不把 `emit_event` 现状当既定契约**：现有"只吞异常"的实现不是组合语义，Task 0 会显式定义，
  届时 `emit_event` 可能被重构（顺序/聚合），但必须保持"单 handler 失败不影响他人"的 back-compat 行为。
- 文档口径（"Baldric can create extensions. Ask it to…" + `baldric install git:` 分发包）
  是**独立的小改动**，不属本计划代码面。

---

## 9. 验收总则（每个 Task 收尾必跑）

- `uv run ruff check . && uv run ruff format --check . && uv run mypy`（mypy 允许正好 14 个已知 Windows 错误）
- `uv run python scripts/check_import_graph.py`（OK）
- 三个棘轮 + `verify_versions.py`（OK 或已评审 `--init`）
- `uv run pytest`（完整；行为等价于基线，仅允许已知 Windows TUI flaky，重跑即过）
- `uv build`（wheel 内容不变形）
- 该 Task 的 fake-extension 用例通过；公共 API 契约测试同步。
