# ADR：session 准备与动态 provider 生命周期

- **状态：** issue #602 Phase 0 已接受
- **日期：** 2026-08-18
- **范围：** 仅架构与当前行为刻画
- **实现：** 后续阶段；本 ADR 不添加任何动态 provider、built-in extension、`/local` 或 llama.cpp 运行时代码

## 这个决策为什么存在

Baldric 目前要求两个 frontend 在 `CodingSession.load()` 之前选择并构建模型 provider。Extension 在 `CodingSession.load()` 内加载，那时 provider 已存在。因此 extension 无法供给一个按命令行选择或从 session 恢复的 provider。

只修这个顺序是不安全的。启动、reload、resume、new-session、
分支、信任、模型切换、transcript 持久化、extension 世代与 provider 清理在同一个边界交汇。本 ADR 在生产行为变更之前定义这条边界。

历史 PR #352 与 #417 仅作为证据参考。两个 PR 的代码与分支均不复用。特别是，本设计否决 PR #417 的进程级 provider/extension registry 假设。

## Pi 兼容性核对

在已接受计划的 pin
`eb1f87fa9a29e27e0c63dcb40dbed9a3624c82b1`（2026-08-17）重新核对了 Pi。审计期间观察到的上游远程
HEAD 是 `2509b5c037d366979f2febfce4174b88aeaadc6a`；该 pin 仍是本阶段可复现的架构参考。

被 pin 的实现确认了 Baldric 应当遵循的模式：

- extension provider 注册在正常模型使用之前到达模型 runtime；
- extension context 在替换/reload 之后失效；
- `session_shutdown` 先于世代 teardown，`session_start` 跟随替换；
- 有响应活动时交互 reload 拒绝运行；
- llama.cpp 协议与管理行为位于打包 extension 内。

Baldric 在其架构要求之处刻意不同：全新的 cwd/信任绑定 registry、`/local` 而非 `/llama`、无假认证、单模型
服务器支持、不猜元数据、不静默卸载，以及下文的持久提交/不失败发布协议。

## 当前 main 审计

审计基线是 Baldric `9c1285d68f41059105bd8a834d309a4d601a3b07` 加已接受的 #602 计划提交。相关代码在：

- `src/baldric_coding/cli.py`
- `src/baldric_coding/tui/app.py`
- `src/baldric_coding/session.py`
- `src/baldric_coding/project_trust.py`
- `src/baldric_coding/extensions/runtime.py`
- `src/baldric_coding/provider_config.py`
- `src/baldric_coding/provider_runtime.py`
- `src/baldric_agent/session/`

### 今天的启动

print 启动目前这样做：

```text
load durable ProviderSettings
→ resolve record and provider/model
→ create provider
→ CodingSession.load(provider=...)
→ install stderr extension UI
→ emit pending session_start
→ run prompt
→ close CodingSession-owned replacement providers
→ frontend closes the original provider
```

TUI 启动遵循同样的 provider 优先顺序。provider 构建失败时，只有 TUI 换上 `LoginRequiredProvider`；print mode 失败。TUI 随后创建或解析其 session 记录并调用 `CodingSession.load()`。显式的 TUI 与 print resume 在可用时使用记录的 provider/model 锚。

`CodingSession.load()` 已有有用的 staging 行为：

1. 读 transcript 并推导活动叶。
2. 创建全新的、cwd 绑定的 `ExtensionRuntime`。
3. 加载用户与显式 extension，排除项目 extension。
4. 解析项目信任。
5. 构建连贯的受信任或不受信任资源计划。
6. 只在批准后加载选择加入的项目 extension。
7. 组合工具、命令、guideline 与 system prompt。
8. 构建并绑定 harness。
9. 把 `session_start` 推迟到宿主装好 UI 桥。

此序列中没有已知路径会在目标信任决定之前导入项目 extension 代码。这条不变量必须在抽取中幸存。

然而 `load()` 不是完整的准备事务。它会持久化工具历史修复并发现运行时模型限制。它还接收一个已构建的 provider，并可能从持久设置替换它。初始 provider 所有权因此分裂在 frontend 与 session 之间。

### 今天的替换与 reload

reload 与目标替换 stage 一个全新 extension runtime。取消或准备失败通常保留退场 session。项目信任缓存发布推迟到采纳，但一个已保存的 UI 选择目前在解析期间就写入 `trust.json`，而不是与采纳一起 stage。

当前发布序列仍有缺口：

- 生命周期回调在一次同步字段交换之前运行，但尚未成为形式化的被包容不失败区；
- 目标 transcript 修复可能在准备期间写入；
- transcript 初始化/model/叶写入不是一次原子批次；
- session 索引写入未被显式归类为可修复缓存写入；
- 替换 provider 所有权分裂；
- `new_session()` 与 `resume()` 自身不强制空闲 harness；TUI 目前在调用某些替换前取消活动运行；
- 分支替换确实拒绝活动运行。

### 今天的模型选择与恢复

`ModelChangeEntry` 只存 `model`。provider 身份活在可重建的
session 索引记录里。因此回放能在所选分支恢复模型，但无法无歧义恢复跨 provider 分支。当前分支测试展示了后果：状态可以回放较早的模型，而配置的 runtime 仍锚在记录的 provider/当前模型上。

跨 provider 选择在改动活动 provider 之前先创建候选，runtime 构建失败保住旧组合。同 provider 选择是先改动。选择写持久默认与索引元数据，但普通 picker 切换不原子地追加 provider/model 历史加叶。

### 今天的清理

session 切换创建的 provider 保存在 `CodingSession._owned_providers`，最终 session 关闭时关闭。print/TUI 启动构建的 provider 归 frontend 所有、由 frontend 关闭。这个分裂解释了重复的清理职责，不能在共享准备服务中幸存。

## 决策

### 1. 三个显式准备阶段

Phase 3 创建 `src/baldric_coding/session_preparation.py`。它拥有一次请求，返回带幂等 `adopt()` 与 `abort()` 的 `PreparedCodingSession`。

#### state 阶段

- 解析新或既有 session 记录与规范化的目标 cwd。
- 在 session 锁下读 transcript/session 状态。
- 确定活动叶、legacy provider 锚、staged 修复/初始 entry。
- 不创建 provider、不加载项目内容、不写权威 JSONL。

#### environment 阶段

- 创建全新的目标 `ExtensionRuntime`。
- 先加载受信任 built-in，然后用户与显式 extension。
- 检测受保护项目输入并解析信任。
- 只有在信任之后，才加载项目资源与选择加入的项目 extension。
- 恢复安全的内置快照并组合有效的持久/动态 provider 视图。
- 不为无关 provider 做网络刷新。

#### runtime 阶段

- 对照有效视图解析 provider/model。
- 仅当没有安全快照能满足请求时，刷新显式要求的休眠 provider。
- 在构建候选之前立即解析认证。
- 创建 provider、harness、coding session 与缓冲的 frontend 附着。
- 返回未做权威 transcript/索引写入的准备好的候选。

既有直连 `CodingSession.load(provider=...)` 接缝保留为测试与嵌入式静态 provider 消费者的兼容包装。CLI 与
TUI 必须使用共享准备服务；两者都不得重建这个顺序。

### 2. 信任顺序固定

environment 阶段保持此顺序：

```text
built-in/user settings
→ built-in, user, and explicit extension setup
→ metadata-only project detection
→ override / eligible extension / saved / default / UI trust resolution
→ trusted project resources
→ opted-in trusted project extension setup
→ provider snapshot restoration and effective composition
→ optional requested-provider refresh
```

项目 extension 不能在信任之前自我批准或自我注册。信任仍是输入加载守卫，不是进程、文件系统、凭据、网络、provider
或模型沙箱。

### 3. registry 是世代局部的

每个 staged `ExtensionRuntime` 恰好拥有一个动态 provider registry 与
一个本地 backend registry。registry 不是进程全局的，绝不跨目标 cwd、reload、resume 或 new-session 准备共享。

每条注册携带：

- 稳定来源身份；
- extension/runtime 世代身份；
- provider 层身份。

退役一个世代会取消其任务并只移除其注册。来自旧来源/层/世代 token 的发布被拒绝。持久 provider 设置是不可变的基线输入，不是动态 registry。

动态 provider 优先级是有意的最近活动层优先：

持久基线、built-in、用户、显式、受信任项目。移除一层会露出前一个完整定义。

### 4. 本地 backend 绑定到来源拥有的 provider 层

本地 backend 绑定到同一来源与世代注册的 provider 层，而不只是 provider ID 字符串。若另一来源遮蔽该 provider ID，backend 可以显示状态/配置，但不能选择、reset 或改动遮蔽层。reset 只移除来源拥有的状态、
注册、快照与凭据引用。

这条来源绑定在 `/local` 存在之前就是强制的。

### 5. 准备有唯一的所有权账本

所有权只在显式转换点变化：

| 资源 | 准备期间 | 采纳后 | 中止时 |
| --- | --- | --- | --- |
| 候选 provider | `PreparedCodingSession` | `CodingSession` | 恰好关闭一次 |
| extension/provider registry | `PreparedCodingSession` | `CodingSession` | 恰好退役一次 |
| 刷新/任务 | staged 世代 | 采纳世代 | 取消并等待 |
| 退场 session 资源 | 退场 `CodingSession` | 发布后退役 | 保持存活 |
| frontend 桥 | 缓冲的候选附着 | 活动 frontend | 丢弃缓冲 |

Frontend 不关闭被采纳的 provider。`CodingSession.aclose()` 是唯一的最终所有者路径且幂等。失败的切换只关闭其候选。
成功的切换在发布后关闭被替换的 Baldric 自有 provider。外部 llama.cpp 服务器进程与模型文件永远不归 Baldric 所有。

### 6. 采纳与中止协议

准备是可逆的。在持久提交之前，任何错误/取消都调用 `abort()`，关闭 staged 资源，不提交任何信任决定，退场 session 与目标 transcript 保持不变。

采纳做这些：

1. 要求退场 harness 空闲。
2. 以缓冲模式接上候选 frontend 桥。
3. 原子追加完整的 staged transcript 批次。其最后一条非叶 entry 成为活动尖，即持久提交点。
4. 进入串行化的不失败发布边界。
5. 替换场景下，在其 API 仍有效时发出退场 shutdown 并清空其 UI；handler 失败成为诊断。
6. 同步交换活动 frontend 的 session 引用。
7. 附着/冲刷候选 UI 并发出 `session_start`；失败诊断。
8. 为未来操作提交 staged 信任；失败对未来的运行 fail-closed，但不回滚这次已批准的运行。
9. 修复/更新 session 索引；失败诊断并稍后修复。
10. 退役退场 provider、任务与 extension 世代。

步骤 3 之后，预期的 extension、UI、信任库与索引错误不会作为普通回滚失败逃逸。步骤 3 之后崩溃留下完整的最后 entry，下一次 resume 按文件顺序选中它。

`abort()` 幂等。`adopt()` 与 `abort()` 是互斥的状态转换。

### 7. transcript 是权威；索引可修复

给 `ModelChangeEntry` 加可选 `provider`。每次新的初始选择与切换都写它。provider/model 变更本身成为活动的文件顺序尖。

选择优先级：

1. 显式 CLI provider/model 覆盖；
2. 活动 transcript 路径上最近的 provider 感知模型 entry；
3. 仅当路径历史没有时，session 索引 provider 作为 legacy 锚；
4. 新 session 的持久默认；
5. 新 session 的第一个有凭据可用持久 provider；
6. 仅 TUI 的 login-required 引导。

动态本地 provider 只经显式选择、稳定的
session 引用或会话内动作参与。它们绝不悄悄进入步骤 5。

append-only transcript 胜过过期索引元数据。索引更新失败不能使已提交的切换失效；之后的启动从 transcript 修复索引。legacy entry 保持可读且不被改写。没有 provider 身份的历史跨 provider 分支天然歧义，使用记录的最佳 legacy provider 锚。

### 8. 切换与替换只在空闲时允许

模型/provider 切换、reset、reload、resume、new-session、cwd 替换
与分支在 harness 运行中一律拒绝，并指引先取消。
它们不关闭或替换在途 provider。取消不假设等于已排水；未来的 cancel-and-drain API 只有在流与工具都结束后才可放宽。

切换事务候选优先：

```text
validate effective provider/model
→ create candidate provider
→ prepare history/thinking/route/image state
→ append provider-aware ModelChangeEntry as the new file-order tip
→ synchronous no-fail in-memory publication
→ repairable index update
→ close replaced provider
```

批次之前的任何失败都让 provider、model、thinking、route、索引、
transcript 与活动 runtime 保持不变。

### 9. 内置 provider 标识与共存

规范的内置 provider ID 与显示名是 **`llama.cpp`**。
名为 **`llama-cpp`** 的既有用户目录 provider 保持独立，不因名字归一化而被迁移、改写、隐藏或遮蔽。CLI/session
ID 是确切字符串；标点不做规范化。

用户也可以定义持久的 `llama.cpp` 层。正常层优先级生效，诊断指明有效来源。移除动态层露出完整的持久定义。通用内核代码不得按 llama.cpp 标识分支。

### 10. 稳定的 scoped 引用

内置 llama.cpp 的 scoped 引用使用既有的确切组合：

```json
{"provider": "llama.cpp", "model": "<server-reported-id>"}
```

它不存端点、provider 定义、headers、凭据、发现的
元数据、路由状态或文件路径。最初只有受信任 built-in 可以选择加入这个宿主定义的持久引用方案；用户/项目动态 provider 不行。

解析只在受信任内置来源及其端点键控的
安全快照/活动目录可用之后发生。缺失、过期、sleeping 或 unloaded 的模型在 scoped 引用管理处保持可见为不可用/惰性。
它不合成模型、不探测网络、不下载、不加载、不切换。

### 11. 其余的有界选择

这些选择为后续阶段固定：

- 模块名：`session_preparation.py`、`extensions/provider_registry.py` 与
  `local_backends.py`；
- 内置状态路径：`BaldricPaths.home / "state/extensions/llama.cpp.json"`；
- 具名刷新超时默认：启动解析 5 秒、显式 `/model` 刷新 10 秒、`/local` 操作 15 秒；
- 恢复 llama.cpp session 既无安全快照也无成功刷新时：以可执行的 setup/重试指引失败；绝不回退或擦除其稳定引用；
- Phase 6 真实适配器 spike：Ollama，因为其 API/能力与 llama.cpp 不同且本地容易伪造；
- 隐藏 built-in：计入详细的 `/session` 诊断（来源 `built-in`），从普通安装/发现计数中省略；
- 安全状态 schema：不支持的版本是只读错误，绝不破坏性重写。

超时保留先前的安全快照并记录一条有界诊断。这些数字是默认值，不是协议承诺。

## 后果

### 正面

- TUI 与 print 可以选择 extension provider，而无需复制信任顺序。
- 项目代码仍不能在信任之前执行。
- provider/任务清理有唯一所有者。
- resume 与分支变得 provider 感知。
- 持久 transcript 提交与内存发布有了可测试的边界。
- 既有的 `llama-cpp` 自定义 provider 保持兼容。
- `/local` 保持 provider 中立与来源安全。

### 代价

- session 存储需要原子批次追加与跨进程锁。
- frontend 附着需要缓冲与被包容的诊断。
- `CodingSession.load()` 必须拆分而不丢其静态 provider 接缝。
- legacy 跨 provider 分支无法在不重写历史的前提下消除歧义，而本设计禁止重写。

## 特征化基线

Phase 0 测试有意在重构前描述当前行为：

- print 启动与 resume 选择；
- TUI 启动、显式 resume 与 login-required 引导；
- 启动、reload、new 与目标采纳期间的项目信任取消；
- 全新 runtime 的 reload/new/resume 行为；
- 分支模型恢复与活动运行拒绝；
- provider 构建失败保住活动的跨 provider 选择；
- 当前所有权接缝处的 frontend/session 清理；
- `llama.cpp` 与 `llama-cpp` 标识的确切共存。

一些测试暴露本 ADR 将取代的行为，特别是 provider 先于 extension 的
启动、分裂的初始 provider 所有权、只有 model 的历史，以及 TUI 替换前取消。新事务落地时，后续阶段必须更新那些测试，而不是偶然保留过时行为。

## 验证

Phase 0 运行交接的重点生命周期 pytest 文件、Ruff check、Ruff
format check 与 mypy。不需要活动 provider、本地服务器、历史分支或 secret。
