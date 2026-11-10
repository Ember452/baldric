---
title: 快速上手
description: 安装 Baldric、连接模型，跑起你的第一个编码 session。
type: doc
---

本页带你从零到第一个 Baldric session。应该花几分钟。

## 1. 安装 Baldric

Baldric 是一个需要 Python 3.12 或更新版本的 Python 工具。它的安装器用
[`uv`](https://docs.astral.sh/uv/) 创建隔离环境，并在 `uv` 不存在时先安装它。

macOS 或 Linux 上运行：

```bash
curl -LsSf https://ember452.github.io/baldric/install.sh | sh
```

Windows 上在 PowerShell 运行：

```powershell
irm https://ember452.github.io/baldric/install.ps1 | iex
```

安装器会在安装 `uv` 前先行告知，绝不使用 `sudo`，验证安装好的 `baldric` 命令，并告诉你是否需要重启 shell 使 `PATH` 更新生效。想先审查代码再执行，可以先下载并检查
[`install.sh`](/install.sh) 或 [`install.ps1`](/install.ps1)。

确认装好了：

```bash
baldric --version
```

> [!TIP] 已经有包管理器？
> 直接用 `uv tool install baldric`、`pipx install baldric` 或
> `python -m pip install baldric` 安装。

### 升级 Baldric

正常安装时，让 Baldric 检测并复用拥有其环境的那个安装器：

```bash
baldric update
```

Baldric 在环境凭据存在时复用 uv 或 pipx。对 uv tools，它显式安装最新稳定版，避免旧版本 pin 卡住更新。对普通 Python 安装，标准包元数据告诉 Baldric 该用 uv 还是 pip，并以正在运行 Baldric 的那个确切 Python 环境为目标。遇到 editable、直连 URL、Conda/Pixi 或无法识别的安装时，它会停下来而不是切换安装器。

如果你用 `uv tool install --editable .` 安装了本地 checkout，拉取变更后再跑一次安装命令：

```bash
uv tool install --editable --force .
```

editable 安装让源码变更立即生效，但已安装的包元数据（包括版本）、依赖与 entry point 只在 uv 重装时刷新。

## 2. 连接一个模型

Baldric 需要一个 AI 模型来对话。**provider** 是托管模型的服务（OpenAI、Anthropic……）。启动 Baldric 并用 `/login` 连接一个：

```bash
baldric
```

然后在 Baldric 里运行：

```text
/login              # 选择一个 provider
/login openai       # 保存一个 OpenAI API key
/login openai-codex # 认证 Codex/ChatGPT 订阅
```

Baldric 内置 OpenAI、Anthropic、OpenAI Codex、OpenRouter 与 Hugging Face 条目。切换模型或添加自定义/本地 OpenAI 兼容端点见 [Providers & models](/how-to/providers-and-models/)。

## 3. 开始一个 session

在你想工作的项目目录里运行 Baldric：

```bash
cd my-project
baldric
```

这会打开交互式终端 UI。输入一个请求并按 **Enter**：

```text
explain what this project does
```

Baldric 流式输出回复，并在需要时读文件、跑命令来回答。试一个会改代码的请求：

```text
add a docstring to every function in src/utils.py
```

你会看到每个工具调用（read、edit、bash）实时发生。

> [!TIP] 有用的第一批按键
> **Enter** 提交 · **Esc** 取消当前运行 · **Ctrl+K** 打开命令面板 · **Ctrl+D** 退出。完整列表见[键盘快捷键](/reference/keybindings/)。

## 4. 之后回来

Baldric 保存每个 session。列出它们：

```bash
baldric sessions
```

恢复本目录最近的一个，或从列表里挑选：

```bash
baldric --session <session-id>
```

……或在 TUI 内用 `/resume` 打开 picker。恢复、分支与导出见 [Sessions](/how-to/sessions/)。

## 单次模式

不需要界面？运行单条 prompt 并把结果写到 stdout——适合脚本和管道：

```bash
baldric -p "summarize the changes in the last commit"
```

更多见 [Print mode & scripting](/how-to/print-mode/)。

## 接下来去哪

- **[核心概念](/explanation/concepts/)**——弄明白实际发生了什么。
- **[交互式会话](/how-to/tui/)**——把 TUI 用熟。
- **[Providers & models](/how-to/providers-and-models/)**——切换模型、添加 provider、使用本地模型。
