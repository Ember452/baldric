# wire 契约基线

**状态：** 已接受 —— 2026-11-06（分支 `chore/p0-contract-baselines`）

本笔记记录可靠性计划的第一片：改行为之前，先钉住已有依赖者的形状。它也记录这一片刻意**没做**什么，让下一次变更不必重新争论。

## 为什么

三个消费者读这些形状：

- 持久化的 JSONL transcript（用户数据；新旧 Baldric 都必须能读）；
- JSON 事件流（`--print` / JSON mode，与 RPC wire）；
- 每个 frontend 与 extension 渲染的内置消息/事件联合。

本变更前只有两个消息形状被锁定
（`assistant_message.json`、`tool_result_message.json`）。联合本身、
provider 流事件、loop 事件与每种 session entry 类型都没钉：加一个字段、改一个别名或重排联合分支，都能在绿色套件下改变协议。

## 钉住了什么

| 快照（`tests/expected/`） | 覆盖 | 写入者 |
| --- | --- | --- |
| `agent_message_union.jsonl` | 8 个 `AgentMessage` 分支（text、image、assistant、tool result、bash、custom、branch summary、compaction summary） | `tests/agent/test_wire_contract.py` |
| `provider_events.jsonl` | 12 个 `AssistantMessageEvent` 分支 | 同上 |
| `agent_events.jsonl` | 10 个 `AgentEvent` 分支 | 同上 |
| `session_entries.jsonl` | 规范持久 JSONL 中的 10 种 `SessionEntry` 类型 | `tests/agent/test_session_entry_contract.py` |

每个文件都是生产序列化输出（别名开、`None` 省略），
一行一个对象，diff 因此指向变化的分支而不是一条长行。

两个守卫让快照诚实：

- **覆盖** —— fixture 集与联合声明的分支对照，新的消息/事件/entry 类型会让测试失败，而不是悄悄缺席快照；
- **往返** —— 每个 fixture 被序列化、解析回来、整体比对。

session 快照还钉住既有的混合约定：
entry 是 snake_case，而其内嵌的消息与用量是 camelCase。

## 修改快照

改快照就是改协议。只在显式旗标下更新并评审 diff：

```bash
UPDATE_EXPECTED=1 uv run pytest tests/agent/test_wire_contract.py tests/agent/test_session_entry_contract.py
git diff tests/expected/
```

## provider 层导入面

`baldric_ai` 可以导入 harness 的 provider 中立 wire 契约，仅此而已：

```
baldric_agent.messages
baldric_agent.provider
baldric_agent.provider_events
baldric_agent.tools
baldric_agent.types
```

`scripts/check_import_graph.py` 现在报告任何其他 `baldric_agent…` 导入，
包括 `from baldric_agent import X`（包根会运行 `__init__`，拉起 session 存储与 JSONL）。扫描器有自己的植入违规测试，还有一个测试证明允许列表仍指向存在的模块。

**该守卫不声称的事。** 它不说两个包拥有其文档描述的方向。`baldric_ai/AGENTS.md` 仍称 provider 层为"最底层"并禁止导入 `baldric_agent`，而代码恰好相反：适配器依赖 harness 的领域契约。那是正常的适配器 → 契约方向；错的是声明。修复声明、补上缺失的 `rendering → tui` 方向，推迟到 frontend/extension 卫生阶段。没有加一刀切的
`("baldric_ai", "baldric_agent")` 规则，因为今天它是假的。

## session 格式演化（现在决策，以后写代码）

第一个真实的 session 格式变更落地时，遵循此政策：

1. 每条 entry 带整数 `v`，默认 `1`，等于当前格式版本时从序列化行省略；
2. 读取者以清晰的 `SessionJsonlError` 拒绝大于支持版本的 `v`，而不是笼统的校验错误；
3. 迁移限于 `session/jsonl.py`（既有的形状嗅探迁移对 v1 继续有效）；
4. 未知字段政策（拒绝/保留）等 v2 真正存在时再定，不提前。

**为什么本片不实现：** 今天存在的每个文件按定义都是 v1，字段没有任何行为可锻炼，且 `src/` 受结构棘轮覆盖——没有消费者的字段要么撑大被棘轮的文件，要么逼一次无关重构。第一个格式变更（prompt/工具集版本 entry、compaction 检查点、usage entry）携带它。

## 本片刻意推迟的

| 项 | 推迟到 | 理由 |
| --- | --- | --- |
| provider 记录/回放 fixture | 有回归需要钉住（可靠性阶段） | 适配器测试已驱动 fake transport 与录制载荷；没有消费者的 VCR 层是投机 |
| 故障注入 harness | 第一个存储/取消修复 | harness 只在有修复需要它时有用；先建有未用抽象的风险 |
| 通用风险开关框架 | 第一个风险行为变更 | 在既有配置路径上按行为加开关；不要预建旗标系统 |

## 验证

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run python scripts/check_import_graph.py
uv run pytest -q tests/agent tests/guards
```
