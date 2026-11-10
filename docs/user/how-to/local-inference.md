---
title: llama.cpp 本地推理
description: 通过 /local 配置 Baldric 内置的 llama.cpp backend。
---

Baldric 把 llama.cpp 作为受信任的隐藏内置本地 backend 一起交付。provider 中立的入口是 `/local`；不存在 `/llama` 或 `/llama-cpp` 命令。内置 provider ID 是 `llama.cpp`，有别于早期用户自建的 `llama-cpp` 目录 provider。

## 启动 llama.cpp

用它的官方
[server quick start](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md#quick-start)
单独安装 llama.cpp。Baldric 推荐为 `/local` 的模型下载/加载/卸载管理使用[路由模式](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md#using-multiple-models)：**不带**模型参数启动服务器。这个保守的单用户基线保持一个模型和一个推理槽常驻：

```bash
llama-server \
  --models-max 1 \
  --parallel 1 \
  --flash-attn auto
```

有些安装把同一入口暴露为 `llama serve`。裸 `llama-server` 也能用，但其默认允许最多四个已加载模型并自动选择槽位数量。单模型服务器仍支持推理，但不暴露路由管理：

```bash
llama-server -hf <tool-capable-gguf>
```

没有普遍最优的命令。对单个交互式 Baldric 用户、内存/显存充足且模型支持 65,536-token context 的情况，只有确认装得下才使用长 context 配置：

```bash
llama-server \
  --models-max 1 \
  --parallel 1 \
  --ctx-size 65536 \
  --flash-attn on \
  --cache-type-k q8_0 \
  --cache-type-v q8_0
```

- `--models-max 1` 限制的是同时加载的模型数，不是可下载的模型数。
- `--parallel 1` 把 context/KV cache 给一个请求，而不是把内存花在并发槽位上。
- `q8_0` KV cache 比 `f16` 默认省内存，保真度高于更低位的 cache 类型。
- `--ctx-size 65536` 仍可能超过硬件或模型上限；加载失败先调小它。
- `--flash-attn auto` 可移植；仅在受支持的后端上强制 `on`。

采样与推理选项是模型行为，不是普适的性能设置。`--min-p 0` 关闭 llama.cpp 默认的 min-p 采样器。`--reasoning-effort medium`（或较旧的 template-kwargs 等价物）与 `--reasoning-preserve` 只应与支持它们的模板一起使用。先查模型卡、运行 `/local` → Doctor，而不是把这些旗标应用到每个模型。

默认端点是 `http://127.0.0.1:8080`。Baldric 不安装、启动、停止或扫描 llama.cpp。Baldric 使用期间保持服务器运行。在兼容的路由模式下，Baldric 可以明确请那台独立服务器下载选定的 Hugging Face 模型；Baldric 自己绝不写或删除模型文件。

## 配置 `/local`

启动 Baldric 并输入：

```text
/local
```

选择推荐的 `llama.cpp` backend 并确认，即使它是唯一的 backend。Baldric 立即探测已保存端点、`LLAMA_BASE_URL` 或默认 `http://127.0.0.1:8080`。用 **Configure** 配置别处的服务器 URL（带或不带 `/v1`）与可选 API key。Baldric 只探测那一个生效端点；它从不扫描端口、进程或本地网络。

端点优先级为：

1. 通过 **Configure** 提交的 URL；
2. 已保存端点；
3. 当前进程的 `LLAMA_BASE_URL`；
4. `http://127.0.0.1:8080` 作为提供的默认。

打开已确认的 backend 触发探测。探测提供的默认值会让发现的模型对当前 Baldric 进程可用但不保存端点；要持久化用 **Configure**。成功发现使用 `/v1/models` 的确切 ID，从不需要假模型 ID。

### 认证

用可选 key 的三种方式之一：

- 通过 `/local` 的 secret 字段输入；Baldric 存到 `~/.baldric/credentials.json`；
- 设 `LLAMA_API_KEY` 做纯环境变量配置；
- 两者都留空，对接未认证服务器。

已存 key 优先于 `LLAMA_API_KEY`。没有 key 时 Baldric 不发送 `Authorization` header。key 绝不进入 llama.cpp 状态文件、session、导出或诊断。见[项目信任与安全](/how-to/project-trust/#安全边界)。

## 选择模型

设置完成后，`/model` 显示服务器报告的模型 ID 与显示名。用脚本或新 TUI session 时显式启动：

```bash
baldric --provider llama.cpp --model <model-id>
baldric --provider llama.cpp --model <model-id> --print "summarize this project"
```

print mode 与 TUI 都在验证显式选择之前加载内置 provider。已保存的安全快照可以在服务器暂时宕机时维持显式启动。可用模型多于一个时，无头启动要求确切的 `--model`；Baldric 绝不静默改选别的显式模型。本地推理不是自动的全局 provider 回退。

图片输入跟随服务器的报告。模型的 `/v1/models` 条目在 `architecture.input_modalities` 里列出 `image`（llama.cpp 以 `--mmproj` 启动视觉投影器时上报）就会接收图片，例如来自 read 工具。上报的 `audio` 与 `video` 输入被忽略，因为 Baldric 不发送它们。对在 `/v1/models` 里没有报告可用输入的旧单模型服务器，Baldric 检查 `/props.modalities.vision`。两个端点都报告不出可用能力时，模型按纯文本处理；用 [`catalog.toml`](/how-to/providers-and-models/) 条目声明其图片输入。

安全集成快照存放在
`~/.baldric/state/extensions/llama.cpp.json`。它只包含归一化端点、选定模型引用、允许列表内的模型元数据和时间戳。文件带版本、加锁、原子替换且私有。动态 provider 定义绝不拷贝进 `catalog.toml` 或 `providers.json`。

## 路由模型管理

不带模型启动的新版 `llama-server` 运行在路由模式。只有当 `/props` 识别出路由且 `build_info` 处于已测试的 **b9688–b10595** 区间时，Baldric 才启用管理。未知、更旧或更新的 build 安全降级到 `/v1/models` 发现：推理仍可用，但 Baldric 不发任何路由变更。单模型服务器完全受支持。

自动探测或 Refresh 确认兼容路由后，`/local` 在专属模型区块里列出 loaded、sleeping、unloaded、loading、downloading、failed 与 unknown 服务器状态。单独的 actions 区块包含 Hugging Face 搜索/下载、配置、Refresh、Doctor 与 reset。方向键在两个区块内及之间移动，Tab 直接切换区块。只有聚焦区块显示 `focused` 标记、accent 边框与高亮行，Enter 的目标因此明确。只有 loaded 或 sleeping 模型进入 `/model`。处于 `unloaded` 状态的路由模型标注为**可加载**；按 Enter 审阅加载确认。对 loaded/sleeping 行按 Enter 提供使用或卸载。动作始终显式：

- 确认 unloaded 行会等到刷新后的路由状态报告 loaded 或 sleeping。若有其他活动模型，选择保留还是卸载它们；Baldric 绝不替共享路由做决定。取消预选为安全默认，但不标注为推荐。
- **Unload model** 要求模型专属确认。
- **Search Hugging Face models…** 接受模型 ID 或搜索文本，然后打开可用方向键导航的仓库/量化列表，含门控与报告大小。`Q4_K_M` 仅作为 UI 偏好标为推荐，不持久化为模型元数据。
- **Download an exact Hugging Face model…** 接受 `owner/repository[:quantization]`。搜索与确切 ID 两条路径都会打开单独确认，先展示选定模型与已知大小再请求服务端下载。传输期间，`/local` 显示整宽块状进度条、已传输与剩余字节。关闭 `/local` 只脱离传输不停止 llama.cpp。重开会刷新服务器状态、重新附着最新字节进度，并提供 **Cancel active download…**
  显式停止下载。完成后，过期的传输文字与进度条被清除，模型立即显示为**可加载**。

进度有界且显式可取消。llama.cpp 文档把 `/models/unload` 定为加载/下载的取消操作，Baldric 据此请求然后刷新。超时或断连时 Baldric 尽可能刷新且绝不重放被中断的 POST；手动重试前先检查状态。Baldric 绝不在没有显示决策的情况下恢复、卸载、下载或删除模型。

### Hugging Face token 与受限仓库

Baldric 只在 Hugging Face **搜索/详情**请求中使用 `HF_TOKEN`、`$HF_HOME/token` 或标准 Hugging Face token 文件。它不保存这个 token、不拷贝进集成状态、也不转发给 llama.cpp。受限仓库需要先在 `huggingface.co` 接受条款。

独立运行的 llama.cpp 服务器执行下载，所以那台服务器进程需要在自己的环境里有授权的 `HF_TOKEN`。Baldric 侧搜索成功不代表服务器能下载受限模型。

## scoped llama.cpp 模型

已加载或 sleeping 的 llama.cpp 模型可以通过 `/scoped-models` 添加和移除，然后像普通 scoped 模型一样从 `/model` 选择或轮换。Baldric 只持久化 `{provider: "llama.cpp", model: "<exact-id>"}`；动态 provider 定义、端点、凭据与元数据不进入 `providers.json`。

如果其他客户端卸载了模型，它的 scoped 行保持可见为**不可用**。它是惰性的：选择或轮换不能合成模型、联系 Hugging Face 或触发路由加载/下载。通过 `/scoped-models` 移除，或经 `/local` 与 Refresh 显式加载模型。

## 状态与 Doctor

`/local` 提供状态与刷新。Refresh 原子发布完整模型快照。临时宕机保留最近的安全快照并标记过期；它不会擦除活动 provider，也不阻塞无关 provider。如果服务器停止报告活动模型，Baldric 保持当前 runtime 可用、把快照标为过期，且在原模型恢复后不未经显式选择就提供替代模型。

Doctor 是显式动作。它报告端点可达性、模型发现、流式、tool schema 接受度与观察到的 tool 调用发射。能流式但不发出探测工具的模型收到兼容性警告而非连接失败。工具调用不可用时，使用具备工具能力的 instruct 模型和服务器的必要 chat-template 选项。

## Reset

reset 只移除 Baldric 的 llama.cpp 集成设置与安全快照。它绝不停止外部服务器或删除模型文件。设置 reset 与已存凭据删除是两个动作；已存凭据保持到其单独的删除确认成功为止。

## 排障

- **连接拒绝或超时：** 启动 `llama-server`，核对确切 URL，选择 `/local` → Refresh。Baldric 不会发现其他端口。
- **HTTP 401/403：** 在 `/local` 输入服务器配置的 key，或设 `LLAMA_API_KEY`。已存 key 优先于环境值。
- **加载中：** 等 llama.cpp 加载完成后刷新。
- **下载时 `model limit reached`：** 共享路由拒绝了请求。检查 `/local`；仅在有意时卸载另一个模型，或稍后再试。Baldric 刷新状态并显示路由的确切拒绝消息。
- **`/v1/models` 畸形或为空：** 检查服务器响应与模型加载状态。Baldric 不编造 ID 或元数据。
- **print mode 报模型不可用：** 先配置 `/local`，再传 `--provider llama.cpp` 加确切发现的 `--model`。缓存快照可离线工作，但首次显式模型需要发现。
- **工具不被调用：** 运行 Doctor。流式可以正常而模型的 GGUF chat template 不支持工具。使用具备工具能力的 instruct GGUF 并检查 llama.cpp 的模板/服务器旗标。
- **旧 `llama-cpp` provider 还在：** 它是单独手工配置的 provider。内置 backend 用 `llama.cpp`；保留旧 provider 以沿用其既有目录设置。

## 从手工本地 provider 迁移

既有自定义 OpenAI 兼容 provider 继续工作。要把手工配置的 llama.cpp 服务器迁到内置集成，打开
`/local`，选择并确认推荐的 backend，输入端点与可选 key，然后使用 `/v1/models` 返回的确切 ID。内置
provider ID 是 `llama.cpp`；旧的 `llama-cpp` 目录条目不会被自动迁移、重写或移除。验证新 session 后再移除它。Ollama 与其他本地服务器仍走自定义 provider 路径，不是 Baldric 交付的 backend。

Baldric 绝不把旧的假 key、假模型 ID、目录定义、项目设置或环境端点拷贝进内置状态。reset 只移除内置设置与安全快照；它绝不停止服务器或删除模型文件。其他 OpenAI 兼容端点继续用 [`/login custom`](/how-to/providers-and-models/#添加自定义本地-provider)
或 `baldric setup`。

路由管理不改变安全边界：所有变更都是显式的，模型文件绝不被删除，标准 OpenAI 兼容单模型推理继续受支持。
