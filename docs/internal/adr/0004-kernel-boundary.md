# ADR-0004：内核边界与 `baldric_protocol` 契约包

- 状态：Accepted
- 日期：2026-11-08
- 伴随实现：`refactor/kernel-protocol-extraction` 分支（protocol 抽取、内核零 I/O、边界守卫、契约版本冻结均已落地）

## 决策（三个，全部定稿不再挂起）

### D-pydantic：`baldric_protocol` 允许依赖 pydantic，且只允许它一个

判据：契约层需要"结构化数据 + 校验"，Python 里这就是 pydantic；pi 的 `packages/schema` 承担同一角色。手写序列化等于把已被 session 文件 / RPC wire / provider 适配三处共同验证的 wire 兼容换成新写的 bug 集合。**约束**：protocol 的依赖白名单 = `{pydantic}`，其余第三方依赖需 ADR 显式批准；由 `scripts/check_import_graph.py` 的 protocol 规则 + `tests/protocol` 守卫强制。

### D3：`session/memory.py`（SessionState 投影）下沉 `baldric_coding`，不进 protocol

判据："第三方实现 session 必须与之"一致的只有**形状/路径/线格式**（entries/tree/jsonl → protocol）；**带产品策略的投影语义**（leaf 解析、compaction 合并、摘要措辞）不属于契约。pi 同样把 SessionManager 放在 coding-agent。protocol 因此保持"一句话能说清的边界"：wire 形状 + 线格式 + 机械变换。

### 会话 I/O：`storage.py` 下沉 `baldric_coding`，内核零 I/O

fcntl/msvcrt/fsync/torn-tail 是平台细节（pi 放在 coding-agent 的 session-manager.ts）。`baldric_agent` 现在 9 个文件、零 fcntl/fsync/tempfile；原先 7 个 Windows-only mypy 错误随文件迁至 coding 层（AGENTS.md 记录的预期）。

## 分层定稿

```
baldric_protocol   ← 纯契约（仅 pydantic）：messages/tools/types/provider/provider_events
                     + session/{entries,tree,jsonl}；PROTOCOL_VERSION=1 冻结
   ↑        ↑
baldric_ai   baldric_agent(9 文件纯内核)   ← 互不依赖（静态 + 运行时双向守卫）
   ↑        ↑
       baldric_coding  ← session/{memory,storage}（投影 + I/O）+ 全部应用层
```

## 机器守卫（不靠文档自律）

- 静态：`check_import_graph.py` — protocol 禁止依赖上层与平台模块；agent ⇏ ai；ai ⇏ agent/coding；coding 子域 ⇏ tui。
- 运行时：`tests/guards/test_import_boundaries.py` 的 subprocess `sys.modules` 断言，抓静态看不见的 `__init__` re-export 间接耦合。两条守卫均已用"植入违规 → 确认炸 → 回退"证明有牙。
- wire 冻结：`tests/expected/*.jsonl` golden 快照锁死字节 + `tests/protocol/test_contract_version.py` 钉 `PROTOCOL_VERSION` 与 golden 存在性。

## 遗留债务（记录，不隐藏）

- 内建扩展直连 coding 内部实现 8 处（subagents/ui → tui.config/state/widgets、schedule_store → session.manager、llama_cpp → backends.contracts）。阶段 6 产品化时按 guard-rules-draft 的"黑名单 + 存量棘轮"方案收编；现在加 guard 只会立即产生 8 个豁免，无防护价值。
- `CodingSession`（179 方法）/ `BaldricTuiApp`（149 方法 / 177 状态属性）两个 god-class 不做文件级拆分，见 `0005-god-class-deferral.md`。
