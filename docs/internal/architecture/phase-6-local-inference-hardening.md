---
title: "Phase 6：本地推理加固与第二 backend 验证"
---

Phase 6 关闭 issue #602 的通用本地 provider 验证闭环。它
刻意保持交付实现很小：llama.cpp 仍是唯一的内置本地 backend，而一个确定性的第二 fake 与一个仅测试的
Ollama 适配器锻炼公开接缝。

## 变更了什么

- 一个常驻的 fake 第二 backend 覆盖不同的 normal、secret、choice
  配置字段、来源绑定的 provider/backend 层、原子的失败配置、取消、过期结果拒绝、进度脱敏与可选能力。
- Ollama 适配器 spike 位于 `tests/fixtures/`；它不被
  Baldric 生产代码导入、不注册 Ollama backend。provider 发现用官方 OpenAI 兼容 `/v1/models` 形状，已安装/运行状态用原生 `/api/tags` 与 `/api/ps` 形状。
- 刷新/reload 压力测试覆盖合并、世代退役、敌意取消、有界清理与迟到结果包容。凭据测试覆盖世代引用、离线 setup、状态文件脱敏与清理孤儿行为。
- 缺失的 llama.cpp 选择保持为稳定引用，而不被新发现的模型覆盖。状态与模型选择把该快照标为过期。显式 Doctor 可以为诊断探测当前唯一上报的模型，但绝不改变活动选择。

## 来自 Ollama 的契约压力

spike 不需要在通用 API 里出现 llama.cpp 词汇。它确实确认了三条有用的边界：

1. provider 发现与本地状态可以使用不同协议端点。
   `DynamicProvider.refresh_models` 返回一份完整的 provider 快照，而 `LocalBackend.status` 经开放的 `LocalModel.state` 字段返回已安装/运行状态。
2. `NoAuth` 是真实用例。Ollama 的本地 OpenAI 兼容端点不需要合成 key 或 `Authorization` header。
3. backend 能力操作保持可选且可由宿主渲染。宿主拥有字段、确认、取消与渲染；协议适配器返回结构化值，绝不构建 Textual 组件。

观察到的官方 API 引用：

- <https://docs.ollama.com/api/openai-compatibility>
- <https://docs.ollama.com/api/tags>
- <https://docs.ollama.com/api/ps>

spike 刻意不承诺原生 Ollama 模型管理。它只验证一个发现/状态端点分离的适配器符合
provider 中立契约。

## 生命周期与安全决策

registry 保持世代局部。退役使来源/层 token 失效、恰好取消一次自有工作、只在文档化的有界取消窗口内等待，并让仍在运行的回调被监护到结束。迟到回调不能向替换世代发布。准备好的 runtime 拥有
其 provider 与 backend 资源；失败的候选只关闭自己的资源，最终关闭幂等。

内置 llama.cpp 状态是用户级、带版本、加锁、私有且
原子替换的。它只存归一化端点、确切模型 ID、
允许列表元数据、一个选定引用与时间戳。API key 留在凭据库或环境。旧 `llama-cpp` 目录 provider
不被迁移或覆盖，Ollama 保持为文档化的自定义 provider 选项而非交付的 backend。

本阶段不含 Phase 7 路由变更。没有生产 Ollama
backend、没有 Hugging Face 搜索/下载、没有 llama.cpp 加载/卸载实现、也没有隐式模型文件操作。

## 迁移指引

既有手工配置的 OpenAI 兼容本地 provider 继续工作。把 llama.cpp 设置迁到内置集成：

1. 独立启动服务器。
2. 打开 `/local`，选择并确认推荐的 llama.cpp backend，输入端点与可选 key。
3. 在 `/model` 或 `--provider llama.cpp --model <id>` 中使用 `/v1/models` 返回的确切模型 ID。
4. 新 session 验证可用后再移除旧的 `llama-cpp` 目录条目。

Baldric 不把旧的假 key、假模型 ID、目录定义、项目
设置或环境端点拷进内置状态。reset 只移除内置设置；服务器进程与模型文件绝不被触碰。

## 验证

```bash
uv run pytest tests/test_local_backends.py tests/test_extension_providers.py \
  tests/test_llama_cpp_extension.py tests/test_phase6_hardening.py \
  tests/test_ollama_adapter_spike.py -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
```
