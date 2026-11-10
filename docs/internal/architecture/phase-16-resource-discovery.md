---
title: "Phase 16：健壮的资源发现"
---

Phase 16 让 skill 与 prompt template 的发现足够宽容，能面对真实的用户资源目录。

实现位于：

```text
src/baldric_coding/resources.py
src/baldric_coding/skills.py
src/baldric_coding/prompt_templates.py
src/baldric_coding/session.py
src/baldric_coding/commands.py
```

## 加了什么

Baldric 现在有 `ResourceDiagnostic` 类型承载非致命的资源发现注记。它记录：

- 资源种类，如 `skill` 或 `prompt`
- 已知时的受影响资源名
- 已知时的路径
- 一条短消息
- 严重度字符串

skill 与 prompt template 现在有诊断式加载器：

```python
load_skills_with_diagnostics(...)
load_prompt_templates_with_diagnostics(...)
```

旧的严格加载器仍在，供希望发现错误抛 `ResourceError` 的调用者使用。

## 发现行为

资源目录仍按优先级递增加载：

1. 用户 Baldric 资源
2. 用户 `.agents` 资源
3. 项目 Baldric 资源
4. 项目 `.agents` 资源

高优先级资源与低优先级资源同名时，高优先级获胜。诊断式加载器报告该覆盖而不是隐藏它。

一个目录里有两个同名 skill 时，Baldric 保留第一个确定性匹配并报告重名诊断。这防止一个坏掉的本地资源阻止 TUI 打开。

## coding session 集成

`CodingSession.load()` 使用诊断式加载器。已加载诊断在：

```python
session.resource_diagnostics
```

这让发现诊断留在 `baldric_coding`——本地资源、命令与 UI 行为所在之处。可复用的 `baldric_agent` 包保持对资源路径与 markdown 发现独立。

## 命令与 TUI 可见性

slash 命令注册表现在包含：

```text
/resources
```

它显示加载了多少 skill 与 prompt template，加任何发现
诊断。`/status` 也含资源诊断计数，`/skills`
在有 skill 诊断时显示它们。

Textual TUI 不需要专门的诊断 API。它已把命令结果渲染为 transcript 项，`/resources` 因此以交互方式呈现同一信息。

## 测试

本阶段覆盖于：

```text
tests/test_skills.py
tests/test_prompt_templates.py
tests/test_commands.py
tests/test_coding_session.py
```

测试验证：

- 确定性的覆盖处理
- 重名 skill 诊断
- 宽容的 `CodingSession` 加载
- `/status` 的资源诊断计数
- `/resources` 命令输出
