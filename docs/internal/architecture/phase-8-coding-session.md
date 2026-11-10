---
title: "Phase 8：coding session 包装"
---

Phase 8 加了 Baldric 第一个 coding-session 环境包装。

实现位于：

```text
src/baldric_coding/session.py
```

## 加了什么

Baldric 现在有一个 `CodingSession`，组合：

- `AgentHarness`
- append-only session 存储
- 还原的 transcript 消息
- 内置编码工具
- 模型/session 元数据
- 一个最小 slash 命令接缝

这是第一层开始像 Pi 的 `AgentSession` 的层，但仍刻意保持小。

## 为什么住在 `baldric_coding`

`baldric_agent` 拥有可复用原语：

- 消息
- 事件
- 作为抽象的工具
- 纯循环
- `AgentHarness`
- 底层 session entry/存储/回放

`baldric_coding` 拥有这些原语周围的编码 agent 环境：

- 本地 cwd
- 内置编码工具
- 存储选择
- slash 命令
- 日后的 prompt/资源加载
- 日后的 print 与交互 frontend

所以 `CodingSession` 属于 `baldric_coding`。

## 加载 session

session 从 `SessionStorage` 实现加载：

```python
from pathlib import Path
from baldric_coding import CodingSession, CodingSessionConfig
from baldric_agent.session import JsonlSessionStorage

session = await CodingSession.load(
    CodingSessionConfig(
        provider=provider,
        model="gpt-4.1-mini",
        system=system_prompt,
        storage=JsonlSessionStorage("session.jsonl"),
        cwd=Path.cwd(),
    )
)
```

加载执行这些步骤：

1. 读全部 session entry
2. 为空 session 初始化元数据
3. 把 entry 回放进 `SessionState`
4. 用还原的消息创建 `AgentHarness`
5. 注册内置编码工具，除非提供了自定义工具

对新的空 session，Baldric 追加：

- `SessionInfoEntry`
- `ModelChangeEntry`

## prompt 与 continue

`CodingSession.prompt()` 经 harness 运行新的用户 prompt：

```python
async for event in session.prompt("Read README.md"):
    ...
```

运行结束后，所有新的 harness 消息作为 `MessageEntry` 记录追加。每条 entry 以成为文件中最后一条非 legacy 叶线的方式成为活动尖；Baldric 不再写单独的指针。

`CodingSession.continue_()` 从还原状态恢复，不先追加新的用户消息。

## 持久化模型

Phase 8 在运行完成后持久化消息。这让实现简单，并避免 `AgentHarness` 改动内存 transcript 期间的双重保存。

后续阶段可以让持久化更增量，如果 Baldric 需要在流式响应期间的崩溃恢复。

## 最小命令

`CodingSession.handle_command()` 目前只支持：

- `/help`
- `/exit`

未知 slash 命令以解释性消息处理。普通 prompt 返回 `handled=False`。

这是未来命令注册表的小接缝。`/model`、`/sessions`、`/fork`、`/compact` 之类的完整命令有意推迟。

## 非目标

Phase 8 不加：

- 自动 print-mode session 持久化
- session 目录发现
- 模型切换命令
- 直接 bash 命令前缀
- 项目指令加载
- skill 或 prompt template
- Rich 渲染
- Textual UI
- compaction

它们属于后续阶段。

## 测试

本阶段覆盖于：

```text
tests/test_coding_session.py
```

测试验证：

- 空 session 元数据初始化
- prompt 持久化
- transcript 还原
- 继续运行持久化
- 工具结果持久化
- 最小命令处理

## 下一阶段

路线图下一阶段是 skill、prompt template 与 system prompt 组装地基。这里创建的 coding-session 包装给那些后续系统一个稳定的插入点。
