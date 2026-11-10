---
title: 管理 context
description: 用自动与手动 compaction 保持长 session 可用，并用 thinking mode 控制模型的投入程度。
---

模型一次能读的文本有限——它的 **context window**。长时间编码
session 会把它填满。Baldric 用 **compaction**（总结较早的历史）处理这个问题，并让你用 **thinking mode** 调节模型的投入程度。

## 查看 context 用量

TUI prompt 下方的紧凑状态以 `used/limit` 显示 provider 锚定的活动 context。还没有有效的 provider 用量时，它显示 `?/limit` 而不是把回退估算当作 provider 确认的用量。运行 `/session`
查看详细的 provider 依据或回退估算：

```text
Estimated context tokens: <count>
Context window: <count>
Context window source: configured catalog | provider live catalog
Context token breakdown: system=<count>, messages=<count>, tools=<count>
Thinking mode: <mode>
```

一次成功的模型响应之后，Baldric 把 provider 上报的 token 用量当作该响应所处理 context 的权威大小，只估算其后新增的消息。第一次响应之前、compaction 刚结束、或没有有效用量时，Baldric 回退到确定性估算（约 `字符数 / 4` 加少量每消息与每工具开销）。
回退覆盖 system prompt、项目 context（`AGENTS.md`）、skill
元数据、活动消息历史与 tool schema。

provider 用量锚定活动计数时，`/session` 报告 `Context token basis: provider=<count>, estimated
trailing=<count>`。否则显示回退的 system/message/tool 构成。来自出错或已中止响应的 provider 用量不可信。

这与侧栏 **usage** 区的累计 token 总数不同。累计用量把活动分支上每次请求的 provider 上报输入与输出 token 相加，包括之后被 compaction 替换的历史。反复发送
同一 context 因此会推高累计输入用量，而活动 context 消耗只描述 Baldric 预期下一次发送的内容。两个数字本来就不该相等。

## 自动 compaction

默认情况下，估算值接近模型 context window 时 Baldric 自动 compact。它检查三个时机：

- 新 prompt 之前（捕获带外加入的 context），
- 成功一轮之后（在你的下一轮之前压缩），
- context 溢出错误之后（无视本地估算强制压缩，
  然后重试一次）。

compact 时，Baldric 请模型总结较早的消息，保留对话最近的尾部，然后继续。原始 session 文件从不被编辑——变化的只是发给 provider 的*活动 context*。

默认阈值跟随模型的 context window 减去一个保留额。宣传了显式运行时阈值的 provider 可以覆盖该默认。特别是
Codex 订阅 session 会从 Codex 的认证模型目录发现账户/rollout 专属限制，因为那些限制可能与公共 OpenAI API 不同。你可以为一次运行覆盖最终阈值：

```bash
baldric --auto-compact-threshold 100000
```

自动 compaction 是尽力而为：总结失败时，Baldric 记录并保留原 context。成功的溢出恢复期间，TUI 显示 compaction 与重试进度，而不是把中间的 provider 拒绝当作终态错误。只有恢复无法完成时错误才可见。

阈值 compaction 同样可见。估算越过阈值触发 compact 时，transcript 在生成摘要期间显示 `Compacting context` 状态行，compaction 成功后该行消失。
总结失败时，该行保持为
`Automatic compaction failed: <reason>`，这一轮不会看起来像静默卡住。外层轮次仍只拥有那一次 turn-finished 通知，所以以阈值 compaction 结束的一轮只通知一次，不会两次。

## 手动 compaction

随时按需压缩：

```text
/compact
/compact focus on the database migration work
```

`/compact` 后的可选文本作为摘要的额外焦点。与自动 compaction 一样，手动 compaction 总结较早的前缀、保留最近的尾部。在保留一条真实 entry 的前提下没有足够早的 context 可总结时，Baldric 报告 context 太短无法压缩。摘要生成失败保持可见。

TUI 中，手动 compaction 看起来像普通的工作轮：运行时 prompt
活动指示器与终端标签页标题有动画，应用失焦时完成会触发
turn-finished 通知。
按 `Esc` 取消正在运行的 compaction。

## thinking mode

一些模型可以在回答前花额外精力推理。Baldric 暴露一个可轮换的 thinking 级别：

```text
off → minimal → low → medium → high → xhigh → max
```

- **Shift+Tab** 轮换 thinking 级别（默认 `medium`）。
- **Ctrl+T** 切换是否显示 reasoning token（默认隐藏）。
  reasoning 块与 assistant 回复一起保存，恢复 session 时其原始位置与可见性开关一并还原。

thinking 是模型感知的：只有活动 provider 为活动模型声明了支持的级别时才启用。不可用时，`/session` 显示原因（例如 provider 没声明 `thinking_levels`，或模型不在列表里）。自定义 provider 可以在其配置里用 `thinking_levels` 选择加入——见 [Configuration](/reference/configuration/#providers)。

启动时 Baldric 为所选模型自动选一个有效级别：已记住的每模型选择优先，然后 `medium`，然后 provider 自己的默认，然后模型支持的第一个级别。例如 `kimi-code:k3`
支持 `low`、`high` 与 `xhigh`；因为 `medium` 不可用，它以目录默认的 `xhigh` 打开，而不是报"Thinking mode medium is
not available"。显式选择不支持的级别（经 `/think` 或
thinking picker）仍会报错并列出可用模式。

也可以在命令行用 `--thinking`
（`-t`）设置启动级别，例如 `baldric -t high` 或 `baldric -t max -p "explain this"`。该旗标对本次运行优先于已记住与目录默认，但不保存为新默认；请求所选模型不支持的级别会以错误退出并列出可用模式。此后交互选择的级别（经 `/think` 或 Shift+Tab）照常持久。
