# TUI 终端标签页标题

Issue: #260

## 变更了什么

Textual TUI 现在用活动 Baldric session 名与运行状态更新终端模拟器的窗口/标签页标题：

- 空闲未命名 session：`τ`
- 空闲已命名 session：`τ | <session name>`
- 运行中 session：动画布莱叶 spinner 前缀加空闲标题

TUI 关闭时 Baldric 写中性的 `τ` 标题，终端不会留下过期的运行帧。

## 为什么住在 `baldric_coding`

终端标题更新是 frontend 事务。实现使用 TUI 已有的状态：

- `TuiState.running`，由适配器从 `AgentStartEvent`、`AgentEndEvent` 与
  不可恢复的 `ErrorEvent` 填充；
- `CodingSession.session_title`，由 `/name` 与自动 session 命名更新。

没有终端或 Textual 依赖加进 `baldric_agent` 或 `baldric_ai`。

## 机制

`src/baldric_coding/tui/terminal_title.py` 发出 OSC 0 序列：

```text
ESC ] 0 ; <title> BEL
```

OSC 0 被常见终端模拟器广泛支持，设置终端窗口/标签页标题。`TerminalTitleController` 只在计算出的标题变化时写入，空闲刷新不刷屏 stdout。运行期间，既有活动计时器同时驱动应用内 prompt 动画与标签页标题 spinner。

## 能力检测与安全

只在 stdout 是 TTY、`TERM` 不是 `dumb`、且未检测到 CI 时启用标题写入。用户可用 `BALDRIC_TERMINAL_TITLE=0` 关闭；CI/无 TTY 场景仅在 helper 规则允许处用 `BALDRIC_TERMINAL_TITLE=1` 显式打开。标题写入是尽力而为：Baldric 写 OSC 序列时终端流抛异常，则对该 TUI 进程禁用后续标题写入，而不打断 session。

session 名在进入 OSC 载荷前净化：C0/C1 控制字符（含 BEL 与 ESC）被剥离，标题截到 120 字符。

## 测试与手动验证

自动化测试覆盖标题构建、净化、能力检测、
去重写入，以及 TUI 运行/命名/空闲转换。

手动验证：

1. 在真实终端标签页打开 `baldric`。
2. 确认未命名的空闲 TUI 标签页标题显示 `τ`。
3. 运行 `/name build notes`，确认标签页变为 `τ | build notes`。
4. 提交一个运行足够久能看到动画 spinner 前缀的 prompt。
5. 取消或等运行结束；确认 spinner 停止。
6. 退出 TUI，确认标签页重置为 `τ`。
7. 用 `BALDRIC_TERMINAL_TITLE=0 baldric` 再来一次，确认 Baldric 不管理标签页标题。
