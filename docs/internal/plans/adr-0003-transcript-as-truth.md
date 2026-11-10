# ADR-0003：transcript-as-truth（pi 1.5.0 的系统消息承载设计）

- 状态：Declined（暂不采纳，含重开触发条件）
- 日期：2026-11-08
- 伴随实现：无——本 ADR 只做决策，不写实现（plans/agent-kernel-parity-plan.md 阶段 F）

## pi 1.5.0 的做法（源码核对）

- `SystemMessage` 携带 systemPrompt 与工具声明；`AgentState.systemPrompt` 从 transcript 回放
  （agent.ts:86-91 `getCurrentSystemPrompt(messages)`，初始系统消息由 `createInitialSystemMessage` 注入）。
- 工具集变更以增量系统消息声明：`declareToolChanges`（agent-loop.ts:438-485）在每次请求前把
  `context.tools` 与 transcript 已声明集合的差集写成 `toolsAdded`/`toolsRemoved`，
  已存在的待发系统消息被视为意图并被改写，保证回放收敛到 `context.tools`。
- 效果：会话历史自描述——改提示词/换工具是可重放的历史事件，不是可变槽位。

## baldric 现状

- 系统提示词是 `AgentHarnessConfig.system` 配置槽；工具每次请求隐式传入；transcript 的 7 角色封闭联合
  没有 system 角色；`PROTOCOL_VERSION = 1` 冻结（ADR-0001）。
- session entry 体系已有变更历史的**同类先例**：`ModelChangeEntry`、`ThinkingLevelChangeEntry`
  （baldric_protocol/session/entries.py）——配置变更已经以事件形式落盘。

## 采纳的收益

1. 会话历史自描述：提示词/工具集变更成为可重放历史，审计与调试不用查运行时配置。
2. 多轮工具集变更可审计（子代理并行、分支会话尤其受益）。
3. 与 pi 语义完全对齐（内核面最后一个大的设计分歧消除）。

## 采纳的代价

1. wire 破坏性变更：新增 system 角色 + 工具声明字段，`PROTOCOL_VERSION` 必须升版（非可加性）。
2. `SessionState` 投影与 coding 层的提示词组装要重做；适配层需要处理 transcript 内 system 消息。
3. 收益兑现阶段没有消费方：当前没有跨会话回放工具声明的需求方。

## 替代方案（弱化版，零版本成本）

沿用 entry 先例：在 coding 层为提示词/工具集变更增加对应的 entry 类型
（如 `SystemPromptChangeEntry` / `ToolSetChangeEntry`，可加性变更，不升版本），
把"变更历史"记在 session 层。内核保持 config 语义不变；回放时由应用层重建配置轨迹。

## 决策

**暂不采纳。** transcript-as-truth 的收益在"历史需要自描述"时才兑现，而当前没有这样的消费方；
其代价是一次 wire 破坏性升级。采用替代方案记录变更历史，保持内核与 wire 的现状。

**重开触发条件（满足其一即重开本 ADR）：**

1. 出现跨会话/跨产品回放工具集声明的真实消费方（如子代理产物被第三方工具消费）。
2. 出现"改提示词或换工具后，旧会话行为不可解释"的真实事故，且 entry 轨迹不足以解释。
3. 需要与 pi 的会话格式互通（导入/导出）。
