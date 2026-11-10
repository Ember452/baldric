---
title: "Phase 25：system prompt 展示命令"
---

Phase 25 增加 `/system`——一个仅本地的 slash 命令，显示 Baldric 将发给 provider 的有效 system prompt。

## 变更了什么

- coding 命令注册表现在包含 `/system`。
- `CodingSession.system_prompt` 把 harness 当前有效的 system prompt 暴露给命令 handler。
- print mode 在发起 provider 调用之前处理本地 slash 命令。
- TUI 把 `/system` 输出内联渲染在可见会话流里，同 `/reload`。

## 为什么存在

system prompt 是重要的调试 context，尤其当项目指令、skill、工具与自定义 prompt 组合在一起时。用户需要一种直接检视它的方式，而不改变模型看到的对话。

## 持久化与 context 行为

`/system` 返回 `CommandResult.message`；它不追加用户消息、assistant 消息或自定义持久 entry。这意味着：

- 不为该命令发起 provider 请求；
- 显示的 system prompt 不加入 `CodingSession.messages`；
- JSONL session 存储不变，除非本来就存在正常的初始 session 元数据。

这保住了用户可见 UI 输出、模型 context 与 append-only session 历史之间的分离。

## 怎么测试

运行：

```bash
uv run pytest tests/test_commands.py tests/test_coding_session.py tests/test_cli.py
```
