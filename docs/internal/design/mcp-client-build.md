# 构建日志：MCP 客户端支持

构建了什么、为什么长这样、如何对应 pi 的设计，以及
怎么测试。完整产品规格在
[mcp-client-support.md](mcp-client-support.md)；实施计划（含
约束性执行规则与偏差记录 D1–D8）在
[plans/mcp-client-implementation.md](../plans/mcp-client-implementation.md)。

## 加了什么

- **`baldric_mcp`** — `baldric_coding` 旁边的新顶层包，
  wire 协议委托给官方 `mcp` SDK（锁定 `>=1.0,<2`，
  构建时 1.30.0）：
  - `config.py`：`mcp.json` 解析（用户 + 受信任项目）、项目替换与仅 `enabled` 覆盖的合并、`${VAR}` 与 `~`
    展开，以及保留文件缩进与无关键的 `/mcp on|off` 写回。
  - `client.py`：每服务器一条受监护连接——六态
    状态机、初始 HTTP 连接的瞬时错误重试、HTTP 401 →
    `needs-auth`、掉线惰性重连，以及进度通知会重置的单调用期限看门狗。
  - `supervisor.py`：全部连接的所有权——并发启动、
    首轮等待的有界 `wait_ready`、工具调用路由，以及
    `/mcp on|off|restart` 操作。它从不读配置文件。
  - `adapter.py`：生态工具命名（`mcp__<server>__<tool>`，净化，
    溢出/冲突时哈希后缀）、schema 归一化，以及带 20 KiB 中段截断的结果转换。
- **一个薄的内置 extension**（`baldric_coding/extensions/builtins/mcp/`）
  在 `session_start` 启动 supervisor，随服务器状态变化经 live 接缝注册/撤回工具，
  发布 `MCP servers` prompt 区块，放行第一轮（有界等待），并服务 `/mcp`。
- **通用 agent 接缝**（其中不含 MCP 语义）：extension runtime 上的 `bind_live_tools` +
  `unregister_tool`（注册立即到达 harness 的按次运行工具列表）、harness 上的 `update_system_prompt`、
  session 与 `BoundSession`
  协议上的 `refresh_system_prompt`，以及带标题 prompt 区块的 upsert 语义。
- **组合层子代理门**：`CodingSessionConfig.disabled_built_in_extensions`
  过滤内置 registry；subagents 子代理传 `frozenset({"mcp"})`，
  child 永不启动 MCP 服务器。
- **测试**：每模块单测套件（`tests/mcp/`）、带 fake supervisor 的 extension 测试（`tests/coding/extensions/test_mcp_extension.py`）、对 FastMCP fixture 的
  真实进程 stdio 集成测试，以及 resume-repair 回归。

## 为什么长这样（pi 对应）

- 状态机、瞬时重试、惰性重连、带进度重置的单调用超时移植自 `pi-main/packages/coding-agent/src/extensions/mcp/runtime.ts`。
- 命名规则逐行移植自 `pi-main/packages/mcp/src/naming.ts`；
  20 KiB 中段截断移植自 `pi-main/packages/mcp/src/output-limit.ts`。
- `mcpServers` 配置形状、项目替换、覆盖条目与
  写回语义移植自 `packages/coding-agent/src/extensions/mcp/config.ts`。
- 一个有意的 Baldric 差异：`command` + `url` 同时存在是诊断（pi 静默偏好 `url`）——含糊的配置应该失败可见。
- pi 在 `/new` 与 `/resume` 间复用同一 runtime；Baldric 每世代 stage 一个全新
  runtime（信任边界），因此 MCP extension 每世代启动一个 supervisor 并在 `session_shutdown` 时总是关闭——跨世代保留连接会让服务器进程变成孤儿。

## 怎么测试

```bash
uv run pytest -q tests/mcp tests/coding/extensions/test_mcp_extension.py
uv run pytest -q tests/mcp/test_integration_stdio.py   # spawns a real server
uv run pytest -q --ignore=tests/coding/tui             # full fast suite
```

手动冒烟：把一个服务器放进 `~/.baldric/mcp.json`，运行 `uv run baldric`，
`/mcp` 应列出其已连接，工具调用应可用，`/mcp off
<name>` 应持久化该选择。
