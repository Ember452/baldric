# TUI 轮次通知

## 变更了什么

Baldric 的 Textual frontend 现在可以在 agent 运行完全落定、而其终端表面失焦之后请求终端注意。`~/.baldric/tui.json` 的 `turn_notification` 设置接受：

- `"desktop"`（默认）：检测到 Ghostty、iTerm2 或 MinTTY 会话时写 OSC 9，检测到 Kitty 会话时写 OSC 99；
- `"bell"`：写标准 BEL 控制字符；
- `"off"`：什么都不写。

终端模拟器决定这些序列如何呈现。例如，铃声可能标记非活动标签页、请求应用注意，或按终端设置播放声音。桌面通知也可能使用操作系统配置的通知音。Baldric 从终端环境变量检测受支持的桌面协议：Kitty 优先并收到 OSC 99；
Ghostty、iTerm2 与 MinTTY 收到 OSC 9。未知终端不收到桌面序列，而不是不兼容的转义序列。

## 为什么属于 TUI

完成仍是 provider 中立的 session 事件。焦点上报、终端
控制序列与用户通知偏好是 frontend 政策，所以实现留在 `baldric_coding.tui`；`baldric_agent` 与 coding
session 都不知道 Textual 或终端能力。

Textual 的 `AppBlur` 与 `AppFocus` 事件维护活动表面状态。Baldric 在 `AgentSettledEvent` 上通知，而不是 `agent_end` 或 `turn_end`，因为重试、自动 compaction、排队的 steering 消息或 follow-up 可能在那些更低层的边界之后继续运行。这在 Baldric 真正空闲时产生一条通知。

写入使用 `sys.__stdout__`，与终端标题更新一致；非 TTY 流、
`TERM=dumb` 与 CI 跳过写入。构建 OSC 9 或 OSC 99 前剥离载荷控制字节，写失败禁用后续尝试而不崩溃 TUI。

## 怎么测试

自动化覆盖配置解析、控制序列生成、
写失败处理，以及聚焦与失焦完成行为。

在有两个标签页的终端里手动验证：

1. 启动 Baldric 并提交一个运行数秒的 prompt。
2. 在其完成前切到另一个标签页。
3. 确认 Baldric 落定时 Ghostty/iTerm2/MinTTY（OSC 9）或
   Kitty（OSC 99）出现桌面通知。
4. 在 `~/.baldric/tui.json` 设 `"turn_notification": "bell"`，重复，确认终端配置的铃注意出现。
5. 保持 Baldric 聚焦完成一条 prompt，确认无通知。
6. 设为 `"off"`，确认失焦完成保持安静。
