# hook 组合契约（v2 extension API）

状态：**仅契约** —— 定义每个 extension hook 必须遵守的语义。
写于 provider 级与 session 结构 hook（计划任务 A/B）之前，让两者用同一本规则手册而不是各自发明分歧的。此处不改运行时行为。

这是 extension 自由度的第三个乘数：

```
freedom = handle width (who can mutate what)
        x replayability (every mutation lands in the event-sourced log)
        x composition determinism (what happens when several extensions intercept)
```

没有第三条，宽 handle 就是未定义行为。本文修复它。

## 四条规则

1. **顺序确定。** handler 按注册顺序运行：
   先 extension 加载顺序，再 extension 内注册顺序。顺序
   可观察、可测试。同一事件的 handler 之间不得重排、去重或并发运行。

2. **错误按 handler 隔离。** 一个 handler 抛异常不停其他 handler、也不中止运行；失败记为针对该 extension 的运行时
诊断。*操作*是否失败由 hook 的**失败模式**决定（每个 hook 在下表设置）——绝不由"异常悄悄改了全局结果"决定。两种失败模式：
   - `fail-open`（观察/渲染/通知接缝）：抛异常的 handler 被跳过，
     操作用其他 handler 的结果继续。
   - `fail-closed`（安全接缝：信任、tool-call 拦截）：抛异常的 handler
     视为对该操作的拒绝/拦截（绝不视为"允许"）。

3. **聚合按接缝，绝不混用。** 接缝恰为以下之一：
   - **chained**（变换）：handler *N+1* 收到 handler *N* 返回的值；最后一个 handler 的返回值是结果。用于 `input`、
     `context`、`context_with_system`、`message_end`、`tool_result`、
     `before_provider_request`、自定义摘要改写。
   - **in-place**（原地变更）：handler 收到并改动同一对象；对象本身即结果。用于 `before_provider_headers.headers`、
     `before_agent_start.system_prompt_options`。
   chained 接缝的 handler 返回新值；in-place 接缝的 handler 返回值无意义。一个接缝绝不同时是两者。由类型强制：
   chained 接缝类型为 `Callable[[Payload], Payload]`，in-place 接缝
   `Callable[[MutableView], None]`。

4. **终止按接缝声明。** "门"接缝（block/cancel/handled）
   是**首个获胜短路**：第一个返回门结果的 handler 结束该接缝；操作被门控，该操作的后续 handler 不运行。"末者覆盖"接缝（如缓存预热决策）是**最后有效者获胜**：
   每个 handler 都运行，最终非空结果获胜。每个接缝在下方声明是哪种；绝不同时是两者。

## 接缝目录

v2 extension 可挂钩的每个接缝在此恰有一行。新接缝不加行即不合格。`capability domain` 列指 extension 声明的
`ExtensionCapabilities` 字段：`provider_hooks` 与
`renderers` 是 v2 为新表面加的。能力域是**声明式契约元数据，不是运行时权限门**——宿主绝不因为未声明某域而拒绝接缝，因为 extension 契约承诺的是生态，不是沙箱（计划里"默认拒绝"的想法在核对了明确说明这一点的既有设计后被放弃）。声明域仍是评审者要看的披露步骤。

| 接缝 | 聚合 | 失败模式 | 终止 | 能力域 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `input` | chained | fail-open | —（变换） | `hooks`（既有） | shipped |
| `tool_call`（before） | in-place | fail-closed | first-wins（`block`） | `hooks`（既有） | shipped |
| `tool_result`（after） | chained | fail-open | last-override（`replace`） | `hooks`（既有） | shipped |
| `project_trust` | in-place | fail-closed | first-wins（门） | `hooks`（既有） | shipped |
| `message_end` | chained | fail-open | —（变换） | `hooks`（既有） | shipped |
| `user_bash` | — | fail-open | first-wins（`UserBashResult`） | `hooks` | shipped（v2） |
| `model_select` | —（观察） | fail-open | —（通知） | `hooks` | shipped（v2） |
| `thinking_level_select`（`thinking_level_changed` 的别名） | —（观察） | fail-open | —（通知） | `hooks` | shipped（v2） |
| `session_before_compact` | — | fail-open | first-wins（`CompactionSummaryResult`），无 `block` | `hooks` | shipped（v2，仅摘要） |
| `context`（provider） | chained | fail-open | —（变换） | `provider_hooks` | shipped（v2） |
| `context_with_system`（provider） | chained | fail-open | —（变换） | `provider_hooks` | shipped（v2） |
| `before_provider_headers` | in-place | fail-open | last-override（变更获胜） | `provider_hooks` | shipped（v2） |
| `before_provider_request` | chained | fail-open | last-override（载荷） | `provider_hooks` | shipped（v2） |
| `after_provider_response` | in-place（读） | fail-open | —（观察） | `provider_hooks` | shipped（v2） |
| `provider_stream_event` | in-place（读） | fail-open | —（观察） | `provider_hooks` | shipped（v2） |
| `cache_warming_decision` | chained | fail-open | last-override（动作） | `provider_hooks` | 推迟（无缓存预热机制） |
| entry 渲染器 | — | fail-open | 每命名空间 first-wins | `renderers` | shipped（v2） |
| 工具渲染解析器 | — | fail-open | 第一个有效者获胜，`next()` 回退 | `renderers` | shipped（v2） |
| markdown 变换器 | chained | fail-open | —（显示变换） | `renderers` | shipped（v2） |
| `session_before_fork/switch/tree` | — | fail-closed | first-wins（`block`\|`replace`） | `hooks` | 推迟（无真实需求；需先做变更审计） |

compaction 注记：extension 可以供给摘要，绝不能否决。溢出
与阈值 compaction 必须总能完成，所以 `block` 不在本契约里——宿主回退内置摘要器，而不是让模型溢出 + extension 否决的无限重试循环发生。供给文本钳到
`MAX_EXTENSION_COMPACTION_SUMMARY_CHARS`（20k），防止它撑爆自己保护的预算。

## 当前 runtime 已满足什么

`ExtensionRuntime.emit_event`（runtime.py）已经按注册顺序运行 handler 并隔离抛异常的 handler（记录运行时失败，继续）。既有接缝因此已遵守其声明失败模式的规则 1、2。规则 3（聚合形状）与 4（终止）是计划接缝必须实现的新**契约承诺**；上表 shipped 接缝按其已有形状记录，下方的守卫测试钉住今天存在的部分，重构无法静默回归它们。

## 怎么加接缝（清单）

1. 在上方目录加一行，填全四列。
2. 按规则 3 类型化为 chained 或 in-place。
3. 声明其能力域；若新域则加进 `ExtensionCapabilities`。
4. 实现使抛异常的 handler 按其失败模式表现。
5. 加覆盖以下场景的 fake-extension 测试：正常、两 handler 一致、两 handler
   冲突（按终止规则）、单 handler 抛异常。
6. 门接缝要加"违反契约"测试（如溢出 + block）。

## provider 接缝——如何接线（任务 A1 + A2）

provider 级 hook 遵循 Pi 的两层拆分：AI 包暴露原生
请求 hook，extension 层把事件名桥接到它们之上。

- **AI 层（A1）。** `RequestHooks`（协议）携带 `payload`（chained）、
  `headers`（in-place）、`response`（观察）。`ai.hooks.apply_payload` /
  `apply_headers` / `observe_response` 以隔离边界运行它们并 await 同步或异步 handler。每个适配器在其真实的
  载荷构建 / header 构建 / 响应后调用点调用。适配器只经
  `stream_response(..., hooks=...)` 获得它们，没有 hook 的适配器逐字节一致。
- **provider 边界（A1）。** `HookableProvider` 包裹 `ModelProvider` 并
  暴露 `context`（chained）、`provider_stream_event`（观察）、
  `response_start`（观察首个事件）。它把自己的 payload/headers/response
  handler 作为 `RequestHooks` 转发给被包裹适配器。
- **extension 桥（A2）。** `ExtensionRuntime.build_provider_hooks()` 把以
  `on("context"/"context_with_system"/
  "before_provider_headers"/"before_provider_request"/"after_provider_response"/
  "provider_stream_event")` 注册的 handler 适配到 AI 接缝，给每个 handler 一个类型化事件
  （`ProviderContextEvent` / `ProviderHeadersEvent` / ...）。session 把每次
  `_harness.config.provider` 赋值都经 `_apply_provider_hooks` 漏斗，仅当 extension 注册了 provider 接缝时才把 provider 包进
  `HookableProvider`（否则零开销）。这与 Pi 的 coding-agent →
  ai 桥是同一路由。

与上方目录的接缝形状对齐：`before_provider_request` = payload
（chained）、`before_provider_headers` = headers（in-place）、
`context`/`context_with_system` = context（chained）、`after_provider_response` =
response（观察）、`provider_stream_event` = stream（观察）。`ai.hooks._guarded` 与
`ExtensionRuntime._invoke_provider_handler` 各有一条 `# noqa:
BLE001` 边界——都是契约要求的隔离边界，作为已评审例外记录在豁免基线中。
