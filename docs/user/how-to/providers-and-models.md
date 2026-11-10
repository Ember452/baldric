---
title: Providers 与模型
description: 连接 OAuth 订阅、API-key provider 或本地模型——并随时切换模型。
---

**provider** 是托管 AI 模型的服务；**model** 是你对话的具体那个。Baldric 内置若干 provider，并允许你添加自己的 OpenAI 兼容端点（包括本地模型）。

## 最快的设置：`/login`

启动 Baldric 并用 `/login` 连接 provider。provider 选择器带搜索框，对较长的 API-key provider 列表尤其有用：

```bash
baldric
```

```text
/login              # 选择一种登录方式
/login openai       # 保存一个 OpenAI API key
/login openai-codex # 经 OAuth 认证 Codex/ChatGPT 订阅
/login anthropic-subscription # 经 OAuth 认证 Claude Pro/Max
/login anthropic-api # 保存一个 Anthropic API key
/login github-copilot # 用设备码认证 GitHub Copilot
/login opencode-go  # 保存一个 OpenCode Go API key
/login nvidia       # 保存一个 NVIDIA NIM API key
/login custom       # 添加一个 OpenAI 兼容自定义 provider
```

内置 provider 包括 **OpenAI**、**Anthropic**、**OpenAI Codex**（订阅）、**GitHub Copilot**、**OpenCode Go**、**OpenCode Zen**、**Moonshot AI (Kimi)**、**Kimi Code**（订阅）、**OpenRouter**、**Hugging Face** 与 **NVIDIA NIM**。

### OAuth 订阅

在 `/login` 里选择 **Subscription / OAuth** 可用：

| Baldric provider | 登录流程 | 前提 |
| --- | --- | --- |
| `openai-codex` | 浏览器回调，可回退粘贴授权码 | 受支持的 ChatGPT/Codex 订阅 |
| `anthropic` | 浏览器回调（PKCE），可回退粘贴授权码 | Claude Pro/Max 且 Anthropic 额外用量可用 |
| `github-copilot` | GitHub 设备码 | 活跃的 Copilot 套餐；组织策略须允许所选模型 |

GitHub Copilot 会询问 GitHub Enterprise Server URL/域名。留空即为 `github.com`。设备登录在 SSH/无头 session 里同样可用：在任意设备上打开显示的验证 URL 并输入展示的代码。

Anthropic 使用不同的直登别名让认证方式无歧义：`/login anthropic-subscription` 启动 OAuth，`/login anthropic-api` 保存 API key。顶层 `/login` 选择器仍同时把 Anthropic 列在 **Subscription / OAuth** 与 **API key** 下。OAuth 订阅请求使用 Anthropic 要求的 Claude Code 身份，可能按额外用量计费而非消耗普通 Claude 套餐额度。使用前请核对 Anthropic 当前的账户条款。

OAuth token 自动刷新。`/logout` 移除 Baldric 的本地凭据，但不远程撤销授权；远程撤销请用 provider 的账户设置。

#### OpenAI prompt caching

对直连 OpenAI API 与 Codex OAuth session，Baldric 为每个模型请求发送稳定的 session 派生 prompt-cache key，包括 tool 调用之后的续请求。OpenAI 可以用该 key 让连续的 append-only 请求落在同一条缓存路径上，提高 system prompt、tool schema 与对话前缀的复用。恢复 Baldric session 复用其 key；开始或分支 session 创建新 key。

请求保持无状态：Baldric 保持 provider 存储禁用并重发完整 transcript。这个 key 提升缓存亲和，但前缀变化或 provider 缓存过期时无法保住命中。除非网关的目录兼容设置显式开启，OpenAI 兼容网关收不到这些字段。TUI 侧栏的最近请求缓存率显示最近一次请求是否命中。

#### Anthropic prompt caching

Baldric 在 Anthropic 请求上标记缓存断点，让 system prompt、tool schema 与对话历史跨轮复用而不是重复处理。Baldric 请求的保留时长取决于你的认证方式：

- **经 OAuth 的 Claude Pro/Max** 请求一小时缓存。订阅认证不按 token 计费，五分钟默认比一次构建、一轮测试或读 diff 的时间都短——否则缓存会在 session 中途过期。
- **Anthropic API key** 使用五分钟默认，因为一小时缓存写入单价更高，应当是刻意选择。

通过网关而非 Anthropic 本体说 Anthropic 协议的 provider——`minimax`、`minimax-cn`、`fireworks` 与 `vercel-ai-gateway`——不发送缓存断点，因为并非所有网关都接受。看侧栏的缓存命中率确认缓存生效；如何读它见[交互式会话](/how-to/tui/)。

Anthropic 把 `input_tokens` 报告为最后一个缓存断点之后的新鲜部分。Baldric 把它保留为新鲜输入，保留独立的 cache-read 与 cache-write 计数器，并把总输入报告为二者之和。这让用量与成本显示与 Anthropic 的响应契约对齐。

#### Codex 订阅 context 限制

OpenAI 公共 API 与 ChatGPT/Codex 订阅是两个独立的服务面。同一个 ID 的模型，经 Codex OAuth 广告的 context window 可能小于 API key 渠道。例如公共 GPT-5.6 Sol API 宣传 1.05M-token 窗口，而 Codex 经其认证模型目录宣传过明显更小的限制。

Baldric 在 session 启动时从 `~/.baldric/codex-models-store.json` 加载最后一次成功的账户级快照，前一 session 发现的模型无需打开 picker 即可用。`/model` 或 `/scoped-models` 打开时它在后台刷新认证目录。因为 OpenAI 按官方客户端版本过滤响应，Baldric 从 npm registry 解析当前稳定的 `@openai/codex` 版本，并把安全、非机密的版本号在 `~/.baldric/codex-version-store.json` 缓存四小时。查找失败使用过期的缓存版本或 Baldric 打包的回退。成功的刷新替换 Codex 模型 picker 清单，新启用与解除客户端门控的模型因此无需 Baldric 发版即可出现。账户不可用的模型不会从独立的公共 API 目录拷贝。Baldric 还会使用报告的 context window、compaction 阈值、输入模态与 reasoning effort（存在时）。

发现不可用或非法时，Baldric 保留最后匹配账户的快照，无快照时用签入的 Codex 模型列表；它不复用公共 API 清单或限制。`/session` 报告活动 context 值来自实时 provider 目录还是 Baldric 的配置回退。模型缓存只含解析后的账户/模型元数据（无 OAuth token），限定在已保存的 Codex 账户 ID，绝不写入 `catalog.toml`、`providers.json` 或 models.dev 缓存。

以仅实时 Codex 模型启动或恢复会先发现账户清单再校验选择。这要求发现成功；离线启动仍可用于静态模型。若后续刷新省略了活动模型，Baldric 保留其运行时元数据而不把它加回 picker。恢复会还原 transcript 已保存的模型选择。旧 session 恢复出过期选择时，恢复它并在 `/model` 里显式重选一次以记录修正。

实时限制可能因账户或 rollout 而异并独立变化。发现失败非致命：Baldric 在 `/session` 报告并继续用回退。直连 OpenAI API session 保留 API 模型页记载的 context 限制。具备视觉的 Codex 模型把这些运行时 context 限制与图片输入元数据分开保留，让 Baldric 读入的图片文件能到达模型。`gpt-5.6` 别名（路由到 GPT-5.6 Sol）只经直连 OpenAI API 提供；Codex 订阅用户应选显式的 `gpt-5.6-sol` 模型。Baldric 为 Codex provider 墓碑化这个仅 API 的别名，旧的用户目录覆盖与已存偏好升级后无法恢复它。

### OpenCode Go 与 Zen

OpenCode Go 与 OpenCode Zen 是 **API-key provider**，不是 OAuth provider。在 OpenCode 控制台登录、订阅 Go 或充值 Zen、复制 API key，然后运行：

```text
/login opencode-go  # 订阅限额；https://opencode.ai/zen/go/v1
/login opencode     # Zen 按量付费；https://opencode.ai/zen/v1
```

两者也读取 `OPENCODE_API_KEY`。Baldric 把它们已存凭据放在独立的 `opencode-go` 与 `opencode` 名下，允许同时持有不同的 key。可用模型与套餐限额随时间变化；当前清单见 [OpenCode Go](https://opencode.ai/docs/go) 与 [OpenCode Zen](https://opencode.ai/docs/zen) 页面。

### Z.AI

用 `/login zai` 登录或设 `ZAI_API_KEY`。Baldric 发送 Z.AI 专属的 thinking 对象而不是 OpenAI 的 `reasoning_effort` 字段：启用逻辑模式用 `{"thinking": {"type": "enabled"}}`，关闭用 `{"thinking": {"type": "disabled"}}`。这让已配置的 thinking 在端点不接受原始 effort 字段的 GLM 模型上保持启用。

Z.AI 只为 GLM-5.2 及更新版本记载 `reasoning_effort`，且按模型给出取值。Baldric 因此只在所选模型的兼容性元数据显式支持时发送该附加字段；不支持的 provider 与模型继续省略它。权威的 wire 契约见 [Z.AI deep-thinking
reference](https://docs.z.ai/guides/capabilities/thinking) 与 [chat-completion
schema](https://docs.z.ai/api-reference/llm/chat-completion)。

### Hugging Face Inference Providers

用 `/login huggingface` 登录或设 `HF_TOKEN`。Baldric 的 Hugging Face 模型列表在构建期由 [models.dev](https://models.dev) 生成，经 `https://router.huggingface.co/v1` 路由。它包含 DeepSeek、Gemma、GLM、GPT OSS、Kimi、Llama、MiniMax、MiMo、Qwen、Step 等家族的工具可用模型。用 `/model` 搜索生成的列表；可用性与背后的 inference provider 可能随时间与账户变化。

与 Pi 一样，Baldric 的发布快照包含模型名、限制、成本、模态、reasoning 支持与已验证的 effort 值。thinking 级别为 `off`、`minimal`、`low`、`medium`、`high`、`xhigh`、`max`；`max` 与 `xhigh` 不同。空的或仅开关的 reasoning 选项不替换 provider/手动行为。Hugging Face `zai-org/GLM-5.2` 目前使用一个窄的已验证修正集，只暴露 `off`、`high` 与 `max`，Baldric 因此绝不发送其不支持的 `medium` 值。打包快照保证启动可离线。打开 `/model` 会在后台刷新目录并缓存在 `~/.baldric/models-store.json`；运行 `baldric update --models` 强制再验证。新模型与能力变化因此无需升级 Baldric 即可到达。设 `BALDRIC_OFFLINE=1` 在无目录网络访问下使用缓存/内置数据。

对没有显式偏好的新 session，Hugging Face 起初自动路由模型。第一次成功响应后，Baldric 读取 Hugging Face 的 `x-inference-provider` 响应 header，把那个背后的 provider 保留为粘性自动路由。若该路由稍后在产出前以可重试的 HTTP 失败耗尽普通重试，Baldric 经无后缀的自动路由重试被中断的一轮，并把成功的替换设为新的粘性路由。要改用固定 provider，给 `~/.baldric/providers.json` 加每模型的 `inference_providers` 偏好：

```json
{
  "schema_version": 2,
  "default_provider": "huggingface",
  "provider_preferences": {
    "huggingface": {
      "default_model": "zai-org/GLM-5.2",
      "inference_providers": { "zai-org/GLM-5.2": "deepinfra" }
    }
  },
  "scoped_models": []
}
```

使用 Hugging Face 为该模型宣传的确切 provider 后缀。Baldric 在 wire 上发送 `zai-org/GLM-5.2:deepinfra`，同时继续显示并存储逻辑模型 `zai-org/GLM-5.2`。固定在恢复后保留；改偏好不改写既有 session。`/session` 显示活动 pin。路由选择经外部
[`Ember452/baldric-extension`](https://github.com/Ember452/baldric-extension)
extension 提供，不是内置命令。它要求 Baldric 0.1.0 或更新。克隆并显式加载：

```bash
git clone https://github.com/Ember452/baldric-extension.git
baldric -e ./baldric-extension
```

然后用 `/hf route` 从该模型当前存活的路由中选择，`/hf route <provider>` 选固定路由，`/hf route automatic` 回到可恢复的自动路由。切换模型使用该模型配置的固定路由或重新开始自动解析。`/session` 对粘性自动路由报告 `automatic (currently <provider>)`，对显式路由报告 `<provider> (fixed)`。

瞬时失败先在同一 wire 模型上重试，模型输出开始后的流失败不重试也不改路由。这些重试耗尽后，只有以自动模式选择的粘性路由会 failover；经 `/hf route <provider>` 或 `inference_providers` 偏好选择的路由保持固定，Baldric 绝不覆盖显式的用户意图。自动 failover 发出可见的重试进度与持久 provider 诊断。固定可以减少跨 provider 路由造成的冷前缀缓存未命中，但无法防止所选 provider 内部的逐出、TTL 过期或 worker 间负载均衡。改路由可能需要冷前缀 prefill，账户级限速仍可能让自动重试失败。见
[Configuration](/reference/configuration/#provider-偏好)。

### Moonshot AI API 与 Kimi Code 的区别

两个 Kimi provider 都用 Bearer API key 认证；都不用 OAuth。它们分开是因为 key 来自不同控制台、端点不同、计费套餐不同：

| Baldric provider | 获取与计费 | 模型 | 端点 | 环境变量 |
| --- | --- | --- | --- | --- |
| `moonshotai` | [Kimi 开放平台](https://platform.kimi.ai/console/api-keys)的按量 key | `kimi-k2.7-code` | `https://api.moonshot.ai/v1` | `MOONSHOT_API_KEY` |
| `kimi-code` | [Kimi Code 控制台](https://www.kimi.com/code/console)的订阅 key | `k3` 或滚动的 `kimi-for-coding` 别名 | `https://api.kimi.com/coding/v1` | `KIMI_CODE_API_KEY` |

Kimi K3 使用 `k3` 模型 ID，接受文本与图片输入，合格套餐支持最高 1,048,576-token context window。它经 `reasoning_effort` 字段支持 `low`、`high`、`max`（默认）三档 reasoning effort。Baldric 把它们暴露为独立的 `low`、`high`、`max` thinking 级别，且在没有已记住的每模型选择时，新 K3 session 从 `max` 开始。切换到 K3 时开新 session，避免前一模型的 context cache 被重新预填。当前套餐可用性与 context 限制见 [Kimi 的模型文档](https://www.kimi.com/code/docs/en/kimi-code/models)。

不要把一家的 key 当另一家的用。Baldric 在 `moonshotai` 与 `kimi-code` 凭据名下独立保存它们，所以 `/login moonshotai` 与 `/login kimi-code` 可以同时配置两者。不同的环境变量名在 shell 提供凭据时提供同样的隔离。

经 `/login` 保存的凭据存在 `~/.baldric/credentials.json`，权限 `0600`、原子替换。文件不加密；保护好你的 Baldric home，不要分享其内容。自定义 provider 流程询问 provider 名、显示名、base URL、API key 环境变量、默认 model 与 API key；它把 provider 定义写到 `~/.baldric/catalog.toml`，运行时偏好写到 `~/.baldric/providers.json`。

检查配置了什么、每个 provider 如何认证：

```bash
baldric providers
```

## 管理已存凭据

在 Baldric 内使用这些 slash 命令：

```text
/login [provider]   # 添加或刷新已存凭据
/logout [provider]  # 移除已存凭据
```

已存凭据优先于环境变量。`/logout` 只编辑已存凭据——它不碰环境变量或 `providers.json`。

### 多账户 profile

Baldric 在其用户数据 home 里为每个 provider 存一份凭据。同一 provider 要用多个账户，给每个账户单独的 `BALDRIC_HOME`。它隔离凭据、session、provider 偏好、settings、extension 与缓存：

```bash
# POSIX shells
install -d -m 700 "$HOME/.baldric-work" "$HOME/.baldric-personal"
alias baldric-work='BALDRIC_HOME="$HOME/.baldric-work" command baldric'
alias baldric-personal='BALDRIC_HOME="$HOME/.baldric-personal" command baldric'
```

PowerShell 里可以用函数把环境变更限定在一次调用内：

```powershell
function baldric-personal {
  $previous = $env:BALDRIC_HOME
  try { $env:BALDRIC_HOME = "$HOME\.baldric-personal"; baldric @args }
  finally { $env:BALDRIC_HOME = $previous }
}
```

每个别名或函数各认证一次：

```text
/login anthropic-subscription
```

`BALDRIC_HOME` 在可选的 `~` 展开后必须是绝对路径。用户级 `~/.agents` 资源与项目 `.baldric`/`.agents` 资源保持共享，直接经环境变量提供的凭据也是。完整边界见
[Configuration](/reference/configuration/#baldric-home)。

> [!NOTE] OAuth 排障
> 回调端口不可用或浏览器在另一台机器上时，浏览器登录可以回退到粘贴重定向 URL/码。该流程会把授权 URL 复制到剪贴板并渲染为链接，所以请粘贴或点击它，而不是选中换行后的文本——手工重组的 URL 会在换行处丢字符，provider 会拒绝它。Copilot 用设备码：打开短验证 URL 并输入其下方显示的码。码被拒或过期需要新的 `/login`。如果 Copilot 模型报告不支持，在 Copilot Chat 的模型选择器里启用，或询问你的组织管理员；provider/模型访问因套餐与策略而异。

## 选择与切换模型

- **`/model`** — 打开 picker（列出各已配置 provider 的模型；选中可能同时切换活动 provider）。
- **`baldric -m <model>`** 或 **`baldric --provider <name> -m <model>`** — 启动时选择。
- **Ctrl+P** / **Shift+Ctrl+P** — 向前/向后轮换你的 *scoped*（收藏）模型，不打开 picker。
  用 `/scoped-models` 建列表，或在 `/model` picker 里对模型按 `Space`。在 `/scoped-models` 弹窗里按 `Tab` 切到仅 scoped 视图，`Enter` 从列表移除模型。

两个 picker 都从当前快照立即打开，不等 provider 设置重载。省略活动模型的后台刷新让其现有 runtime 继续工作，但不把那个模型作为新选项提供。即使目录为空，活动模型过期时 picker 也能打开。

Baldric 在创建或刷新运行时 provider 之前，先对照活动 provider 的已配置模型列表校验所选模型。这防止意外的 provider/model 错配，例如把仅限 OpenAI API 的模型发给独立的 `openai-codex` 订阅 provider。

跨 provider API 切换时，Baldric 为目标 provider 编译既有工具历史。provider 特定的 tool-call ID 被确定性地翻译为可移植格式，每次调用与结果用同一个翻译后的 ID。为 Anthropic 编译历史时，Baldric 还会省略其他 API 创建的不透明 reasoning 签名。这让工具跑完之后 session 仍能继续，而用户不接触 provider 校验错误、已存 JSONL 历史不被改写。

### Claude Opus 5

Baldric 经直连 `anthropic` provider 支持 Anthropic 的 `claude-opus-5`。该模型有 1M-token context window，接受文本与图片，最多生成 128k token，价格为每百万输入/输出 token $5 / $25。Anthropic 默认启用 adaptive thinking。Baldric 把 models.dev 已验证的 `low`、`medium`、`high`、`xhigh`、`max` effort 暴露为不同模式。

用 `/login anthropic-api` 或 `/login anthropic-subscription`，然后在 `/model` 里选 **Claude Opus 5**。当前行为与可用性见 Anthropic 的
[Claude Opus 5 指南](https://platform.claude.com/docs/en/about-claude/models/whats-new-opus-5)。

## 动态 extension provider

Baldric 的 extension API 有一个经常驻第二 fake backend 与仅测试 Ollama 适配器验证的进程级 `DynamicProvider` 契约。与 `/login custom` 或 `baldric setup` 创建的 provider 不同，这些定义是来源/世代所有的覆盖层，绝不拷贝进 `catalog.toml`、`providers.json`、session 或通用磁盘存储。来源所有权是源自规范 extension 入口路径的稳定宿主身份——不是显示名。Baldric 在导入 extension 代码之前冻结每个发现的身份，符号链接重指向无法改变注册或清理所有权；同名分离的 extension 文件无法移除彼此的 provider。它们支持休眠模型集、深度不可变的兼容性元数据、原子模型快照刷新、按调用者的刷新期限、可重试安全的合并，以及不需要假 key、不暴露 auth 来源的 required/optional/no 认证。自定义认证解析异常在运行时创建时被归并为类别化宿主错误；Baldric 的 required-key 指引保持可执行。

Phase 1 建立了契约与 registry 机制。`/local` 宿主现在为已注册的动态本地 backend 提供通用 TUI 流程。动态 provider 仍不成为持久目录条目或自动启动回退：配置 backend，然后显式选择其 provider/model。受信任内置 llama.cpp provider 是窄的 scoped-model 例外：Baldric 只持久化其稳定 provider ID 加确切 model ID。未加载/过期的引用保持可见为不可用，且不能触发加载或下载。用户与项目动态 provider 不能选择持久引用。见[本地 backend 指南](/how-to/local-inference/)与
[Extensions](/how-to/extensions/#动态-provider)。

## 添加自定义/本地 provider

任何 OpenAI 兼容端点都可以——包括 llama.cpp、Ollama 这类本地服务器。最容易的交互路径：

```text
/login custom
```

Baldric 询问 provider 细节、保存 API key、把 provider 元数据写入 `~/.baldric/catalog.toml` 并立即使 provider 可用。

### 内置 llama.cpp backend

Baldric 的一等 llama.cpp 集成经 provider 中立的 `/local` 命令配置。要管理下载/加载/卸载，不带模型参数独立以路由模式启动 llama.cpp：

```bash
llama-server --models-max 1 --parallel 1 --flash-attn auto
```

添加硬件或模型相关旗标前，先看[官方路由指南](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md#using-multiple-models)
和下方 Baldric 的完整指南。

然后打开 Baldric 运行：

```text
/local
```

选择并确认推荐的 `llama.cpp` backend。Baldric 自动检查已保存、环境或默认端点；别处的服务器用 **Configure** 加可选 API key。Baldric 经 OpenAI 兼容或兼容路由发现来发现确切的已加载模型 ID；它不用假 key 或假模型。兼容的 b9688–b10595 路由显示方向键导航的模型状态，以及显式确认的加载、卸载、Hugging Face GGUF 搜索与服务端下载动作。加载/下载确认预选"取消"作为未标注的安全默认。关闭 `/local` 会留下正在运行的服务端下载；重开即可显式取消。没有 key 就没有 `Authorization` header。已存 key 优先于 `LLAMA_API_KEY`。

从 TUI 或 print mode 显式使用发现的 ID：

```bash
baldric --provider llama.cpp --model <model-id>
baldric --provider llama.cpp --model <model-id> --print "summarize this project"
```

已配置端点与安全模型快照存放在
`~/.baldric/state/extensions/llama.cpp.json`；secret 留在凭据存储。缓存快照允许服务器临时宕机时显式启动。
`/local` 从不扫描端口或进程、不停止外部服务器、不删除
模型文件。端点优先级、Doctor、reset 与排障见 [完整 llama.cpp 指南](/how-to/local-inference/)。

一个更早的手工配置 provider `llama-cpp` 保持独立、不被迁移。经 `/local` 配置内置 `llama.cpp` 层；Ollama 与其他 OpenAI 兼容服务器用下方的自定义 provider 流程。Baldric 不交付 Ollama backend。

对另一台 OpenAI 兼容服务器的脚本化或一次性设置，使用同一个 `baldric setup` 流程。例如 Ollama 的 OpenAI 兼容端点通常在
`http://localhost:11434/v1`：

```bash
baldric --provider local \
  --base-url http://localhost:11434/v1 \
  --api-key-env LOCAL_API_KEY \
  --model qwen \
  setup
```

这会把 provider 定义写入 `~/.baldric/catalog.toml`，把运行时偏好写入 `~/.baldric/providers.json`，并（默认）把它设为默认
provider。

要可复用的 provider 定义，在 `~/.baldric/catalog.toml` 加用户级目录覆盖：

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

Baldric 先加载内置的 `src/baldric/runtime/data/catalog.toml`，再叠加
`~/.baldric/catalog.toml`。与内置 provider 同 `name` 的用户条目可以扩展或覆盖：标量字段替换内置值，`models` 先并你的模型再合并，`context_windows` 合并。

有意**没有项目级** `.baldric/catalog.toml`。只加载用户级
`~/.baldric/catalog.toml`，克隆仓库不可能悄悄把 provider 的 `base_url` 或凭据重定向到意外服务。

运行自定义 provider：

```bash
baldric --provider local-gateway
baldric --provider local-gateway "summarize this project"    # TUI 带初始 prompt
baldric --provider local-gateway -p "summarize this project" # 一次性 print mode
```

目录 TOML 存 provider 与模型元数据。它**不**接受自定义 HTTP headers、超时或重试设置这类运行时请求选项。那些放 `~/.baldric/providers.json`。已存的 `providers.json` 条目支持
`headers`、`timeout_seconds`、`max_retries` 与 `max_retry_delay_seconds`。完整 JSON 形状、目录 TOML 形状与自定义模型的 `thinking_levels`，见 [Configuration](/reference/configuration/#providers)。

> [!TIP] Hugging Face 组织计费
> 要发送 Hugging Face 计费 header，把 provider 定义留在目录里，然后在
> `~/.baldric/providers.json` 给匹配的 provider 偏好加 header：
>
> ```json
> {
>   "default_provider": "huggingface",
>   "provider_preferences": {
>     "huggingface": {
>       "default_model": "openai/gpt-oss-120b",
>       "headers": { "X-HF-Bill-To": "my-org" },
>       "thinking_defaults": { "openai/gpt-oss-120b": "low" },
>       "timeout_seconds": 60,
>       "max_retries": 2,
>       "max_retry_delay_seconds": 1
>     }
>   },
>   "scoped_models": []
> }
> ```

## 凭据如何解析

对给定 provider，Baldric 依次使用：`~/.baldric/credentials.json` 里的已存凭据，然后 provider 的
`api_key_env` 指名的环境变量。OAuth 凭据在请求前立即刷新，替换值原子保存。内置 provider 用 `/login`，OpenAI 兼容自定义 provider 用
`/login custom`。
