---
title: "Phase 13：Baldric home、路径与 `.agents` 资源"
---

Phase 13 把 Baldric 的用户/项目文件系统位置显式化，并开始为每个正常 Baldric session 自动加载 `.agents` 资源。

实现位于：

```text
src/baldric_coding/paths.py
src/baldric_coding/resources.py
src/baldric_coding/skills.py
src/baldric_coding/prompt_templates.py
```

## 加了什么

Baldric 现在有一个规范的路径 helper：

```python
BaldricPaths
```

它定义用户级位置，如：

```text
~/.baldric/
~/.baldric/sessions/
~/.baldric/skills/
~/.baldric/prompts/
~/.agents/
~/.agents/skills/
~/.agents/prompts/
```

与项目级位置，如：

```text
<project>/.baldric/skills/
<project>/.baldric/prompts/
<project>/.agents/
<project>/.agents/skills/
<project>/.agents/prompts/
```

## session 位置

早期 TUI 默认 session 路径从项目本地存储：

```text
<project>/.baldric/sessions/default.jsonl
```

移到按项目路径为键的用户 home 存储：

```text
~/.baldric/sessions/<project-hash>/default.jsonl
```

这让 JSONL transcript 留在一致的用户自有位置，同时仍按项目分离 session。

## 自动 `.agents` 资源

BaldricResourcePaths 现在默认包含 `.agents` 目录。

未提供 cwd 时，Baldric 从这些位置加载用户资源：

```text
~/.baldric/skills/
~/.agents/skills/
~/.agents/
~/.baldric/prompts/
~/.agents/prompts/
```

提供 cwd 时，Baldric 还从这些位置加载项目资源：

```text
<project>/.baldric/skills/
<project>/.agents/skills/
<project>/.agents/
<project>/.baldric/prompts/
<project>/.agents/prompts/
```

这使 `.agents` 成为正常 Baldric session 环境的一部分，而不是可选的扩展机制。

## 优先级

资源目录按优先级递增加载：

1. 用户 Baldric 资源
2. 用户 `.agents` 资源
3. 项目 Baldric 资源
4. 项目 `.agents` 资源

两个目录定义同名 skill 或 prompt template 时，靠后/更高优先级的资源获胜。项目资源因此可以覆盖用户默认。

同一目录内的重名仍然非法并抛 `ResourceError`。

直接位于 `.agents` 目录内的 `AGENTS.md` 不当作 skill。项目指令发现留给后续的 context 发现阶段。

## CodingSession 集成

`CodingSession.load()` 现在用 session cwd 构建默认资源路径：

```python
BaldricResourcePaths(cwd=config.cwd)
```

这意味着正常 coding session 自动看到用户与项目两侧的 `.agents` 资源。

print mode 在为 system prompt 组装加载 skill 时也传 cwd 感知的资源路径。

## 测试

本阶段覆盖于：

```text
tests/test_paths.py
tests/test_resources.py
tests/test_skills.py
tests/test_prompt_templates.py
tests/test_cli.py
tests/test_coding_session.py
```

测试验证：

- 规范 Baldric 路径构建
- 用户 home 的项目 session 路径
- `.agents` skill 发现
- `.agents` prompt 发现
- 项目资源覆盖用户资源
- `AGENTS.md` 不被当作 skill 加载
- 隔离的资源路径保证测试确定性

## 下一阶段

下一阶段应在这稳定的用户 home session 位置之上加真正的 session 管理器与 resume 流程。
