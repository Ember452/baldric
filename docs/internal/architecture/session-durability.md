# session 持久性：撕裂行与原子写入

**状态：** 已接受 —— 2026-11-06（分支 `chore/p0-contract-baselines`）

session 文件是用户数据。此前三种写入可能摧毁数据而不是只丢最后一步：

| 写入 | 失败 |
| --- | --- |
| transcript 追加 | 进程在追加中途被杀留下残缺的最后一行；严格读取器从此永远拒绝打开该 session |
| session 索引 | `write_text` 先截断，被打断的写入留下残缺行；严格读取器扫描失败，该项目里所有 session 被藏起来 |
| HTML/JSONL 导出 | 同样的非原子写入，被打断的导出摧毁之前的好文件 |

## 策略：读取者容忍，写入者修复

残缺的**最后**一行是崩溃唯一可能合理留下的东西，所以它是唯一被容忍的：

- `entries_from_transcript(text)` 在不得不丢弃最后一行时返回 entry 加一个标志。其他任何位置的损坏仍抛 `SessionJsonlError`，
  `test_jsonl_storage_still_rejects_corruption_before_the_final_line` 钉住这一点。
- 读取从不改写文件。`JsonlSessionStorage` 记一条警告并保留解析出的前缀。
- 写入先修复，因为往未终止的行上追加会把新记录粘到旧片段上，把一行损坏变成整份损坏的 transcript。修复丢弃不可解析的尾部，并给只是丢了换行的完整记录补上终止符。
- 修复在既有排他锁下、走既有原子替换运行，修复期间崩溃让先前文件保持完好。

## 索引自我重建

`SessionManager._read_index` 现在跳过损坏行、记录数量、
从幸存记录重写索引。重写失败被记录且仍返回解析出的记录，只读盘或满盘不会把损坏索引变成读循环。

写入经 `baldric_coding/utils/atomic.py`（同目录临时文件、
fsync、替换）。被打断的写入让先前文件字节不变——管理器与导出测试通过让 `os.replace` 失败来断言这一点。

helper 刻意不 fsync 目录：替换后立即崩溃可能找回先前文件——那是被回退的更新，不是部分更新。transcript 批次写
在需要处已为目录 fsync 付费，encoding 不变量
（`tests/invariants/`）统计裸 `os.open` 调用，第二份该 helper 会被记为债务。

## 与 Pi 对比

Pi 的 JSONL 存储在打开时修复撕裂的追加：`JsonlStorage.recover()`
在存储交付前运行，其提交标记让它找到"更短的完整前缀"（`packages/durable/src/storage/jsonl/storage.ts`），之后的每次追加都从干净文件开始。

Baldric 没有提交标记、没有打开时事务层，所以本变更以不同方式拆分同一保证：

- 读取容忍撕裂的最后行，而不是让读取者改写文件；
- 写入者在追加前于既有排他锁下修复尾部——那正是粘记录本会产生的时刻。

安全性质相同（撕裂记录被丢弃，绝不并进下一条）；差别是文件在下一次追加前保持撕裂。Pi 的打开时修复在这里也可行，但它会让 `read_all` 改写 transcript，导出/查看器路径不应写用户数据。

## 不覆盖的范围

- transcript 中间的损坏行仍是损坏：修复就得猜丢了哪条记录。
- 跨进程追加顺序不变；既有的每 session 锁仍串行化写者。
- session 格式本身不变，`tests/expected/session_entries.jsonl` 不动。

## 测试

- `tests/coding/session/test_session.py`：撕裂最后行被读取并记录；
  追加与批处理先修复尾部；丢了换行的完整最后行被保留；中间损坏仍抛异常；只含撕裂行的文件读作空。
- `tests/coding/session/test_session_manager.py`：损坏的索引行丢弃该
  记录、保留其余并重写文件；替换失败保留先前索引且不留临时文件。
- `tests/coding/session/test_session_export.py`：替换失败保留先前导出。
