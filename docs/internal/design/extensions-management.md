---
title: "extension 清单与管理边界"
---

# extension 清单与管理边界

Issue #35 把 `/extensions` 引入为可搜索、只读的 TUI 清单。
它把成功加载（含来源元数据）与 extension 诊断集中在一处。这解决了眼下的可见性问题，同时不暗示 Baldric 尚未提供的包管理能力。

## 数据模型

`ExtensionInfo` 是运行时元数据，源自既有
`extension_metadata` 来源信息加上加载时计算的 scope 分类：

- `name`：加载器身份
- `path`：展示给用户的已解析入口文件（built-in 为 `None`）
- `scope`：`project`、`user`、`explicit` 或 `built-in`
- `status`：当前为 `loaded`

失败仍是 `ResourceDiagnostic` 值。它们是清单里的行，
不是安装。不持久化任何 registry 或 manifest。

## 所有权与移除

当前来源的边界：

| 来源 | Baldric 拥有文件吗 | 移除的含义 |
| --- | --- | --- |
| `~/.baldric/extensions` 手工放置 | 否 | 说明路径；由用户移除 |
| `<project>/.baldric/extensions` | 否 | 说明项目路径；绝不删除 |
| 显式 `-e` 文件/目录 | 否 | 不带旗标重启；绝不删除 |
| built-in 打包 extension | 随 Baldric 发布 | 由安装管理，用户不可删 |
| 未来的 Baldric 托管用户安装 | 是 | 确认后仅移除其登记的受管目录 |

因此本阶段不暴露移除动作。未来的安装器（issue #39）
必须维护一个区分 Baldric 受管目录与恰好放在那里的用户文件的 registry，破坏性动作才是安全的。

## 启用与禁用

runtime 目前只持久化全局发现选择。按 extension 的
启用需要 registry 记录稳定的安装身份、来源、
路径、scope、修订与启用状态。仅凭名字不行，因为
加载优先级允许重名。变更必须走既有
`session_shutdown` → reset/reload → `session_start` 生命周期。失败时，
Baldric 必须保留或恢复先前的 registry、文件与可用 runtime。

## 仓库安装信任模型

从 URL 安装被推迟。实现前需定义：

1. 初始接受的规范化公开 GitHub HTTPS 仓库 URL；
2. 安装 ID 与 Baldric 自有目录下的目的地，与手工放置的 extension 分开；
3. 原子 registry 中的固定修订与入口发现元数据；
4. 先克隆到临时兄弟目录、校验 manifest/entry，再改名；
5. 显式确认任意 Python 将在 Baldric 进程内执行；
6. clone、校验、setup 或 reload 出错时回滚文件与 registry；
7. 更新与移除行为，包括本地修改；
8. 用本地 fake 仓库的确定性测试，绝不碰网络。

SSH/私有认证、自动更新与项目安装保持为后续项，直到公开 HTTPS 流程与信任话术被验证。

## 验证

Textual 试点测试覆盖：已填充的清单、大小写不敏感过滤、
无匹配、空状态、Escape 取消与诊断行。命令测试
覆盖注册与参数校验。运行时测试覆盖全部四种来源的 scope 分类与 reset-for-reload 生命周期。
