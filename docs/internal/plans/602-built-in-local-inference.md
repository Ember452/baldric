# Issue #602 实施计划：以 llama.cpp 为内置本地推理

**状态：** 修订版实施计划（要求路由管理）
**总纲 issue：** [#602 — Built-in local inference: `/local` with llama.cpp as the default backend](https://github.com/Ember452/baldric/issues)
**取代：** #415、#443 与草案 PR #417
**Baldric 实施基线：** `origin/main` @ `9c1285d68f41059105bd8a834d309a4d601a3b07`
**Pi 参考基线：** `eb1f87fa9a29e27e0c63dcb40dbed9a3624c82b1`
**计划类型：** 多 PR 实施；不是单一巨石变更

> 实施前已刷新基线。全部总纲工作从上述确切的 `origin/main` commit 起步；历史原型分支仅作为证据。

## 1. 目标

给 Baldric 一等公民的内置本地推理体验：

```text
/local
  llama.cpp  <- 初始且默认的本地 backend
  Ollama     <- 可能的未来 backend
  vLLM       <- 可能的未来 backend
  LM Studio  <- 可能的未来 backend
```

首个交付的 backend 是 llama.cpp。它作为受信任的隐藏内置 extension 随 Baldric 打包，但经通用 extension API 注册，而不是在整个 Baldric 内核里散布 llama.cpp 分支。

实现还必须建立未来本地或远程动态 provider 所需的可复用基础：

- 受信任的隐藏内置 extension；
- 进程级动态 provider 对象；
- 感知来源与世代的 provider 覆盖；
- 异步模型发现与安全快照发布；
- required、optional 与 absent 三种认证；
- TUI 与 print 共享的一条信任感知 session 准备路径；
- 失败安全的 provider/model 切换；
- provider 中立的本地 backend registry 与 `/local` 宿主体验；
- 正确的 reload、resume、cwd 替换、取消与资源清理。

## 2. 决策摘要

1. **把 #602 当总纲。** 经小型子 issue 与可评审 PR 交付。
2. **用 `/local`，不用 `/llama`。** `/local` 归 Baldric 所有，聚合通用本地 backend。
3. **经 extension 系统打包 llama.cpp。** 它受信任且隐藏，但像其他 extension 一样被生命周期管理、故障隔离。
4. **优先以 `llama.cpp` 为规范 provider ID，待 Phase 0 裁决。** 它与 Pi 一致并避免与既有用户自建 `llama-cpp` 目录条目冲突，但 CLI/目录/session 可移植性与共存必须在冻结前测试。显示名为 `llama.cpp`。
5. **"默认"指推荐的本地 backend。** `/local` 总是呈现 backend 选择并把 llama.cpp 标为推荐/预选，即使它是唯一实现。由用户确认；llama.cpp 绝不静默替换 Baldric 的全局启动 provider。
6. **动态定义保持进程级。** 绝不把动态 provider 拷进 `catalog.toml` 或持久 provider 定义 schema。
7. **只持久化引用与安全快照。** session 记录可保留 `provider="llama.cpp"` 与一个 model ID。带版本的内置集成存储可保留端点与安全模型快照。secret 留在 Baldric 凭据库或环境变量里。
8. **复用 Baldric 的 OpenAI 兼容 transport。** `baldric_agent` 或 `/local` 宿主里不写 llama.cpp 流式实现。
9. **不要求假认证。** 没有 key 就没有 `Authorization` header。不合成 `Bearer local`。
10. **不猜元数据。** 未知 context window、输出限制、reasoning、模态、定价与兼容性保持未知。
11. **基础推理不依赖路由模式，但交付路由管理。** 普通单模型 OpenAI 兼容 `llama-server` 必须能用。对兼容路由，`/local` 还必须支持显式 Hugging Face 搜索/下载与模型加载/卸载，而不把路由模式当推理前提。
12. **信任之后才加载项目代码。** 动态 provider 启动不得绕过现行 staged 项目信任生命周期。
13. **用一个 staged 准备服务。** TUI 启动、print 启动、print resume、TUI resume/new 与 reload 不得各自发明 provider/extension 顺序。
14. **每个资源恰好一个所有者负责关闭。** 准备好/被采纳的 `CodingSession` 拥有其 provider、provider 刷新任务与 extension 世代；frontend 不同时关闭同一 provider。
15. **用第二个 backend 验证通用 API。** 必须有确定性 fake。在宣布公开 API 稳定前，优先做一个小型 Ollama/vLLM/LM Studio spike。

## 3. 范围与发布边界

### 3.1 首个完整版本的必需项

- 受信任隐藏内置 extension 加载；
- 通用动态 provider API；
- 休眠零模型 provider；
- provider 供给的安全初始模型快照，加一份带版本的内置 llama.cpp 磁盘缓存；
- 带超时、取消、共享工作与过期世代保护的异步刷新；
- optional/无认证的 OpenAI 兼容 provider 支持；
- 一条共享的 session/provider 准备路径；
- 模型 picker 与启动选择集成；
- 通用本地 backend registry；
- `/local` 的 setup、状态、模型发现、选择、doctor 与 reset 体验；
- 内置 llama.cpp 连接与推理支持；
- 单模型服务器与已加载路由模型的标准 OpenAI 兼容发现；
- llama.cpp 路由模型状态发现、加载与卸载；
- Hugging Face GGUF 仓库搜索、量化选择与服务端下载；
- 进度、取消、重试与共享路由确认；
- 不持久化其定义的内置动态 provider 安全持久 scoped-model 引用；
- 确定性 fake 服务器与 fake Hugging Face 测试；
- 对照 fake 第二 backend 的验证；
- 已发布文档与架构笔记。

### 3.2 完整版本内的必需顺序

基础单模型连接与推理先于路由管理落地，让协议特定工作建立在稳定的通用 API 之上。但 Phase 7 在总纲分支与 issue #602 视为完成之前是必需的。已发布的第二 backend 保持可选；常驻 fake 第二 backend 与真实适配器 spike 仍是必需的验证。

## 4. Baldric `main` 的当前行为

### 4.1 Extension 生命周期

相关模块：

- `src/baldric_coding/extensions/api.py`
- `src/baldric_coding/extensions/loader.py`
- `src/baldric_coding/extensions/runtime.py`
- `src/baldric_coding/project_trust.py`
- `src/baldric_coding/session.py`

当前行为：

1. `CodingSession.load()` 读 transcript。
2. 创建全新的 cwd 绑定 `ExtensionRuntime`。
3. 加载合格的用户与显式 extension，但不加载项目 extension。
4. `ProjectTrustCoordinator.resolve()` 判定受保护项目输入是否合格。
5. 加载受信任资源，带 `--project-extensions` 时加载受信任项目 extension。
6. 组合工具、命令、guideline 与 system prompt。
7. 用调用者已创建的 provider 构建 `AgentHarness`。
8. frontend 附着 UI 并放行待处理的 `session_start`。
9. 信任只在 staged session 采纳之后提交。

reload 与目标 session 替换会 stage 全新 runtime。旧 runtime 只在准备成功后退役。这防止 extension 状态跨越 cwd 信任边界。

当前 extension 不能注册 provider 或本地 backend。

### 4.2 provider 生命周期

相关模块：

- `src/baldric_coding/provider_catalog.py`
- `src/baldric_coding/catalog_loader.py`
- `src/baldric_coding/provider_config.py`
- `src/baldric_coding/provider_runtime.py`
- `src/baldric_ai/env.py`
- `src/baldric_ai/openai_compatible.py`

当前行为区分：

- 打包目录定义；
- `~/.baldric/catalog.toml` 用户目录覆盖；
- `~/.baldric/providers.json` 运行时偏好；
- `~/.baldric/credentials.json` 凭据。

它假设 provider 定义是持久的。选择、模型校验、thinking 偏好、scoped-model 偏好与运行时构建都操作 `ProviderSettings`。

`OpenAICompatibleConfig` 可以省略 Authorization header，但现行持久 provider 凭据门要求 API key。动态 optional/无认证 provider 需要独立的通用认证契约，而不是假环境值。

### 4.3 必须修复的启动倒置

两个 frontend 目前都在调用 `CodingSession.load()` 之前解析并构建 provider：

```text
load durable settings
→ resolve provider/model
→ create runtime provider
→ call CodingSession.load()
→ load extensions and resolve project trust
```

因此 extension provider 无法满足：

```bash
baldric --provider llama.cpp --model <id>
baldric --provider llama.cpp --model <id> --print "hello"
```

除非引入新的准备边界。

新的必需顺序：

```text
resolve destination cwd/session
→ create fresh extension runtime
→ load trusted built-ins and eligible extensions
→ resolve project trust
→ load trusted project extensions
→ restore safe provider snapshots
→ compose effective provider layers
→ refresh an explicitly requested provider when needed
→ resolve provider/model
→ create candidate provider
→ build coding session
→ attach frontend and emit session_start
→ commit staged trust/session
→ retire old generation
```

### 4.4 既有的本地模型权宜方案

用户可以经 `/login custom`、`baldric setup` 或 `~/.baldric/catalog.toml` 手工添加 OpenAI 兼容 provider。现行 llama.cpp 指南要求假非空 key，还常要假模型 ID。

新特性不得破坏手工配置的本地 provider。既有 `llama-cpp` 用户目录条目继续工作。内置 provider 用不同的规范 ID `llama.cpp`。

## 5. 期望的用户体验

### 5.1 首次连接

用户独立启动 llama.cpp：

```bash
llama-server -hf <tool-capable-gguf>
```

然后运行 Baldric 并打开：

```text
/local
```

`/local` 先呈现已注册的本地 backend。llama.cpp 被标为**推荐**并预选，包括它是唯一 backend 时，但由用户确认选择。这让入口保持 provider 中立，让加 LM Studio、Ollama、vLLM 或其他 backend 成为一次注册变更而非命令重设计。

llama.cpp 向导：

1. 按文档化的优先级提供已保存端点，然后 `LLAMA_BASE_URL`，然后 `http://127.0.0.1:8080`。
2. 只探测那个已知配置/默认端点；不扫描进程、端口或本地网络。
3. 接受带或不带 `/v1` 的 URL 并归一化。
4. 经宿主 secret 输入接受可选 API key。
5. 区分不可达、超时、加载中、认证、畸形响应、单模型与路由模式结果。
6. 经 OpenAI 兼容 API 发现真实已加载模型 ID；路由模式下按服务器报告状态列出已加载与未加载路由模型。
7. 路由模式下允许显式加载/卸载与 Hugging Face GGUF 搜索/下载，含量化选择、进度、取消、重试、受限仓库指引与共享路由确认。
8. 只有一个已加载模型时自动选择；多个已加载模型时显示 picker。
9. 选择有歧义时无头使用要求显式模型。
10. 凭据库之外只存端点、安全发现数据、选定模型与稳定 scoped-model 引用。
11. 已加载 provider 模型立即出现在 `/model`，无需重启；未加载模型保持为管理选项，不是推理选项。
12. 只在候选 runtime 就绪后才提议切换当前 session。

反馈示例：

```text
✓ Found llama.cpp at http://127.0.0.1:8080/v1
✓ Discovered model: qwen3-coder.gguf
✓ Ready: llama.cpp:qwen3-coder.gguf
```

### 5.2 `/local` 信息架构

宿主拥有的 `/local` 视图支持：

- 多于一个 backend 时的 backend 选择；
- setup/configure；
- 连接状态；
- 模型刷新；
- 当前与缓存模型；
- 使用/选择模型；
- doctor/兼容性诊断；
- reset 集成设置；
- backend 贡献的模型管理动作（支持时）。

视图只渲染所选 backend 支持的能力。检测到兼容路由时 llama.cpp backend 必须贡献路由管理，而单模型服务器在没有管理控件时保持完全可用。

没有 `/llama` 或 `/llama-cpp` 别名。

### 5.3 模型选择与启动

setup 之后：

```text
/model
```

显示 provider 显示名与发现的模型显示名。显式启动可用：

```bash
baldric --provider llama.cpp --model <model-id>
baldric --provider llama.cpp --model <model-id> --print "summarize this project"
```

选择规则：

- 有有效缓存快照时，启动不要求成功的网络刷新。
- 显式请求的 provider/model 没有安全快照且无法发现时，以可执行错误失败；绝不静默改选别的显式模型。
- 未请求 llama.cpp 且它不可用时，它不阻塞普通启动，也不因内置而成为回退候选。
- 保留 Baldric 现行无凭据 TUI 引导：没有普通 provider 可用时，TUI 仍以 login-required provider 打开，`/login` 与 `/local` 保持可用。print mode 以可执行错误非交互失败。
- 被恢复的 llama.cpp session 在校验前还原其稳定 provider/model 引用。网络发现失败不擦除引用或缓存快照。
- 刷新后的目录不再含活动模型时，保持活动 runtime 可用、在诊断中标记过期，并在该模型重新出现前阻止对缺失模型的新选择。

### 5.4 Doctor 流程

llama.cpp backend 提供确定性 doctor 动作，独立报告各阶段：

1. 端点归一化与服务器可达性；
2. 可用时的健康/加载状态；
3. 模型发现；
4. 认证接受度；
5. 流式 chat completion；
6. tool schema 接受度；
7. 实际 tool call 发射。

能流式但模型不调用探测工具的服务器收到警告，不是连接失败。解释可能原因：

- 模型不是具备工具能力的 instruct 模型；
- GGUF/chat template 缺 tool-call 支持；
- 需要 `--jinja` 或别的服务器旗标；
- llama.cpp 需要更新。

Doctor 探测必须是显式的用户动作。普通启动期间不花模型 token、不执行兼容性请求。

### 5.5 Reset

reset：

- 分开确认安全状态重置与已存凭据删除；
- 要求 session 空闲；
- 活动运行时使用内置 llama.cpp 层时，先请用户选另一个可用 provider；TUI 在没有可用 provider 时接受 login-required 引导，无头 reset 不支持；
- 回退切换被取消或失败时不删任何东西直接中止；
- 切换成功后，只移除 llama.cpp 内置自有的非 secret 设置、缓存快照与 provider/backend 层；
- 单独确认后才最后删除被引用的已存凭据；删除失败留下一个未被引用的凭据与可执行的清理诊断，不是部分生效的配置；
- 只移除/替换内置来源的层，绝不碰别的来源的覆盖；
- 内置层被另一来源遮蔽时如实报告；
- 绝不停止外部服务器；
- 绝不删除模型文件。

## 6. 架构与包所有权

```text
baldric_ai
  existing OpenAI-compatible transport and conditional auth header

baldric_agent
  provider-neutral harness, messages, events, tools, sessions
  generic atomic session-entry batch append and provider-aware model history

baldric_coding
  built-in extension registry
  dynamic provider contracts and registry
  trust-aware session preparation
  local-backend registry and /local host UI
  extension-scoped safe state and credential integration

built-in llama.cpp extension
  endpoint normalization
  discovery and status
  diagnostics
  OpenAI-compatible provider descriptor
  optional router capabilities
```

### 6.1 硬边界

- `baldric_agent` 不得导入 extension、目录、凭据、本地 backend、llama.cpp、Rich 或 Textual 代码。
- `baldric_ai` 可以暴露 transport 级的通用选项，但不得知道 extension 或 `/local`。
- provider 组合、信任、持久化、session 启动与本地 UI 属于 `baldric_coding`。
- llama.cpp 的 URL、端点、响应形状与诊断属于其内置 extension 包。
- Textual 组件留在 `baldric_coding.tui` 之后；provider 与 backend 契约是 UI 工具集中立的。

### 6.2 建议的模块布局

名字可以再打磨，但职责应保持分离：

```text
src/baldric_coding/
  built_in_extensions.py       built-in extension declarations and source metadata
  session_preparation.py       shared staged startup/resume/replacement orchestration
  local_backends.py            LocalBackend contract and runtime-local registry
  provider_config.py           durable settings only
  provider_runtime.py          durable + dynamic runtime construction dispatcher

  extensions/
    api.py                     public register_provider/register_local_backend actions
    runtime.py                 generation owner and registration routing
    providers.py               DynamicProvider, ProviderModel, auth and transport contracts
    provider_registry.py       layered runtime-local registry and refresh coordinator
    builtins/
      llama_cpp/
        extension.py           setup() registrations
        client.py              llama.cpp HTTP API and response parsing
        provider.py            provider/model conversion and refresh
        backend.py             /local capabilities, setup, doctor, reset
        state.py               versioned non-secret settings/snapshot persistence
```

不要把所有 provider 生命周期逻辑塞进 `extensions/runtime.py`；让它保持协调者，而不是又一个 provider 配置巨石。

## 7. 公开契约与数据模型

下面的草图定义职责，不是最终拼写。类型必须是类型化 dataclass 或 Protocol，尽量不可变。

### 7.1 动态模型

```python
@dataclass(frozen=True, slots=True)
class ProviderModel:
    id: str
    display_name: str | None = None
    api: ProviderApi | None = None
    base_url: str | None = None
    reasoning: bool | None = None
    input_modalities: tuple[str, ...] | None = None
    context_window: int | None = None
    max_tokens: int | None = None
    cost: ModelCost | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    compat: Mapping[str, JSONValue] = field(default_factory=dict)
    thinking_levels: tuple[ThinkingLevel, ...] | None = None
```

规则：

- `id` 必填且非空。
- 未知元数据用 `None`，绝不发明回退值。
- 空元组表示"已知都不支持"；`None` 表示未知。
- 模型级 headers 是运行时数据，除非显式证明非 secret，否则不进持久化安全快照。
- 重复 model ID 原子拒绝候选快照。

### 7.2 认证

```python
class ProviderAuth(Protocol):
    async def resolve(self, context: ProviderAuthContext) -> ResolvedProviderAuth: ...

@dataclass(frozen=True, slots=True)
class ResolvedProviderAuth:
    api_key: str | None
    headers: Mapping[str, str]
    source: str
    omit_authorization_header: bool
```

提供通用策略：

- `RequiredApiKey(credential_name, env_var)`；
- `OptionalApiKey(credential_name, env_var)`；
- `NoAuth()`。

key 策略的解析顺序：

1. Baldric 凭据库；
2. 配置的环境变量；
3. 缺失结果。

required 认证失败给可执行的 setup 指引。optional 认证返回无 key 并置 `omit_authorization_header=True`。无认证绝不查凭据且总是省略 header。

secret 值绝不进入 repr、诊断、快照、设置或 session 元数据。

### 7.3 Transport/运行时创建

```python
@dataclass(frozen=True, slots=True)
class OpenAICompatibleTransport:
    base_url: str
    api: ProviderApi = "openai-completions"
    auth: ProviderAuth = field(default_factory=NoAuth)
    headers: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: float = DEFAULT_...
    max_retries: int = DEFAULT_...
    max_retry_delay_seconds: float = DEFAULT_...

RuntimeFactory = Callable[
    [ProviderRuntimeContext, ProviderModel],
    Awaitable[ClosableModelProvider] | ClosableModelProvider,
]
```

`DynamicProvider` 提供通用 transport 描述符或运行时工厂之一。OpenAI 兼容 provider 走既有 `OpenAICompatibleProvider` 路径。自定义运行时工厂支持未来非 OpenAI 兼容的 extension，而不把 provider 特定假设塞进 registry。

复用 transport 需要兼容性审计：选 `openai-completions` 的动态 provider 不得仅凭模型名启发式继承第一方端点路由。用 `gpt-*` 与 `o*` 这类模型 ID 对照本地服务器测试，必要时加显式的 provider 范围 API 选择。

宿主在候选运行时创建之前立即解析认证。运行时工厂不得改动活动 session 状态。

### 7.4 provider 对象

```python
@dataclass(frozen=True, slots=True)
class DynamicProvider:
    id: str
    display_name: str
    models: tuple[ProviderModel, ...] = ()
    default_model: str | None = None
    transport: OpenAICompatibleTransport | None = None
    runtime_factory: RuntimeFactory | None = None
    refresh_models: RefreshModels | None = None
```

校验：

- provider ID 与显示名非空；
- 零模型合法；
- `default_model` 存在时属于该快照；
- 恰好一种运行时机制可用；
- provider/model 元数据在跨越持久化边界处 JSON 安全；
- 非法替换不动先前层。

暴露给 extension 的 API 形状：

```python
def setup(baldric):
    baldric.register_provider(dynamic_provider)
    baldric.register_local_backend(local_backend)
```

不要把变更导向的 `update_provider_models(...)` 作为主契约。发现返回完整候选快照，registry 原子发布它。

### 7.5 刷新上下文与结果

```python
@dataclass(frozen=True, slots=True)
class ProviderRefreshContext:
    signal: CancellationToken
    allow_network: bool
    cached_models: tuple[ProviderModel, ...]
    auth: ResolvedProviderAuth

RefreshModels = Callable[
    [ProviderRefreshContext],
    Awaitable[ProviderModelSnapshot],
]
```

宿主刷新策略：

- 该 provider 来源被加载且受信任后，同步接受 provider 供给的安全初始快照；
- 成功快照为该世代保留在内存；
- Phase 1 不加通用 extension 快照磁盘存储：内置 llama.cpp 在 Phase 5 拥有自己带版本的允许列表缓存，未来的公开 extension 存储 API 需要单独的来源身份与信任设计；
- 启动期间不为无关 provider 做网络刷新；
- 模型解析需要时刷新显式请求的休眠 provider；
- 让 `/local` 与 `/model` 请求显式刷新；
- 同一 provider 层/世代的并发刷新合并；
- 使用具名、文档化的超时常量；
- 超时、取消、畸形输出或网络错误保留缓存/当前快照；
- 只有来源 ID、provider 层 ID 与世代仍匹配时才发布；
- retire/reset/reload 时取消自有工作；
- 每个失败的刷新世代记录一条有界诊断。

### 7.6 本地 backend 契约

本地 backend API 描述能力与操作；不返回 Textual 组件。

```python
@dataclass(frozen=True, slots=True)
class LocalConfigField:
    key: str
    label: str
    kind: Literal["text", "secret", "choice"]
    required: bool = False
    placeholder: str | None = None
    choices: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class LocalConfigureSpec:
    fields: tuple[LocalConfigField, ...]

@dataclass(frozen=True, slots=True)
class LocalBackend:
    id: str
    provider_id: str
    display_name: str
    configure_spec: ReadConfigureSpec
    configure: ConfigureLocalBackend
    status: ReadLocalBackendStatus
    refresh: RefreshLocalBackend
    doctor: DoctorLocalBackend | None = None
    reset: ResetLocalBackend | None = None
    load_model: ManageModel | None = None
    unload_model: ManageModel | None = None
    download_model: DownloadModel | None = None
```

`register_local_backend()` 给每条注册盖上 extension 来源与世代戳。它还把 backend 绑定到同一来源注册的 provider 层，而不只是 provider ID。另一来源遮蔽配对 provider 层时，`/local` 可以仍显示状态/配置，但必须把 `use` 标为不可用，直到该 provider 层生效。reset 只移除其来源拥有的注册与状态。

配置是宿主渲染的事务：

1. backend 返回结构化字段规格。
2. 宿主收集普通与 secret 值，不记录也不持久化。
3. 宿主把一个临时值对象提交给 backend。
4. backend 校验连通性，返回字段/全局错误或完整候选配置。
5. 校验成功后 backend 才提交配置，用下述跨库协议。
6. 取消让先前设置、凭据、provider 快照与活动 runtime 原封不动。写失败要么留下先前已提交配置，要么留下可恢复的未被引用凭据孤儿——绝不是部分选中的 provider 配置。

对已存 key，用世代专属凭据名如 `llama.cpp:<random-id>`。安全状态只存这个非 secret `credential_ref`；动态 provider 构建 `OptionalApiKey(credential_name=credential_ref, env_var="LLAMA_API_KEY")`。先写新凭据，再原子提交引用该凭据世代的安全状态；安全状态写入即配置提交点。状态提交前崩溃留下一个未被引用的凭据，启动清理可按集成自有前缀移除。状态提交后，尽力删除旧的被引用凭据。reset 在单独确认后只删除当前被引用凭据。诊断把任何世代折叠为来源标签 `stored credential`，绝不打印引用。绝不日志明文 secret。仅环境/无认证 setup 存 `credential_ref=null`。对每次存储操作测试失败与进程恢复行为。

backend 可以为第二步返回修订版规格，但不构建 Textual 组件、不收原始 UI 内部。Phase 4 必须用两个请求不同 text/secret/choice 字段的 fake backend 证明这一点。

结果是结构化的宿主可渲染值：

- 连接状态；
- 端点显示值；
- 不含 secret 值的认证来源；
- 已发现/缓存模型与状态；
- 选定模型；
- 支持的动作；
- 进度事件；
- 可执行诊断。

宿主控制 secret 输入、确认、选择、取消、通知与渲染。backend 代码控制协议操作与其服务器专属消息。

## 8. provider 覆盖与所有权语义

### 8.1 层模型

有效 provider 视图在不改持久设置的前提下组合：

```text
provider ID
  durable catalog/settings baseline
  built-in extension layer
  user extension layer
  explicit extension layer
  trusted project extension layer  <- effective when present
```

用稳定的来源 ID 与世代 ID，不只是 provider 名。

建议的优先级是注册顺序、最近活动层生效。按现行 staged 加载，即持久 < built-in < 用户 < 显式 < 受信任项目。文档化它与先注册者获胜的工具/命令 registry 的刻意差异：provider 定义是可替换的配置层，移除必须露出前一个完整定义。

必需操作：

- 原子层注册；
- 同来源原子替换；
- 多来源同 provider ID；
- 注销一个来源不删其他层；
- 还原前一个完整动态层；
- 最后一个动态层消失后还原完整持久 provider 定义；
- 移除被退役世代拥有的全部层/任务；
- 拒绝过期刷新的发布；
- 为诊断暴露来源信息而不暴露 secret。

### 8.2 registry 生命周期

每个 staged `ExtensionRuntime` 拥有一个 `DynamicProviderRegistry` 与 `LocalBackendRegistry`。它们不是进程级单例。

runtime 可以接收不可变持久 provider 基线与安全缓存存储，但其活动注册与任务只属于该运行时世代。resume/new/cwd 替换 stage 全新 registry，并按目标信任决定重建 built-in/用户/项目注册。

这是相对 PR #417 旧的长生命周期 runtime 假设的核心变更。

### 8.3 运行时资源所有权

- 准备好的 session 在构建后拥有其候选模型 provider。
- 准备失败时，准备对象关闭候选并退役 staged extension/provider runtime。
- 采纳成功时，所有权恰好一次转移到 `CodingSession`。
- provider/model 切换、reset、reload、resume、new-session 与 cwd 替换要求 harness 空闲。运行活动时拒绝动作并指引先取消；不关闭在途 provider。未来的 cancel-and-drain 操作只有在完整等待流与工具关闭后才可放宽。
- 空闲模型切换成功后，在不失败发布边界之后立即关闭被替换的 Baldric 自有 provider。
- 模型切换失败时，只关闭失败的候选，当前 runtime 原封不动。
- reload/resume/new/cwd 替换时，退场 session 在候选完全准备好之前保持存活。
- 最终关闭时，取消刷新任务、发出 shutdown、退役 extension 世代并关闭所有剩余自有 provider。
- session 所有权统一后，移除 frontend 层的重复 provider 关闭。

## 9. 共享的信任感知 session 准备

### 9.1 从 `CodingSession.load()` 抽出准备

在 `src/baldric_coding/session_preparation.py` 引入 staged 服务。不要把 extension 加载分别塞进 `cli.py` 与 `tui/app.py`。

建议的内部类型：

```python
@dataclass(frozen=True, slots=True)
class SessionPreparationRequest:
    storage: SessionStorage
    destination_cwd: Path
    session_record: CodingSessionRecord | None
    requested_provider: str | None
    requested_model: str | None
    provider_override_is_explicit: bool
    model_override_is_explicit: bool
    # resource, extension, trust, prompt, and runtime options

class PreparedCodingSession:
    session: CodingSession
    async def adopt(...): ...
    async def abort(...): ...
```

把 `CodingSession.load()` 抽成三个概念阶段：

1. **state 阶段：** 读 transcript/session 状态并确定目标元数据，不创建 provider。
2. **environment 阶段：** 加载 built-in/extension、解析信任、加载受保护资源、恢复 provider 快照、组合有效 provider 视图。
3. **runtime 阶段：** 解析 provider/model、创建候选 runtime、构建/绑定 harness 与 coding session。

为直接提供静态 `ModelProvider` 的测试与内部消费者保留兼容包装，但 CLI/TUI 应用启动走共享 staged 服务。

### 9.2 选择优先级

provider/model 选择顺序保持可预测：

1. 显式 CLI `--provider` 与/或 `--model` 覆盖；
2. 被恢复 transcript 叶上活动的 provider 感知 `ModelChangeEntry`；
3. 仅当活动 transcript 路径没有 provider 感知 entry 时，session 索引/记录作为 legacy provider 锚；
4. 新 session 的持久用户默认；
5. 新 session 的第一个有凭据可用持久 provider；
6. 都不可用时仅 TUI 的 login-required 引导。

已提交切换之后 transcript 是权威；过期索引元数据绝不覆盖它。索引保持为定位器/缓存并从 transcript 修复。print mode 没有步骤 6，以可执行的非交互错误退出。动态本地 provider 不自动进入步骤 5。它们只被显式 CLI 选择、既有 session 引用或当前 session 的 `/model`/`/local` 动作选中。

校验任何动态 provider/model 引用之前解析有效 provider 视图。

保留既有特殊行为：

- Hugging Face 逻辑 provider 与 inference-provider pin；
- provider schema 迁移；
- Codex 运行时限制发现；
- provider 锚定的 context 恢复；
- 图片输入元数据；
- thinking 级别兼容性；
- system prompt 启动覆盖；
- print-mode session resume。

### 9.3 采纳序列

准备对权威 session 存储是只读的：transcript 初始化、修复 entry、provider/model 变更与叶更新保持在内存 stage。引入每 session 的跨进程锁文件，把每条 JSONL 读取、普通追加与新的批次追加都迁过它（支持处共享读；排他写）。给 provider 中立的 `SessionStorage` 契约扩展原子批次追加。`JsonlSessionStorage` 拿排他锁、重读当前文件、把当前字节加完整批次写到同目录临时文件、flush 并 `fsync`、原子替换 JSONL，然后 `fsync` 目录。普通追加同样拿排他锁，所以不会在替换期间丢失。内存存储在一个异步锁下应用批次。失败的批次让先前文件不变；恢复拒绝或安全移除不完整的临时产物。测试并发进程/任务执行普通追加与批次替换，并定义咨询锁不可用时的平台行为。批次即持久的采纳提交。

启动时：

1. 准备 session、staged entry、extension 世代与候选 provider，无权威写入。
2. 以缓冲/staged 模式附着 frontend UI 桥。
3. 原子追加 staged entry 批次，含最终 `LeafEntry`；这是持久提交点。
4. 经同步不失败赋值把准备好的 session 发布为活动 frontend session。
5. 冲刷/附着 UI 并发出待处理 `session_start`；handler/组件失败被包容为诊断。
6. 采纳后才提交 staged 信任。信任库失败对未来运行 fail-closed，不使这份已批准的仅运行快照失效。
7. 更新可重建 session 索引；失败成为修复诊断。
8. 开始接受用户输入。

替换/reload 先要求空闲 harness。然后用同一提交边界：

1. 准备完整目标快照与全部修复/初始 entry，不改当前或目标权威存储。
2. 以还不能替换退场组件的缓冲/staged 模式附着候选 UI 桥。
3. 原子追加完整目标 entry 批次，以预期 `LeafEntry` 结尾。批次失败则中止候选，两个 session 的权威状态都保持不变。
4. 进入串行化的**不失败发布边界**。此后，预期的 extension/UI/存储错误被包容为诊断而非抛出。
5. 在其 API 仍有效时发出退场 `session_shutdown`；包容 handler 失败。
6. 清空退场 extension UI。
7. 原子交换 frontend 的活动 session 引用。
8. 冲刷/附着候选 UI 并发出候选 `session_start`；包容 handler/组件失败。
9. 采纳成功后才提交 staged 信任库决定。信任库写失败对未来运行 fail-closed、成为诊断，不使已批准的仅运行快照失效。
10. 更新可重建 session 索引；失败成为修复诊断。
11. 退役并关闭退场 provider/extension 资源。

原子 entry 批次之后、内存发布之前的进程崩溃，留下完全提交的目标叶，下一次 resume 可恢复。实现必须文档化哪些操作发生在不失败边界之前与之内，并在批次/索引/信任每一步测试失败。被中止或不完整的候选绝不持久写信任。边界后的意外失败是尽可能被包容的宿主 bug，不是普通回滚路径。

### 9.4 模型切换

把现行先改动的切换替换为只在空闲时允许的、异步候选优先的事务：

```python
async def select_provider_model(provider_id: str, model_id: str) -> ModelSelectionResult:
    reject while harness is running
    validate against effective snapshot
    create candidate runtime
    prepare history/tool compatibility and next thinking/route state
    atomically append provider-aware ModelChangeEntry + LeafEntry as the durable batch
    publish the already-prepared in-memory provider/model state without awaiting
    update the repairable session index cache
    close replaced owned runtime
```

append-only transcript 是权威；session 索引是可重建缓存。`ModelChangeEntry` 与其活动 `LeafEntry` 是一次原子存储批次。批次失败中止并关闭候选，没有孤儿 entry 也没有切换。批次持久之后，发布是一次同步不失败赋值。索引更新失败记录诊断并保持已提交切换完好，留待索引修复。

给 `ModelChangeEntry` 加可选 `provider` 字段，每条新的初始/切换 entry 都写它。回放与分支恢复用最近的 provider 感知 entry。legacy entry 从 session 记录继承最佳可用 legacy provider 锚；不自动改写旧 JSONL。文档化旧跨 provider 分支不可避免的歧义，加兼容性、分支、导出与降级测试。

持久提交之前的失败让活动 provider、model、thinking、推理路由、session 元数据与 runtime 保持不变。

TUI picker 回调与 extension 动作必须 await 这条路径。不要调同步 `set_model()` 然后再尝试 provider 刷新。

## 10. 内置 extension 机制

### 10.1 声明

加一个精神上类似 Pi 的通用声明：

```python
@dataclass(frozen=True, slots=True)
class BuiltInExtension:
    name: str
    setup: ExtensionSetup
    hidden: bool = True
```

初始 registry：

```python
BUILT_IN_EXTENSIONS = (
    BuiltInExtension(name="llama.cpp", setup=llama_cpp.setup, hidden=True),
)
```

### 10.2 加载规则

- built-in 先于用户/显式/项目 extension 加载。
- `--no-extensions` 下 built-in 也加载，因为该旗标禁用的是被发现的 extension 目录，不是 Baldric 打包的产品能力。
- built-in 受信任，不作为受保护项目输入参与。
- built-in 只有在通用契约刻意允许时才可处理项目信任；llama.cpp 不需要。
- built-in `setup()` 保持同步且只注册。
- 网络工作只经刷新或本地 backend 动作开始。
- setup 失败成为 extension 诊断，不崩溃 Baldric。
- 隐藏 built-in 从普通 extension 安装/发现清单省略，但 `/session` 与诊断可把它们标为 built-in 来源。
- reload 创建新的内置世代并取消旧世代的工作。
- 在 llama.cpp 落地之前，最小 fake 内置 extension 必须证明加载、诊断、世代失效与 `--no-extensions` 行为。

## 11. llama.cpp 内置实现

### 11.1 连接设置

首选值，由 Phase 0 标识符裁决定稿：

- provider ID 候选：`llama.cpp`；
- 显示名：`llama.cpp`；
- 默认服务器 URL：`http://127.0.0.1:8080`；
- 推理 URL：归一化的 OpenAI 兼容 `/v1` 基底；
- 集成自有凭据名前缀：`llama.cpp:` 加一个以非 secret 引用存储的不透明世代 ID；
- 可选环境端点：`LLAMA_BASE_URL`；
- 可选环境 key：`LLAMA_API_KEY`。

端点优先级：

1. 进行中的显式 `/local` setup 值；
2. 已保存端点状态；
3. 未保存端点时当前进程的 `LLAMA_BASE_URL`；
4. `/local` 提供的默认。

因此显式成功的 setup 即使存在 `LLAMA_BASE_URL` 也保持有效。环境端点绝不拷进已存状态，除非用户经 setup 显式确认。默认本身不表示已配置，也不触发启动网络访问。已存端点或非空环境端点才算已配置。缓存模型以归一化生效端点为键，端点变化时被忽略。

URL 归一化必须：

- 要求 `http` 或 `https`；
- 拒绝嵌在 URL 里的凭据；
- 对基底端点拒绝 query/fragment 组件；
- 归一化尾部斜杠；
- 接受服务器根或 `/v1` 输入；
- 为健康/路由调用保留明确的服务器根，为 OpenAI 兼容请求保留推理基底；
- 避免把远程主机悄悄改写为 localhost。

### 11.2 基础发现

基础模式使用文档化、兼容的端点与防御性解析：

- 从 `/v1/models` 发现 OpenAI 兼容模型 ID；
- 可选检查可用处的健康/加载状态；
- 接受一个或多个模型；
- 无可选模型时保持 provider 休眠；
- 临时失败后保留缓存安全快照；
- 区分畸形成功响应与 transport 错误；
- HTTP 401/403 附 `LLAMA_API_KEY`/凭据指引呈现；
- 绝不持久化响应 headers、key 或任意服务器载荷。

单模型模式对首个版本足够。标准 `/v1/models` 也可能暴露当前已加载的路由模型。未加载模型的路由专属发现与路由管理是 Phase 7；路由元数据只在字段存在且可信时用于丰富 Phase 5 状态。

### 11.3 元数据转换

对每个发现的模型：

- 使用服务器的确切模型 ID；
- 有上报显示名用之，否则用 ID；
- 只在含义有文档时使用正的服务器上报 context window；
- 只从可靠的服务器架构/模态数据推断图片输入；
- 只有 UI 能区分"本地/未定价"与"已验证零商业价"时才把零成本报告为前者；否则定价保持未知；
- reasoning、输出限制、工具支持与兼容性未经直接验证保持未知；
- 区分未知 provider 元数据与 Baldric 的运行 context 回退：`/session` 与诊断把元数据来源显示为 unknown/fallback，而 compaction 可以只为保持可用而使用 Baldric 既有的保守回退；
- 图片支持在未被正向报告前保持不可用，context 计量不得把运行回退呈现为服务器声明；
- 不抄 Pi 的 128K 回退；
- 不因知道 context window 就设 `max_tokens=context_window`。

### 11.4 认证

- 没有 key 时，端点配置也算已配置。
- 已存凭据胜过 `LLAMA_API_KEY`。
- 没有 key 就没有 `Authorization` header。
- 有 key 经既有 transport 产生 `Authorization: Bearer <key>`。
- setup 只经宿主 secret 输入接受 secret。
- reset 分开处理设置与凭据移除。
- 诊断只显示 `none`、环境变量或已存凭据。

### 11.5 安全状态

为内置集成数据创建带版本、加锁、原子替换的用户级状态文件，例如：

```text
~/.baldric/state/extensions/llama.cpp.json
```

最终路径应遵循既有 `BaldricPaths` 约定并文档化。建议 schema：

```json
{
  "schema_version": 1,
  "endpoint": "http://127.0.0.1:8080",
  "selected_model": "qwen3-coder.gguf",
  "credential_ref": "llama.cpp:<opaque-generation-id>",
  "models": [
    {"id": "qwen3-coder.gguf", "display_name": "qwen3-coder.gguf"}
  ],
  "checked_at": "2026-08-18T12:00:00Z"
}
```

快照 schema 只允许安全元数据子集。未知字段按一份文档化的版本策略忽略（向前兼容）或拒绝。不支持的 schema 版本不得被破坏性改写。

不存：

- API key；
- 任意 headers；
- 服务器 PID；
- 猜测的元数据；
- 下载文件路径（除非后续路由特性明确需要并保护好它们）；
- 项目级端点覆盖。

### 11.6 必需的路由能力阶段

基础推理稳定后，对照官方文档研究当前 llama.cpp 路由 API 并钉住已测试版本区间。路由支持是能力探测且版本门控的；未知或不兼容路由降级为标准 OpenAI 兼容发现，而不是冒险发变更请求。

兼容路由的必需操作：

- 列出路由模型与服务器上报状态；
- 加载一个模型并等待对账后的已加载状态；
- 显式确认后卸载一个模型；
- 用认证或匿名 API 访问搜索 Hugging Face 的 GGUF 仓库；
- 检视仓库门控与 GGUF 文件，按上报呈现量化与大小，`Q4_K_M` 只作为 UI 偏好推荐而非模型元数据；
- 请 llama.cpp 服务器下载选定的 `owner/repository[:quantization]` 模型；
- 经文档化的路由操作取消加载/下载；
- 展示来自路由事件/轮询的有界进度；
- 重试连接与刷新而不重放被中断的变更；
- 每次状态转换后刷新动态 provider 快照。

安全规则：

- 绝不静默卸载别的模型；
- 行动前展示路由当前状态；
- 询问保留还是卸载既有模型；
- 取消绝不导致 Baldric 在刷新确认前声称模型已加载；
- 失败的替换尝试只在显式用户批准后尽力还原先前加载的模型；
- 受限仓库显示 Hugging Face 访问 URL，并说明 llama.cpp 服务器进程也需要授权的 `HF_TOKEN`；
- Baldric 可为搜索读取 `HF_TOKEN` 与标准 Hugging Face token 文件位置，但绝不存储或把该 token 转发给 llama.cpp；服务端下载认证属于独立运行的服务器；
- 绝不删除模型文件；
- 绝不假设路由私有于 Baldric；
- 单模型服务器隐藏仅路由特性。

## 12. `/local` 宿主实现

### 12.1 命令集成

把 `/local` 作为内置命令加进 `src/baldric_coding/commands.py`。给 `CommandResult` 扩展一个宿主动作，而不是实现一个 spawn 失控任务的同步 extension 命令。

TUI 流程：

```text
CommandRegistry.execute("local")
→ CommandResult(local_requested=True)
→ BaldricTuiApp opens LocalBackendScreen
→ screen calls async backend/service methods
```

这把异步工作、取消与弹窗所有权留在 TUI 适配器。

print mode 不执行交互式 `/local`。无头使用的配置依赖持久化 setup 加 `--provider`/`--model`。未来的 `baldric local ...` CLI 超出范围，除非出现具体自动化需求。

### 12.2 通用 TUI 状态

覆盖：

- 没有注册 backend；
- 一个 backend，未配置；
- 一个 backend，已配置且可达；
- 一个 backend，已配置但不可用；
- 多个 backend；
- 零模型的休眠 backend；
- 刷新失败的缓存快照；
- 活动模型从当前发现中缺失；
- 刷新进行中/已取消/已超时；
- 刷新后 backend 能力变化；
- setup 与 doctor 进度；
- reset 确认。

screen 用通用状态/动作模型。通用 TUI 类里不出现 `llama`、GGUF、路由、量化或 Hugging Face 词汇。

### 12.3 `/model` 集成

- `available_model_choices` 读有效 provider 视图。
- 动态 provider 与模型显示名出现在 picker。
- 休眠零模型 provider 不制造假模型行。
- 刷新入口可以显式刷新动态 provider；打开 picker 时不得同步探测每个本地端点。
- 动态 provider 定义与模型元数据绝不拷进持久 provider 设置。
- 内置动态 provider 可以选择加入宿主定义的持久引用方案。对 llama.cpp，scoped model 用既有 scoped-model 存储只持久化稳定 provider ID 与确切 model ID；只有受信任内置来源已加载且其端点键控安全快照或活动目录含该模型时解析才成功。
- 未加载、缺失或过期的 scoped 引用保持惰性、可见为不可用，而不制造假模型定义或触发网络/下载/加载工作。
- 用户/项目动态 provider 在未来的受信任稳定来源身份契约出现前，不具备 scoped 持久化资格。thinking 偏好在没有独立支持的已验证元数据与持久引用契约前保持禁用。
- 选择动态模型走异步候选优先选择路径。

## 13. 持久化、迁移与安全

### 13.1 持久与运行时数据

| 数据 | 存储 | 规则 |
|---|---|---|
| 内置/用户 provider 目录 | 打包/用户 `catalog.toml` | 既有行为 |
| provider 偏好 | `providers.json` | 动态定义绝不拷到这里 |
| API key/OAuth | `credentials.json` 或环境 | 绝不进 extension 状态/session/诊断 |
| 动态 provider 层 | 内存，staged runtime 拥有 | 世代退役时移除 |
| 内置 llama.cpp 安全模型快照 | 带版本的内置 extension 状态 | 以端点为键；内置来源加载后才还原 |
| 通用动态 provider 初始快照 | provider 注册/内存世代状态 | 本 issue 不做通用磁盘持久化 |
| 端点 | 带版本 extension 状态 | 仅用户级；绝不被环境性设置项目控制 |
| 活动 provider/model 引用 | session 元数据/历史 | 只有稳定 ID/模型，不是 provider 定义 |
| 本地全局默认 | 初期不支持 | llama.cpp 只是 `/local` 的默认 backend |

### 13.2 项目信任

- 内置 extension 代码受信任，因为它随 Baldric 发布。
- 用户与显式 extension 按既有规则保持合格。
- 项目 extension 发现只检视元数据（信任前）。
- 项目 extension 的 provider/backend 注册只在批准与 `--project-extensions` 之后。
- 项目 extension 的 provider 供给初始快照不能在该确切来源受信任并加载之前注册；本 issue 不从磁盘还原通用项目 extension 快照。
- 拒绝项目信任产生连贯的全局/显式/内置 provider 视图。
- reload/resume 期间取消信任保持当前 session 与 provider 不变。
- 信任仍是输入加载守卫，不是网络/模型/凭据沙箱；文档必须如此声明。

### 13.3 向后兼容

- 既有静态 provider 与设置文件照常加载。
- 既有 `llama-cpp` 自定义 provider 不被 `llama.cpp` 迁移或遮蔽。
- 给 `ModelChangeEntry` 扩展可选 `provider` 字段。既有 entry 保持可读；每条新的初始与切换 entry 写 provider 身份。
- 新回放与分支恢复优先 provider 感知 entry。legacy entry 使用 session 记录的最佳可用 provider 锚，保留历史跨 provider 分支的文档化歧义。
- 不自动改写既有 JSONL。文档说明旧版 Baldric 可能按其严格 wire 模型拒绝或忽略新可选字段；加显式降级指引。
- provider 设置 v2 迁移对持久定义保持权威。
- 动态 provider 保存路径必须绕过 `save_default_provider_model`、`save_provider_thinking_level` 与 `toggle_saved_scoped_model`，除非只操作受支持的持久引用。

## 14. 实施阶段与 PR 序列

每个阶段应是一个子 issue，带一个或多个原子 PR。前一阶段的退出标准未通过前，不开始下一层用户可见工作。

### Phase 0 — 生命周期设计与基线刷新

**目标：** 在加产品 UI 之前解决最高风险的准备边界。

工作：

1. 拉取当前 Baldric `main` 与当前 Pi。
2. 对已变化的启动/session/provider 代码重跑架构审计。
3. 在 `dev-notes/design/` 写一份聚焦 ADR，描述：
   - state/environment/runtime 准备切分；
   - 信任顺序；
   - provider registry 生命周期；
   - 采纳/中止语义；
   - provider/任务所有权；
   - TUI/print 共享入口；
   - 动态选择持久化规则；
   - provider 感知 `ModelChangeEntry` 回放与 legacy 回退；
   - 仅空闲的切换/替换与不失败发布边界；
   - 本地 backend 到 provider 层的来源绑定；
   - 内置 provider 标识裁决及与 `llama-cpp` 的共存；
   - 稳定内置 scoped-model 引用编码与不可用引用行为。
4. 为当前 TUI 启动、print 启动/resume、login-required 引导、信任取消、reload、new/resume、分支 provider 恢复、provider 切换失败、活动运行拒绝与清理加特征化测试。

退出标准：

- 准备/采纳状态机达成一致；
- 没有未解决路径能在信任之前执行项目 extension setup；
- 每个候选/退场资源有一个具名所有者；
- transcript 提交、session 索引修复与不失败内存发布语义达成一致；
- provider ID 与旧 `llama-cpp` 共存经测试决定；
- 重构前既有行为已被覆盖。

### Phase 1 — 动态 provider 契约与分层 registry

**目标：** 加 provider 中立的注册与刷新机制，不碰启动或 UI 集成。

可能的文件：

- 新 `src/baldric_coding/extensions/providers.py`；
- 新 `src/baldric_coding/extensions/provider_registry.py`；
- `src/baldric_coding/extensions/__init__.py` 导出；
- `extensions/api.py` 与 `extensions/runtime.py` 的注册方法；
- 聚焦 `tests/test_extension_providers.py` 或 `tests/test_extensions.py` 增补。

工作：

- 加 `ProviderModel`、`DynamicProvider`、认证策略、OpenAI transport 描述符、运行时工厂契约；
- 加来源/世代感知 provider 层；
- 加休眠 provider；
- 接受安全的 provider 供给初始快照并在内存保留成功快照；通用磁盘持久化推迟；
- 加异步刷新协调器、共享任务、超时、取消、诊断与过期发布保护；
- 加有效持久基线组合；
- 注销/退役时完整还原；
- 确保 setup 失败移除该 extension 来源的 provider 注册。

退出标准：

- 全部 registry 行为确定性且不含 frontend；
- 没有动态定义经持久 provider 设置写入；
- 过期刷新不能在再注册、reload 或退役之后发布；
- optional/无认证在无假 key 下表达。

### Phase 2 — 受信任隐藏内置 extension

**目标：** 在 llama.cpp 之前加通用打包 extension 来源。

可能的文件：

- 新 `src/baldric_coding/built_in_extensions.py`；
- `extensions/loader.py` 与 `extensions/runtime.py` 变更；
- `tests/test_extensions.py` 的 fake 内置 fixture 与测试。

工作：

- 定义内置 extension 声明；
- built-in 先于被发现的 extension 加载；
- 保留 hidden/来源元数据；
- `--no-extensions` 下也加载；
- 隔离 setup 失败；
- 纳入全新世代的 reload/resume/new 行为；
- 证明 built-in 不引发项目信任提示。

退出标准：

- fake 内置能注册工具、命令与 provider；本地 backend 注册在 Phase 4 加并测试；
- 失败产生诊断而无启动失败；
- 世代退役使全部捕获的 API 与 provider 工作失效；
- 通用加载器逻辑中不出现 llama.cpp 专属名字。

### Phase 3 — 共享的信任感知 session/provider 准备

**目标：** 消除 provider 先于 extension 的启动倒置。

可能的文件：

- 新 `src/baldric_coding/session_preparation.py`；
- 重构 `src/baldric_coding/session.py`；
- 适配 `src/baldric_coding/cli.py`；
- 适配 `src/baldric_coding/tui/app.py`；
- 适配 `src/baldric_coding/provider_runtime.py`；
- `test_cli.py`、`test_tui_app.py`、`test_coding_session.py`、`test_project_trust.py` 与 provider 测试。

工作：

- 从 provider 构建中抽出 transcript/资源/信任 staging；
- 启动选择前加载有效 provider；
- 统一 TUI 与 print 准备；
- 支持显式动态 `--provider`/`--model`；
- 支持 print resume 与 TUI resume/new/cwd 替换；
- 加异步候选优先模型切换；
- 把运行时 provider 所有权统一到 `CodingSession`；
- 强制仅空闲的切换/替换，并在不失败发布边界后关闭被替换 provider；
- 保留现行持久 provider 迁移、HF 路由、provider 锚定分支恢复、login-required TUI 引导、图片支持、thinking 与 system prompt 控制；
- 在启用动态跨 provider 切换前落地 provider 感知 `ModelChangeEntry` 回放；
- 让准备失败关闭候选资源并保留退场 session。

退出标准：

- 动态 provider 启动在 TUI 与 print mode 工作；
- 项目 extension provider 绝不在信任前加载；
- setup 每个 staged runtime 执行一次；
- 失败不留下部分切换的 session/provider 元数据；
- 全部既有启动/resume 测试继续通过。

### Phase 4 — 本地 backend 契约与 `/local`

**目标：** 在真实 llama.cpp 行为之前加 provider 中立的宿主体验。

可能的文件：

- 新 `src/baldric_coding/local_backends.py`；
- extension API/runtime 注册增补；
- `commands.py` 的 `/local` 命令；
- `src/baldric_coding/tui/` 下新 TUI screen/模块；
- `test_commands.py`、`test_tui_app.py` 与一个聚焦 backend registry 测试文件。

工作：

- 定义结构化配置字段/事务与 backend 状态/动作/结果/进度；
- 加来源/世代感知 backend registry；
- 加内置 `/local` 命令动作；
- 实现零/一/多 backend UI，带显式选择器与推荐/默认标记；一个 backend 也预选但仍需确认；
- 加通用 configure、refresh、use、doctor、reset 动作；
- 集成异步取消与过期 backend 世代；
- 用两个能力不同的确定性 fake backend 验证。

退出标准：

- 通用 UI 不含 llama.cpp 专属协议词汇；
- 一个或多个 backend 打开同一 picker；可用时 llama.cpp 被推荐/预选，但选择是显式的；
- 两个 fake backend 能请求不同 normal/secret/choice 字段，失败的配置绝不部分持久化；
- backend 操作绑定到其自有来源/provider 层，不能 reset 或选择遮蔽来源；
- 缺失的可选能力不被渲染；
- print/无头行为显式且安全；
- 第二个 fake backend 证明契约不是 llama.cpp 形状的。

### Phase 5 — 内置 llama.cpp 连接与推理

**目标：** 在没有路由管理的情况下交付有用的本地推理。

可能的文件：

- 新 `src/baldric_coding/extensions/builtins/llama_cpp/` 包；
- 内置声明注册；
- fake HTTP transport fixture；
- 聚焦 `tests/test_llama_cpp_extension.py` 加集成测试。

工作：

- 实现端点归一化；
- 实现带版本的非 secret 状态；
- 集成 optional 已存/env 认证；
- 对单模型服务器与当前已加载路由模型实现可达性/健康与 `/v1/models` 发现；
- 注册休眠/动态 provider 与本地 backend；
- 实现 setup、状态、刷新、使用、doctor 与 reset；
- 复用 OpenAI 兼容流式；
- 确保缓存启动与服务器不可用行为；
- 在 `/model` 暴露真实模型 ID；
- 加可执行的 401/403、超时、加载中、畸形响应与工具兼容性消息。

退出标准：

- 未认证与已认证 llama.cpp 服务器在无假值下工作；
- 单模型服务器可用；
- setup 后 TUI 与 print 显式启动可用；
- 服务器宕机不破坏无关 provider 启动；
- 不输出猜测的模型限制/能力；
- 非 secret 状态或诊断中不出现 secret。

### Phase 6 — 加固与第二 backend 验证

**目标：** 只在另一个实现锻炼过公开通用 API 之后才稳定它们。

工作：

- 在常驻测试套件保留必需的 fake 第二 backend；
- 做一个小型 Ollama、vLLM 或 LM Studio 适配器 spike；
- 记录契约过于 llama.cpp 专属之处；
- 在把名字/能力文档化为公开 extension API 之前修订它们；
- 加刷新/reload/resume 竞态与资源泄漏的压力测试；
- 完成已发布文档与迁移指引。

退出标准：

- 第二 backend 不需要任何 llama.cpp 概念；
- spike 引发的 API 变更在稳定性声明之前被采纳；
- #602 的全部必需验收标准达标；
- 必需的路由管理契约仍可实现，而不往通用 API 加 llama.cpp 词汇；
- issue #602 关闭前 Phase 7 仍是最后必需交付。

### Phase 7 — 必需的 llama.cpp 路由管理与 scoped model

**目标：** 在 provider 中立的 `/local` 内完成类 Pi 的模型管理工作流，不改基础 provider 语义。

工作：

- 钉住官方 llama.cpp 路由 API 行为与已测试版本区间；
- 能力探测路由模式，同时保留单模型回退；
- 实现模型状态列表、加载、卸载、服务端下载与操作后 provider 刷新；
- 实现 Hugging Face GGUF 仓库搜索、确切 `owner/repository[:quantization]` 输入、仓库详情、受限访问指引、量化/大小选择，以及仅搜索用途的 token 发现；
- 加进度、取消、重试、断连对账与共享路由确认；
- 实现稳定的内置 scoped-model 引用，不持久化动态定义、不触发隐式加载/下载；
- 加 fake Hugging Face/路由测试、活动路由验证、失败恢复与用户文档。

退出标准：

- 没有操作会静默下载、加载、卸载、还原或删除任何东西；
- 取消与断连经刷新把状态对账；
- 只有已加载/sleeping 模型进入 `/model`，并可通过 `/scoped-models` 与 `/model` picker 增删；
- 过期/未加载的 scoped 引用绝不合成可用性或触发路由变更；
- 受限仓库与 token 职责被解释而不泄漏凭据；
- 单模型模式保持完全受支持；
- 全部路由与 Hugging Face 行为留在 llama.cpp 内置包内。

## 15. 确定性测试计划

### 15.1 provider 契约与 registry

测试：

- 零模型的合法 provider；
- 非法空 ID/名字；
- 重复 model ID；
- 非法默认模型；
- transport/工厂校验；
- 持久基线被覆盖且被完整还原；
- 两个具有确定性优先级的 extension 层；
- 同来源原子替换；
- 非法替换保留旧层；
- 注销未知来源无害；
- setup 失败移除来源注册；
- 世代退役移除 provider/backend；
- 缓存快照还原；
- 失败刷新保留当前/缓存；
- 超时保留当前/缓存；
- 被取消的刷新不发布；
- 并发刷新调用者共享一个任务；
- 再注册使旧刷新失效；
- 旧世代完成不能覆盖新世代；
- 诊断有界且感知来源；
- required/optional/无认证解析；
- 缺失 optional key 省略 `Authorization`；
- 有 key 加 `Authorization`；
- secret 值绝不出现在 repr/诊断/快照序列化。

### 15.2 内置 extension

测试：

- 内置 setup 每个 staged runtime 运行一次；
- `--no-extensions` 下内置也加载；
- 内置先于用户/显式/项目来源加载；
- hidden 元数据影响清单但不影响诊断；
- setup 异常被隔离；
- 内置不触发项目信任；
- reload 创建全新世代；
- resume/new/cwd 替换不复用旧世代；
- 被退役的内置任务被取消。

### 15.3 准备与信任

对 TUI 与 print 路径测试：

- 静态持久启动不变；
- 显式动态 provider/model 启动；
- 动态 provider 先休眠后刷新；
- 显式的缺失模型不回退直接失败；
- 隐式启动忽略不可用的本地 backend；
- 缓存本地 provider 无网络启动；
- 动态 provider 的 print-mode resume；
- 被恢复动态 session 的显式覆盖；
- provider 迁移仍正确运行；
- HF inference-provider pin 不施加于非 HF provider；
- 项目 provider 在批准前不可用；
- 批准后项目 provider 在 setup 后可用；
- 拒绝排除项目 provider 但保留内置/用户/显式来源；
- 信任取消保持当前 session；
- 项目 cwd 替换重建 provider registry；
- setup 运行一次，而不是 frontend 一次 session load 又一次；
- 候选 runtime 创建失败保留活动 runtime/model；
- 原子 `ModelChangeEntry` + `LeafEntry` 批次失败既不留孤儿 entry 也不留下已切换 harness；可修复索引失败留下一条已提交的 provider 感知切换加诊断；
- 原子启动/替换批次覆盖初始化与 staged 修复 entry；失败让先前文件不变、提交后崩溃恢复到已提交叶；
- 新的跨进程 session 锁下并发普通追加与批次替换不丢 entry；临时文件、文件与目录持久化路径被测试；
- 已提交切换加索引更新失败后的 resume 跟随 transcript provider/model 并修复过期索引；
- 活动运行期间切换/reset/reload/resume/new 被拒绝且不关闭在途 provider；
- 候选中止关闭 provider 并取消任务；
- 成功切换立即关闭被替换的 Baldric 自有 provider；
- 最终关闭恰好关闭每个 provider 一次。

### 15.4 `/local`

测试：

- 命令已注册并出现在补全/参考清单；
- 无 backend 状态；
- 一个 backend 打开 picker 并预选、要求确认；
- 多 backend picker 把 llama.cpp 标为推荐/默认；
- 不可用 backend 的重试/关闭；
- 休眠 backend；
- 缓存/过期状态；
- 配置取消；
- secret 输入不回显也不存进 backend 状态；
- 刷新取消/超时；
- doctor 阶段渲染；
- 模型使用调用异步候选优先切换；
- reset 确认、空闲要求、回退选择/取消、活动模型安全、来源层隔离与凭据删除的部分失败；
- 两个 fake backend 之间不同的 normal/secret/choice 配置字段；
- 配置校验/取消让设置与凭据不变；
- 安全状态提交前的配置写失败只留下一个可检测的未引用世代凭据；提交后旧凭据清理失败保持新配置可用并报告清理；
- 不支持的路由动作保持隐藏；
- 能力集不同的 fake 第二 backend；
- 通用宿主渲染 backend 模型管理进度/动作而不出现 llama.cpp、GGUF、路由、量化或 Hugging Face 词汇。

### 15.5 llama.cpp fake HTTP 服务器

用 `httpx.MockTransport` 或 Baldric 已用的 transport 注入。覆盖：

- 根 URL 归一化；
- `/v1` 归一化；
- 尾斜杠归一化；
- 非法 scheme/userinfo/query/fragment；
- 连接拒绝；
- 超时；
- 加载中/不可用健康状态；
- 401 与 403 指引；
- 无认证请求 header 省略；
- 世代引用的已存/env key header 的包含与优先级；
- 孤儿世代凭据清理与只 reset 被引用凭据；
- 成功的 `/v1/models` 发现；
- 单模型自动选择；
- 多模型选择；
- 空模型列表；
- 重复 ID；
- 畸形 JSON 与畸形模型对象；
- 服务器上报的安全元数据；
- 缺失元数据保持未知，Baldric 运行回退标注为回退；
- 与第一方 OpenAI/Codex 名字相似的模型 ID 仍用显式选择的本地 API 端点；
- 刷新失败后的缓存快照；
- 刷新后活动模型消失；
- 流式 completion doctor 探测；
- tool schema 被接受；
- tool call 已发射；
- 流式可用但 tool call 不确定；
- 状态文件往返、权限、加锁、原子替换与 schema 版本；
- 端点优先级、环境不持久化与端点变化时的缓存失效；
- reset 移除状态但未经单独确认不动凭据；
- 真实 `ExtensionRuntime` 加载而非只直接模块导入；
- 对照钉住契约的路由 `/models`、`/models/load`、`/models/unload`、`/models/sse` 与下载响应解析；
- loaded、sleeping、unloaded、loading、downloading、failed 与 unknown 状态；
- 加载/卸载/下载的成功、失败、取消、超时、断连、重试与操作后对账；
- 有其他模型活动时加载不静默卸载；保留/卸载/取消选项与已批准的还原行为；
- fake Hugging Face GGUF 搜索、确切仓库输入、详情、量化抽取、大小、限速、匿名/token 认证与受限仓库；
- Hugging Face 与 llama.cpp 凭据不出现在日志、状态、诊断、session 与导出；
- 已加载模型成为 `/model` 选项与安全 scoped 引用；未加载/过期引用保持惰性。

### 15.6 回归套件

聚焦文件可能包括：

```text
tests/test_extensions.py
tests/test_project_trust.py
tests/test_provider_config.py
tests/test_provider_runtime.py
tests/test_coding_session.py
tests/test_session.py
tests/test_session_manager.py
tests/test_cli.py
tests/test_tui_app.py
tests/test_commands.py
tests/test_cross_provider_history.py
tests/test_http.py
tests/test_baldric_ai.py
```

每 PR 运行：

```bash
uv run pytest <focused test files>
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

每次面向用户的合并与最终关闭前运行：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
hugo --source website --minify
uv build
```

可用时也运行仓库的 GitHub Python 与文档检查。

## 16. 手动验证

### 16.1 单模型未认证服务器

```bash
llama-server -hf <tool-capable-gguf>
baldric
```

验证：

```text
/local
/model
```

然后跑一个编码工具轮，确认不需要 `Authorization` header。

### 16.2 API-key 服务器

以 `--api-key` 启动 llama.cpp，经 `/local` 配置，验证：

- 错误/缺失 key 指引；
- 已存凭据使用；
- `LLAMA_API_KEY` 回退；
- 状态/session/诊断/导出中无 key。

### 16.3 print mode 与 resume

```bash
baldric --provider llama.cpp --model <id> -p "summarize this project"
baldric --print --session <session-id> "continue"
```

验证发现端点暂时不可用时的缓存启动。

### 16.4 多模型与元数据

验证：

- 返回多个模型 ID；
- 模型 picker 显示名；
- 一个选定模型消失；
- 未知 context/输出/模态字段保持未知；
- 可靠的正向服务器元数据存在时被使用。

### 16.5 工具兼容性

运行 doctor 与真实编码轮：

```text
Use the bash tool to run pwd and report the result.
```

验证具备与不具备工具能力的模型。后者应收到有用的警告，不是笼统的连接失败。

### 16.6 reload 与替换

验证：

- `/reload`；
- `/new`；
- 同 cwd 的 `/resume`；
- 经信任批准 resume 到不同 cwd；
- 信任拒绝/取消；
- 替换期间服务器失败；
- 无重复注册/任务；
- 旧 provider 连接已关闭。

### 16.7 路由发现与管理

关闭 Phase 6 之前，跑一台至少加载一个模型的现行 llama.cpp 路由，验证标准 `/v1/models` 发现、`/model` 选择与推理。关闭必需的 Phase 7 与 #602 之前，额外验证：

- 无已加载模型；
- 单模型加载/卸载；
- 多个已加载模型；
- 另一模型已加载时加载；
- 取消的加载/下载；
- 断连与重试；
- 受限 Hugging Face 仓库；
- 被另一客户端改变的共享路由状态；
- 确切 `owner/repository[:quantization]` 输入与 GGUF 搜索/量化选择；
- 匿名与认证 Hugging Face 搜索，含受限仓库；
- 已加载模型经 `/scoped-models` 与 `/model` picker 添加与移除；
- scoped model 稍后被卸载或缺失而无隐式重载；
- 单模型模式仍不受影响。

## 17. 文档交付物

更新安装文档：

- `src/baldric_coding/data/docs/extensions.md` —— provider/本地 backend API 与内置来源语义；
- `src/baldric_coding/data/docs/models.md` —— `/local`、optional/无认证、动态与持久 provider；
- `src/baldric_coding/data/docs/cli.md` —— 显式本地 provider 启动行为；
- `src/baldric_coding/data/docs/tui.md` —— `/local` UI；
- `src/baldric_coding/data/docs/security.md` —— 内置信任与项目 provider 边界；
- `src/baldric_coding/data/docs/architecture.md` —— 包所有权与准备边界。

更新发布文档：

- `website/content/guides/extensions.md`；
- `website/content/guides/providers-and-models.md`；
- 新或扩展的 local-inference/llama.cpp 指南；
- `website/content/reference/slash-commands.md`；
- `website/content/reference/cli.md`；
- `website/content/reference/configuration.md`；
- `website/content/guides/project-trust.md`；
- `website/content/guides/tui.md`；
- `website/content/internals/architecture.md`。

加面向初学者的开发笔记：

- 准备生命周期 ADR；
- 动态 provider registry 与覆盖语义；
- 受信任内置 extension 设计；
- 本地 backend 契约；
- 内置 llama.cpp 实现与 Pi 对照；
- llama.cpp 路由管理、Hugging Face 搜索/下载、scoped 引用与 Pi 对照。

文档必须移除或明确取代当前假 key/假模型的 llama.cpp 快速上手。为其他端点保留静态自定义 provider 路径的文档。

## 18. Pi 对齐与有意差异

### 18.1 跟随 Pi

- 隐藏内置 llama.cpp extension；
- provider 对象注册；
- 休眠/缓存动态模型；
- 启动选择之前注册 provider；
- extension 自有的协议与管理行为；
- 路由模型状态列表、显式加载/卸载、Hugging Face GGUF 搜索/下载、进度、取消与共享路由保障；
- 注册后的普通模型 picker 与流式；
- 管理变更后的模型刷新；
- 隔离的 extension 失败；
- reload/session 替换时的来源失效。

钉住 Pi 基线处的参考文件：

```text
packages/coding-agent/src/core/extensions/types.ts
packages/coding-agent/src/core/model-registry.ts
packages/coding-agent/src/extensions/index.ts
packages/coding-agent/src/extensions/llama/provider.ts
packages/coding-agent/src/extensions/llama/index.ts
packages/coding-agent/docs/llama-cpp.md
```

### 18.2 刻意不同

- `/local`，不是 `/llama`；
- 通用多 backend 本地 UI；
- 不带路由模式的单模型服务器基础支持；
- 无假 `local` API key；
- 无 128K 回退或 `maxTokens=contextWindow` 猜测；
- 无静默卸载；
- 一个 provider 中立的 `/local` 向导合并 backend 选择、连接 setup 与管理，而非 Pi 分离的 `/login llama.cpp` 与 `/llama` 入口；
- Baldric 现行的项目信任与 cwd 绑定 staged runtime 语义；
- Python 类型化 dataclass/Protocol 而不是照抄 TypeScript 形状；
- 与 Baldric 持久 provider 目录分开的进程级覆盖。

额外偏差作为显式裁决记录在实施架构笔记里。

## 19. 风险与缓解

### 启动/session 重构回归

**风险：** 共享准备触碰 TUI、print、resume、信任与 provider 选择。
**缓解：** Phase 0 特征化测试；先在不改行为的前提下抽取阶段；每次迁移一个 frontend 到同一服务之后。

### 项目信任绕过

**风险：** provider 注册或刷新在批准前执行项目代码。
**缓解：** runtime 局部 registry；只在信任后加载/还原项目来源；分别测试 setup 与网络回调。

### 过期异步发布

**风险：** reload 后旧刷新覆盖新端点/模型。
**缓解：** 来源+层+世代发布 token；取消；一个协调器下的共享任务记账。

### provider/session 部分切换

**风险：** 运行时创建成功前活动模型已变化。
**缓解：** 异步候选优先切换与唯一原子采纳点。

### 资源泄漏或双重关闭

**风险：** frontend 与 session 都拥有启动 provider，或替换丢失所有权。
**缓解：** 准备 session 所有权账本；幂等中止；session 拥有被采纳 provider；显式关闭计数测试。

### 持久配置污染

**风险：** 动态 provider 定义进入目录/全局默认，或 scoped-model 持久化意外序列化临时定义或元数据。
**缓解：** 分离有效 provider 视图与持久化守卫；保存时不转换回 `ProviderSettings`。scoped 持久化限于宿主定义的受信任内置稳定引用，绝不存 provider 定义、端点数据、凭据或发现元数据。

### secret 泄漏

**风险：** API key 进入 extension 状态、快照、诊断、URL 或 session 导出。
**缓解：** 宿主 secret 输入；只在凭据库持久化；拒绝 URL userinfo；允许列表快照 schema；脱敏测试。

### 通用 API 只围绕 llama.cpp 成形

**风险：** `/local` 变成换个名字的 `/llama`。
**缓解：** Phase 4 的 fake 第二 backend 与 API 稳定前的真实适配器 spike。

### 未知元数据被转成不安全默认

**风险：** compaction、图片处理或请求限制使用猜测值。
**缓解：** 可选元数据穿透所有层；只在 Baldric 已要求处用保守既有回退；`/session` 显示来源。

### 内置集成阻塞正常启动

**风险：** 本地网络失败拖慢或搞崩每次 Baldric 启动。
**缓解：** 同步缓存注册、无无关启动探测、显式有界刷新、休眠 provider、隔离诊断。

### 既有自定义 llama.cpp 配置冲突

**风险：** 既有 `llama-cpp` 用户 provider 含义改变。
**缓解：** 规范内置 ID `llama.cpp`；无自动迁移；文档化共存与可选手工清理。

### 公开 API 抖动

**风险：** 外部 extension 采纳未验证契约。
**缓解：** 在第二 backend 验证前把 API 标为临时；Phase 6 之后才文档化稳定性。

## 20. 非目标

- 安装或编译 llama.cpp；
- 启动或停止 `llama-server`；
- 配置 CUDA、Metal、ROCm 或其他加速；
- 在 Baldric 里量化模型；
- 静默下载/加载/卸载/删除模型；
- 要求路由模式；
- 加 `/llama` 或 `/llama-cpp`；
- 把 extension 或本地 provider 逻辑放进 `baldric_agent`；
- 把 llama.cpp 协议分支放进通用 session/TUI 代码；
- 持久化明文 secret；
- 猜测模型 context、输出、模态、reasoning 或工具支持；
- 自动把 llama.cpp 设为全局 provider；
- 普通启动时探测每个本地 backend；
- 首版交付所有本地 backend；
- 在本工作中稳定 provider 贡献的 `/login`；
- 没有单独自动化需求就加顶层 `baldric local` CLI。

## 21. Phase 0 期间待确认的决定

这些是有界的实现选择，不是推迟拆分的理由：

1. 在 CLI、session、目录共存与诊断上验证 `llama.cpp` 之后的最终 provider ID。
2. provider registry 与 session 准备的最终模块名。
3. `BaldricPaths` 下的确切状态路径；首选形状 `~/.baldric/state/extensions/llama.cpp.json`。
4. 启动、`/model` 与 `/local` 的具名刷新超时默认。
5. 无缓存的显式恢复本地 session 的确切不可用行为。
6. 哪个真实第二 backend 获得 Phase 6 spike。
7. scoped llama.cpp 模型的确切稳定引用编码与不可用渲染。
8. 内置 extension 出现在 `/session` 计数里还是只在详细诊断。

每个决定必须记录在架构笔记并测试。不要为解决方便性问题而发明 provider 元数据或安全行为。

## 22. 完成定义

只有到 Phase 7 为止的全部必需阶段满足以下条件，issue #602 才算完成：

### 架构

- [ ] llama.cpp 以受信任隐藏内置 extension 发布。
- [ ] `baldric_agent` 保持 provider 与 extension 无知。
- [ ] built-in 使用通用 extension/provider/backend 注册 API。
- [ ] 动态 provider 组合遵循现行信任感知的全新 runtime staging。
- [ ] TUI 与 print mode 用一条准备路径。
- [ ] 动态定义与持久目录定义保持分离。

### provider 生命周期

- [ ] provider 可以零模型注册。
- [ ] provider 供给的初始快照与端点键控 llama.cpp 缓存在可选网络刷新之前还原。
- [ ] 刷新是异步、可取消、超时感知、合并、原子且世代安全的。
- [ ] 非法注册/刷新保留最后一个可用层/快照。
- [ ] 注销/退役还原前一个动态或持久定义。
- [ ] 运行时创建或原子权威 entry 批次失败保留活动 session 与目标 transcript。
- [ ] 新的模型变更历史记录 provider 身份且分支/resume 回放使用它。
- [ ] 切换与替换拒绝活动运行而不关闭在途 provider。
- [ ] 被替换/中止的资源恰好关闭一次。
- [ ] 启动与替换共享一个经测试的持久提交/不失败发布协议。

### 用户体验

- [ ] `/local` 存在且没有 `/llama` 别名。
- [ ] `/local` 呈现 backend 选择器并把 llama.cpp 标为推荐/预选，而不静默选择 Baldric 的全局 provider。
- [ ] 端点与可选 API key setup 可用，只探测配置/默认端点而不扫描进程、端口或网络。
- [ ] 本地服务器不可用不阻塞无关的 Baldric 启动。
- [ ] 没有普通 provider 可用时 TUI login-required 启动保持可用；print mode 安全失败。
- [ ] 已加载发现模型以真实 ID 出现在 `/model`；未加载路由模型只出现在 `/local` 管理。
- [ ] 兼容路由支持显式 Hugging Face GGUF 搜索/下载与模型加载/卸载，带进度、取消、重试与共享路由确认。
- [ ] 已加载 llama.cpp 模型可经 scoped-model 控件用安全稳定引用管理；过期/未加载引用绝不触发隐式管理。
- [ ] setup 后 TUI 与 print 显式选择可用。
- [ ] resume、reload、新 session 与 cwd 替换保持正确行为。
- [ ] Doctor 区分连通性、认证、流式、schema 与 tool call 行为。
- [ ] optional/无认证在无 key 时不发 authorization header。
- [ ] 未知元数据保持未知，Baldric 运行回退标注为回退而非服务器声明。

### 可扩展性

- [ ] `/local` 消费 provider 中立的 backend 契约，带结构化、事务性的 normal/secret/choice 配置字段。
- [ ] backend 绑定到其来源拥有的 provider 层，不能改动或选择遮蔽来源。
- [ ] llama.cpp 协议逻辑留在其内置包。
- [ ] fake 第二 backend 被永久测试。
- [ ] 真实第二 backend spike 反哺公开契约，或以具体理由文档化推迟。
- [ ] 外部 extension 有通往相同 provider/backend API 的受支持未来路径。

### 安全与持久化

- [ ] 项目 extension 绝不在信任与显式项目 extension 选择加入之前执行。
- [ ] 内置失败是诊断，不是宿主崩溃。
- [ ] secret 绝不进入非 secret 状态、快照、session、导出或诊断。
- [ ] 既有 provider schema 迁移与用户目录行为保持完好。
- [ ] 既有 `llama-cpp` 自定义 provider 在最终 provider ID 裁决下保持有效且独立。

### 质量与文档

- [ ] 确定性测试覆盖完整生命周期与失败矩阵。
- [ ] 活动未认证与已认证 llama.cpp 冒烟测试通过。
- [ ] 完整 pytest、Ruff、格式化、mypy、Hugo、包构建与 GitHub 检查通过。
- [ ] 安装与发布文档描述 `/local`、llama.cpp、安全、配置与排障。
- [ ] 面向初学者的架构笔记解释设计与 Pi 对照。
- [ ] 必需的路由管理、Hugging Face 搜索/下载与 scoped-model 集成已交付并文档化，单模型推理无回归。

## 23. 参考

Baldric：

- issue #602；
- 已关闭 issue #415 与 #443；
- 已关闭草案 PR #417；
- `AGENTS.md`；
- `src/baldric_coding/data/docs/{extensions,models,cli,security,tui,architecture}.md`；
- `website/content/guides/extensions.md`；
- `website/content/guides/providers-and-models.md`；
- `website/content/guides/project-trust.md`；
- `website/content/guides/tui.md`；
- `website/content/reference/{cli,slash-commands,configuration}.md`；
- `website/content/internals/architecture.md`；
- `dev-notes/architecture/phase-21-extensions.md`。

原型证据，不是当前 main 的实现权威：

- `feat/llama-cpp-extension-api:dev-notes/architecture/extension-providers.md`；
- `feat/llama-cpp-first-class:dev-notes/architecture/llama-cpp-first-class.md`。

Pi @ `eb1f87fa9a29e27e0c63dcb40dbed9a3624c82b1`：

- `packages/coding-agent/src/core/extensions/types.ts`；
- `packages/coding-agent/src/core/model-registry.ts`；
- `packages/coding-agent/src/extensions/index.ts`；
- `packages/coding-agent/src/extensions/llama/provider.ts`；
- `packages/coding-agent/src/extensions/llama/index.ts`；
- `packages/coding-agent/docs/llama-cpp.md`。
