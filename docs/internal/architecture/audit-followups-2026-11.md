# 审计跟进：2026-11 评审改了什么

**状态：** 首轮已在 `fix/audit-followups-2026-11` 完成。

本笔记逐条记录评审发现：本分支修复了它、删除了死物、还是刻意保留。`contract-debt.md`
的规则适用：条目要么带测试接线、要么移除、要么在此列出使其回归的触发条件。

## 已修复

| 发现 | 变更 |
| --- | --- |
| session entry 无法增加字段（P0） | 每条 entry 的 `schema_version`（v1 省略，文件保持字节一致）、宽容读取（任意深度剥离未声明字段），以及新旧版本双双指名的 `SessionVersionError`（针对更新文件或未知类型） |
| `prompt()` 后接 `cancel()` 无效；被放弃的运行卡死 harness（P0） | 运行与其取消 token 在生成器体执行前注册；`_RunIterator` 拥有生命周期，`aclose()` 释放它 |
| TUI 从不观察 `x-inference-provider`（P0） | `load()` 经 print 与 RPC frontend 已用的观察者路径重建自有的 Hugging Face provider |
| `resume()` 丢弃 `tools=` 与 `runtime_model_catalogs`（P1） | 两者都被拷贝；一个 parity 测试驱动真实 `resume()` |
| `/model` 与 `/thinking` 在 print mode 是静默 no-op（P1） | print mode 应用意图；只需屏幕的命令说 `interactive-only` |
| print 渲染器对失败判断不一致（P1） | 单一谓词：`error`、`aborted` 与截断（`length`）都使运行失败 |
| 持久化消息是 O(session 长度)（P1） | 尖端追加扩展派生状态；完整回放保留给重试、非尖端父节点与其他 entry 类型。只有时间戳变化时限流索引写入 |
| Google 与 Mistral 从不报告用量（P0） | 两者都解析进与其他适配器相同的归一化 `Usage` 形状 |
| 四个部分 SSE 解析器（P1） | `_sse.iter_sse_events` 是唯一的；每个适配器断言拆分帧产出与单行帧相同的事件 |
| Codex 把 `item_id` 编进 `ToolCall.id`（P1） | 只存可移植的 `call_id`；适配器保留自己的映射 |
| 重试数据被丢弃、默认 1 秒重试（P1） | 重试数据落到消息诊断（截断、永不对模型可见）；默认延迟 15 秒 |
| extension API 无版本（P0） | `EXTENSION_API_VERSION` + `ExtensionCapabilities`，加载时检查 |
| extension 可读所有凭据并遮蔽内置 provider id（P0） | 单一认证咽喉处的范围化凭据读取器与环境允许列表；id 冲突被拒 |
| `/reload` 从不卸载模块；`reset_for_reload` 已死且 docstring 撒谎（P1） | 删除死方法；`retire()` 在前缀守卫之后卸载该世代加载的模块名 |
| 失败的 `setup()` 收不到 `session_shutdown`（P1） | 放入仅关闭队列，由下一次被 await 的关闭排空 |
| 安装器 registry 写入非原子（P2） | `atomic_write_text`，损坏的 registry 保留为 `<name>.corrupt` |

## 仍开放（附使其回归的触发条件）

| 发现 | 仍开放的原因 |
| --- | --- |
| `Usage.cost` 有读者无生产者 | 移除它改变 wire 形状；接线它需要在 provider 层做定价，而定价今天不在那里。按 `deferred-decisions.md` 条款决策待定。触发：第一个需要成本在导出中存活的消费者。 |
| `execution_mode="parallel"` | **以拒绝方式修复**：`AgentHarness` 拒绝声明 `parallel` 的工具，因为本循环串行运行工具。Pi 经 `toolExecution` 实现并行批次；那仍是一个特性。 |
| `EntryAppendedEvent` | **已删除**连同其白名单条目；守卫测试现在拒绝任何没有事件模块声明的白名单类型。 |
| `BashExecutionMessage` 从不被构造 | Pi 的 `!!` 路径的 wire 对齐占位，Baldric 以不同方式实现。触发：把 `!!` 实现为消息。 |
| `/help` 与 `/context` 命令函数未注册 | **通过注册修复。** 它们已实现并有测试但不可达。旧的 `test_non_pi_commands_are_not_registered` 守卫以 pi-parity 理由禁止它们；该政策现在被有意反转（`/provider` 与 `/resources` 仍不注册），两个测试都钉住新契约。 |
| 工具级授权不存在（`before_tool_call` 无调用点） | 信任模型按设计是项目级；工具门控是新特性。触发：第一个限制特定工具的请求。 |
| Windows `os.kill(pid, 0)` "杀进程" | **不是缺陷。** 在本平台验证：child 持续写心跳（4 → 19）并保持存活。记录以免再查。 |
| extension 凭据范围由 extension 自己声明 | 敌意 extension 仍可指名别的 provider 的凭据。关闭它需要宿主自有的 provider 到凭据映射与 `resolve_provider_auth` 签名变更。 |
| `CodingSession` 拥有约 33 个被其他模块写的可变字段 | **已加棘轮，未消除。** 四个最热字段现在在类上有语义写入器，所有调用点都用它们（154 个外部写点 → 119）。`tests/guards/test_session_state_write_ratchet.py` 对任何新写失败、清理未记录时也失败，数字只能降。剩余大头是 `_adopt_replacement`——它一次拷贝整个状态。 |
| `SessionInfoChangedEvent` / `ThinkingLevelChangedEvent` 到不了 frontend | **已修复。** 两者在发生时排队，在其自身事件之前交给下一次 `prompt()` 流（pi 把 session 级事件发布给 session 订阅者；排队是这里更小的等价物）。因此 frontend 即使是 extension 触发的改名或 thinking 变更也能看到。空闲期的情况仍要等下一次运行。 |
| `Usage.cost` 无生产者 | **已修复。** `_persist_message` 在 entry 写入前从目录给响应计价（provider 上报的成本获胜，未定价模型保持零）。Pi 在适配器计价因为其模型对象自带费率；我们的来自 provider 目录。 |
| `BashExecutionMessage` 从不被构造 | **已修复。** 终端命令持久化为 `bashExecution` 消息；context 投影渲染模型之前看到的同一文本，遵守 `exclude_from_context`，transcript 加载器在 resume 时显示它们。 |
| `before_tool_call` 无应用调用点 | **不是缺陷。** loop 遵守并测试该 hook（`tests/agent/test_agent_loop.py`），应用层刻意改用 extension 的 `tool_call` hook——因为那个 hook 还能改写参数，而 `before_tool_call` 表达不了。保留 harness hook 是给嵌入者的 pi parity；记录以免再查。 |
| extension 凭据范围由 extension 声明 | **已修复。** 宿主把 provider id 传入 `resolve_provider_auth`，只保留属于它的已声明名字（`<id>` 或 `<id>:<suffix>`）。环境名按声明保留，因为任何进程内 extension 都能直接读 `os.environ`；凭据库才是真边界。 |

## 验证

- `ruff check`、`ruff format --check`、`mypy`（Windows：只有已知 `fcntl` 错误）、四个棘轮。
- `pytest -q`（全量，含 TUI）。
- 上面每个修复都带着一个对旧实现会失败的测试落地；那些通过回退源文件验证过的，在 commit message 里写明。
