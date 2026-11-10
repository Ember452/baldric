---
title: Sessions
description: 恢复过去的对话、从历史任意点分支、重命名 session 并导出它们。
---

每段 Baldric 对话都是一个 **session**，保存到磁盘以便之后回来。session 以 append-only JSONL 存放在 `~/.baldric/sessions/` 下，按工作目录组织，恢复流程聚焦于你当前所在的项目。

## 列出 session

```bash
baldric sessions
```

每行显示 session id、标题、model 与工作目录。

## 恢复

从 shell：

```bash
baldric --session <session-id>
```

在 TUI 内：

```text
/resume            # 打开过往 session 的 picker
/resume <id>       # 恢复指定的 session
```

`/resume` picker 把项目与最近 session 呈现为连续的 Finder 式栏位浏览器。项目栏用不带 session 计数的紧凑文件夹名；所选项目的完整路径显示在 session 栏上方。其 shell 立即打开，当前项目与其他项目索引随后在后台加载。按
**Left** 移到项目栏，用 **Up/Down** 选另一个
项目，再按 **Right** 回到其 session。按 **Enter**（或点击）恢复一个。按 **Ctrl+Enter** 归档高亮的 session。
项目栏活动时，**Ctrl+Enter** 归档整个项目。选
picker 上方的 **Archived** 标签页检视已归档的项目与 session。
在 picker 任意处按 **F2** 打开该标签页；对已归档 session 按 **Enter** 恢复它，对已归档项目按 **Enter**
恢复其全部 session。恢复的条目回到 **Active** 标签页。
归档从不删除 session 文件或项目目录。

搜索框在所选项目内过滤 session 名与模型。

想有意重新开始而不是恢复，用 `baldric --new-session`（TUI 里是
`/new`）。

退出 TUI 且 session 已持久化时，Baldric 打印恢复它的确切命令作为提醒：

```text
To resume this session: baldric --session <session-id>
```

## 从历史分支（`/tree`）

session 是一棵*树*，不只是一条线——你可以回到过去尝试不同的路径，而不丢掉已有的东西。

运行 `/tree` 打开 session 树，然后选择一个更早的 entry。每个分叉点上，历史最长的子分支显示为主分支。交替分支紧跟父节点之后、在分支点缩进显示，然后未缩进的主历史继续。

- **Enter** — 从该点继续，保留既有分支。
- **S** — 移动活动点之前，请活动模型为你要离开的消息生成结构化摘要。
- **C** — 为这一次摘要提供自定义焦点指令。
- **L** — 为高亮 entry 创建或编辑书签标签。提交空标签清除它。
- **Ctrl+F** — 切换到只含带标签 entry 的视图。
- **Ctrl+L** — 显示或隐藏每个可见标签的最近修改时间。
- **Ctrl+T** — 显示或隐藏 tool-call 行。

标签渲染为 entry 前的 `[label]`。它们是每 entry 的书签，跨分支跟随其 entry；它们不重命名 session。session 的显示标题用 `/name` 单独设置。

摘要请求失败时，Baldric 回退到确定性摘要。

活动分支尖是最后写入的 session entry。纯 **Enter**
导航只在内存中：在下一个动作前退出再重开，会回到文件顺序中最后一条非 legacy-leaf entry。你的下一条消息或状态变更以所选点为父，使新分支成为持久化的活动尖。**S** 立即写入其分支摘要，因此总结过的导航在重启后仍然有效，哪怕之后没再发消息。

## 恢复较旧的 session

旧版 Baldric 可能在运行被中断时留下畸形的 tool-call 历史。provider 拒绝这种历史，被恢复 session 里的每个 prompt 都可能因缺失 tool call 或 tool 输出而报 400 错误。

Baldric 在恢复时与 `/tree` 导航后校验活动分支。它通过追加 provider 安全的分支修复缺失、错位、重复或孤立的工具结果，同时保留原始 JSONL entry。持久的 session 诊断记录改了什么。重复恢复是幂等的，历史已有效时不会追加另一次修复。

崩溃还可能在 transcript 里留下残缺的最后一行，这曾让 session 不可读。Baldric 现在只丢弃那条不完整的行，保留其前每条完整记录；其他任何位置的损坏仍然响亮失败。读操作从不改写 transcript：撕裂的尾部在下一次追加时修复。session 索引行为相同——损坏的记录被跳过并报告，索引从幸存 entry 重写，一条坏行藏不住该项目里的所有 session。

## 重命名

Baldric 能生成时，新 session 会自动从第一条消息获得短名。Baldric 先显示已确认的消息——包括经 prompt-template slash 命令展开的文本——再与 agent 回复并行发送命名请求，命名不拖延 transcript 也不拖延响应。名字出现在一切已显示 session 名的地方，包括
`/resume` picker 与 id 补全。

自动命名发一次高层 provider 请求。provider 适配器可按其配置的 `max_retries` 重试瞬时失败。重试耗尽或响应不是可用标题时，Baldric 不再发起另一次命名请求：session 正常继续，并在可能时使用短的本地回退。

```text
/name My refactor session
```

随时用 `/name` 手动覆盖自动名。Baldric 不会替换你自己设的名字。

## 导出

把 session 导出为可分享的文件：

```text
/export                              # HTML，输出到当前目录
/export --format jsonl               # 原始 JSONL
/export --format html report.html    # 显式目标
```

或从 shell：

```bash
baldric export <session-id>                     # HTML（默认）
baldric export <session-id> session.html
baldric export <session-id> --format jsonl
```

来源可以是已索引的 session id **或** JSONL session 文件的路径。`/export` 成功后，Baldric 在 TUI transcript 里显示目标路径。该状态仅用于显示：不保存进 session 历史，也不作为 context 发给模型。

HTML 导出自包含并含两个标签页：**Transcript** 按存储顺序保留 session 树与 entry，**Usage** 汇总活动分支的模型请求，包括生成 compaction 与分支摘要的请求、prompt 缓存、输出与 reasoning token、估算的 API 费率成本、tool 调用与 compaction。摘要生成请求在请求表中单独标注，不混入 assistant 轮次。用量图表是
交互式的——悬停看确切数值，点图例可隐藏一条曲线——并可下载为白底静态 PNG。导出跟随 Baldric 的主题：浅色模式用 baldric-light、深色模式用 baldric-dark，切换主题时图表实时重新着色。`/export` 从活动 session 生成 HTML 时，还会在单独折叠的 **System Prompt** 区块里包含当前
system prompt。分享前请检查该区块：prompt 可能暴露项目指令、skill
指引、路径或其他本地 context。对已索引 session 或任意 JSONL 文件的离线
`baldric export` 省略该区块，因为 session JSONL 不持久化 prompt。

system prompt 是仅显示的导出元数据，不是 transcript entry。
直接 JSONL 导出与从 HTML 下载的 JSONL 仍只含 entry，不包含它。

新的 compaction entry 存储 `first_kept_entry_id` 边界：回放插入摘要，然后保留该活动路径 entry 及其后的一切。这是对旧版 Baldric 文件 `replaces_entry_ids` 数组的定长、Pi 兼容替代。旧数组保持可读并在回放时优先，导出或恢复 legacy session 不改变其消息历史。HTML 的 entry 细节为现代 compaction 显示 first-kept 边界，并标出不可用的 legacy 边界。

导出头部以总 entry、消息、工具、session 事件与耗时的紧凑摘要开始。摘要下方的时间戳时间线把消息、工具与事件标记分入独立泳道；选中标记跳到该 entry。每条 transcript entry 是一行紧凑的手风琴行（图标、标题、单行预览、时间戳），展开可见完整内容；thinking 块、tool-call 参数与工具结果细节是嵌套手风琴。导出头部提供控件：

- 在 transcript 与 session 树中显示或隐藏 tool call 与 tool result——芯片过滤器显示 session 含每类多少 entry
- 一个按钮展开或折叠 transcript 里所有手风琴
- 隐藏 session 事件——session 信息、模型与 thinking 变更、compaction、标签、自定义 entry——聚焦用户与 assistant 消息
- 把 session 下载为 JSONL 文件——完整 entry 数据内嵌在页面里，下载可离线工作并包含每条 entry（包括旧版 Baldric 的历史 `leaf` 记录）

工具行标题为 `Tool: <name>`（例如 `Tool: read`），session 树为可读性只用工具名标注工具 entry。已解析的书签标签也以 `[label]` 前缀出现在其目标树节点上；标签变更 entry 仍在 entry 流中可审计。

Extension 注入的模型 context 存为一等 `custom_message`
entry。其 `custom_type` 标识 extension，`content`、`details`
与 `display` 保留载荷与呈现选择。`display: false` 让内容保留在模型 context 中，但在 TUI 与可见的
HTML transcript 中隐藏；完整 entry 保留在 JSONL 导出中。把它存为通用 `role: "custom"` `message`、或存为带 `custom_type` 的 Baldric-v1 用户消息的旧文件，加载时被归一化并回放相同 context。

Baldric 持久化的 entry 包装字段用 snake_case，如 `parent_id` 与
`custom_type`。Pi 兼容的 RPC 检视 API 把这些字段投影为
`parentId` 与 `customType`；见 [RPC 参考](/reference/rpc/)。

## session 存放在哪里

```text
~/.baldric/sessions/<cleaned-path>-<short-hash>/
```

例如 `/Users/you/repos/baldric` 变成类似
`repos-baldric-a1b2c3`。原始 JSONL 是 append-only 的。新版 Baldric 不再写单独的 `leaf` 指针记录；文件顺序中最后一条非 `leaf` entry
是活动尖。包含 `leaf` 记录的旧文件保持可读，但这些记录不覆盖文件顺序的尖选择。compaction 与
分支只改变*活动*视图，从不改变已记录历史。标签变更存为 `{"type":"label","target_id":"<entry-id>","label":"checkpoint"}`；
`null` 或空标签清除目标的书签。书签功能之前、label entry 缺 `target_id` 的 Baldric 文件，确定性地加载为最早可分支 entry 上的书签。

新的 compaction 与 branch-summary entry 为生成摘要的那次模型调用携带可选的 `usage`、`provider`、
`model` 与 `response_provider` 字段。路由服务上报时，`response_provider` 标识解析出的后端。`usage` 字段形状与 assistant 消息相同（`input`、`output`、
`cacheRead`、`cacheWrite`、可选 `cacheWrite1H` 与 `reasoning`、`totalTokens`、
`cost`）。多个 completion 共同贡献一个摘要时，Baldric 存逐字段总和。旧 entry 与启发式 branch-summary 回退省略
`usage`；它们照常加载，且不往用量分析里加零成本请求。

确切布局见
[Configuration](/reference/configuration/#sessions)。
