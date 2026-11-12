# baldric 结构重构计划 v2：先砌墙，再搬家

> 状态：**执行中 —— 阶段 A0、A、B、C 已完成**（2026-11-12）。执行记录：
> [stage A0](../notes/2026-11-12-stage-a0-wall.md)、[stage A](../notes/2026-11-12-stage-a-rules-and-dedup.md)、
> [stage B](../notes/2026-11-12-stage-b-subagents.md)、[stage C](../notes/2026-11-12-stage-c-mcp-llamacpp.md)。
> 后续阶段 D–H 待逐阶段推进，每阶段原子完成并停下评审。
> v1 依据：2026-11-11 全量深扫 + 2026-11-12 逐目录实测裁定
> v2 修订：吸收独立评审的 6 个 P0 + 11 个 P1，并补入本会话新发现的 2 项（`protocol/session/jsonl.py` 是行为、`ai/` 与 `providers/` 是两层配置）
> 目标读者：维护者本人（个人开发者，时间充足，目标是长期产品，不发独立包）

## 0.1 阶段 A0 执行后的现实修正（2026-11-12）

A0 动手前逐字段重扫代码，发现计划正文有三处与代码现实不符，按「现实为准 + 回写计划」处理，
详见执行记录。要点：

- **`ExtensionAPI` 等是带行为的实现类，不是 Protocol**，不搬入 `protocol/`（否则违反
  「protocol 只放形状」与运行时无上层依赖门）。A0 只把**纯形状**（事件 dataclass、
  类型别名、能力元数据、事件常量）迁入 `protocol/extension.py`；实现类留 runtime，
  随阶段 E/F 搬。
- **`PluginManifest` 全仓不存在**（它是 P9 产物）。A0 不凭空创建，等 P9 再定义为 protocol 形状。
- **`ports.py` 只落无歧义的 `HookDispatcher` + `FeatureSetup`**；计划原列的
  `ProviderCatalog`（返回不存在的 `ProviderRecord`）/`SessionLifecycle` 推迟到 D/E
  真实类型出现后再定型。

## 0. v2 相对 v1 的根本变化

v1 是"描述现状的计划"——它把"家具该放哪个房间"想清楚了，但**没定义"墙在哪里"**。执行到阶段 E 会立刻撞墙（实测 11 处 core→platform 硬依赖 + 2 处 rendering→extensions.api）。

v2 的原则：**先把墙砌好（protocol 契约 + port + scanner 白名单 + 阶段顺序），再搬家。** 墙不砌完，搬家就是"边搬边改架构"的失控。

**v2 对闭环的诚实表述**：本计划**完全解决 4 项、部分解决 2 项、延后 1 项**（见 §9）。不再声称"彻底解决"。

---

## 1. 实测基线（所有数字由此生成，禁止手写）

> **规则**：计划里任何行数/符号数/文件数，一律由 `scripts/measure_structure.py` 生成再粘贴；验收时也用它，避免手写口径漂移。

**基线快照（2026-11-12 实测，由 `scripts/measure_structure.py` 生成，A0 建脚本后重测）**：

| 项 | 数值 |
|---|---|
| `src/` | 249 文件 / **77,712** 行（A0 前 250/67,987；本表随协议新增文件更新，脚本为准） |
| `tests/` | 216 文件 / **77,790** 行 |
| `runtime/` | 198 文件 / 65,935 行 |
| `runtime/tui/` | 40 文件 / 19,053 行 |
| `runtime/session/session.py` | **2,097** 行 / **183** 个方法（v1/v2 写 1,864 行——已过时，以脚本为准） |
| `runtime/__init__.py` | **317** 行 / **139** 个 `__all__` |
| `runtime/extensions/__init__.py` | **249** 行 / **116** 符号 |
| `scripts/check_import_graph.py` 规则数 | **29** 条（28 RULES + 1 AllowRule） |
| fast suite（除 TUI） | 2276 passed（会变，验收看"不减少"而非绝对数） |

> 口径纪律：任何行数/符号数以此脚本 `uv run python scripts/measure_structure.py` 输出为准，
> 不手写。首次引入脚本时发现计划旧数字已漂移（session.py 实际 2,097 行而非 1,864），
> 正说明该纪律必要。

---

## 2. 问题陈述（4 条成立，1 条是症状）

| 条目 | 判断 | 证据 |
|---|---|---|
| 加功能横跨 5–6 目录 | ✅ 成立 | subagents 散落 24 文件、跨 6 目录 |
| 技术层与功能域混杂 | ✅ **根因** | 顶层目录一半按层切、一半按域切 |
| extensions 框架与插件同居 | ✅ 成立 | `extensions/__init__.py` 247 行 `__all__` 同时为框架和插件背书 |
| session god class | ✅ 成立 | `session.py` 1,864 行 / 183 方法 |
| 同一契约两处定义 | ✅ 成立，但**是症状** | 根因是"公共契约没有单一来源" |

**S1 的定义修正（v1 自相矛盾）**：v1 的 S1 "任一功能的实现文件只在其功能目录内"与 §2 定位表冲突（新 provider→`ai/`、新 tool→`core/tools/` 也是功能）。修正为两条：
- **S1a（产品能力）**：`runtime/features/<name>/` 内的产品能力，实现文件只在该目录内；`core`/`platform`/`frontends` 不得静态 import `features.*`。
- **S1b（技术扩展点）**：`ai/`、`core/tools/`、`core/commands/` 的扩展点各自有明确约定，不适用 S1a。

---

## 3. 目标骨架（v2，含 5 处修正）

```
baldric/
├── protocol/                 # 契约层：只放"形状"，不放"行为"（见 §4.1 新规）
│   ├── messages.py
│   ├── provider.py
│   ├── provider_events.py
│   ├── tools.py
│   ├── types.py
│   ├── extension.py          # 【新】ExtensionAPI 契约(Protocol) + 事件类型 + PluginManifest
│   ├── ports.py              # 【新】跨域 port：HookDispatcher / ProviderCatalog / SessionLifecycle / FeatureSetup
│   └── session/
│       ├── entries.py        # 形状（保留）
│       ├── tree.py
│       └── # jsonl.py 移出！它是行为 → runtime/core/session/jsonl.py
│
├── api/                      # 【新·顶层】稳定公共面：只 re-export protocol.*
│   └── __init__.py           # __all__ 按消费方分组 + 公共面治理 docstring
│
├── agent/  ai/  mcp/         # 不动（agent kernel / wire adapters / MCP 客户端核心）
│
└── runtime/
    ├── app.py                # 【新】组合根：构造 ExtensionRuntime，注入 CodingSession
    ├── cli.py                # 瘦身：参数解析 + 模式分派（< 600 行）
    ├── core/
    │   ├── session/          # 原 runtime/session（含 compaction/export + 移入的 jsonl.py）
    │   ├── tools/  commands/  context/
    │   └── rendering/        # 前端共享原语（CustomMessageMarkup 上移 protocol 后只依赖 protocol）
    ├── providers/            # provider 子系统（config+catalog+stores+runtime+auth+backends）
    │   ├── config/ catalog.py loader.py runtime.py stores/
    │   ├── auth/             # 原 runtime/auth
    │   └── backends/         # 原 runtime/backends
    ├── platform/             # 扩展框架（不含插件，不静态 import features）
    │   ├── api.py runtime.py loader.py installer.py provider_registry.py providers.py
    │   ├── features.py       # 【新】静态 FEATURES 声明（先 tuple，不上 registry）
    │   └── catalog.py        # 【新】FeatureCatalog：给 UI 的元数据
    ├── features/             # 产品能力（每个一个目录）
    │   ├── mcp_tools/        # 【改名】原 builtins/mcp，避开顶层 baldric.mcp 重名
    │   ├── subagents/
    │   └── llama_cpp/
    ├── frontends/
    │   ├── tui/              # 原 runtime/tui
    │   ├── rpc/              # 原 modes/rpc
    │   └── print/            # cli 的 print 路径（rendering 的 print 部分见 §3.1）
    ├── config/ observability/ update/ trust/ utils/   # 横切设施（依赖矩阵见 §4.3）
    └── data/ → 迁到顶层 examples/extensions/   # scanner 跳过 data 目录，示例不能被漏
```

### 3.1 `rendering` 的最终裁定（v1 自相矛盾，v2 定死）

**实测**：`rendering/transcript.py:20`、`rendering/__init__.py:7` 依赖 `extensions.api.CustomMessageMarkup`。把 rendering 放 core 且禁 `core→platform`，阶段 E 必红。

**定死方案**：
- `CustomMessageMarkup`（插件渲染契约类型）**上移至 `protocol/extension.py`**（它是形状，属契约层）。
- 上移后 `rendering/` 只依赖 `protocol`，**整体留 `core/rendering`**。
- `frontends/print/` 只消费 `core/rendering` 的 print 渲染器（`base/plain/json/transcript`），**不拥有任何渲染实现文件**。
- **不拆 rendering 文件到 frontends/print。** rendering 是共享原语库，print 和 tui 都是它的消费者。

### 3.2 `ai/` 与 `providers/` 的边界（v1 漏定义，provider 散落没解决）

**实测**：`ai/env.py` 有 `AnthropicConfig`（运行时构造参数：api_key/timeout/thinking_budget），`providers/config/models.py` 有 `AnthropicProviderConfig`（持久化设置：name/models/api_key_env/credential_name）。**两者字段仅约 3 个重叠——这不是重复定义，是"两层配置"**：适配器入参 vs 持久化设置。

**边界规则（v2 新增）**：
- `ai/` = **wire protocol adapter**：请求/响应/流式/重试/适配器入参 `XxxConfig`。不含产品持久化配置。
- `runtime/providers/` = **产品配置层**：持久化设置、catalog、鉴权、模型列表、从持久化设置构造适配器入参。
- **新 provider 的标准落点**：`ai/<name>.py`（适配器）+ `providers/config/models.py` 加 `XxxProviderConfig` + `providers/auth/flows/<name>.py`（若需 OAuth）。**这是两处不同的扩展点，允许。**
- **禁止**：把持久化配置塞进 `ai/`，或把 wire adapter 塞进 `providers/`。

### 3.3 `features/mcp` → `features/mcp_tools`（避开与顶层 `baldric.mcp` 重名）

### 3.4 `protocol/` 只放形状（v2 最重要的新墙）

**实测违规**：`protocol/session/jsonl.py`（271 行 / 12 函数）是 JSONL 解析 + 迁移 + TypeAdapter——**这是行为，不是形状**。按"只放形状"规则它现在就该移出。

**规则（CI 强制）**：
- `protocol/` **允许**：dataclass、Pydantic BaseModel、TypedDict、Protocol、Literal、TypeAlias、常量。
- `protocol/` **禁止**：默认实现（有函数体的方法除 `__post_init__`/validator）、辅助函数、I/O、注册逻辑、模块级单例。
- **例外**：`protocol/session/jsonl.py` 这类"序列化 + 迁移"是行为 → 移到 `runtime/core/session/jsonl.py`。
- **每个 protocol 模块行数预算 400 行**，超了必须拆文件，CI 检查。
- **按模块白名单**（已有 `AI_PROTOCOL_SURFACE` 机制）：每个消费包声明它允许 import 哪些 protocol 子模块。

**为什么这是墙**：`protocol/` 是唯一"人人可依赖"的包，它会自然长大。没有这条规则，10 万行时它是 6000 行的 god module，`api/__init__.py` re-export 300 符号，任何改名都是 breaking——回到今天的起点，只是更贵。

---

## 4. 墙：契约与规则（v2 核心，阶段 A0 就要建）

### 4.1 `protocol/extension.py` + `protocol/ports.py`（解决 core→platform 硬依赖）

**实测的 11 处 core→platform 硬依赖**（阶段 E 会全部违规）：

```
session/lifecycle.py:35   UserBashEvent          → protocol/extension.py
session/lifecycle.py:36   DynamicProvider        → protocol/ports.py (ProviderCatalog)
session/lifecycle.py:37   ExtensionRuntime       → 注入，见下
session/lifecycle.py:314  ExtensionRuntime(...)  ← 构造上移到 app.py
session/model_selection.py:21  DynamicProvider   → protocol/ports.py
session/provider_helpers.py:23 DynamicProvider   → protocol/ports.py
session/resource_helpers.py:38 ExtensionRuntime  → 注入
session/runtime.py:48     SessionBeforeCompactEvent → protocol/extension.py
session/session.py:52-53  DynamicProvider, ExtensionRuntime → protocol/ports.py + 注入
session/session.py:544    BUILT_IN_EXTENSIONS    → 由 app.py 注入 feature 列表
session/session.py:587,687 ExtensionRuntime(...)  ← 构造上移到 app.py
```

**定义三个 port（`protocol/ports.py`）**：

```python
class HookDispatcher(Protocol):
    async def dispatch(self, event: object) -> object | None: ...
    def run_user_bash(self, event: "UserBashEvent") -> object: ...

class ProviderCatalog(Protocol):
    def effective(self, name: str) -> "ProviderRecord | None": ...
    def dynamic_definitions(self) -> tuple["DynamicProvider", ...]: ...

class SessionLifecycle(Protocol):
    def rebind(self, **kwargs: object) -> "SessionLifecycle": ...
```

**注入点**：`runtime/app.py` 构造 `ExtensionRuntime` 与 `ExtensionAPI`，作为参数注入 `CodingSession`。`CodingSession` 只持有 port 类型，不 import platform。

**`FeatureSetup` port（对称生命周期，v2 新增）**：

```python
class FeatureSetup(Protocol):
    def __call__(self, api: "ExtensionAPI") -> Callable[[], None] | None: ...
    #                                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^ teardown disposer
```

现状核查：`register_key_interceptor` 已返回 disposer（好形状），`subagents` 有 `shutdown`——但没有统一契约。v2 要求每个 feature 的 `setup` 返回 teardown，`app.py` 在会话结束时统一调用。**现在只有 3 个 feature，5 行代价；15 个 feature 时每个自己发明关闭方式，CodingSession 里 15 个特判。**

### 4.2 scanner 加 allowlist（现有黑名单表达不了两条核心规则）

**问题（实测）**：现有 `check_import_graph.py` 的 `RULES = tuple[(source_prefix, forbidden_prefix)]` 只能表达"禁止 A import B"。但：
- "feature 只能 import 对方 port" = 白名单（允许 `features.b.port`，禁 `features.b.service`）
- "frontend 只消费 api + protocol + FeatureCatalog" = 白名单

**v2 新增规则类型**：

```python
@dataclass
class AllowRule:
    source: str                        # e.g. "baldric.runtime.features.a"
    target: str                        # e.g. "baldric.runtime.features.b"
    allow: tuple[str, ...]             # e.g. ("port",)
```

**同时补合法允许边（v1 漏写，否则误报）**：
```
features → platform.api         (feature 用 ExtensionAPI)
features → providers.backends   (llama_cpp 用 LocalBackend)
features/mcp_tools → baldric.mcp (MCP 客户端)
frontends → platform.catalog    (TUI 读 FeatureCatalog)
frontends → core.session 的公共 API  (RPC 现在直接 import session，见 §4.4)
```

**lazy import 规则（实测：scanner 用 ast.walk，函数体 import 也会抓）**：`builtin_registry.py:80-114` 5 处函数内 `from ...builtins.xxx import setup`。阶段 E 加 `(platform, features)` 会全部违规。**规定**：只有 `platform/loader.py` 可用 `importlib` 动态加载 features；`platform/features.py` 与 `builtin_registry.py` 只存**字符串路径**（如 `"baldric.runtime.features.mcp_tools:setup"`），不得静态 import feature 模块。

### 4.3 横切设施的依赖矩阵（v1 漏写 5 个顶层设施）

不写清楚，scanner 会漏、未来会出现新环。**8×8 矩阵（行=发起方，列=禁止依赖方）**：

| ↓可依赖→ | config | observability | update | trust | utils | core | providers | platform | features | frontends |
|---|---|---|---|---|---|---|---|---|---|---|
| config | — | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| utils | ✓ | ✗ | ✗ | ✗ | — | ✗ | ✗ | ✗ | ✗ | ✗ |
| trust | ✓ | ✗ | ✗ | — | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| observability | ✓ | — | ✗ | ✗ | ✓ | ✓(只类型) | ✓ | ✓ | ✗ | ✗ |
| update | ✓ | ✓ | — | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| core | ✓ | ✓ | ✗ | ✓ | ✓ | — | ✓ | ✗ | ✗ | ✗ |
| providers | ✓ | ✓ | ✗ | ✗ | ✓ | ✗ | — | ✗ | ✗ | ✗ |
| platform | ✓ | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ | — | ✗(只经 loader 动态) | ✗ |
| features | ✓ | ✓ | ✗ | ✓ | ✓ | §4.4 | ✓ | ✓(api) | 只 port | ✗ |
| frontends | ✓ | ✓ | ✗ | ✗ | ✓ | ✓(公共 API) | ✓ | ✓(catalog) | 只 catalog | 互不依赖 |

（`✓`=允许，`✗`=禁止，`—`=自身）

### 4.4 frontends↔session（RPC 直接持有 session）

**实测**：`rpc/server.py:30`、`rpc/session.py:15-21`、`rpc/wire.py:22-23` 直接 import `session.session` / `SessionManager` / `JsonlSessionStorage`。

**v2 裁定**：**不造 `SessionService` 门面**（评审 §5 自己也说门面会变 god object）。改用**按用例的窄 port**，但**先只做 RPC 已有的形态，不强推**：
- 允许 `frontends` import `core/session` 的**公共方法**（`send`/`cancel`/`branch`/`compact`/`snapshot`/`subscribe`）。
- 规则检查：frontends 不得 import `session` 的 `_private` 名称。
- TUI 向 RPC 的"命令 + 事件"形态靠（长期，非本次强制）。

**理由**：现在只有 2 个前端，RPC 已是正确形态。现在造 3 个 Protocol 是为想象中的第 3 个前端付费，违反"不为一种实现建抽象"。

### 4.5 阶段顺序修正（v1 有环：E 依赖 F 的 api.py）

**v1 错误**：阶段 E 验收要"示例改 `from baldric.runtime.api import ExtensionAPI`"，但 `runtime/api.py` 阶段 F 才建 → E 依赖 F。

**v2 修正（strangler：先挂门牌再搬家具）**：

```
A0（api facade + protocol 契约 + port + scanner 白名单 + 示例路径固定）
 └─> A（规则 + 删重复契约）
      └─> B（subagents 试点）
           └─> C（mcp_tools / llama_cpp）
                └─> D（providers 域）
                     └─> E（platform 抽离）
                          └─> F（app 组合根）
                               └─> G1(tui) / G2(rpc) / G3(print)
                                    └─> H（session 消肿，独立分支）
```

**A0 只做一件事：把公共 import 路径固定下来（`baldric.api` 是兼容 facade，内部先 re-export 旧 `extensions.api`），之后所有搬家都不改路径。** 阶段 E/F 只搬实现，不改公共路径。

---

## 5. 阶段（v2，含原子性铁律）

**铁律**：每个阶段必须**原子完成**（旧路径在同一个 PR 删除），时间盒只限制"是否开始下一阶段"，**绝不停在阶段中间**（半迁移 = 两套结构并存，比不开始还贵）。

### 阶段 A0：墙（1–2 天，零行为变化）｜**已完成 2026-11-12**

实际落地（与下述「原计划」的差异见 §0.1；执行记录见
[../notes/2026-11-12-stage-a0-wall.md](../notes/2026-11-12-stage-a0-wall.md)）：

1. ✅ 建顶层 `baldric/api/__init__.py`，re-export 旧 `extensions.api` 全部符号（兼容 facade，按消费方分组，63 个名字）。
2. ✅ `protocol/extension.py`：只迁**纯形状**——18 个事件/结果 dataclass + 类型别名 + `ExtensionCapabilities` + 事件常量 + Literal；`ExtensionAPI`/`ExtensionContext`/`ExtensionUi`/UI 桥等实现类**留在** `extensions/api.py`（原计划说搬 `ExtensionAPI` 契约，与"纯形状"冲突，已改）。事件 payload 用 `X as X` 形式从 protocol 显式 re-export 回 `extensions/api.py`，46 处消费点零改动。
3. ✅ `protocol/ports.py`：定义 `HookDispatcher` + `FeatureSetup`（原计划的 `ProviderCatalog`/`SessionLifecycle` 因返回类型尚不存在，推迟到 D/E）。
4. ✅ `CustomMessageMarkup`（及 `ToolCallMarkup`/`ToolResultMarkup`/`MessageRenderer` 等别名）定义于 `protocol/extension.py`，`extensions/api.py` 以 `as` re-export；3 个 rendering/tui 消费点零改动。
5. ✅ scanner 加 `AllowRule` + `LAYER_MATRIX` + `scan_allow_violations`（真实目录尚不存在故 0 违规，合成样例 guard 测试证明能报违规）；`baldric.api` 已可作稳定入口（示例改路径留待后续阶段统一）。
6. ✅ `scripts/measure_structure.py`（生成基线，禁手写数字；已据其修正 §1 漂移）。
7. ✅ 新增 guard 测试：`test_protocol_extension_and_ports_pull_no_upper_layer`、`test_protocol_extension_and_ports_contain_only_shapes`（AST 形状闸门 + 自证有牙）、AllowRule 4 个合成样例测试。
8. ✅ **验收**：fast suite 2276 passed / 52 skipped（零行为变化）；`check_import_graph` 0 违规；`baldric.api` 可 import；ruff/mypy 无新增。

> 原计划条目（保留作历史对照）：
> 1. 建顶层 `baldric/api/__init__.py`，先 re-export 旧 `extensions.api`（兼容 facade）。
> 2. `protocol/extension.py`：把 `ExtensionAPI` 契约、事件类型、`PluginManifest` 从 `extensions/api.py` 抽出（先并存，A0 只加不删）。
> 3. `protocol/ports.py`：定义 `HookDispatcher`/`ProviderCatalog`/`SessionLifecycle`/`FeatureSetup`。
> 4. `CustomMessageMarkup` 上移 `protocol/extension.py`；`rendering` 改 import（此时仍可并存）。
> 5. scanner 加 `AllowRule` + 依赖矩阵（§4.3）；示例路径改 `baldric.api`。
> 6. `scripts/measure_structure.py`（生成基线，禁手写数字）。
> 7. **验收**：fast suite 全绿；`check_import_graph` 0 违规；`baldric.api` 可 import。

### 阶段 A：规则 + 删重复契约（1 天）｜**已完成 2026-11-12**

实际落地（执行记录见 [../notes/2026-11-12-stage-a-rules-and-dedup.md](../notes/2026-11-12-stage-a-rules-and-dedup.md)）：

1. ✅ 删重复：`CredentialReader` 唯一真源留 `providers/config/models.py`，`ClosableModelProvider` **改留 `protocol/provider.py`**（原计划"留 `providers/runtime.py`"会造成 extensions↔runtime 循环导入，已修正）。
2. ✅ `protocol/session/jsonl.py` → `runtime/core/session/jsonl.py`；`protocol/session/__init__` 停导出 jsonl；4 处 importer 同步。
3. ✅ 落地 `protocol/` 形状规则 + 每模块 400 行预算：`protocol/extension.py` 拆分出 `extension_events.py`；guard 加「模块分类 ratchet + 400 行预算」。既有协议辅助函数（messages/provider/tools/entries/tree）登记为遗留行为债务白名单（只减不增），迁出列为后续独立任务。
4. ✅ **验收**：fast suite 2277 passed / 52 skipped；protocol 中 **新模块**均为纯形状（既有债务已登记）；scanner/guard 新规则对合成样例能报违规；mypy 无新增。

> 原计划条目（保留作历史对照）：
> 1. 删重复：`CredentialReader`（留 `providers/config/models.py`）、`ClosableModelProvider`（留 `providers/runtime.py`）。
> 2. **`protocol/session/jsonl.py` 移到 `runtime/core/session/jsonl.py`**（它是行为）。
> 3. 落地 `protocol/` 只放形状规则 + 每模块 400 行预算。
> 4. **验收**：fast suite 全绿；protocol 无行为文件；scanner 新规则能报违规。

### 阶段 B：subagents 试点（最散，验证方案）｜**已完成 2026-11-12**

实际落地（执行记录见 [../notes/2026-11-12-stage-b-subagents.md](../notes/2026-11-12-stage-b-subagents.md)）：

1. ✅ `git mv extensions/builtins/subagents/ → features/subagents/`（20 文件）；新增 `runtime/features/__init__.py`。
2. ⚠️ `platform/features.py` 静态 `FEATURES` **推到阶段 E**（`runtime/platform/` 那时才建，提前建是半迁移）。B 用 `builtin_registry` 内 `importlib.import_module("…features.subagents.extension")` 实现解耦。
3. ⚠️ `ExtensionRuntime` 由 app 注入 **推到阶段 F**（组合根 `runtime/app.py` 是 F 产物）。B 只做物理搬迁 + 字符串化，不断开 core→platform（无半迁移）。
4. ✅ tests → `tests/features/subagents/`（14 文件）；helper 路径同步。
5. ✅ **验收（S1a）**：`runtime.core/platform/frontends/extensions` 静态 import `runtime.features.*` = 0（AST 扫描器新增 + 4 个 guard 测试）；subagents 测试 232 passed；fast suite 2282 passed。

> 原计划条目（保留作历史对照）：
> 1. `git mv extensions/builtins/subagents/ features/subagents/`。
> 2. `platform/features.py` 静态声明 `FEATURES`（`setup="...:setup"` 字符串 + `kind`）；`builtin_registry` 改字符串路径。
> 3. `CustomMessageMarkup`/事件走 protocol；`ExtensionRuntime` 由 app 注入（A0 已备好 port）。
> 4. tests → `tests/features/subagents/`（**不放 src 内**，见 §6）。
> 5. **验收（S1a）**：`core/platform/frontends` 静态 import `features.*` = 0（AST 检查，非 grep）；10 个 subagents 测试全过；fast suite 全绿。

### 阶段 C：mcp_tools / llama_cpp｜**已完成 2026-11-12**

实际落地（执行记录见 [../notes/2026-11-12-stage-c-mcp-llamacpp.md](../notes/2026-11-12-stage-c-mcp-llamacpp.md)）：

1. ✅ `builtins/mcp → features/mcp_tools`、`builtins/llama_cpp → features/llama_cpp`；删除空 `extensions/builtins/` 包。
2. ✅ `builtin_registry` 统一 `_load_feature_setup`（importlib 字符串路径）；5 个 setup 包装全改；name 不变、行为不变。
3. ✅ 测试搬 `tests/features/{llama_cpp,mcp_tools}/`；`test_phase6_hardening.py` 保留 `tests/` 根（通用硬化套件）仅改导入；conftest 的 Windows-skip nodeid 同步。
4. ✅ **验收**：fast suite 2282 passed；TUI 767 passed；S1a 静态 import features = 0；mypy 无新增；两基线纯路径重命名（supp 138 不变）。

> 原计划：阶段 C：mcp_tools / llama_cpp —— 「同 B。llama_cpp 验证只依赖 `providers/backends` 契约。`bgrep` 核心层无功能名（smoke）。」

### 阶段 D：providers 域合并

`git mv auth/ → providers/auth/`、`backends/ → providers/backends/`。更新 import。

### 阶段 E：platform 抽离

`extensions/{api,runtime,loader,installer,provider_registry,providers,builtin_registry} → platform/`。`extensions/__init__.py` 247 行按消费方拆。

### 阶段 F：app 组合根

从 `cli.py` 抽装配到 `runtime/app.py::build_app(config)`。`cli.py` 1,411 → < 600 行。

### 阶段 G：frontends 收口（拆三步，G1/G2/G3）

- **G1**：`tui/ → frontends/tui/`（40 文件 16.8k 行，单独提交，Linux CI 绿）
- **G2**：`modes/rpc/ → frontends/rpc/`
- **G3**：cli print 路径 → `frontends/print/`（import core/rendering，不搬渲染实现）

### 阶段 H（独立分支）：session 消肿

照 OpenHands `conversation/{base,impl,goal,state,cancellation}` 形态：门面 + 单职责文件 + 子功能目录。`session.py` 1,864 行 / 183 方法 → < 500 行。**验收**：公共方法签名零变化；fast suite 全绿；**S1 到此时才完全成立**。

---

## 6. 决策点（v2 修订）

### 6.1 `runtime/__init__.py` 313 行 `__all__` + feature tests 打包

- `baldric/api/` = 稳定公共面（re-export protocol）。
- `runtime/__init__.py` 瘦身（只 `__version__` + 必要符号）。
- **feature 测试放 `tests/features/<name>/`（不放 src 内，避免打进 wheel 与 scanner 误扫）**。v1 的"放 features/<name>/tests/"撤回。
- 老命令 `pytest tests/runtime/extensions/test_subagents_*` 失效 → CI/文档同步更新。

### 6.2 兼容 shim 的纪律（shim 最易变永久债）

旧路径保留 `__getattr__` shim，但**必须带三样**：
1. 收缩型 baseline：CI 记录旧路径使用点数，**只减不增**。
2. 带日期的删除项（写版本号，不写"以后"）。
3. 文档/示例同时改新路径。

### 6.3 FeatureCatalog 先静态 tuple，不上 registry 三件套（v2 修正 v1）

v1 借鉴 OpenHands 的 `_REG/_USABILITY_REG/ToolCatalogEntry` 三件套——**对 3 个 feature 是过度设计**（多 300–500 行、多间接层、多"注册表与目录不一致"故障模式），违反 §2"不为一种实现建抽象"。

**v2 改为静态声明**：
```python
FEATURES: tuple[FeatureSpec, ...] = (
    FeatureSpec("mcp_tools", kind="integration", setup="...mcp_tools:setup"),
    FeatureSpec("subagents", kind="capability", setup="...subagents:setup"),
    FeatureSpec("llama_cpp", kind="backend", setup="...llama_cpp:setup"),
)
```
`FeatureSpec` **无 `order` 字段**（整数顺序在 20 个 feature 时必然退化成 float/字符串，是"3 个最省事、30 个最没用"的典型；现在 3 个 feature 无 hook 顺序依赖，不加）。`kind` 字段区分 capability/integration/backend（否则 TUI 会把 llama.cpp 后端显示成可开关的"功能"）。加校验测试：每个 `features/*` 都有条目。**feature ≥ 6 或需外部插件时才升级 registry。**

### 6.4 阶段 H 延后 → S1 的诚实表述

A–G 只验收 **S1a**（core 不 import features 实现）；**S1（含 session 耦合）到 H 完成才成立**。§9 会标注。

---

## 7. 验收表（v2，可机器验证的才留）

| 编号 | 标准 | 验证方式 | 可机器验证？ |
|---|---|---|---|
| S1a | core/platform/frontends 不静态 import features.* | **AST scanner**（非 grep） | ✅ |
| S1b | 技术扩展点各自约定 | 文档 + 规则 | 部分 |
| S1 | 含 session 的完整内聚 | 阶段 H 后 | ⏳ 延后 |
| S2 | 分层 import 纪律 | `check_import_graph` 0 违规 + AllowRule + 依赖矩阵 | ✅ |
| S3 | 行为不变 | fast suite **测试数不减少**（非固定 2265）+ 无断言降级 | ✅ |
| S4 | 公共面=protocol re-export | `baldric/api` 只 import protocol（CI） | ✅ |
| S5 | 新功能可定位 | **人工评审**（非机器） | ❌ 人工 |
| S6 | 无回归禁止项 | 不改断言/不加 skip/不降级 | ✅ |
| S7 | Feature 注册完备 | 每个 features/* 有 FEATURES 条目（校验测试 + `kind`） | ✅ |
| S8 | feature 级 teardown | 每个 setup 返回 disposer 或被调用（校验测试） | ✅ |
| S9 | 多会话隔离 | 同时起 2 会话，断言 feature 状态对象不同 | ✅ |
| S10 | protocol 只放形状 | 无行为文件 + 每模块 ≤400 行（CI） | ✅ |

---

## 8. 风险与缓解（v2，补 4 个真实风险）

| 风险 | 后果 | 缓解 |
|---|---|---|
| re-export 破坏（139+116 符号） | 大量测试/示例断 | A0 先建兼容 facade；shim 带收缩 baseline（§6.2） |
| feature tests 打进 wheel | 包变大、pytest 进运行时 | 放 `tests/features/` |
| Linux-only TUI gate | 本地绿、CI 红 | **每阶段 PR 必须 Linux CI 绿才合并**（不等最后） |
| registry 过度设计 | 3 feature 配 300–500 行基础设施 | 静态 tuple（§6.3） |
| 半迁移状态 | 两套结构并存 | 原子完成铁律（§5） |
| 4 周上限停在阶段中间 | 半迁移 | 时间盒限制"开始"不限制"完成"（§5） |
| `check_structure --init` 全量重生掩盖变化 | 非预期 rename 被吞 | 改 `--update` + 断言"文件集合 diff 只含预期 rename" |
| protocol 长大成 god module | 回到今天起点 | §3.4 只放形状 + 400 行预算 + 白名单 |

---

## 9. 闭环表（v2 诚实版）

| 你提出的问题 | 实际结果 | 阶段 |
|---|---|---|
| 加功能散落 5–6 目录 | **部分**：产品能力解决；provider/tool/command 按技术层（§3.2 定义边界） | B–C |
| 技术层与功能域混杂 | **完全** | B–E |
| extensions 框架与插件同居 | **完全** | E |
| 公共 API 埋在 1335 行 api.py | **部分**：`baldric/api` 稳定，但依赖 protocol 治理（§3.4） | A0/F |
| 同一契约两处定义 | **完全** | A |
| session god class | **延后** | H |
| 将来几十万行又出问题 | **部分**：层次规则能防；session 膨胀靠 H；protocol 长大靠 §3.4 预算 | 全程 |

---

## 10. OpenHands 参考对照（v2 修订）

**值得学（已并入）**：分层规则脚本形态（`check_import_rules.py`）、provider 子系统内聚切法（`llm/{auth,options,router,exceptions,utils}`）、受控 `__all__` + 分组 + deprecation 治理、门面+impl 拆 god class（`conversation/`）。

**不学**：多 distribution 多包结构（baldric 不发独立包）、深度绑定 LiteLLM（baldric 自研 5 适配器）、Pydantic DU mixin 全家桶（protocol 已有 WireModel + 联合类型）。

**v2 修正**：`_REG/_USABILITY_REG/ToolCatalogEntry` 三件套 **不学**（3 个 feature 时过度设计），改静态 `FEATURES` tuple。

**撤回（更早的建议）**：不抽 `baldric-tui` 独立发行包。同一发行包内目录隔离 + `[project.optional-dependencies] tui=[...]` 即可。拆包是为独立发布节奏，不为架构边界；以后想拆容易，拆了想合回难。

---

## 11. 工期（硬上限 4 周，只限"开始"）

| 阶段 | 预估 |
|---|---|
| A0 墙 | 1–2 天 |
| A 规则+删重复 | 1 天 |
| B subagents 试点 | 2–3 天 |
| C mcp_tools/llama_cpp | 2–3 天 |
| D providers | 1–2 天 |
| E platform | 2–3 天 |
| F app | 2 天 |
| G1/G2/G3 frontends | 4–6 天 |
| **A–G 合计** | **≈ 3–4 周** |
| H session 消肿 | 独立分支，不设硬上限 |

**铁律**：4 周是"是否开始 G/H"的闸门，不是"必须压缩"的目标。每个阶段原子完成后才进下一阶段。

---

## 12. 前置条件

1. 当前工作树有上一轮 P2 修复的**未提交改动**（`git status` 见 google/mistral/openai_codex/mcp/credentials/settings/runtime/protocol 等 + 新测试 + 新文档）。**先提交 P2 修复**，或另存 stash，再开重构分支 `refactor/structural-v2`。
2. 每个阶段一个 PR，Linux CI 绿才合并。
3. 所有行数/符号数由 `scripts/measure_structure.py` 生成。
