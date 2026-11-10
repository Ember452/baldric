---
title: CLI 参考
description: Baldric 的全部命令行命令与旗标。
---

`baldric` 命令默认启动交互式 TUI；子命令与旗标覆盖其余一切。

```text
baldric [OPTIONS] [PROMPT] [COMMAND] [ARGS]
```

- 不带参数时，`baldric` 打开交互式 [TUI](/how-to/tui/)。
- 位置参数 `PROMPT` 打开 TUI 并把它作为第一轮提交。
- `/local` 在 TUI 中可用于已注册的本地 backend；print mode 会提示该设置仅限交互模式。
- `-p/--print`（或 `--mode`）把同一条位置 prompt 以 [print mode](/how-to/print-mode/) 运行而不是 TUI。
- 旗标放在 prompt 之前——Baldric 把最后一个可识别旗标之后的一切都当作 prompt 文本，包括看起来像旗标的 token。

在 TUI 与 text print-mode 启动时，若 PyPI 上有更新的 `baldric` 版本，Baldric 可能显示一条非阻塞提示。TUI 中，缓存的结果是第一条 transcript 项并以亮黄色显示；当日检查到期时，它在 TUI 打开后于后台运行，PyPI 应答后提示才追加。运行 `baldric update` 升级。用 `BALDRIC_NO_UPDATE_CHECK=1` 禁用检查；`baldric --version`、`baldric update`、`baldric sessions`、`baldric export` 这类工具命令不运行它。升级后，TUI 还会把一次性 release-notes 消息加进 transcript，介绍新功能与修复。

## 命令

| 命令 | 作用 |
| --- | --- |
| `baldric` | 打开交互式 TUI |
| `baldric "<prompt>"` | 打开 TUI 并附带初始 prompt |
| `baldric update` | 用拥有当前环境的安装器升级 Baldric。Windows 上 uv-tool 的更新会被移交并在 Baldric 退出后开始；按打印的日志路径查看最终结果。 |
| `baldric update --models` | 强制刷新 models.dev 目录并缓存到 `~/.baldric/models-store.json`，不升级 Baldric。 |
| `baldric install <source> [--force]` | 在 `~/.baldric/extensions/` 安装受信任的本地或 Git extension；`--force` 替换已存在的安装。 |
| `baldric sessions` | 列出已索引的 session（id、标题、model、cwd） |
| `baldric export <ref> [dest] [--format html\|jsonl]` | 按 session id 或 JSONL 路径导出（默认 HTML） |
| `baldric --export <ref> [dest]` | 与 `baldric export` 相同，作为顶级旗标 |
| `baldric providers` | 列出已配置的 provider 及各自的认证方式 |
| `baldric [setup options] setup` | 创建/更新一个 OpenAI 兼容 provider |

## 选项

| 旗标 | 说明 |
| --- | --- |
| `-p, --print` | 以非交互 print mode 运行位置 prompt |
| `-m, --model TEXT` | 向 provider 请求的模型 |
| `--provider TEXT` | 要使用的已配置 provider 名称 |
| `-t, --thinking LEVEL` | 本次运行的初始 [thinking 级别](/how-to/context/#thinking-mode)（`off`…`max`）；覆盖已记住的默认值而不持久化，模型不支持时报错 |
| `--cwd PATH` | 内置工具的工作目录 |
| `--mode [text\|json\|transcript\|rpc]` | 选择无头输出；`rpc` 启动 JSONL 子进程协议 |
| `--session TEXT` | 在 TUI 或 print mode 恢复一个 session id |
| `--new-session` | 开始新 session 而不是恢复默认 |
| `--session-id TEXT` | 为新建的 print-mode session 设定确切 id；已存在时报错 |
| `--system-prompt TEXT_OR_PATH` | 用字面文本或存在的 UTF-8 文件替换 Baldric 的默认 system prompt 基底 |
| `--append-system-prompt TEXT_OR_PATH` | 追加字面文本或存在的 UTF-8 文件（可重复） |
| `--auto-compact-threshold INT` | 超过这个粗估 token 数就自动 compact |
| `-e, --extension PATH` | 加载一个 [extension](/how-to/extensions/) 文件或目录（可重复） |
| `--no-extensions` | 禁用 extension 目录发现（显式 `-e` 路径仍加载） |
| `--project-extensions` | 同时加载受信任的 `<project>/.baldric/extensions`；项目信任与这个显式开关都必须满足 |
| `--show-full-output` | 以不截断的工具与 `!` 命令输出启动 TUI（替代预览）；运行时 **Ctrl+O** 切换同样的效果 |
| `-a, --approve` | 仅本次调用信任受保护的项目输入 |
| `-na, --no-approve` | 仅本次调用拒绝受保护的项目输入 |
| `-v, --version` | 打印版本并退出 |

`baldric install` 接受本地 Python 文件、本地包目录、Pi 风格的 `git:github.com/owner/repository[@ref]` 源，以及普通的 HTTP/SSH Git URL。包布局、依赖与安全细节见 [Extensions](/how-to/extensions/#安装-extension)。

`--approve` 与 `--no-approve` 互斥，且从不写信任库。交互范围、无头默认、受保护资源与非沙箱边界见[项目信任](/how-to/project-trust/)。

### system prompt 输入

`--system-prompt` 替换 Baldric 的默认基底 prompt。重复 `--append-system-prompt` 按命令行顺序追加区块；Baldric 用恰好一个空行分隔每个值。这些旗标像其他可识别选项一样放在位置 prompt 之前：

```bash
baldric --system-prompt "You are a focused reviewer." \
  --append-system-prompt ./team-rules.md \
  --append-system-prompt "Report risky changes first." \
  -p "review this repository"
```

对这两个选项，Baldric 在路径存在时按 UTF-8 文件读取；否则原样使用该值，所以不存在的路径就是字面 prompt 文本。已存在的目录、不可读文件与无效 UTF-8 文件会以指出选项与路径的错误终止启动。`~` 在检查文件时展开。

自定义基底仍会收到追加文本、发现的项目指令、启用 `read` 工具时合格的 skill、当前日期与工作目录。这些选项对 print mode 与交互启动都生效；与 `--session` 同用时它们配置被恢复 session 的下一次 provider 请求。它们是启动控制项，不存入 session 历史，之后再恢复时需要重新传入。

Baldric 也在项目或用户 `.baldric` 目录下发现 `SYSTEM.md` 与 `APPEND_SYSTEM.md`。CLI 替换值优先于受信任的项目与用户 `SYSTEM.md` 文件。追加内容是累计的：用户 `APPEND_SYSTEM.md`，然后受信任项目 `APPEND_SYSTEM.md`，然后按 CLI 顺序的重复值。改完文件用 `/reload`。这些是 Baldric 专属配置文件，不是 `.agents` 资源。路径、优先级、诊断与项目资源安全警告见 [Configuration & files](/reference/configuration/#system-prompt-文件)。

### print mode 恢复

`--print` 与 `--session` 同用可向既有对话追加一次非交互 follow-up。Baldric 加载该 session 已保存的工作目录、provider、model 与对话历史：

```bash
baldric --print --session <session-id> "Follow-up message"
```

显式的 `--provider`、`--model` 与 system-prompt 选项为本次调用覆盖已保存的启动选择。在 TUI 配置好本地 backend 后，在 print mode 里显式传入它的 provider 与确切发现的模型：

```bash
baldric --provider llama.cpp --model <model-id> --print "summarize this project"
```

Baldric 不会在无头模式下运行 `/local` 设置或隐式选择模型。按端点键控的安全快照可以在 llama.cpp 暂时宕机时支撑显式启动；首次的显式模型仍需发现。`--session` 不能与 `--new-session` 或 `--session-id` 组合。未知 session id 以错误退出。

`--resume`、`--prompt`、`-o/--output` 与 `-x` 已移除；现在各自以错误退出并指名替代项（分别是 `--session`、`--print`、`--mode` 与 `-e/--extension`）。

### provider setup 选项

Baldric 的 setup 模式注册一个 OpenAI 兼容 provider。这些旗标放在最后的 `setup` 参数之前：

| 旗标 | 默认 | 说明 |
| --- | --- | --- |
| `--provider TEXT` | `openai` | 要创建/更新的 provider 名称 |
| `--model TEXT` | 默认模型 | 该 provider 的默认模型 |
| `--base-url TEXT` | OpenAI URL | OpenAI 兼容 base URL |
| `--api-key-env TEXT` | `OPENAI_API_KEY` | 存放 API key 的环境变量名 |
| `--timeout-seconds FLOAT` | `60.0` | HTTP 超时 |
| `--max-retries INT` | `2` | 瞬时失败的重试次数 |
| `--max-retry-delay-seconds FLOAT` | `1.0` | 重试间隔 |
| `--set-default / --no-set-default` | set-default | 设为默认 provider |

示例：

```bash
baldric --provider local \
  --base-url http://localhost:11434/v1 \
  --api-key-env LOCAL_API_KEY \
  --model qwen \
  setup
```

另见：[RPC 协议](/reference/rpc/)、[slash 命令](/reference/slash-commands/)（会话内）、[键盘快捷键](/reference/keybindings/)。
