---
title: 项目信任
description: 在 Baldric 加载之前控制环境性的仓库输入。
---

Baldric 在加载因活动工作目录而发现的受保护输入之前会先询问。决定以规范化且真实存在的 cwd 为键——不是猜测的仓库根。因此符号链接别名共享一个决定，并继承最近一个已保存的父级决定。

## 受保护输入

Baldric 对项目的 `.baldric` 与 `.agents` skill 和 prompt、`.baldric` 主题、`SYSTEM.md` 与 `APPEND_SYSTEM.md`、普通与 scoped `AGENTS.md`、项目 extension 候选，以及预留给未来支持的项目 `settings.json` 设置门槛。

内置本地 backend 是受信任的包代码。它们独立于项目信任加载，不会把环境端点、模型快照或凭据变成项目输入。其 provider/backend 注册仍由活动运行世代拥有；项目 extension 不能绕过正常的来源与信任规则重置它们。检测只查名字与元数据；Baldric 在决定之前不读取、解析或导入任何候选。

`~/.baldric` 与 `~/.agents` 下的用户资源、built-in 与 CLI 显式传入的路径保持合格。受信任内置 extension 是已安装的 Baldric 包代码而非 cwd 发现：它们在决定之前加载，`--no-extensions` 下也一样，其存在本身绝不制造信任提示。受信任项目 extension 仍需要额外的 `--project-extensions` 开关。

## 决定

交互式启动提供：

- 信任这个确切文件夹并保存；
- 信任显示的直接父目录并保存；
- 仅本次运行信任；
- 拒绝这个确切文件夹并保存；
- 仅本次运行拒绝。

Esc/取消会在启动时退出 Baldric 而不加载项目。`/reload` 或跨项目 session 替换期间取消，会保留当前 session 快照并让 Baldric 保持打开。已保存决定存放在 `~/.baldric/trust.json`（版本 1）。Baldric 校验整个文件，并在锁、受限权限与原子替换下更新它。畸形、不可读、被锁或不可写的存储绝不授予已保存信任。仅本次批准仍可用 `--approve`。

子决定覆盖继承的父决定。父信任范围很宽：Baldric 在选择前显示确切的父目录。项目移动时没有自动清理。

## 无头与自动化

`--approve`（`-a`）与 `--no-approve`（`-na`）互斥，只作用于本次调用，绝不改写存储。print、JSON、transcript 及其他无头路径从不弹提示。其未解析行为跟随用户全局的 `defaultProjectTrust` 设置：

| 值 | 无头结果 |
| --- | --- |
| `ask`（默认） | 拒绝 |
| `always` | 批准 |
| `never` | 拒绝 |

信任诊断在结构化模式下走 stderr，stdout 保持机器可读。它们报告有界的类别/计数与决定来源信息，不含受保护内容。

## reload 与 session

`/reload` 重新检测。最初为空、后来获得受保护输入的项目需要新的决定；Baldric 绝不从早先的空状态推断持久信任。资源准备是连贯的：拒绝会构建仅含全局/显式输入的快照。resume 与替换解析目标记录的规范 cwd，而不是复用源项目的结果。

## 内置本地 backend 安全

打包的 `llama.cpp` backend 是受信任的 Baldric 包代码。它在项目信任决定之前加载——包括 `--no-extensions` 时——且绝不制造信任提示。backend 确认之后，`/local` 只探测其输入、已保存、`LLAMA_BASE_URL` 或默认端点；它不扫描端口、进程或本地网络。Baldric 绝不启动/停止外部服务器或删除模型文件。显式下载由独立的 llama.cpp 路由执行，而不是 Baldric 的文件系统代码。

`~/.baldric/state/extensions/llama.cpp.json` 的安全集成快照只包含归一化端点、确切模型 ID、允许列表元数据与时间戳。API key 单独保存在 `~/.baldric/credentials.json` 或读自 `LLAMA_API_KEY`；没有 key 就没有 `Authorization` header。secret 不进入快照、session、导出或诊断。重置设置与删除已存凭据是两个独立确认。排障见[本地推理指南](/how-to/local-inference/)。

内置集成不导入也不改写既有的 `llama-cpp` 目录条目。通过 `/local` 单独配置 `llama.cpp`；Ollama 与其他本地服务器仍走手工自定义 provider 路径。

## 安全边界

**项目信任是输入加载守卫，不是沙箱。** 它不限制文件系统读写、进程、shell 命令、工具、网络访问、凭据、provider、模型、包安装、prompt 注入或数据外泄。受信任的项目仍可能是恶意的。需要隔离时，使用 OS 沙箱、容器、VM、远程环境与受限的凭据/网络。
