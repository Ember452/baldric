# 内核架构改造计划（基于 pi 源码对照 + 本项目 Python 实际）

> 状态：**已执行完毕（2026-11-08，分支 `refactor/kernel-protocol-extraction`）**
> 后续内核补齐：字段级 pi 对齐见 `agent-kernel-parity-plan.md`（已执行，分支 `feat/agent-kernel-parity`）；transcript-as-truth 决策见 `../adr/0006-transcript-as-truth.md`（暂不采纳）。
> 执行结果：阶段 0（缺陷复核，三条伪缺陷否决见 §0.2）、阶段 1（protocol 抽取 + shim + 删 shim）、阶段 2（session I/O/投影下沉，内核 9 文件零 I/O）、阶段 3（静态 + 运行时双向守卫）、阶段 4（PROTOCOL_VERSION 冻结 + golden 存在性锁）全部完成；阶段 5 收窄为 subagents 纯函数抽取（extension.py 1791→1622），两个 god-class 不拆，见 `../adr/0005-god-class-deferral.md`；阶段 6（产品扩展点 guard）按计划留给产品化启动时，存量 8 处直连已记录在 `../adr/0004-kernel-boundary.md`。
> 边界与决策记录：`../adr/0004-kernel-boundary.md`（D3 / D-pydantic / 包发布 / 机器守卫 / 遗留债务）。
> 依据：对 `pi-main/packages/{agent,ai,schema,coding-agent}` 的源码通读 + 对 `baldric/src/{baldric_agent,baldric_ai,baldric_coding}` 的逐文件通读。
> 目标标准：可维护、可扩展、架构漂亮（不在乎迁移工作量），将来在此之上开发大规模产品、并被第三方使用。
> 明确不做：远程执行（`env`）、`durable`、`chord`、`codemode`、`mcp` 独立包、`telemetry`、`evals` —— 这些是 pi 的大规模产品化设施，现阶段做即过度工程；只留扩展插口。

---

## 0. 从 pi 源码得到的事实（这些决定了一切，不是推测）

| # | pi 的真实做法（证据） | 对本项目的含义 |
|---|---|---|
| F1 | `packages/agent/package.json` 的 dependencies 是 `pi-ai` + `pi-schema`；`agent/src/types.ts` 直接 `import type {...} from "@earendil-works/pi-ai"`。**pi 的 agent 依赖整个 ai 包。** | 本项目 `baldric_agent` **不 import `baldric_ai`**（AGENTS.md:47 + `check_import_graph.py` 的 AI_AGENT_SURFACE 白名单强制）。**我们比 pi 更干净。** 抽 protocol **不是"修倒置"**（没倒置），而是把"ai 依赖 agent 的 5 个契约模块"这一条进一步收敛成"两者都依赖一个薄契约包"。 |
| F2 | `packages/agent/src` 仅 6 文件：`agent-loop.ts(944) / agent.ts(557) / types.ts(511) / proxy.ts(361) / stream-fn.ts(17) / index.ts(5)`。**没有 session、没有 compaction、没有 trust、没有 I/O。** | pi 的内核是"一次循环 + 事件 + 类型"。**本项目的 `baldric_agent/session/`（5 文件 + 投影 + I/O）塞进了内核，比 pi 重。** 这是本次改造的主战场。 |
| F3 | session 持久化全在 `coding-agent/src/core/`：`session-manager.ts`（`export class SessionManager`，内含 `writeFileSync`）、`compaction/`、`session-export.ts`、`trust-manager.ts`。 | **按 pi 分层：session 的 I/O 与"会话应用"语义属于 coding 层，不属于 agent 内核。** |
| F4 | `packages/schema`：`sideEffects:false`、零依赖、"JSON Schema validation without eval"。agent 靠它做 `Static<>` 类型。 | **本项目不要抽 schema 包。** Python 的 pydantic 就是 schema 层；`baldric_agent/tool_arguments.py` 的手写校验足够。抄它会变成复刻分包癖。 |
| F5 | `packages/ai/src` = api/*(20+ provider) + auth/* + models*.ts + oauth.ts + telemetry.ts + utils/{overflow,retry,streaming-json}.ts。 | 本项目 `baldric_ai` = anthropic/google/mistral/openai_*/stream/retry/model_catalog/**openai_cache**/_sse。**结构已对齐，不动。** 唯一动作是改变它对 `baldric_agent` 的 import 目标（改成 protocol）。 |

**关键耦合事实（本项目实测，决定搬迁难度）**
- `baldric_ai` 对 `baldric_agent` 的 import **仅 5 个模块**：`messages / provider / provider_events / tools / types`。→ 抽 protocol 时这 5 个整体迁出，`baldric_ai` 改 import 路径即可，**机械且低风险**。
- `baldric_agent/session/*.py` 对内核其余部分的依赖**仅 2 个**：`messages`、`types`（外加 pydantic）。→ `session/` 可整体切走，不与 `loop/harness` 互耦。
- `loop.py / harness.py / tool_calls.py / context_projection.py / assistant_stream.py` **完全不 import `session`**，只把 `session_id: str` 当不透明字符串透传（loop.py:51/136、harness.py:48/271、assistant_stream.py:40/49）。→ **内核运行时不依赖 session 包，切割无损。**
- `baldric_coding` 有 **22 处**从 `baldric_agent.session` / `baldric_agent.session.entries` / `.jsonl` 导入（session/branching/model_selection/provider_helpers/resource_helpers/runtime/session/stats/tree_helpers/usage/export/*、cli、modes/rpc、subagents）。→ 搬迁后这些导入路径要统一改；这是**面最大**的一步，必须脚本不可为（见 §5 约束），需逐文件改并靠 guard 验证。

### 0.1 实测波及面（2026-11-08 全仓 AST 扫描，含 tests）

> 用 AST 扫 `src/ + tests/ + scripts/` 全仓对 `baldric_agent.*` 的 import，按来源区统计。**这修正了上文"22 处"的低估**——那只数了 session 包，漏了 coding 层对契约模块的大量引用。

| 迁移组 | agent 内 | baldric_ai | baldric_coding | tests | 需改 import 合计 |
|---|---|---|---|---|---|
| **阶段1** 契约 5 模块（messages/tools/types/provider/provider_events） | 34 | 28 | **97** | **66** | **225** |
| **阶段2** session 组（entries/tree/jsonl/storage/memory + session 包） | 12 | 0 | 26 | 19 | **57** |
| 保持内核（loop/harness/events/assistant_stream/tool_calls/context_projection/tool_arguments/tool_history） | 14 | 0 | 23 | 29 | 仅改内指，不改包名 |
| **合计需改 import** | | | | | **~282 + 66 tests** |

**结论（决定执行方式）**：
1. **"逐文件手改 282 处"不可作为主路径**——任何一处漏改 = 阶段长期不红。
2. **shim 必须覆盖 5 个契约模块全部 + tests 也走 shim**。正确路径：建 `baldric_protocol` → 原 5 模块变 re-export shim → **此时 282 处一个字不改也能全绿** → 分批把 agent 内/ai/coding/tests 的 import 指向 protocol（每批跑一次测试）→ 最后删 shim。
3. **其他实测**：`baldric_ai` 对 agent 的 import 全部落在 5 契约模块（映射 protocol 后 **0 违规**）；全仓 **0 处**裸包根 `from baldric_agent import X`（阶段2 删 session 无隐蔽引用）；`storage.py import jsonl`（非反向，下沉不切断 jsonl）。

---

## 1. 目标分层（改造后）

```
baldric_protocol            ← 纯契约，唯一外部依赖 pydantic。零 I/O，零平台，零上层。
  ├ messages.py             （从 baldric_agent 迁入）
  ├ tools.py                （迁入）
  ├ types.py                （迁入）
  ├ provider.py             （迁入）
  ├ provider_events.py      （迁入）
  └ session/                （持久化"契约"部分，见 §2 三态表）
       ├ entries.py         （entry wire 形状 —— 第三方要读写 session 文件，属契约）
       ├ tree.py            （纯树遍历，无 I/O）
       └ jsonl.py           （线格式 + 版本迁移 —— 属持久化契约）
      ↑          ↑
baldric_ai    baldric_agent            ← 两层都只依赖 protocol，互不依赖
(providers)   (loop/harness/events/
              assistant_stream/tool_calls/
              context_projection/tool_arguments)
      ↑          ↑
        baldric_coding                 ← 依赖上面全部
  ├ session/storage.py     ← JsonlSessionStorage（fcntl/fsync/torn-tail）从内核下沉至此
  ├ session/memory.py      ← SessionState 投影（D3 已定：下沉 coding，不进 protocol）
  └ ...既有 session/manager/lifecycle/tui/tools/extensions
```

**关键结论**：改造后 `baldric_agent/session/` **整体删除**——entries/tree/jsonl 去 protocol，storage/memory 去 coding。`baldric_agent` 不再有 `session` 子包。

**依赖方向**：`protocol ← {ai, agent} ← coding`，且 `ai ⇎ agent` 互不依赖。相对今天的变化：
- 今天：`ai → agent(5 模块)`。改造后：`ai → protocol`、`agent → protocol`。
- 收益：`ai` 与 `agent` 共享的是**薄契约包**而非"ai 依赖 agent 包"；第三方只 `pip install baldric-protocol` 即可写 provider / 前端 / session 工具，不必拖整个 harness。

---

## 2. session/ 五文件三态归属表（逐文件判定，搬迁照此执行）

| 文件 | 判定 | 去向 | 理由 |
|---|---|---|---|
| `session/entries.py` | **持久化契约** | `baldric_protocol/session/entries.py` | entry 的 wire 形状 + `schema_version` 协商是第三方读写 session 文件的公开 ABI。依赖仅 `messages`/`types`（同迁） + pydantic。 |
| `session/tree.py` | **纯逻辑** | `baldric_protocol/session/tree.py` | `path_to_entry`/`entries_by_id` 纯遍历，无 I/O、无平台。任何实现 session 的人都要用，属契约工具。 |
| `session/jsonl.py` | **持久化契约（线格式）** | `baldric_protocol/session/jsonl.py` | 序列化 + 版本迁移逻辑。第三方要兼容读写就必须共享它。**注意：它只定义格式，不做文件 I/O**（I/O 在 storage.py）。 |
| `session/memory.py` | **投影逻辑（会话应用语义）** | **下沉 `baldric_coding/session/memory.py`（决策 D3 已定，不再挂起）** | `SessionState.from_entries` 虽无 I/O，但它是"会话应用语义"：决定 leaf 解析、`context_entry_ids`、compaction 合并、branch 摘要措辞。这不是 provider/前端要复用的 wire 契约——pi 的 SessionManager（含投影）整个在 coding。protocol 保持"只 entries/tree/jsonl 三个机械件"最纯。代价：第三方若只装 protocol 就拿不到现成投影，需自行实现或装 `baldric_coding`；此为换取"protocol 一句话能说清的纯契约"的有意取舍。 |
| `session/storage.py` | **纯 I/O + 平台** | **下沉 `baldric_coding/session/storage.py`** | fcntl/msvcrt/fsync/torn-tail/temp —— 正是 pi 放在 `session-manager.ts` 的东西。下沉后内核零平台；`baldric_agent` 侧 7 个 Windows mypy 错误消失是**验证信号**，不是目的。 |

**决策 D3（已定）**：`memory.py` 下沉 `baldric_coding`。判据：**"第三方实现 session 必须与之"一致的只有形状/路径/线格式**（entries/tree/jsonl）；**带产品策略的投影语义不属于契约**（压缩措辞、resume 语义），下放 coding。这样 `baldric_agent/session/` 在阶段 2 后可**整体删除**（见 §3 阶段 2），protocol 边界一句话可陈述。

---

## 3. 分阶段执行步骤（顺序不可跳，每步有验证）

> 总原则：**先让行为正确，再让结构正确，再冻结**。顺序理由：带 `outcome[0]` 崩溃路径的内核不能先冻结。

### 阶段 0：修复内核真实缺陷（行为正确优先）
**⚠️ 2026-11-08 实测复核：本阶段原列的三条"缺陷"经分支上 TDD 逐个验证，均不成立，已否决（详见 §0.2）。阶段 0 不再包含强行修改。** 下方保留原始清单仅作记录。

读代码已确认的缺陷，先修再动结构：
1. `tool_calls.py:74-85`：`outcome[0]` 无保护硬索引。取消/中断时 `run_tool` 的 `finally` 只 `task.cancel()` 不 append，回到 `execute_tool_call` 即 `IndexError`。→ 加"tool 未产出结果"的兜底 `AgentToolResult`（error）；补一个取消路径的 failing 测试。
2. `harness.py`：`_RunIterator.__del__` → `_finish()`，但被丢弃的 run 不会 `aclose()` 生成器 → `_run` 的 `finally` 修复逻辑不执行 → 悬空工具调用。→ 评估是否让 `__del__` 无法保证时，改由 coding 层显式 `aclose()`；补测试。
3. `harness.py:279-289` 的中断修复与循环内 append 的边界：补一个"取消发生在 tool 执行中段"的测试，确认消息不重复/不丢。
- **验证**：`uv run pytest -q tests/agent` 全绿 + 新增取消场景测试。

### 0.2 阶段 0 缺陷复核结论（2026-11-08 实测，否决伪缺陷）

| 原列缺陷 | 实测结论 | 证据 |
|---|---|---|
| `outcome[0]` IndexError | **伪缺陷，不可复现** | 全路径探测：normal/tool-exception 正常 append；tool-cancelled 在 `tool_calls.py:213` 主动 raise、line 85 不可达；consumer `aclose()` 的 GeneratorExit 穿过 finally、line 85 不可达。已加回归 guard `test_closing_tool_call_generator_mid_run_emits_clean_result_not_indexerror`（证明当前不崩）。 |
| harness `__del__` 中断修复 | **伪缺陷，生命周期已完整测试** | `tests/agent/test_harness_lifecycle.py` 6 测试覆盖 prompt 前武装/aclose 幂等/gc 丢弃释放/重叠拒绝/完成释放/continue_ 武装。 |
| `retry.py` Retry-After 照睡 | **伪缺陷，代码已是 pi 快速失败** | `retry.py:178-189`：`retry_after > max_delay_seconds` → `retryable=False, code="retry_after_too_long"`，立即失败不睡。 |
| 溢出静默检测（8 关键词） | **待评，属 coding 会话层** | `_CONTEXT_OVERFLOW_MARKERS` 8 条；静默溢出检测若需要，应在 `session/compaction/context_window.py` 层，不属 stage 0 内核。 |

**决策**：阶段 0 无真实内核缺陷可修；**直接进入阶段 1 结构重构**。回归 guard 测试保留（防未来回归）。

### 阶段 0.5：ai 层行为对齐（**执行时已复核改判，见下**）
> ⚠️ **2026-11-08 复核改判**：本节写下后被逐项实测，结论与原判不同（详见 §0.2）：
> - **第 4 项（retry.py 照睡）为伪缺陷**：`classify_http_failure`（retry.py:178-189）已实现"服务器 `Retry-After` 超上限 → `retryable=False, code="retry_after_too_long"` 立即失败"的 pi 语义；原判引用的 88-105 行是 fallback 退避函数，其"只管 fallback"的 docstring 被误读为缺陷。
> - **第 5 项（静默溢出检测）真实存在，但改判为带规格的独立特性任务，不并入内核重构。** 执行时的影响面核实：现有 overflow 自愈只在 `stop_reason=="error"` 的事件上触发（runtime.py:410-422），TUI 路由（adapter.py:186/334）同样只处理 failed-end；而静默溢出是 `stop` 正常结束。接线需要四处联动——① `is_context_overflow_error` 增加可选 `context_window_tokens` 并识别 stop+超窗与 length+零输出两个信号；② runtime 监听器扩到 stop 事件并传入会话窗口；③ `context_projection` 需处理"空 stop turn"的回放丢弃（当前只丢空 error/aborted）；④ TUI 的 pending-overflow 路由适配。这是 pi 的 overflow 自愈特性移植，需要 failing-then-passing 测试与独立评审，塞进重构 PR 违反原子性。**未来任务以本清单为规格。**
>
> 保留本节原文仅作决策轨迹记录。**"必须在抽包前修"的说法以本改判为准。**

### 阶段 1：抽 `baldric_protocol`（契约归位，**模块粒度原子切换 + 兼容 shim**）

> 关键机制（**避免半迁中间态必红**）：搬迁按"模块粒度原子切换"，每个被抽出的模块在原位置留 **re-export shim**，让老 import 路径在过渡期仍可用；全仓 import 改完后，统一在阶段 1 收尾删 shim。

1. 新建 `src/baldric_protocol/`，迁入 `messages.py / tools.py / types.py / provider.py / provider_events.py`（**原样搬，仅改包名**；它们只依赖 pydantic + 彼此）。
2. 迁入 `session/entries.py / tree.py / jsonl.py`（memory.py **不迁**，按 D3 留 coding）。
3. 在**原位置** `baldric_agent/{messages,tools,types,provider,provider_events}.py` 与 `baldric_agent/session/{entries,tree,jsonl}.py` 改为 `from baldric_protocol.<mod> import *`（+ `__all__` 透传）的 **re-export shim** —— 此时老路径仍工作，全仓可绿。
4. `baldric_ai`（12 处 import，逐文件改，同一文件的多条 import **必须一次改完**）、`baldric_agent` 内部（loop/harness/events/assistant_stream/tool_calls/context_projection/tool_arguments）改 import 目标为 `baldric_protocol.*`。
5. `pyproject.toml` 增加 `baldric_protocol` 包（hatchling 多包）与 pytest/ruff/mypy 路径。
6. **收尾**：全仓 grep 确认无 `baldric_agent.{messages,tools,types,provider,provider_events}` 与 `baldric_agent.session.{entries,tree,jsonl}` 的外部引用后，**删除全部 shim**。
- **硬约束（防 shim 变常态）**：**shim 期必须在本阶段内结束，绝不跨阶段。** 阶段 2 开工前，shim 必须已全部删除——否则"阶段 2 删 session 目录"和"shim 仍指向老路径"会打架。任何人不得在 shim 期用老路径写新代码（review 检查项）；shim 删除是阶段 1 的**完成定义（Definition of Done）**，不是"以后再说"。
- **验证**：`uv run ruff check . && uv run mypy && uv run pytest -q`；`check_import_graph.py` 加新规则（见 §4）；**新增"双向运行时守卫"**（见 §4 补充）——`baldric_agent` 任何模块运行时不得（即使间接）import `baldric_ai`，反之亦然。

### 阶段 2：session I/O 下沉 + 内核收缩（`baldric_agent/session/` 整体删除）
1. `session/storage.py` → `src/baldric_coding/session/storage.py`（改名/改包名，逻辑不动）。
2. `session/memory.py` → `src/baldric_coding/session/memory.py`（按 D3 下沉，逻辑不动）。
3. **删除 `baldric_agent/session/` 整个目录**（entries/tree/jsonl 已在阶段 1 迁 protocol；storage/memory 已下沉 coding）。**不存在"仅剩"分支。**
4. `baldric_agent/__init__.py` 的 `SessionState / JsonlSessionStorage / SessionEntry / SessionInfoEntry` 等导出**删除**（不再从内核导出会话物）；`baldric_coding` 22 处 import 逐文件改指向新家（`baldric_protocol.session.*` 或 `baldric_coding.session.*`）。
5. 内核 `baldric_agent` 最终只剩：`loop / harness / events / assistant_stream / tool_calls / context_projection / tool_arguments / __init__`（provider/types 若已全迁 protocol 则内核不再有）。
- **验证**：`uv run python scripts/check_import_graph.py`；**`src/baldric_agent` 下不存在 `session/` 目录**；`grep -R "fcntl\|msvcrt\|fsync\|tempfile" src/baldric_agent` 为空；7 个 Windows mypy 错误消失；全测绿。

### 阶段 3：边界机器守卫 + 边界 ADR（定型，不定死语义）
1. 扩 `scripts/check_import_graph.py`：
   - `baldric_protocol` 禁止 import `baldric_agent / baldric_ai / baldric_coding / textual / rich / fcntl / msvcrt / os(用于 I/O 的 API)`。
   - `baldric_agent` 禁止 import `baldric_coding / baldric_ai / textual / rich`（保留现有）。
   - `baldric_ai` 只允许 `baldric_protocol`（把 AI_AGENT_SURFACE 改为 protocol 白名单）。
2. `tests/guards/test_import_boundaries.py` 同步这些规则（这个 guard 已存在，扩展即可）。
3. 写 ADR：`../adr/0004-kernel-boundary.md` —— 记录"哪些进内核/哪些留层""D3 决策""契约 semver 策略"。ADR 是给人的；**边界靠上面的机器 guard 强制，不靠文档自律。**

### 阶段 4：冻结 + 版本化（不是死封）
1. `baldric_protocol` 进入"契约冻结"：破坏性变更走 major；至少保留一个 minor 的 deprecation 窗口（warning + 迁移说明 + 保留旧构造器）。
2. 把 `jsonl.py` 既有的 `CURRENT_SCHEMA_VERSION` + "refuse newer / migrate older" 正式上升为**持久化契约版本策略**（第三方会用你的 session 文件）。
3. 冻结的是**契约语义**，不是实现：内核可有性能重写，只要 wire 不变。

### 阶段 5：coding 层结构治理（内核纯净后再做，**验收 = 棘轮基线下降，不是"拆分且行为不变"**）

> 现有 `scripts/check_structure.py` 的 `HARD_LIMITS.lines = 1200`，但 `session/session.py(1796)`、`tui/app.py(4180)`、`subagents/extension.py(1666)` 都**超过硬限**——它们靠 baseline 豁免。**"拆分"不算判据；判据是"这几个文件的 `structure-baseline.json` 记录被真实降下来"。**

- 目标（可量化，按棘轮口径 `splitlines()`）：
  - `src/baldric_coding/session/session.py`：1796 → **≤ 1200**（进入硬限内，base 更新为实测值）
  - `src/baldric_coding/tui/app.py`：4180 → 拆分后**每个文件 ≤ 1200**
  - `src/baldric_coding/session/runtime.py`：1177 → 保持 ≤ 1200 且**不增长**
  - `src/baldric_coding/extensions/builtins/subagents/extension.py`：1666 → **≤ 1200**
  - 全局 `module_fanout` 不超过 `HARD_LIMITS.module_fanout(50)`
- 执行后 `uv run python scripts/check_structure.py --init` **只允许把基线收紧（数字变小），不得借 `--init` 把增长记进基线**。
- **验证**：`structure-baseline.json` 中上述文件的 `lines` 数值**逐一下降**并在 PR diff 中可见；`uv run python scripts/check_structure.py` 通过；`tests/guards/test_structure_ratchet.py` 全绿；全测绿且行为不变（无契约测试改动，除非是内部拆分带来的 import 路径）。

### 阶段 6：产品能力（只走已冻结扩展点，**由 guard 强制，不靠约定**）
- 主 agent 一等记忆、第三方扩展装包、personal agent。全部通过阶段 3/4 冻结的扩展 API / 事件钩子接入，不改内核契约。
- **补最后一道锁（决定"可扩展"能否兑现）**：产品层最大的隐藏风险是**绕过 protocol 直接 import coding 内部实现**（例如将来 `from baldric_coding.session import SessionState`），那样 protocol 的中立就白费。因此本阶段加 guard：
  - **扩展内置件 / 新增产品代码只允许通过 `extensions/api.py` 暴露的钩子 + `baldric_protocol` 契约**；禁止直接依赖 `baldric_coding.*` 的**内部实现细节**（session/runtime/tui 等非 api 模块）。
  - `check_import_graph.py` 增加规则：产品/扩展目录（如 `baldric_coding/extensions/builtins/**` 新代码）禁止 `from baldric_coding.session.* | baldric_coding.tui.* | baldric_coding.session.runtime` 等内部实现，白名单只留 `extensions.api` + `baldric_protocol.*`。
  - 至少在 ADR 中记录"扩展只能通过 api.py 钩子"这条边界，并用 `tests/guards` 里的一次故意违规验证 guard 会炸。
- **验证**：上述 guard 规则生效；故意写一个 `from baldric_coding.session import SessionState` 的扩展会被 CI 拦下。

---

## 4. check_import_graph 新增规则（草案）

```python
RULES += (
    # protocol 是最底层：不得依赖任何上层，也不得碰平台 I/O 模块
    ("baldric_protocol", "baldric_agent"),
    ("baldric_protocol", "baldric_ai"),
    ("baldric_protocol", "baldric_coding"),
    ("baldric_protocol", "textual"),
    ("baldric_protocol", "rich"),
    ("baldric_protocol", "fcntl"),
    ("baldric_protocol", "msvcrt"),
)
# AI 层：契约目标从 baldric_agent.* 改为 baldric_protocol.*
AI_PROTOCOL_SURFACE = (
    "baldric_protocol.messages",
    "baldric_protocol.provider",
    "baldric_protocol.provider_events",
    "baldric_protocol.tools",
    "baldric_protocol.types",
)
```

**补充：双向运行时守卫（补 5，修正方向）**

> 说明：今天的依赖是 `baldric_ai → baldric_agent(5 模块)`（AI_AGENT_SURFACE 记录的现状），**不是** `agent → ai`。pi 才是 `agent → ai`（F1）。所以"禁止 agent import ai"今天已成立，但仍要用 guard **钉死**（shim 残留期最易被反向 import）。**两个方向都要守，不是单向。**

- **静态**：`check_import_graph.py` 增加
  - `("baldric_agent", "baldric_ai")` —— 内核不得依赖 provider 实现
  - `("baldric_ai", "baldric_agent")` —— provider 层只能依赖 protocol，不得回流依赖内核
- **运行时（防 shim 残留的间接耦合）**：`tests/guards/test_import_boundaries.py` 增加一条**独立进程**测试：分别 import `baldric_agent` 与 `baldric_ai` 后，断言 `sys.modules` 中**不含对方的任何模块**（用 `subprocess` 隔离，避免测试进程自身交叉污染）。任一方向出现对方模块即失败。
  - 意义：静态 import 检查看不见"通过 re-export shim 间接 import"的情形；运行时 `sys.modules` 断言能抓住"看似纯净、实则耦合"。

---

## 5. 硬约束（本项目 AGENTS.md 既有铁律，必须遵守）

- **禁止用脚本/sed/批量替换改文件**：本计划里"22 处 import 路径替换"必须用编辑器逐文件改，每改一个跑一次 `ruff check`。批量改曾把 3519 行测试文件改成 45 行、静默丢 `async def`。
- **同一文件的多条 import 必须一次改完**：`baldric_ai` 里一个文件可能同时 import `baldric_agent.messages` 和 `baldric_agent.tools`，分两次迁就是半迁中间态、必红。搬迁粒度 = 模块粒度原子切换（见阶段 1 的 shim 机制）。
- **正式断言不许为过测而弱化**：搬迁导致的失败，是契约变了就改测试并在 commit message 说明；否则是实现错。
- **改动面 = 评审面**：每步只做该步的事，不顺手"美化"相邻代码。
- **先读后写**：每个被移动的文件先读签名/依赖再改 import。
- 所有 Python 命令走 `uv run`。

---

## 6. 验收标准（阶段级，全部可证伪）

| 阶段 | 可证伪的验收 |
|---|---|
| 0 | `tests/agent` 全绿 + 新增"取消发生在工具执行中段"测试通过 |
| 0.5 | `tests/ai` 全绿 + 新增 `retry.py` 快速失败、`tree_helpers.py` 静默溢出 两条行为测试通过；无新增 provider/API 形状（diff 只动这两处逻辑） |
| 1 | `baldric_ai` 与 `baldric_agent` 互**不含**对方 import（除 shim 期）；shim 已删除后全仓无 `baldric_agent.{messages,tools,types,provider,provider_events}` 外部引用；**运行时双向守卫测试通过**；`pip show baldric-protocol` 可用；全测绿 |
| 2 | **`src/baldric_agent` 下不存在 `session/` 目录**；`grep -R "fcntl\|msvcrt\|fsync\|tempfile" src/baldric_agent` 为空；Windows mypy 7 错误消失；全测绿 |
| 3 | `check_import_graph.py` 含协议 3 组+双向 2 组规则；`tests/guards` 对违规会失败（**用一次故意违规验证 guard 确实会炸**） |
| 4 | protocol 有 semver 声明（起点 `0.1.0`）；`tests/protocol/test_wire_compat.py` 用**固定 JSONL 快照**锁死 entry wire 格式（字段改名/删除即炸）；覆盖"拒读未来版本" |
| 5 | **`structure-baseline.json` 中 `session/session.py`(1796→≤1200)、`tui/app.py`(4180→每文件≤1200)、`subagents/extension.py`(1666→≤1200) 的 lines 数值逐一下降并在 diff 可见**；`--init` 只允许收紧不得记增长；`check_structure.py` 通过；全测绿 |
| 6 | 产品/扩展新代码不得 `from baldric_coding.{session,tui,*.runtime}` 内部实现（只许 `extensions.api` + `baldric_protocol`）；故意违规被 CI 拦下；ADR 记录该边界 |

---

## 7. 与"另一个 Agent 结论"的差异（为什么本计划这样排）

1. **不把"抽 protocol"说成"修依赖倒置"**：我们本就没倒置（F1）。抽是为共享薄契约、给第三方稳定依赖面。→ 优先级不如阶段 0 的缺陷修复。
2. **session 切割不止一刀**：pi 把整个 session 放 coding（F2/F3）。本计划切 `entries/tree/jsonl → protocol`、`storage + memory → coding`，`baldric_agent/session/` 阶段 2 后整体删除，比"只切 storage.py"更彻底。
3. **不抽 schema 包**：pydantic 就是 schema 层（F4）。
4. **顺序是 缺陷(0/0.5)→抽包(shim)→下沉→守卫→冻结→治理→产品**，不是"重构四步做完就冻结"。冻结前必须有：无 `outcome[0]` 崩溃 + ai 层行为对齐 + 机器守卫边界 + wire 快照。→ 否则冻结=焊死 bug。
5. **明确不做** `env/durable/chord/codemode/mcp/telemetry/evals`（你的判断正确），只留扩展插口。
6. **执行层的三处防翻车（评审补入）**：① shim 期不得跨阶段（阶段1 完成定义）；② 阶段5 验收 = 棘轮基线真实下降，不是"拆分且行为不变"；③ 阶段6 加 guard 强制"扩展只走 api.py 钩子 + protocol"，禁止产品层绕过 protocol 直连 coding 内部实现。

---

## 8. 三个决策（已定稿，不再挂起）

| 决策 | 定稿 | 理由/约束 |
|---|---|---|
| **D3** `memory.py` 归属 | **下沉 `baldric_coding`** | 它是会话应用语义（leaf/compaction/摘要措辞），非 wire 契约。protocol 保持只 entries/tree/jsonl 三个机械件。代价：只装 protocol 的第三方需自行实现投影。 |
| **D-pydantic** | **允许，且只允许 pydantic 一个** | 判据：契约层需要"结构化数据+校验"，Python 里就是 pydantic；pi 也依赖 pi-schema。**约束**：`baldric_protocol` 的 `pyproject.toml` 依赖白名单 = `{pydantic}`，其余需 ADR 显式批准；手写序列化一律不做（保住已验证 wire 兼容）。 |
| **D 包名/发布** | **对外发 PyPI，semver 严格** | 对外发布才让"第三方只装 protocol 即可对齐 wire"成为物理接口。**推论**：阶段 4 的 `tests/protocol/test_wire_compat.py` wire 快照测试是**强制项，不是可选**；`CURRENT_SCHEMA_VERSION` 一旦发布即视为 ABI。 |

**三条判据（钉死，进 ADR + guard）**：
1. 能进 protocol 的，只有"数据形状 + 机械变换"，且"第三方实现必须与之一致"。
2. 凡带平台 I/O（fcntl/msvcrt/fsync/tempfile）或带产品策略（措辞/压缩合成/resume 语义）的，一律下放 coding。
3. protocol 依赖白名单 = `{pydantic}`，其余需 ADR 显式批准。
