---
title: "Phase 20.3：skill 调用可靠性"
---

Phase 20.3 加固 Baldric 暴露与调用 Markdown skill 的方式。

## 自动 skill 可用性

`read` 工具可用时，已加载 skill 纳入 system prompt：

```xml
<available_skills>
  <skill>
    <name>testing</name>
    <description>Use when writing tests</description>
    <location>/repo/.agents/skills/testing.md</location>
  </skill>
</available_skills>
```

prompt 现在用 Pi 的措辞：

```text
Read the full skill file when the task matches its description.
```

这意味着模型可以从索引选择相关 skill，对列出的位置调用 `read`，并作为普通工具结果收到完整 skill Markdown。

## 手动 skill 调用

`/skill:<name> [instructions]` 仍是 prompt 展开指令，不是结束该轮的 slash 命令。它现在展开为同样的 Pi 风格 skill 块：

```text
<skill name="testing" location="/repo/.agents/skills/testing.md">
References are relative to /repo/.agents/skills.

# Testing
Run pytest.
</skill>

add parser tests
```

块自包含：包含源文件，并告诉模型 skill 内的相对引用应从哪里解析。

## TUI 显示

session 仍发送并持久化完整展开的 skill 块，agent 拿到完整指令。TUI 在渲染用户消息时解析该结构化块，改为显示紧凑的 skill 项：

```text
Using skill: testing
```

原始 `/skill:<name>` 输入带额外指令时，这些指令作为可见用户消息显示在紧凑 skill 项之后。完整 skill Markdown 不在正常对话视图显示。

## 边界

skill 发现与 prompt 展开留在 `baldric_coding`。`baldric_agent` 只看到普通的 provider 中立消息与 tool call。模型可见的
skill 索引用既有 `read` 工具，而不是给可复用 harness 加一个特殊 skill 工具。TUI 解析仅用于呈现，不改变存储或 provider 可见的消息内容。

## 测试

本阶段覆盖于：

```text
tests/test_skills.py
tests/test_cli.py
tests/test_coding_session.py
tests/test_system_prompt.py
tests/test_tui_adapter.py
tests/test_tui_app.py
```

测试验证两条路径：

- 显式 `/skill:<name>` 展开把完整 skill 内容发给 provider
- system prompt 列出已加载 skill 位置，模型触发的 `read`
  调用可以把 skill 文件装进下一次 provider 轮
