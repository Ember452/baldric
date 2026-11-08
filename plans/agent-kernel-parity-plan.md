# 内核补齐计划：baldric_agent ↔ pi packages/agent 字段级对齐

> 状态：**已执行（2026-11-08，分支 `feat/agent-kernel-parity`）**——阶段 A/B/C/D 完成（各阶段执行结论已回写本文件），阶段 E 推迟（§6 决策），阶段 F 决策见 `adr-0003-transcript-as-truth.md`（暂不采纳）。`PROTOCOL_VERSION` 维持 1。
> 依据：2026-11-08 对 pi `packages/agent` v1.5.0 全文（types.ts 551 行 / agent-loop.ts 1025 行 / agent.ts 623 行）与 `baldric_agent` 重构后全文的逐字段对照。控制流已确认一致，差距全部在**扩展面与字段**。
> 行数口径：正文引用均为**物理行**（splitlines）；loop.py 实际 260、harness.py 实际 344（早前 234/284 为非空行口径，已修正）。
> 目标：在产品开发开始前把"该加的"一次补齐，避免功能期再做侵入式内核改动。
> 前置：`kernel-refactor-plan.md` 已合并（main 0bfd8f9）；本计划基于其分层（protocol ← {ai, agent} ← coding）。

---

## 0. 范围与非目标（先说清楚不做什么）

| pi 有 | 本次是否做 | 理由 |
|---|---|---|
| `finishTurn` / `prepareRequest` / `prepareNextTurn` 三钩子 | **做**（阶段 C） | 内核扩展面的核心缺口 |
| `convertToLlm` / `transformContext` 注入 | **做**（阶段 B） | 自定义消息类型与窗口管理的前置 |
| `AgentToolResult.isError` 不抛错报失败 | **做**（阶段 A） | 小改动，真实收益：失败时保住 details |
| `ToolResultMessage.usage` / `durationMs` 落盘 | **做**（阶段 A） | 字段补齐，wire 可加性变更 |
| `AssistantMessage.thinkingLevel` 请求级盖戳 | **做**（阶段 A，含一个决策点） | pi 每条响应记录请求等级 |
| harness 状态观测（streamingMessage/pendingToolCalls/errorMessage/signal） | **做**（阶段 D） | 前端可观测性 |
| `continue_()` 前置校验 + assistant 末条时排空队列 | **做**（阶段 D，含契约冲突决策点） | 防 provider 拒绝 |
| 循环崩溃合成错误消息（agent.ts:542-558） | **做**（阶段 D，决策点） | 消费方永远收到完整事件序列 |
| 并行工具执行（pi 默认） | **不做** | 维持 fail-closed 串行；需要时按 pi 的 preflight/execute 分离设计单独立项 |
| `structuredContent` / `outputSchema` | **不做** | 没有 RPC/程序化消费方之前是死代码 |
| `replay?: "never"\|"safe"` | **不做** | 依赖 durable 意图层，无对应物 |
| Transcript-as-truth（系统消息携带 prompt/工具声明） | **不做** | 重理念项：牵动会话格式与 harness 全貌，需独立 ADR |
| `getApiKey` / `identity` / `transport` / `thinkingBudgets` | **不做** | auth/身份属 baldric_ai 适配层；远程传输明确不做 |
| 中断时批次 break（pi） | **不做，保持 baldric 语义** | 你给每个剩余调用生成错误 result（无悬挂），比 pi 的 break+下游修复更严格，与 fail-closed 哲学一致。记为**有意分歧** |

### 有意分歧清单（正式记录，防止将来被当成"忘了做"）

1. **流式 partial 不进上下文**：pi 在 `start` 事件把 partial 消息推进 `context.messages` 并流式原地更新（agent-loop.ts:536,552）；baldric 上下文**只含完整消息**（loop.py:163 在 MessageEnd 才 append）。baldric 的选择与 append-only 持久化对齐——持久化监听器永远不会看到半截消息。**保持 baldric 语义。**
2. **拉式 async 迭代器 vs 推式 EventStream**：pi 的 `agentLoop` 立即返回 EventStream（后台跑、`.result()` 取终值）；baldric 是消费方驱动的 async 生成器（`_start_run` 先武装 token 解决了同等问题）。Python 生态下拉式更地道。**保持 baldric 语义。**
3. **钩子的 signal 传递**：pi 把 AbortSignal 传给所有钩子。baldric 的新钩子通过 `harness.signal` 属性（阶段 D）取消信号；既有 `before/after_tool_call` 签名不变（before 本就 fail-closed，不需要 signal）。**记为简化，不追平。**
4. **`wait_for_idle` / `reset()` 不采纳**：baldric 的 run 是消费方驱动的迭代器，idle 语义不同；会话替换由 coding 层负责。
5. **`Agent.prompt(text, images)` 便捷重载 / `normalizePromptInput`**：product 层构造 UserMessage，内核不加糖。
6. **harness `__del__` 悬空 run**：消费方丢弃迭代器不 `aclose` 时，依赖 asyncio 的 asyncgen finalizer 在 GC 时调度 `aclose()`，`_run` 的 finally（工具修复）最终会执行——时机不保证但必然发生。**已知边界，本次不修**；若将来出现真实案例，方向是消费侧契约（显式 aclose）而非内核。

---

## 1. 决策点（执行前需拍板，已给推荐）

- **D-T1 `thinking_level` 从哪里盖戳**：pi 由循环盖（agent-loop.ts:527 `Object.assign(await response.result(), { thinkingLevel: config.reasoning ?? "off" })`——**盖请求级**；provider 原生生效值是独立字段 `providerThinkingLevel`，types.ts:600-603 原文 "the agent loop **requested**"）。baldric 的 `ModelProvider.stream_response` 签名没有 thinking 参数，循环也不知道等级。**执行前复核结论（2026-11-08，修正原推荐）**："盖实际生效值"前提不成立——5 个适配器的请求路径均无 catalog 降级（codex/openai 直取 config `openai_codex.py:226`、`openai_compatible.py:183`；唯一的"降级"是 `supportsReasoningEffort=False` 时丢弃 effort，openai_compatible.py:824）；且"生效值"在各适配器内无单一定义（google 把 none 映射为 gemini3-pro 的 LOW、mistral 硬编码 high、anthropic budget 模式无等级名），复制这套映射必然漂移。**定稿**：字段进 protocol，语义 = pi 的**请求级**；盖戳走 `baldric_ai/stream.py:141` 的 `canonicalize_provider_stream` 单一漏斗，新增 `thinking_level` 参数（partial 与 final 两处赋值）；适配器用共享 helper `thinking_level_from_effort(config 中的 effort)`（none→off，其余恒等）从自身 config 派生后传入；config 不携带等级时（anthropic budget 模式、协议层 provider）盖 None——对应 pi 文档 "Absent for legacy or unmanaged responses" 的豁免口径。
- **D-T2 `continue_()` 校验会破坏一个既有测试契约**：pi 语义是"末条为 assistant 且队列无货 → 抛错"（agent.ts:403-417）。现有 `test_continue_also_arms_its_cancel_token_immediately`（tests/agent/test_harness_lifecycle.py:94）在末条 assistant 时调用 continue_ 并期望收到 aborted 消息。**执行结论（2026-11-08，半采纳修正原推荐）**：采纳 pi 的**排空分支**（末条 assistant 时整队排空 steering，其次 follow_up，作为新 prompt，pi drain() 语义）与**空历史拒绝**；**不采纳** assistant 尾的一刀切拒绝——(1) baldric 每次 run 的 prelude 修复已保证无悬空工具调用到达 provider（被拒的"注定请求"不存在），(2) coding 层 HF 自动 failover 的重试流真实依赖"错误轮后 continue_"（pi 不需要该路径，因其 failover 在传输层）。严格版曾让 5 个 session 测试失败，其中 3 个是 failover 主干流。测试影响：arming 测试改为 user 尾；空会话 continue 测试补种子消息。
- **D-T3 循环崩溃是否合成事件**：pi 合成 error 消息 + 全套事件后**正常收尾**（不 re-raise）。baldric 目前让异常传播到消费方。**推荐**：采纳 pi——`_run` 捕获 `Exception`（`CancelledError` 照旧穿透），合成 assistant error 消息 + `turn_end` + `agent_end` 后正常结束迭代器；消费方从此永远收到结构完整的 run。破坏性变更（原来 catch 异常的消费方改行为），在发布说明列出。

---

## 2. 阶段 A：字段补齐（**涉及包：protocol + ai + agent**，wire 可加性变更，PROTOCOL_VERSION 不升）

依据 ADR-0001 兼容策略：新增可选字段 = 可加性变更，不升版本。旧版本读新文件靠 `_strip_unknown_fields` 剥离（jsonl.py 已有），新版本读旧文件字段缺省。

**提交序（跨包依赖序，每步全绿）**：① protocol 字段 + wire 快照更新 → ② ai 盖戳 + `tests/ai` 断言 → ③ agent 消费。

1. `AgentToolResult.is_error: bool | None = None`（protocol/tools.py；**agent 消费**；执行时修正：pi 的 `isError?: boolean` 可选且缺省省略，`bool = False` 会让每条工具结果都序列化出 `"isError":false` 的 wire 噪音，故取 None 语义，循环侧只认 `is True` 为失败）
   - `run_tool` / `execute_tool_call`：结果对象的 `is_error=True` 视同失败（对齐 pi agent-loop.ts:988 的 `isError: result.isError === true`）。**执行前复核**：原计划"异常路径改为构造 AgentToolResult(..., is_error=True) 而非丢弃 details"不成立——pi 的 `createErrorToolResult`（agent-loop.ts:1057-1062）同样是 content=错误文本、details={}，baldric 的 `error_result` 已与之一致，异常路径零改动；本项实际改动 = outcome 消费处的 is_error OR + ToolResultMessage 带 duration_ms
   - **`outcome[0]` 不变式随行**：该函数已被实证无空 outcome 路径（GeneratorExit/CancelledError 均使 85 行不可达；回归测试 tests/agent/test_agent_loop.py:988 已提交）。阶段 E 拆分时**测试随行 + 核心处注释固化不变式**，不加死防御代码
   - 测试：工具返回 is_error=True 不抛异常 → 模型见错误文本、details 完整到达 ToolExecutionEndEvent
2. `ToolResultMessage.duration_ms: int | None = None`（protocol/messages.py；**字段源在 pi-ai/types.ts，非 agent**）
   - `execute_tool_call` 构造 ToolResultMessage 时带入（duration 已算好，tool_calls.py:84）
   - **`usage` 不加**：无生产者的字段是影子契约；等第一个真实回报 usage 的工具出现时，一条可加性变更同时加 `AgentToolResult.usage` + `ToolResultMessage.usage`
   - 受影响快照：`tests/expected/*.jsonl` 若 fixture 触达 → `UPDATE_EXPECTED=1` 并人工核对 diff
3. `AssistantMessage.thinking_level: str | None = None`（protocol/messages.py），盖戳按 D-T1：走 `stream.py:141` 的 `canonicalize_provider_stream` 单一漏斗——适配器把**实际生效**等级（catalog 映射后）传入流管线，partial 构造处一次盖戳，不在 5 适配器 7 处复制
4. 验证：`ruff check . --no-cache && ruff format --check . && mypy && pytest -q --ignore=tests/coding/tui`；`tests/ai` 增加盖戳存在性 + 降级场景盖实际生效值两条断言；wire 契约测试全绿（快照按需更新并在 commit 中说明）

## 3. 阶段 B：可注入契约（loop 的转换缝隙）+ **统一失败机制（原 D-T3 前移）**

1. `run_agent_loop` 新增 `convert_to_llm: Callable[[list[AgentMessage]], list[AgentMessage]] | None = None`——None 时用现有 `provider_context`（行为不变）；调用点 loop.py:133 改为经过该参数
2. 新增 `transform_context: Callable[[list[AgentMessage]], list[AgentMessage]] | None = None`——在 convert 之前应用（对齐 pi agent-loop.ts:503-510 的顺序：transform 先、convert 后）
3. `AgentHarnessConfig` 增加同名字段并透传；`SimpleStreamOptions` 式的 async 支持暂不做（provider_context 是纯同步；引入 awaitable 判定留待有真实异步需求）
4. **统一失败机制（D-T3 从阶段 D 前移至此）**：`_run` 在本阶段实现异常合成——捕获 `Exception`（`CancelledError` 穿透），合成 `AssistantMessage(stop_reason="error", error_message=...)` + MessageStart/End + TurnEnd + AgentEnd 后正常收尾迭代器。**为什么前移**：五个新钩子分阶段落地，若失败语义等阶段 D，B→D 之间钩子抛异常会直接炸消费方；一个被测试的机制覆盖所有钩子（含未来钩子），优于五处包裹，也优于 pi 的"契约仅文档、violation 即 unhandled rejection"（pi 对 convertToLlm/finishTurn/prepareRequest/prepareNextTurn 均无 try/catch，agent-loop.ts 全文可查）。钩子契约随之定稿：**"must not raise; violation ends the run with a synthesized error (fail-visible)"**——比静默跳过更能暴露坏钩子。**执行补充（2026-11-08）**：合成事件序列按 pi agent.ts:542-558 逐一对齐（含 `agent_end.messages=[仅失败消息]`、cancelled 时记 `aborted`）；except 块内**不做**悬空工具修复——下一次 run 的 prelude 修复已保证请求前补齐（`_run` 开头既有逻辑），在 except 里再修是对不可达路径的防御代码（AGENTS.md 禁止），pi 亦不修
5. **明确**：coding 层 `runtime.py` 本阶段**不迁移**到 transform_context（现有压缩流程不动，避免同 PR 内行为变更）；钩子面向第三方 loop 消费者与后续迁移
6. 测试：默认行为回归（不传钩子 = 现有输出逐字节一致）；注入自定义 convert 的过滤行为；transform 在 convert 之前执行的顺序断言；**每个新钩子各一条"抛异常 → 合成错误 run、迭代器正常结束"测试**
7. 契约文档：两个钩子的 docstring 写明契约与 violation 语义

## 4. 阶段 C：三钩子（内核扩展面核心，含 pi 的细节语义）

`run_agent_loop` 新增三个可选钩子 + `AgentHarnessConfig` 透传。全部 None = 现行为不变。

> **执行结论（2026-11-08）**：prepared 消息在 turn_start **之后**、与 pending 一起统一 emit（pi :285，先收集后发）；`prepare_request` 的模型替换**持续生效**（pi types.ts:268-269 "for this and later requests"，测试按此断言）；RequestUpdate 的 messages 替换以 `messages[:] = ...` 原位采纳——loop 与 harness 共享同一 list 对象，整体换新对象会分叉持久历史（别名约束下的 pi context 语义等价物）。error/aborted 轮的 TurnContext 照常构造（tool_results=[]），finish_turn 返回值被忽略。

1. `finish_turn(turn: TurnContext) -> Literal["continue","end"] | None`
   - `TurnContext`：message / tool_results / context(=messages) / new_messages
   - 调用点 ①：**error/aborted 轮也调用**（对齐 pi agent-loop.ts:326-337，在 turn_end 之前）——返回值在 error 轮被忽略（pi：error/aborted 保持硬退出）
   - 调用点 ②：正常轮，turn_end **之前**（pi: 373-374）；`"end"` → 直接 agent_end；`"continue"` → 显式继续标记
   - **显式继续语义**（pi: 403-408）：无自然请求（无工具调用、无 steering、无 follow-up）时，用一次仅上下文的额外轮兑现 continue——必须移植，否则钩子语义不完整
2. `prepare_next_turn(turn: TurnContext) -> TurnUpdate | None`
   - `TurnUpdate`：`messages: list[AgentMessage]`（追加并发出生命周期事件）/ `model: str | None`（替换后续请求的模型串）
   - **thinking_level 替换不做**：baldric 的 provider 协议无此参数，强行加=协议变更；需要时随 D-T1 一并决策
   - 调用点：turn_end 之后、下一 turn_start 之前（pi: 250-280）
   - **steering 重轮询细节必须随钩子一起移植**（pi: 269-277）：prepare 可能长跑（如压缩），结束后仅当**首轮询为空**才再拉一次 steering——防 one-at-a-time 模式双投递
3. `prepare_request(state: RequestState) -> RequestUpdate | None`
   - `RequestState`：messages / model；`RequestUpdate`：`messages: list`（此时已 append 并发事件，pi 语义：pending 已就位）/ `model: str | None`
   - 调用点：每次 provider 请求前**包括第一次**（pi: 295-316），在 steering 消息消费之后
4. 模型替换机制：loop 内部把 `model` 变为可变局部（初值来自参数），钩子可替换；provider 不变（baldric 的 provider/model 是分离的，替换 model 串即可，provider 级 failover 仍是 coding 层职责）
5. 测试（每个钩子独立 + 组合）：
   - finish_turn end/continue 两分支；error 轮也收到回调；continue 无自然请求时恰好多跑一轮（上下文不变）
   - prepare_next_turn 追加消息带完整事件序列、替换模型生效（FakeProvider 断言收到的请求）
   - prepare_request 每请求（含首次）都调用；替换模型生效
   - steering 重轮询：prepare_next_turn 长跑期间入队的 steering，one-at-a-time 模式下不双投递
   - error 轮 finish_turn 返回 continue → **被忽略**（error/aborted 保持硬退出）
   - 全部 None 时回归：与现行为逐事件一致
6. 验证：同阶段 A 门禁 + `tests/agent` 新增用例全绿

## 5. 阶段 D：harness 观测 + continue 校验 + after 钩子加固

> 崩溃合成已前移至阶段 B；本阶段剩余项如下。

1. **状态观测**（对齐 pi AgentState / processEvents，agent.ts:575-622）：harness 在 `_notify` 路径加轻量 reducer，暴露只读属性：
   - `streaming_message: AgentMessage | None`（message_start/update 置位，message_end/agent_end 清除）
   - `pending_tool_calls: frozenset[str]`（tool_execution_start/end 增删）
   - `error_message: str | None`（turn_end 的 assistant 消息带 error_message 时记录）
   - `signal: SimpleCancellationToken | None`（当前 run 的 token，公开现有 `_current_signal`）
   - **体量决策**：harness 物理行 344，本阶段 +C/D 增量预计突破 400 棘轮豁免线 → **优先把观测 reducer 抽到 `run_state.py` 小模块**（harness 保持 <400）；`--init` 仅作退化选项且需说明
2. **`continue_()` 校验**（D-T2）：messages 为空或全 assistant → RuntimeError；末条 assistant 且队列无 steering/follow-up → RuntimeError；末条 assistant 且**有**排队 → 排空队列作为新 prompt（pi agent.ts:403-417）。按 D-T2 推荐改既有测试
3. **`after_tool_call` 异常加固（审计发现的真缺口）**：tool_calls.py:87-88 现状——before 钩子异常有 fail-closed 包裹（tool_calls.py:47-55），**after 钩子异常直接炸循环**。对齐 pi（agent-loop.ts:1043-1046）：after 钩子异常 → 工具结果整体替换为错误结果（is_error=True），run 继续。测试：after 钩子抛异常 → 模型收到错误工具结果、轮次正常完成
4. **队列模式运行时可切换**：`steering_mode` / `follow_up_mode` 可写属性（pi agent.ts:290-305；coding 层的 set_steering_mode 类命令将来需要）
5. 测试：观测属性增删时序；continue 校验三分支；after 钩子异常不炸循环；模式切换后排水行为变化
6. **不做** `wait_for_idle`/`reset()`：见有意分歧清单

## 6. 阶段 E：嵌套工具调用管线（`run_tool_call`）——**可选，排最后**

> 降级说明：全计划唯一零消费方项，与 `execution_mode` 同一模式（先例：收下但没兑现成了陷阱）。**规格保留于此；推荐在 subagents 出现嵌套调用需求时立即按本节执行。** 若随本轮执行，排在 D 之后。
> **执行决策（2026-11-08）：推迟。** 执行前复核确认当前零消费方（subagents 未发生工具调工具），按"不做有用的东西"纪律不兑现规格；触发条件与上同——subagents 出现嵌套调用需求时按本节执行，届时同步验收表 E 行。

pi 的 `runToolCall`（agent-loop.ts:955-963）：工具调工具时走与模型发起调用**完全相同**的 prepare→validate→before→execute→after 管线，权限钩子对嵌套调用同样生效；不发事件、不产生消息、永不 reject（一切失败以 isError 返回）。

1. 重构 `tool_calls.py`：把 `execute_tool_call` 拆为**无事件核心**（prepare/validate/gate/execute/finalize）+ 事件发射包装（现有对外行为不变）
2. 新增公开 `run_tool_call(call, *, tools, assistant_message, signal=None, on_update=None, before_tool_call=None, after_tool_call=None) -> ToolCallOutcome`（outcome 含 result/is_error/duration_ms，对齐 pi AgentToolCallOutcome）
3. `execute_tool_call` 改为调用核心 + 发事件——**对外行为零变化**（现有测试守护）
4. 测试：嵌套调用命中 before 钩子（审批门对嵌套生效）；嵌套调用不发事件；失败路径全部 isError 不抛
5. 使用方：当前无（subagents 将来内部调工具时用）——这是"避免到用的时候再加"的直接标的

## 7. 阶段 F：transcript-as-truth 决策 ADR（只写决策，不实现）

> **已完成（2026-11-08）**：决策 = **暂不采纳**，弱化替代方案为 coding 层扩展 entry 类型记录提示词/工具变更历史（零版本成本）；重开触发条件三条见 `adr-0003-transcript-as-truth.md`。

pi 1.5.0 的核心设计分歧：SystemMessage 携带 systemPrompt 与工具声明，工具集变更以 `toolsAdded/toolsRemoved` 增量系统消息声明（agent-loop.ts:438-485，`declareToolChanges` 保证回放收敛到 `context.tools`）；`AgentState.systemPrompt` 从 transcript 回放（agent.ts:86-91）。

1. 交付物：`plans/adr-0003-transcript-as-truth.md` —— 论证采纳/不采纳：
   - 采纳的收益：会话历史自描述（改提示词/换工具成为可重放历史而非可变槽位）、多轮工具集变更可审计、与 pi 语义完全对齐
   - 代价：会话 wire 格式新增 system 角色消息（当前 7 角色封闭联合没有 system）、`SessionState` 投影与 `model_runtime` 的提示词组装要重做、`PROTOCOL_VERSION` 需要升版（**非可加性变更**）
   - 替代方案：维持现状 + 在 coding 层用 `CustomEntry` 记录提示词/工具变更历史（弱化版）
2. **本阶段只产出 ADR 与决策，不写实现**；若决策为采纳，实现是独立计划（会话格式 v2 + harness 重做）

## 8. 执行纪律（沿用仓库铁律）

- 每阶段一个原子提交序列：行为变更与测试同提交；wire 快照更新单独说明；**阶段 A 按 protocol→ai→agent 依赖序提交**
- 测试先行：每个行为先有 failing 测试再实现（continue 校验、钩子异常合成天然是 failing-first）
- 每阶段收尾跑：`ruff check . --no-cache`、`ruff format --check .`、`mypy`、`scripts/check_import_graph.py`、`scripts/check_structure.py`（**物理行口径**：loop.py 260、harness.py 344；harness 增量按阶段 D 的抽 module 方案保持 <400，退化才 --init）、`pytest -q --ignore=tests/coding/tui`；阶段 A 另跑 `tests/protocol`、`tests/ai` 与 wire 契约
- 全部走 `uv run`
- 完成后 `plans/kernel-refactor-plan.md` 加一行指针；A–E 全部为可加性变更，`PROTOCOL_VERSION` 维持 1；发布说明在 0.3.0 条目追加（含 D-T2/D-T3 两处消费方契约变更）；阶段 F 只产出 ADR，不动版本

## 9. 验收表（可证伪）

| 阶段 | 验收 |
|---|---|
| A | `AgentToolResult.is_error` 不抛错路径有测试且绿；ToolResultMessage.duration_ms 出现在落盘 JSONL；thinking_level 经 stream.py 漏斗盖**实际生效**等级并有 tests/ai 断言；快照 diff 已人工核对；PROTOCOL_VERSION 仍为 1 |
| B | 不传钩子时全仓测试零变化；注入 convert/transform 的顺序与过滤断言通过；**每个新钩子各一条"抛异常→合成错误 run"测试绿** |
| C | 三钩子各有独立测试；显式继续恰好多一轮；steering 重轮询不双投递；error 轮 continue 被忽略；全 None 回归零差异 |
| D | 观测属性时序测试绿；continue 校验按 D-T2 执行结论（排空分支 + 空历史拒绝）；**after 钩子抛异常不炸循环**；queue_mode 运行时可切换（单一模式覆盖两队列，有意分歧：不拆 pi 的双模式）；harness 443 行为登记后的实测值（计划原目标 <400 低估了 C/D 的配置面；run_state 抽取与 tool_history 修复搬迁已完成，余量是 run 生命周期+合成+校验的内聚本体） |
| E（可选） | `execute_tool_call` 对外行为零变化（现有测试守护）；`run_tool_call` 嵌套调用命中 before 钩子且不发事件；全部失败路径 isError 不抛；outcome 不变式注释随行 |
| F | ADR-0003 提交，含采纳/不采纳论证与替代方案；无实现代码 |
| 全部 | CI 全绿；`baldric_coding` 零改动（runtime.py 不迁移）；guidance/structure/suppression 棘轮不涨 |
