---
title: "Phase 6：非交互 print-mode CLI"
---

Phase 6 把 Baldric 的 provider 层、agent harness 与内置编码工具接成一个可用的非交互 CLI。后续阶段把 print mode 移到
`CodingSession` 包装之上，与 TUI 共享同一编码 agent 环境。

CLI 入口位于：

```text
src/baldric_coding/cli.py
```

## 加了什么

`baldric` 命令可以用 `-p`/`--prompt` 在 print mode 跑单条 prompt：

```bash
baldric -p "write tests for main.py"
baldric --prompt "explain this repo"
baldric --model gpt-5.5 -p "summarize README.md"
```

不带 `-p`/`--prompt` 时，Baldric 启动交互式 TUI。位置 prompt 被当作
TUI 的初始 prompt：

```bash
baldric
baldric "explain this repo"
```

最初的 Phase 6 命令：

1. 从环境加载 OpenAI 兼容 provider 设置
2. 创建 Baldric 的内置编码工具
3. 构建最小默认 system prompt
4. 创建 `AgentHarness`
5. 把 assistant 文本流式输出到 stdout
6. 把工具执行摘要打印到 stderr

## provider 配置

print mode 使用 Baldric 已配置的 provider 设置。

没有保存过 provider 登录时，默认 OpenAI 兼容 provider 期望：

```bash
export OPENAI_API_KEY="..."
```

可选环境：

```bash
export OPENAI_BASE_URL="https://api.openai.com/v1"
```

默认模型目前是：

```text
gpt-5.5
```

用 `--model` 选择配置端点支持的另一个模型。

## 工作目录

工具默认以当前工作目录为根。

用 `--cwd` 让工具在别处运行：

```bash
baldric --cwd /path/to/project -p "inspect the tests"
```

## 当前行为

print mode 现在组合更高层的 `CodingSession` 环境。一次性运行
仍保持非交互且脚本友好，但现在共享：

- 完整的 Baldric system prompt 组装
- 发现的项目指令
- 已加载 skill 与 prompt template
- 内置编码工具
- `~/.baldric/sessions/` 下的 append-only session 持久化
- 与 TUI 相同的 provider/model 解析
- 配置的 provider 超时与重试设置
- Rich 支撑的工具活动 transcript 渲染

这让面向用户的命令保持简单，同时减少 print mode 与交互模式之间的漂移。

## 历史上的最小 system prompt

Phase 6 最初构建的小 prompt 包含：

- Baldric 的身份
- 可用工具清单
- 每个工具的 `prompt_snippet`
- 每个工具的 `prompt_guidelines`

对第一个 CLI 片这够用了。当前实现改用共享的 system prompt 构建器。

## 边界

CLI 住在 `baldric_coding`。它依赖 provider 设置、
`CodingSession` 与渲染器，但可复用的 `baldric_agent` 包仍无 CLI、Rich、Textual、配置文件或 session 存储依赖。

## 测试

本阶段覆盖于 `tests/test_cli.py`，包括：

- `baldric --version`
- 未提供 print-mode prompt 时默认启动 TUI
- 位置 prompt 作为 TUI 初始 prompt 启动
- 共享 system prompt 内容
- fake provider 的 print-mode 流式
- print-mode session 持久化
- print-mode skill 展开

## 下一阶段

路线图下一阶段是 append-only session 树持久化。
