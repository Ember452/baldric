# 公开 API 政策（`baldric_ai` / `baldric_agent`）

**状态：** 已接受 —— 2026-11-05
**范围：** 三个发行的包，对
`baldric_ai` 与 `baldric_agent` 有具体强制。`baldric_coding` 已有显式
`__all__` 清单，同一政策适用于它。

## 背景

`baldric_coding/__init__.py` 一直显式列出其公开门面
（phase 1 末 139 个名字）。`baldric_ai` 与 `baldric_agent` 却用：

```python
__all__ = [name for name in globals() if not name.startswith("_")]
```

本决策前在 `main` 上测量：

| 包 | `__all__` 名字 | 其中子模块对象 |
|---|---:|---:|
| `baldric_ai` | 55 | 18 |
| `baldric_agent` | 67 | 11 |

动态推导有三个问题：

1. 它把内部模块布局变成意外的公开表面。
2. 它依赖导入顺序：只有恰好在推导运行前被某条导入路径绑定的模块才进 `__all__`。
3. 它从 `baldric_agent` 导出一个 `types` 模块对象，对任何做 `from baldric_agent import *` 的调用者遮蔽标准库 `types` 模块。

蓝图的 phase 2 恰好要重排这些模块——例如
`baldric_agent.messages` → `baldric_agent/contracts/messages.py`，`baldric_ai.providers/*` 变成具名子包。动态 `__all__` 会把每次这样的移动变成未经宣告的公开 API 变更。

## 决策

1. **每个包受支持的公开 API 恰是其静态包根 `__all__` 清单里的名字。** 只有符号（类、函数、常量）是公开的。模块对象不是公开 API。
2. **`__all__` 是静态字面清单。** 不得从 `globals()`、
   `dir()`、推导式或任何其他运行时计算派生。
3. **子模块导入是实现细节。** `import baldric_agent.messages`
   与 `from baldric_agent import messages` 今天可以继续工作，但不是契约。内部模块移动可以变更或移除这些路径而不经 API 弃用周期；*符号*的公开改名/移除仍遵循正常弃用政策。
4. **因此允许在不改 `__all__` 的前提下进行内部重组。**
   更新内部导入，保持包根符号名稳定。
5. **文档化示例必须从包根导入**，不从子模块。

## 本决策的具体效果

- `baldric_ai.__all__`：55 → **37 个符号**（移除 18 个模块对象）。
- `baldric_agent.__all__`：67 → **56 个符号**（移除 11 个模块对象）。
- `from baldric_ai import *` / `from baldric_agent import *` 不再绑定模块
  对象。仓库零个星号导入点，内部代码无需变更；外部星号导入用户应改为显式导入。
- 既有子模块的直接导入在该模块移动前继续工作。其路径从来不是受支持 API 的一部分，移动它们不是 API 破坏。这正是解锁 phase-2 蓝图移动的关键。
- `from baldric_agent import *` 不再踩 `types` 标准库遮蔽雷。

## 强制

`tests/test_public_api_contract.py` 强制两半：

- `baldric_ai` 与 `baldric_agent` 的确切符号集；
- `__all__` 必须是字符串常量的 `ast.List`，拒绝回退到
  `globals()`。

`baldric_coding` 继续由其显式 139 名门面与既有
phase-1 台账检查覆盖。

## 被否决的替代方案

- **永远在 `__all__` 里保留模块对象。** 阻塞计划中的 `providers/`、
  `contracts/`、`tools/` 重组，并保留 `types` 雷。
- **保留动态推导只加快照测试。** 测试会绿，而 API 静默依赖导入顺序；未来一次内部导入可以在不碰 API 声明的情况下把某模块从 `__all__` 挤掉。
- **在每个旧子模块路径加转发模块。** 此阶段不需要：
  项目 pre-1.0（`0.2.1`），子模块路径从未被文档化为受支持 API，垫片会永久冻结内部布局。

## 版本注记

本变更在发行版为 `0.2.x`（pre-1.0）时落地。从 `__all__` 移除意外模块对象视为 minor 版本清理，不是对文档化符号 API 的破坏性变更。项目到达 1.0 后政策延续：模块路径保持实现细节；符号移除遵循语义版本与弃用流程。
