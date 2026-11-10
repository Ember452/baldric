# OAuth provider 对齐与登录生产日志

Issue: [#370](https://github.com/huggingface/tau/issues/370)

## 本阶段加了什么

Baldric 最初的 OAuth 代码与 OpenAI Codex 直接绑定。本阶段在 `baldric_coding` 加了一个小的 provider 中立注册表，移植了 Baldric 缺失的两个广泛有用的 Pi
订阅 provider，并用其受支持的 API-key 机制加入当前的 OpenCode 产品：

- Anthropic Claude Pro/Max OAuth（授权码 + PKCE）
- GitHub Copilot OAuth（设备授权，含 GitHub Enterprise
  域名输入）
- 既有的 OpenAI Codex OAuth 经同一注册表
- OpenCode Go 与 OpenCode Zen 目录条目（`OPENCODE_API_KEY`，非 OAuth）

注册表还可以由应用 extension 扩展，而不给 `baldric_agent` 加 provider 政策。

## 审计的上游快照

对齐审计钉在 Pi commit
[`dcfe36c79702ec240b146c45f167ab75ecddd205`](https://github.com/earendil-works/pi/commit/dcfe36c79702ec240b146c45f167ab75ecddd205)，
提交于 2026-07-14。相关源码在
`packages/ai/src/utils/oauth/`，Pi 的 provider 指南是
[`packages/coding-agent/docs/providers.md`](https://github.com/earendil-works/pi/blob/dcfe36c79702ec240b146c45f167ab75ecddd205/packages/coding-agent/docs/providers.md)。

| provider/产品 | 上游认证 | Baldric 决定 | 注记 |
| --- | --- | --- | --- |
| OpenAI Codex | OAuth 浏览器回调；Pi 也有设备码 | 既有浏览器流程经注册表发布 | 既有 Baldric 凭据保持兼容。设备码仍是后续项。 |
| Anthropic Claude Pro/Max | OAuth 授权码 + PKCE | 发布 | OAuth 请求用 Bearer 认证、Claude Code 身份 headers/beta 与必需的身份系统块。Anthropic 目前把第三方 harness 使用描述为按 token 计费的额外用量。 |
| GitHub Copilot | GitHub 设备授权后换 Copilot token | 发布 | 支持 github.com 与提示输入的 GitHub Enterprise Server 域名。模型可用性取决于账户策略。 |
| Radius | 网关发现的浏览器/设备 OAuth | 不进 Baldric 内核 | Radius 是 Pi 的第一方 `pi-messages` 网关，不是通用 provider。Baldric 不应把可复用 harness 绑到另一个产品的网关。 |
| OpenCode Go | API key | 以 API-key provider 发布 | 官方 setup 让用户在 OpenCode 控制台订阅并复制 API key。 |
| OpenCode Zen | API key | 以 API-key provider 发布 | 这是按量付费的网关访问；不是 OAuth 登录。 |
| Google Gemini API | API key | 保留既有 API-key provider | Gemini CLI 的消费级 OAuth 是第一方客户端登录。本阶段不在第三方 harness 复用未文档化的消费凭据。Vertex ADC 仍是可能单独的环境认证特性。 |

OpenCode 决策对照 OpenCode `dev` 文档核实：
[`go.mdx`](https://github.com/sst/opencode/blob/dev/packages/web/src/content/docs/go.mdx)
与
[`zen.mdx`](https://github.com/sst/opencode/blob/dev/packages/web/src/content/docs/zen.mdx)。
OpenCode 较新的控制台账户 OAuth 动态返回工作区 provider
配置，但 OpenCode Go/Zen 文档化的可移植 provider 凭据仍是 API key。Baldric 因此不把任一产品误标为 OAuth。

## 架构

```text
Textual OAuthLoginScreen
        │ OAuthLoginCallbacks (URL, device code, prompts, progress)
        ▼
baldric_coding.auth.registry
        │ OAuthProvider protocol
        ├── OpenAI Codex
        ├── Anthropic
        └── GitHub Copilot
        │
        ▼
FileCredentialStore ── OAuthRuntimeCredentialResolver ── baldric_ai adapter
```

职责与 Baldric 的包边界保持对齐：

- `baldric_coding` 拥有登录 UX 契约、provider 注册表、token 刷新、本地
  凭据存储与 provider setup 政策。
- `baldric_ai` 只知道请求时认证材料与协议特定的 header 或载荷行为。
- `baldric_agent` 不变，对 provider、OAuth、Textual 或本地路径一无所知。

`OAuthCredential` 现在允许可选 `account_id` 与 JSON 兼容的
provider 元数据。既有 Codex JSON 对象原样加载。GitHub Enterprise 只存其归一化域名。写入用私有临时文件加
原子替换，避免写了一半的 JSON。

请求时解析器刷新过期凭据并在请求前保存替换值。这也让 Copilot 能从短命 token 派生按账户的 API base URL。

## 安全选择与限制

- 浏览器回调保留 PKCE 与 state 校验。
- 设备验证 URL 只接受 `http` 或 `https` scheme。
- 设备轮询遵循 RFC 8628 默认、`slow_down`、过期与取消。
- provider HTTP 失败的用户可见异常不含 token 响应体、token 或授权码。
- 凭据留在 `~/.baldric/credentials.json`，权限 `0600`。OS keyring
  或静态加密存储有意推迟；本地威胁模型更强的用户应优先环境变量或保护其 Baldric home 目录。
- `/logout` 移除本地凭据但不远程撤销 provider 授权。用户可以在 provider 账户设置里撤销 Baldric/CLI 访问。
- Copilot 模型支持随套餐、组织策略与模型选择而异。打包目录是候选清单；解读 provider 错误时应考虑那些账户限制。

## 验证与发布流程

确定性测试用 `httpx.MockTransport` 与 fake 凭据。覆盖：

- Anthropic 刷新成功与错误脱敏
- Copilot 设备登录、token 交换、Enterprise 路由、不可信 URL
  拒绝与刷新元数据
- RFC 8628 `slow_down` 与取消
- 注册表替换/还原
- legacy Codex 凭据加载、可扩展元数据、权限与原子写入
- 登录 picker 对 OAuth 与 API-key 方法的区分

生产检查运行：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

活动 OAuth 冒烟测试刻意不自动化——它们需要付费个人订阅与外部浏览器。发布前维护者应用测试账户手动验证每个启用的流程，包括一次无头 Copilot 设备流程与一次粘贴的浏览器回调。脱敏结果属于发布 PR；任何 token、码、回调查询、JWT 或凭据文件内容都不应拷进 GitHub。

## 回滚

registry 与 provider 目录增项可以回退而不动 session 文件。既有 API-key 凭据与旧 Codex OAuth 对象保持其先前格式。provider 更改端点或条款时，从 `auth_methods`/内置注册表移除它，同时保留凭据解析，让用户可以安全更新或删除旧的本地条目。

## 后续

- 加 OpenAI Codex 设备码登录与显式的浏览器/设备选择器。
- 加 frontend 中立的非 TUI 登录命令供纯 SSH 使用。
- 若 Baldric 引入共享一份凭据文件的并发进程，考虑进程级刷新锁；原子替换保护文件完整性，但不串行化跨进程竞争的读-改-写。
- 评估 OS keyring 集成与远程撤销链接。
- 登录后考虑活动 Copilot 模型发现/过滤。
