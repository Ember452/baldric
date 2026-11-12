# 深扫跟进：P2 修复与 A–D 决策记录（2026-11-12）

来源：2026-11-11 全量只读深扫的汇总报告。三份子报告只在原会话上下文中、未落盘，本文按其汇总与本轮逐行复核记录。本轮全部工作在主会话完成，未使用子智能体；全程 TDD（先写失败测试再实现）。

## 一、P2 修复（4 项全部落地）

### P2-1 Codex 传输重试重复 thinking — 已修复

流内错误分支（`openai_codex.py` 附近 :325-333）检查了 `emitted_content` 与 `emitted_thinking`，但传输错误分支只检查 `emitted_content`：长 reasoning 阶段网络抖断流 → 重试 → thinking 重复进入持久历史。其余四家适配器安全，因为它们把 thinking 计入 content 标志（anthropic.py:277、openai_compatible.py:628、google.py:282、mistral.py:274）。

修复：传输分支补 `and not emitted_thinking`（openai_codex.py:354）。测试：`tests/ai/test_codex_transport_retry.py`（修复前该场景重发 3 次请求、thinking delta ×3；修复后 1 次、×1）。

### P2-2 providers.json / credentials.json「断电即不可启动」— 已修复

读侧两处裸 `loads`（settings.py:65、credentials.py:136）损坏即崩；写侧两处 flush 后直接 replace、无 fsync。

修复（双管齐下）：
- 写侧 fsync：`_atomic_write_text`（settings.py）与 credentials `_save` 在 replace 前 `fsync`。
- 读侧兜底（providers.json）：先试 `.bak`（每次写都留有备份）并自愈主文件；无可读备份则把损坏文件隔离为 `.corrupt`、回退默认值并 `logger.warning`（settings.py `_load_provider_settings_json`）。
- 读侧兜底（credentials.json）：损坏即隔离为 `.corrupt`、空库启动并告警；不引入 `.bak`——凭证文件多一份拷贝就多一份泄露面，重新授权即可恢复。

测试：`tests/runtime/providers/test_provider_config.py` 三个新测试（.bak 自愈 / 无 .bak 回退 / fsync 探针）+ `tests/runtime/config/test_credentials.py` 两个新测试。

### P2-3 llama.cpp Doctor 探针泄漏 client（两处）+ 新发现的探针误报 — 已修复

- 泄漏：`_probe_stream` 与 `_probe_tools` 的 `finally` 调 `provider.aclose()`，但 provider 持注入 client 时 `aclose()` 是空操作（openai_compatible.py:100-104），探针自建的 client 从不关闭。汇总报告只记了 `_probe_stream` 一处，复核确认 `_probe_tools` 同型，共两处。修复为直接 `await client.aclose()`（与 `discover()` 的正确写法一致）。
- **新发现（本轮测试意外暴露）**：`_probe_stream` 把 `AssistantStartEvent` 当成功信号，但 canonicalize_provider_stream 在失败时也会先发 start（stream.py:337-338 的兜底），实测连接失败的事件序列为 `[Start, Error]` → **Doctor 对连不上的服务器也报 "Streaming chat completions accepted."**。修复：成功判定改挂 `AssistantDoneEvent` 终止事件、错误事件优先（service.py:1316-1322）。

测试：`test_llama_cpp_extension.py` 两个新测试同时钉住关闭与失败判定。

### P2-4 估算成本固化进 transcript — 改判为有意设计并加来源标记（A2）

复核确认 docstring 已写明设计意图（runtime.py:745-753），且 provider 报过价则不覆盖（:757）。决策：保留行为，给 `UsageCost` 加 `estimated: bool = False`（protocol/messages.py），`_fill_response_cost` 置 `estimated=True`，`sum_usage` 按 `any` 传播。_wire 变更经 golden diff 审查确认只增 `estimated` 键_。注意：`WireModel` 是 `extra="forbid"`，旧版本 baldric 读新 transcript 会被拒——单向协议演进，属正常代价。

测试：`test_usage_cost_producer.py` 扩展两处断言 + `sum_usage` 传播测试。

## 二、顺带修复

- mcp.json `set_server_enabled` 裸 `write_text`（仓内第 8 处未收敛的原子写）→ 本地 `_atomic_write_text`（temp+fsync+replace；mcp 是独立顶层包，不能反向依赖 runtime/providers 的私有 helper）。测试：fsync 探针 + 无残留 temp 文件断言（test_config.py）。
- MCP `_connect_once` 捕 `BaseException` 吞掉取消 → 取消（anyio cancelled）改为重抛，`connect()` 的 `state=failed` 不再吞 Esc。测试：`test_client.py::test_connect_cancellation_is_not_swallowed`。
- Google API key 从 URL query 改为 `x-goog-api-key` header（A1）：key 不再进 httpx/proxy URL 日志；用户显式配置的同名 header 优先；api_key 为空时不加 header。测试两个（默认走 header / 显式 header 优先）。
- Mistral reasoning_effort 丢弃用户选择（B8）：对齐 pi 的 effort-map 语义（pi: mistral-conversations.ts:200-206、catalog/providers/mistral.ts）。`_MISTRAL_EFFORT_LEVELS` 映射表：这三个模型 API 只接受 none/high——`"none"`（thinking off）显式发 `"none"`（此前被静默省略，是实际 bug）；未支持档位钳到 `"high"`；`None`（未配置）保持省略；非映射模型维持 `prompt_mode`。测试四个（off→none / 钳 high / 未配置省略 / prompt_mode 守卫）。

## 三、A–D 拍板问题的决策记录

| # | 问题 | 决策 |
| --- | --- | --- |
| A1 | Google key-in-URL | 改 `x-goog-api-key` header（已做） |
| A2 | 估算成本入 transcript | 接受现状 + `UsageCost.estimated` 来源标记（已做） |
| A3 | Windows msvcrt 10s 锁上限 | 保留有界等待（偶发失败有兜底优于无限挂起），不改 |
| A4 | codex 目录保存处 `suppress(TypeError/ValueError)` | 本轮未复核，保留现状，待后续单独审 |
| B5 | `set_model`/`_set_provider_model` 不写 `ModelChangeEntry` | 确认为同步 API 限制：写 entry 需 await，而 TUI 路径的 candidate-first 两阶段提交正是为此设计；热修需跨 commands/RPC/extensions 的异步签名重构。**转路线图**（重启后模型静默回退是真实缺口，值得一个独立任务） |
| B6 | `thinking_signature` 一字段三义 | 保留现状 + 待补协议文档（转路线图，文档任务） |
| B7 | branch 纯导航不持久 leaf | pi 同语义、刻意，保留 |
| B8 | Mistral 恒发 "high" | 已修（见上） |
| B9 | MCP 工具调用不可 Esc 取消 | 过渡形态（等 MCP 生态进度），暂缓 |
| B10 | Codex 非标准事件 `response.output_item.completed` | 需实测上游后端才能定，留观察 |
| B11 | Anthropic 空 content 的 tool_result | 无生产拒单证据，不改 |
| B12 | `"codex" in model` 子串路由 responses API | 接受（有手关启发式的逃生门），不改 |
| C13 | Windows 更新 handoff 仅 uv-tool | 记录为已知缺口（pip/uv-pip 撞运行中 exe 是真实约束），暂缓 |
| C14 | Windows Terminal OSC 9 桌面通知 | 功能缺口，转路线图（本轮不做功能新增） |
| C15 | `--mode transcript` 不截断 | 刻意（完整记录语义），保留 |
| C16 | print 模式失败丢弃部分回答 | 保留现状（原子输出契约） |
| C17 | CLI typo 静默变 prompt | 接受的手工路由代价，暂缓 |
| C18 | trust.json pending → `--doctor` 检查 | 低风险小增量，转路线图 |
| D19 | RPC wire 注册表化 | 建议提到 P4a 之前（新增 entry 类型 = ui-web 拿错误不拿数据），转路线图 |
| D20 | TuiSession Protocol | 转路线图（P4a 多前端的最低成本一步，~25 处 getattr 探测待收敛） |
| D21 | `run_tui_app` 的 `getattr(session, "provider")` 兜底 | 暂留（`owns_initial_provider` 常态化后可删，低优先） |

## 四、暂缓项清单（深扫 P3 节选中未在本轮处理的）

以下各项维持深扫判定，待路线图排期：
- 会话持久化磁盘 I/O 同步跑在事件循环上（session/storage.py:79-108）→ 并入 P2.11 存储 conformance；并发语义需要专门设计，不能热修补 `to_thread`。
- provider 更换后旧实例从不关闭（model_runtime.py:272）。
- MCP `close()` 与连接重试竞态（mcp/client.py:288 附近）。
- RPC server 写侧同步阻塞 + 16MiB 读完再查（modes/rpc/server.py）。
- RPC wire 穷举以 `raise AssertionError` 收尾（wire.py:157）。
- lifecycle `aclose()` 不 flush `_pending_message_writes`（退出丢已显示消息）。
- 管道 stdin 未强制 UTF-8（cli.py:928）、GBK 控制台标题动画一次性停用（terminal_title.py:100）、msvcrt 锁 10s vs POSIX 无限等待（storage.py:327，本轮决策 A3 保留）。

## 五、质量门与改动面

- 全量 fast suite：**2265 passed / 52 skipped（Windows 已知基线）/ 0 failed**；TUI 套件未跑（本轮未改 tui/rendering）。
- `ruff check` 全过；`ruff format` 修正 4 个文件的格式漂移；mypy 恰为 14 个已知 Windows 基线错误（trust/policy.py、storage.py 的 fcntl），无新增。
- 协议 golden（`tests/expected/`）5 个文件更新：经 diff 审查，全部变化仅为 `usage.cost` 内新增 `"estimated":false`。
- structure baseline 经 `check_structure.py --init` 记录 7 个文件的已审增长（含 mcp/config.py 越过 400 行门）。
- 本轮改动与工作树中上一段会话的未提交改动（AGENTS.md、agent-guidance-baseline.json、agent/loop.py、4 个未跟踪 docs）共存且互不重叠，**尚未提交**；建议按本文的四个 P2 + 顺带修复分组原子提交。
