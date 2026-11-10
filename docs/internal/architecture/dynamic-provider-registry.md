# 动态 provider 契约与分层 registry

## Phase 1 加了什么

Issue #605 实现 #602 Phase 1 的 provider 中立基础。它
**不**加内置 provider、启动选择、`/local`、TUI 或任何
llama.cpp 行为。

新部件：

- `extensions/providers.py`：不可变的 provider/model/auth/transport/refresh
  契约；
- `extensions/provider_registry.py`：进程级持久/动态组合与刷新协调；
- `ExtensionAPI.register_provider(...)`：经拥有的 `ExtensionRuntime` 路由的 extension 注册；
- `create_dynamic_model_provider(...)`：用 Baldric 既有 OpenAI 兼容 transport 或 extension 工厂的候选运行时构建；
- 一个显式的 OpenAI transport 开关，防止动态模型名被启发式地选到 `/responses`。

Phase 6 用常驻的第二 fake backend 与一个小型仅测试 Ollama 适配器验证这些 API。适配器使用分离的 provider 与本地
状态端点，而不往契约加 provider 专属概念。

## 动态 provider 为什么不是持久设置

Baldric 既有的 `ProviderConfig` 对象描述从打包目录、`~/.baldric/catalog.toml` 与
`~/.baldric/providers.json` 加载的用户/应用配置。extension 注册的所有权不同：其代码来源与信任决定只存在于一个 staged 运行世代。持久化那个定义会让后来的进程在来源消失之后、或受信任之前使用 provider 行为。

registry 因此接收完整的持久 `ProviderConfig` 对象作为不可变基线，绝不序列化动态数据。每个动态层存：

```text
provider id + source id + runtime generation id + layer id
```

最近的活动注册获胜。对已加载 extension，宿主从规范入口文件路径派生稳定
来源 ID；extension 显示名绝不用作 provider 所有权。加载器在导入任何 extension 前冻结每个发现的 ID 并存于 `LoadedExtension`。import/setup 代码因此可以重指向入口符号链接或祖先，而不改变重复检测、API
注册或失败 setup 清理的所有权。名为 `shared.py` 的不同路径即使在分离的信任阶段加载也拿到不同层。同一 runtime 内重复同一规范入口被忽略、先加载者优先；全新的运行时世代可以再次加载那个稳定来源。同一来源注册同一 provider 原子替换该来源的旧层。移除它露出前一个完整动态层；移除最后一层返回确切的原始
持久对象，包括 headers、模型元数据、兼容性、超时、重试、
thinking 配置与其他每个字段。工具与命令保持独立的
先注册者获胜名字 registry。

本阶段有意没有通用快照磁盘存储。未来受信任 built-in 可以拥有带版本、允许列表的安全缓存，但公开 extension 存储需要单独的来源身份与信任设计。

## provider 与模型校验

`DynamicProvider` 有非空的确切 ID/显示名、零或多条唯一的 `ProviderModel` ID、必须属于当前完整快照的可选默认，以及恰好一种运行时机制：

1. `OpenAICompatibleTransport`，或
2. 自定义运行时工厂。

零模型合法：它表示休眠 provider，不发明假模型。未知模型元数据保持 `None`；空元组意为"已知没有"。兼容性数据被拷贝、JSON 校验并深度冻结：嵌套对象变只读映射、数组变元组。registry 视图、刷新结果与回调 `cached_models` 因此能共享同一份已校验模型值，而不让消费者改动活动状态。运行时构建在 transport 边界把兼容性数据转回普通 JSON 字典/列表。运行时 headers 被拷贝但不进表示，也没有持久化 helper。

构建在 registry 变更前校验整个候选。非法的同来源替换或刷新因此让先前层/快照不变。

## 认证与 secret 处理

动态认证只在刷新或候选运行时创建之前解析：

```text
RequiredApiKey / OptionalApiKey
  → Baldric credential reader
  → configured environment variable
  → missing result

NoAuth
  → consult neither source
```

required 认证失败附 setup 指引。缺失 optional 认证与 `NoAuth`
产出 `omit_authorization_header=True`；不使用假 `Bearer local` 值。
已解析 key、auth headers 与 extension 供给的 auth 来源是仅运行时字段，排除在 `repr` 之外。transport/model headers 同样排除。静态
transport/model headers 不能供给 `Authorization`；bearer 或自定义授权必须来自解析时的认证策略。这防止凭据成为已注册定义的一部分，同时仍允许非 Bearer scheme 经解析的 auth headers 通过。刷新诊断绝不含 extension
异常字符串或已解析认证数据——两者都可能含请求数据或
secret；诊断只报告有界的类别与来源 token。运行时创建同样把自定义认证解析异常转成类别化宿主错误。
只有 Baldric 确切的 `RequiredApiKey` 策略保留宿主撰写的缺 key setup 指引。

## 刷新生命周期

刷新回调收到：

- 取消 token；
- 是否允许使用网络；
- 当前安全的内存模型元组；
- 已解析的认证。

它返回一份完整的 `ProviderModelSnapshot`。协调器：

1. 识别确切有效的来源/层/世代 token；
2. 只在 token 与 `allow_network` 政策匹配的调用者之间共享一个任务；
3. 应用每个调用者自己的超时，同时屏蔽兼容的共享工作；
4. 校验返回的整份快照；
5. 同步重查来源、层、世代与操作修订；
6. 只有全部所有权仍匹配才发布。

相反的网络政策用分离的发现任务，无网络调用者绝不消费启用网络的发现，而稍后启用网络的调用者仍可做网络工作。短等待者可以超时而不结束兼容长等待者的工作。当最后一位等待者超时——或 `cancel_refresh` 取消操作——合并条目在该调用者返回前同步分离。立即重试因此创建新操作。每个完成回调携带旧操作身份，无法移除同键下创建的后继者。被分离的工作留在独立自有操作集合里直到真正完成。

超时、显式取消、来源替换、注销、reload 与 runtime 退役都会通知并取消自有工作。调用者取消被屏蔽，一个等待者不能摧毁另一位等待者共享的工作。发现最多收到一次
`Task.cancel()` 请求。异步 close 等回调退出或自请求起 0.25
秒，绝不因清理超过 0.1 秒就往普通 `finally` 块注入第二次取消。在包容区间内完成的清理在 reload、替换、reset 关闭或最终关闭返回前排水。

0.25 秒仍在运行的回调被归类为**被包容**，不是已排水。
`ProviderRegistryCloseResult(drained=False, contained_discovery_tasks=...)` 报告该确切状态。进程自有的 supervisor 强引用发现任务——其完成回调又引用其退役世代 registry——直到真正完成。这个显式根避免依赖 session 丢弃退场 runtime 后 asyncio 的弱任务引用。回调在外层操作结束后没有发布路径，且来源/层/世代/修订守卫仍然生效。
失败的工作保留当前快照，每个层 token 至多记录一条诊断；registry 还施加全局上限。

## 运行时创建与 transport 路由

OpenAI 兼容动态 provider 复用 `baldric_ai.OpenAICompatibleProvider`。
transport headers、模型 headers 与解析的 auth headers 只在内存合并。缺失 optional 认证传空内部 key 加
`omit_authorization_header=True`，HTTP 适配器因此不发 Authorization
header。

自定义运行时工厂只在 `stream_response` 与 `aclose` 都可调用时被接受。构建后被校验拒绝的候选尽可能恰好关闭一次；关闭错误被包容，不能取代类别化的配置错误。

既有适配器历史上对某些 OpenAI/Codex-
形状模型 ID 推断 `/responses`。对持久 provider 那仍是兼容默认。动态 transport 描述符显式拥有自己的 API 选择并设
`infer_api_from_model=False`；名为 `gpt-5.4-local` 或
`my-codex-local` 的本地模型在 `api="openai-completions"` 时仍到达配置的 `/chat/completions`
端点。

## ExtensionRuntime 所有权

每个 `ExtensionRuntime` 现在创建一个带与其 `ExtensionGeneration` 相同显式世代身份的 provider registry。加载器在导入任何 extension 前给每个发现的入口从
`Path.resolve().as_uri()` 派生来源 ID，把该值存于
`LoadedExtension`，之后只用存储的 ID。`register_provider` 使用宿主自有 ID。显示名只是面向用户的标签。

`setup()` 抛异常时，runtime 只移除携带该确切存储来源 ID 的注册——包括 provider、工具、命令、guideline、渲染器与事件 handler。因此失败的第二个 `shared.py` 不能移除另一路径成功的第一个 `shared.py`；成功的同名 provider 照常作为独立层遮蔽与还原。重复工具与命令仍按名忽略，先注册语义不变。

reload 与退役在使退场 API 失效前取消 registry 工作并移除层。`CodingSession.reload()` 与目标替换同步发布全新状态，然后把退场 runtime 的关闭放进独立拥有的任务。该已提交接缝处的取消被包容，直到清理排水或报告有界敌意工作，操作返回采纳的结果而不是声称回滚。最终
`CodingSession.aclose()` 同样拥有一个持久关闭任务，但只在 extension registry 与每个 provider 台账条目都收到那一次关闭尝试之后才传播观察到的调用者取消。重复 close 观察同一任务，不可能关闭 provider 两次。staged 替换显式拥有其候选 provider 台账，贯穿退场 shutdown、
进场 start 与所有其他发布前接缝。取消或失败在传播前关闭该候选 session，同时保持活动 provider 打开；成功把台账恰好一次转移给幸存的外层 session。`reset_for_reload()`
是同步的，因此为 runtime 稍后的异步关闭保留每个退役 registry。被包容的任务经其完成回调保持进程监护及其退役 registry；不会被误标为已排水。reload 随后在同一不可变持久基线上创建新世代与空 registry。provider 刷新诊断投影进正常运行时诊断，不暴露 secret。

## 怎么验证

聚焦测试覆盖休眠/非法契约、认证优先级与省略、
secret 安全表示、确切的持久还原、多来源优先级、
同来源替换、同名/异路径与符号链接重指向隔离、
完整的失败 setup 清理、政策安全与立即重试安全的刷新
合并、按等待者超时、单取消协作清理、显式
敌意工作包容、发布前候选中止、发布时取消的
生命周期排水、最终关闭/provider 台账清偿、畸形输出、过期工作、
深度不可变性、被拒运行时清理、认证异常脱敏、无持久写入、
退役、HTTP 认证 headers，
与模型名路由：

```bash
uv run pytest tests/test_extension_providers.py tests/test_extensions.py \
  tests/test_provider_config.py tests/test_provider_runtime.py tests/test_http.py
uv run ruff check .
uv run ruff format --check .
uv run mypy
```
