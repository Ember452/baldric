---
title: 配置与文件
description: Baldric 在哪里存放状态，以及各配置文件的格式。
---

Baldric 把持久状态放在你的用户目录（`~/.baldric/`），并从工作目录读取项目级资源。本页是这些位置与文件格式的参考。

## Baldric home

Baldric 默认把用户级配置与状态放在 `~/.baldric/`。设置 `BALDRIC_HOME` 可以让一次调用或一个 shell profile 使用不同的 home：

```bash
BALDRIC_HOME="$HOME/.baldric-personal" baldric
```

非空覆盖值必须在可选的 `~` 展开后是绝对路径。未设置或空值保持 `~/.baldric` 默认。Baldric 不对值内部做变量插值，所以让 shell 替你展开 `$HOME`（如示例）。符号链接路径保持原样而不解析。

本文档里显示为 `~/.baldric/...` 的每个 Baldric 用户路径都跟随 `BALDRIC_HOME`，包括凭据、session、provider 偏好、settings、信任决策、extension、日志、本地 backend 状态与模型/更新缓存。该覆盖不迁移 `~/.agents`、项目级 `.baldric`/`.agents` 资源、显式 extension 路径，也不迁移直接通过环境变量提供的凭据。它是应用 profile 边界，不是安全沙箱。提供显式 `BaldricPaths` 的嵌入应用继续使用那些路径，无视环境变量。

对包含 OAuth 凭据的 profile，先以私有权限建目录再登录：

```bash
# POSIX shells
install -d -m 700 "$HOME/.baldric-personal" "$HOME/.baldric-work"
```

Windows 上先建目录；如果其他本地用户可能读到你的 profile，使用平台的访问控制工具。PowerShell 可以在启动 `baldric` 前用 `$env:BALDRIC_HOME = "$HOME\.baldric-personal"` 为当前进程选择 home。

```text
<baldric-home>/              # 未设 BALDRIC_HOME 时即 ~/.baldric
├── catalog.toml        # 可选的 provider/model 目录覆盖
├── providers.json      # provider/model 偏好
├── models-store.json   # 刷新的 models.dev 目录缓存
├── codex-models-store.json # 账户级 Codex 模型快照
├── credentials.json    # 已存 API key / OAuth token（0600、原子写入）
├── state/extensions/    # 内置集成状态，包括 llama.cpp
├── settings.json       # 一般设置（trust 默认、shell 前缀）
├── trust.json          # 带版本的项目输入信任决策
├── tui.json            # TUI 主题、键位与布局
├── sessions/           # 已保存 session，按项目分目录
├── skills/             # 用户级 skill
├── prompts/            # 用户级 prompt template
├── themes/             # 用户级 TUI 主题
├── SYSTEM.md           # 可选的 system prompt 替换基底
├── APPEND_SYSTEM.md    # 可选的追加 system prompt 指令
├── AGENTS.md           # 全局项目指令
└── logs/               # 诊断
```

Baldric 还读取用户级 `.agents` 资源：`~/.agents/skills/`、`~/.agents/prompts/`、`~/.agents/AGENTS.md`。

`settings.json` 可以包含 `"defaultProjectTrust": "ask" | "always" | "never"`。它只属于用户全局；项目不能自选信任策略。默认 `ask`。交互式 `ask` 打开信任弹窗；无头 `ask` 安全拒绝。`trust.json` 由 Baldric 原子化管理；不要添加相对路径或未知字段。见[项目信任](/how-to/project-trust/)。

启动更新检查把最近一次 PyPI 结果缓存在 `~/.baldric/cache/update-check.json`，每天最多刷新一次。失败的检查（例如离线）一小时后重试。设 `BALDRIC_NO_UPDATE_CHECK=1` 禁用；设置了 `CI` 时 Baldric 也会跳过。

`models-store.json` 缓存一份经 ETag 再验证的、比内置快照新的 models.dev 目录。`/model` 每4小时最多在后台刷新一次；`baldric update --models` 强制再验证。设 `BALDRIC_OFFLINE=1` 禁用目录网络访问。用户 `catalog.toml` 覆盖仍在缓存之后生效。

`codex-models-store.json` 只包含解析后的模型元数据与活动 Codex 账户 ID。Baldric 启动时加载它，并在 `/model` 或 `/scoped-models` 打开时刷新；来自不同账户的快照会被忽略。它绝不包含 OAuth token。

## system prompt 文件

Baldric 可以用 Baldric 原生的 Markdown 文件替换或扩展生成的 system prompt：

```text
~/.baldric/SYSTEM.md                 # 用户替换
~/.baldric/APPEND_SYSTEM.md          # 用户追加
<project>/.baldric/SYSTEM.md         # 项目替换
<project>/.baldric/APPEND_SYSTEM.md  # 项目追加
```

替换输入的优先级：显式 CLI 输入，然后项目 `SYSTEM.md`，然后用户 `SYSTEM.md`。追加输入是叠加而不是互相遮蔽：Baldric 依次加入用户 `APPEND_SYSTEM.md`、项目 `APPEND_SYSTEM.md`，再按 CLI 顺序加入每个显式 `--append-system-prompt` 值。替换内容仍会收到全部追加文本、项目指令、合格 skill、当前日期与工作目录。空文件也是有效贡献。

添加、修改或删除文件后运行 `/reload`。Baldric 为下一次模型请求重建 prompt，不加入 session 历史。`/session` 的资源诊断会标出选中的追加文件，以及选中、被遮蔽或被 CLI 覆盖的替换文件。选中的文件若无法检视或无法按 UTF-8 解码，会终止启动或 reload，而不是静默回退。

system prompt 文件是 Baldric 专属的，不从 `.agents` 发现。项目文件只在目标 cwd 受信任后加载。项目输入被拒绝时，用户文件与显式 CLI 值仍然可用。信任是输入加载守卫，不是沙箱；请检查受信任的 prompt 文件，因为它们能替换或扩展模型的最高优先级指令。

## 网络代理

Baldric 用 `httpx` 发起 provider 请求、OAuth token 刷新与启动更新检查，因此遵循标准代理环境变量，如 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 与 `NO_PROXY`。

基础安装即支持 SOCKS 代理。尽量使用显式 scheme：

```bash
export ALL_PROXY=socks5://127.0.0.1:1080
# 或者，当需要代理侧 DNS 解析时：
export ALL_PROXY=socks5h://127.0.0.1:1080
```

Baldric 也接受某些系统与工具设置的通用 `socks://` 形式。在创建自己的 HTTP 客户端之前，Baldric 会把 `socks://...` 归一化为 `socks5://...`，因为 `httpx` 不能直接识别通用 scheme。

这对身处公司代理、VPN、本地隧道或隐私/网络路由环境中的用户很重要：没有 SOCKS 支持与归一化，Baldric 可能在发起模型 API 请求之前就失败，报形如 `Unknown scheme for proxy URL URL('socks://...')` 的错误。

## Providers

Baldric 把 provider 元数据与运行时偏好分开：

- `src/baldric/runtime/data/catalog.toml` 内置 provider/model 目录。
- `~/.baldric/catalog.toml` 可选地添加个人 provider 或覆盖内置项。
- `~/.baldric/providers.json` 存放运行时偏好，如默认 provider、默认 model、scoped models、headers 与超时/重试设置。

内置 llama.cpp backend 只把归一化端点与安全的服务器报告模型快照存放在 `~/.baldric/state/extensions/llama.cpp.json`。可选凭据仍在 `credentials.json` 或 `LLAMA_API_KEY`；动态 llama.cpp provider 定义不写入 `catalog.toml` 或 `providers.json`。`providers.json` 里的 scoped llama.cpp 条目只包含稳定的 `llama.cpp` provider ID 与确切 model ID；过期条目不会制造可用性或路由工作。Hugging Face GGUF 搜索时，Baldric 读取 `HF_TOKEN` 或标准 Hugging Face token 文件，但绝不保存或把 token 转发给 llama.cpp 服务器。独立的服务器需要自己的 `HF_TOKEN` 才能下载受限模型。见[本地推理指南](/how-to/local-inference/)。

Baldric 有意只从用户级 `~/.baldric/catalog.toml` 读取目录覆盖。不存在项目级 `.baldric/catalog.toml`，克隆一个仓库不可能悄悄把 provider 的 `base_url` 或凭据重定向到意外服务。

### provider 目录覆盖

把可复用的自定义 provider 定义加进 `~/.baldric/catalog.toml`：

```toml
schema_version = 1

[[providers]]
name = "local-gateway"
display_name = "Local Gateway"
kind = "openai-compatible"
base_url = "http://localhost:11434/v1"
api_key_env = "LOCAL_GATEWAY_API_KEY"
credential_name = "local-gateway"
models = ["qwen-coder"]
default_model = "qwen-coder"
docs_url = "https://example.test/local-gateway"

[providers.context_windows]
qwen-coder = 64000
```

目录条目支持的 `kind` 值为 `openai-compatible`、`anthropic` 与 `openai-codex`。对大多数自定义服务，从 `openai-compatible` 开始。

与内置 provider 同 `name` 的用户目录覆盖可以是部分的。标量字段替换内置值，`models` 先并用户模型再合并，`context_windows` 合并。provider 级 `compat` 逐键合并。模型元数据按模型合并；其 `headers`、`compat` 与 `thinking_level_map` 映射合并，其余元数据字段——包括完整的 `cost_tiers` 数组——整体替换内置值。模型的 `compat` 胜过 provider 的，所以内置的模型级值覆盖 provider 级覆盖——想改它就在模型层覆盖。

`removed_models` 是一个加法的 provider 级墓碑列表。Baldric 最后应用它，在合并后移除匹配的模型列表、元数据、context window、thinking 与默认引用。内置墓碑因此防止过期的用户覆盖恢复 Baldric 曾因配错 provider 而宣传过的模型。它们不影响同一 model ID 在其他 provider 上的存在。

### OpenAI prompt-cache 兼容键

Baldric 只对 `api.openai.com` 与专用 Codex OAuth provider 自动启用 OpenAI 缓存亲和。OpenAI 兼容网关可以按 provider 或模型显式开启：

| 键 | 效果 |
| --- | --- |
| `supportsPromptCacheKey` | 发送稳定的 session 派生 `prompt_cache_key` 请求体字段 |
| `sendSessionAffinityHeaders` | 按 `sessionAffinityFormat` 发送 headers |
| `sessionAffinityFormat` | `openai` 发送 `session_id`；`openrouter` 发送 `x-session-id` |

未知网关默认保持现有请求形状。只启用目标服务文档记载的字段。Codex 使用专属的 `session-id` header 映射，不读取这些 OpenAI 兼容设置。

### Anthropic prompt-cache 兼容键

使用 `anthropic-messages` API 的 provider 接受三个控制 prompt 缓存的 `compat` 布尔值。除 `cache_control` 外默认全部启用——对任何非 `api.anthropic.com` 的 base URL，`cache_control` 都被判定为不支持，因为多个 provider 通过网关说 Anthropic 协议。

| 键 | 为 `false` 时的效果 |
| --- | --- |
| `supportsCacheControl` | 完全没有缓存断点；请求与未缓存的逐字节一致 |
| `supportsLongCacheRetention` | 把 1 小时 TTL 钳到 5 分钟默认 |
| `supportsCacheControlOnTools` | 只丢弃 tool schema 的断点 |

按 provider 或模型设置。例如在 Claude 订阅上停止请求一小时缓存：

```toml
schema_version = 1
[[providers]]
name = "anthropic"
compat = { supportsLongCacheRetention = false }
```

thinking 字段（`thinking_levels`、`thinking_models`、`thinking_default`、`thinking_parameter`）在 `thinking_levels` 出现时作为一组整体替换。

`catalog.toml` 不保存运行时请求选项，例如自定义 HTTP headers、超时或重试设置。那些放在 `~/.baldric/providers.json` 对应的 provider 条目里。

非法目录文件会响亮地失败。Baldric 拒绝未知键、空的必填字符串、空模型名、不支持的 provider kind、不在 `models` 列表里的默认模型、指向未知模型的 `thinking_models` 或 `context_windows` 条目，以及非正数或非整数的 context-window 值。

模型元数据可以保留向后兼容的扁平 `cost`，并可选提供按输入大小计价的有序 `cost_tiers`：

```toml
[providers.model_metadata."long-context-model"]
cost = { input = 0.3, output = 1.2, cacheRead = 0.06, cacheWrite = 0 }
cost_tiers = [
  { max_input_tokens = 512000, input = 0.3, output = 1.2, cacheRead = 0.06, cacheWrite = 0 },
  { input = 0.6, output = 2.4, cacheRead = 0.12, cacheWrite = 0 },
]
```

上限含端点、必须严格递增，最后一个 tier 必须省略 `max_input_tokens`，使每个合法输入大小都有费率。理解 tier 的调用者应选择第一个上限覆盖输入 token 数的 tier；老调用者继续把 `cost` 当基础费率。

所有费率按百万 token 计。`cacheWrite` 是 5 分钟缓存写入费率；条目可以加可选的 `cacheWrite1h` 费率，用于 Anthropic 的 1 小时 TTL 缓存写入（计费更高）。`cacheWrite1h` 缺失时，1 小时写入回退到 `cacheWrite` 费率。

### provider 偏好

provider 偏好存放在 `~/.baldric/providers.json`：

```json
{
  "schema_version": 2,
  "default_provider": "local-gateway",
  "provider_preferences": {
    "local-gateway": {
      "default_model": "qwen-coder",
      "headers": { "X-Provider-Header": "value" },
      "thinking_defaults": { "qwen-coder": "low" },
      "timeout_seconds": 120,
      "max_retries": 2,
      "max_retry_delay_seconds": 0.5
    }
  },
  "scoped_models": [
    { "provider": "local-gateway", "model": "qwen-coder" }
  ]
}
```

- `provider_preferences` 的键必须指向有效目录（`src/baldric/runtime/data/catalog.toml` 加 `~/.baldric/catalog.toml`）里的 provider。
- `headers` 可选（字符串→字符串）。例如 Hugging Face 组织计费可以在 `huggingface` 的 provider 偏好上配置 `"headers": { "X-HF-Bill-To": "my-org" }`。`thinking_defaults` 为新 session 记住每个模型偏好的 thinking 级别；恢复的 session 仍跟随其 session 历史。内置 `huggingface` 偏好还接受 `"inference_providers": { "zai-org/GLM-5.2": "deepinfra" }`。每个键必须是已配置的模型，每个值必须是 Hugging Face 为该模型宣传的显式 provider 后缀——不是 `fastest`、`cheapest` 或 `preferred` 这类路由策略。Baldric 把选中的后缀作为固定路由快照进新 session 元数据，恢复时保留，且只在 wire 上发送带后缀的模型；普通模型身份与目录元数据不带后缀。没有偏好时，Baldric 以自动模式启动，并把第一次成功响应报告的 `x-inference-provider` 记录为粘性但可恢复的路由。可重试的输出前 HTTP 失败耗尽 provider 级重试后，Baldric 清除该自动 pin，改经 Hugging Face 自动路由重试被中断的一轮，并保存成功的替换结果。显式配置的路由永不 failover。`/session` 同时报告模式与当前路由；修改活动 session 路由可通过外部 [`baldric-extension`](https://github.com/Ember452/baldric-extension) extension 完成：克隆后用 `baldric -e ./baldric-extension` 启动，再用 `/hf route`。`timeout_seconds` 默认 `60`（> 0）；`max_retries` 默认 `2`；`max_retry_delay_seconds` 默认 `1`（均 ≥ 0）。重试覆盖瞬时 HTTP 状态（`408`、`409`、`425`、`429`、`5xx`）、传输错误，以及发生在原本成功的 HTTP 200 响应之上的瞬时流内 SSE 错误。`Retry-After` header（先 `retry-after-ms`，再 `retry-after`，秒数或 HTTP 日期）被精确遵守，`x-should-retry: false` 把可重试状态变成终态。超过 `max_retry_delay_seconds` 的服务器延迟不会等待：请求以 `retry_after_too_long` 诊断失败，长限制不会阻塞 session。context 溢出与认证失败永不重试，每次 provider 失败都会记录稳定代码（如 `rate_limit`、`context_overflow`、`auth`）。Anthropic 重试 `api_error`、`overloaded_error` 与 `rate_limit_error`；OpenAI Codex 重试 `server_is_overloaded` 等瞬时事件。流内错误在已有部分内容后仍为终态，防止重复输出或工具调用。包含 Hugging Face 路由但早于路由模式元数据的旧 session 记录按固定处理，防止升级覆盖可能是显式的用户选择。
- API key 与 OAuth 凭据**不**存这里——它们在 `~/.baldric/credentials.json`（私有但未加密）。OAuth 对象可以包含 GitHub Enterprise 域等 provider 元数据，并自动刷新。解析顺序：已存凭据，然后 `api_key_env` 指名的环境变量。
- 选中的模型必须在该 provider 的 `models` 列表里。在用作默认值、CLI/TUI 选择或 scoped model 之前，先把自定义或本地模型名加进 `models`。
- `scoped_models` 是 **Ctrl+P** / **Shift+Ctrl+P** 前进/后退快速轮换的收藏。
- `providers.json` 使用 `schema_version: 2`，只存偏好。provider 能力——模型列表、context window、transport、元数据、thinking 支持——永远来自当前有效目录。
- 含完整 `providers` 条目的旧 `providers.json` 在首次加载时自动迁移。Baldric 把原文件保留为 `providers.json.bak`，把自定义 provider 定义移到 `~/.baldric/catalog.toml`，并在保留安全偏好的同时从当前目录重写内置 provider。这防止旧的模型或 thinking 元数据遮蔽 Baldric 升级带来的能力。
- 为了跨版本兼容，Baldric 忽略无法识别的偏好字段；但会拒绝不支持的 `schema_version`，而不是冒以错误格式破坏性重写的风险。
- 自定义模型在 `catalog.toml` 里用 `thinking_levels`、`thinking_default`、`thinking_models` 与 `thinking_parameter`（`"reasoning_effort"`、`"reasoning.effort"` 或 `"anthropic.thinking"`）声明 thinking 支持。

`/login`、`/model` 或 scoped-model 变更后的写入会先重载文件、只应用被请求的变更、原子写入并保留 `.bak` 备份。

用法见 [Providers & models 指南](/how-to/providers-and-models/)。

## Shell 设置

Baldric 在**非交互** shell 里运行 shell 命令——包括终端输入命令（`! gst`、`!! ll`）和 agent 的 `bash` 工具。非交互 shell 不加载你 `~/.zshrc` 或 `~/.bashrc` 里的别名，Baldric 也刻意从不读那些文件（它们可能含有 token 和副作用）。

shell 按平台解析：POSIX 上是 `bash`（或没有 bash 时的 `sh`），Windows 上是 PowerShell——先 `pwsh` 再 Windows PowerShell——最终回退 `cmd.exe`。`shellCommandPrefix` 在解析出的 shell 里运行，请用匹配的语法书写。

在 `~/.baldric/settings.json` 设 `"shell"` 覆盖自动选择：`"auto"`（默认）、`"bash"`（Windows 上需要 Git Bash）、`"pwsh"` 或 `"cmd"`。显式 `"bash"` 而没装 bash 会失败并给出安装提示，而不是静默换一个 shell。

要让自己的别名可用，在 `~/.baldric/settings.json` 里用 `shellCommandPrefix` 加载一个小的 Baldric 专用别名文件：

```bash
# ~/.baldric/shell-aliases.bash
alias gst='git status'
alias ga='git add'
alias gc='git commit'
```

```json
{
  "shellCommandPrefix": "shopt -s expand_aliases\nsource ~/.baldric/shell-aliases.bash"
}
```

然后开新 session 试 `! gst`。注意：

- 命令经 bash 风格非交互执行，别名要保持 POSIX/bash 兼容（仅 zsh 的语法、函数或交互式启动逻辑可能无效）。
- 修改 `settings.json` 只影响**新** session；已在运行的 session 保持启动时的前缀。
- 也接受 snake_case 键 `shell_command_prefix`。
- 为了与更新版本的 Baldric 兼容，未识别字段被忽略；已识别字段保持严格校验。
- subagent 继承 session 的 `shell` 与 `shellCommandPrefix`，子代理用你选的同一个 shell 跑命令。

## TUI 设置

内置 frontend 从 `~/.baldric/tui.json` 读取可选设置：

```json
{
  "theme": "high-contrast",
  "sidebar_position": "right",
  "turn_notification": "desktop",
  "keybindings": {
    "cancel": "escape",
    "command_palette": "ctrl+k",
    "session_picker": "ctrl+r",
    "queue_follow_up": "alt+enter",
    "insert_newline": "shift+enter",
    "accept_completion": "tab",
    "completion_next": "down",
    "completion_previous": "up",
    "thinking_cycle": "shift+tab",
    "model_cycle": "ctrl+p",
    "model_cycle_reverse": "ctrl+shift+p",
    "toggle_thinking": "ctrl+t",
    "toggle_tool_results": "ctrl+o",
    "copy_message": "ctrl+c",
    "quit": "ctrl+d"
  }
}
```

内置主题：`baldric-dark`（默认）、`baldric-light`、`high-contrast`。自定义主题是 `~/.baldric/themes/` 或项目 `.baldric/themes/` 里的 JSON 文件——见 [Themes](/how-to/themes/)。用 `/theme` 设置。Textual 原生主题选择器映射到同一批 Baldric 主题并持久化同一个 `theme` 设置。找不到的已配置主题会回退 `baldric-dark` 并给启动提示，不覆盖设置。键位用 Textual 语法；省略的键保持默认。Baldric 忽略无法识别的设置与键位名，让更新版本写的 `tui.json` 不会阻止旧版本启动。已识别设置保持严格：Baldric 拒绝非法值、空键位与重复赋值。

- `sidebar_position`：`"right"`（默认）、`"left"` 或 `"off"`。控制 session 元数据侧栏的位置。`"off"` 完全隐藏侧栏；prompt 下方的紧凑 session 信息行仍然工作。运行中的 TUI 里，`/sidebar` 临时切换可见性而不写该设置；临时显示的 `"off"` 侧栏用默认右侧位置，重启后再次遵循已保存设置。
- `turn_notification`：`"desktop"`（默认）、`"bell"` 或 `"off"`。当 Baldric 的终端表面失焦且 agent 完全空闲时，`"desktop"` 对 Ghostty、iTerm2 与 MinTTY 用 OSC 9，对 Kitty 用 OSC 99 协议。未知终端不收到任何序列，而不是不兼容的序列。`"bell"` 显式发出标准终端铃声，让终端标记标签页或按其配置请求注意；取决于终端设置，BEL 可能发声。桌面通知也可以使用操作系统配置的通知音。Baldric 有焦点时不发通知。

完整列表见[键盘快捷键](/reference/keybindings/)。

## Sessions

```text
~/.baldric/sessions/<cleaned-path>-<short-hash>/
```

每个工作目录有自己的子目录；transcript 是保留消息与状态变更的 append-only JSONL。文件顺序中最后一条非 legacy-leaf entry 是活动 session 树尖；历史 `leaf` 记录仍可读但被忽略。每条 entry 的书签是带 `target_id` 与可选 `label` 的 append-only `label` 变更；每个目标以最近一次变更为准，`null`/空清除。session 显示名仍是 `session_info.title`。元数据按项目索引。见 [Sessions 指南](/how-to/sessions/)。

## Skill、prompt 与项目 context

资源发现顺序（后者覆盖前者）记录在 [Skills & prompt templates](/how-to/skills-and-prompts/) 与[项目指令](/how-to/project-instructions/)。简言之：用户级 `~/.baldric` 与 `~/.agents`，然后项目级 `.baldric` 与 `.agents`，`AGENTS.md` 从项目根一路发现到当前目录。

## Context

`/session` 报告粗估的 context 用量与构成。自动 compaction 在接近模型的 context window 减去保留额时触发；每次运行可用 `--auto-compact-threshold` 覆盖。细节见[管理 context](/how-to/context/)。
