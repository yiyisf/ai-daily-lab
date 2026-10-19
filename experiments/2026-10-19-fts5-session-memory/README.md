# 用 SQLite FTS5 + BM25 复现 Agent 会话记忆检索

## 目的

今天的开源项目 [context-mode](https://github.com/mksglu/context-mode) 的一个核心机制是：把编码 Agent 的会话事件（文件修改、git 操作、用户决定）写入 SQLite，用 FTS5 建全文索引；上下文被压缩之后，Agent 不必回放全部历史，只按需检索几条相关记录。它的检索组合了 Porter 词干和 trigram 两种匹配，再用 Reciprocal Rank Fusion（RRF）融合。

本实验用**纯 Python 标准库**做一个最小复现，回答两个问题：

1. 只靠词法检索（不用向量模型），能不能找回「压缩后 Agent 需要的那条记录」？
2. 相比全量回放历史，检索能省下多少上下文？

## 步骤

1. 构造 25 条模拟的会话事件（决定、编辑、测试、git、备注）
2. 建两张 FTS5 虚拟表：`porter unicode61` 分词与 `trigram` 分词
3. 对 8 个「压缩后可能会问的问题」分别做 BM25 检索，再用 RRF（k=60）融合
4. 统计 Top-3 命中率，并粗略估算上下文体积（按 4 字符 ≈ 1 token，仅用于数量级对比）

运行：

```bash
python main.py
```

## 预期结果

- 8 个问题中，RRF Top-3 至少命中 6 个，程序以 `RESULT: RRF Top-3 recall = ...` 结尾
- 单次检索取回的内容只占全量历史的一小部分
- 可能出现词面完全不重合的问题（例如问「database」而记录里写的是「PostgreSQL」）检索不到，这是纯词法检索的固有局限，正是很多工具会再叠加语义检索或同义词扩展的原因

## 可以继续尝试

- 增加到几百条事件，观察全量回放与 Top-K 体积的差距如何拉开
- 给查询加一个同义词表（database → postgresql/mysql），看未命中的问题能否找回
- 调整 RRF 常数 k，或只用单路检索，对比命中率

## 内网复现

- **无需任何第三方依赖**，只用 Python 3.9+ 自带的 `sqlite3` 模块，无需联网，可直接在内网运行
- 需要 SQLite 编译时启用 FTS5（主流发行版的 Python 默认已启用），且 trigram 分词器要求 SQLite ≥ 3.34
- 把 `main.py` 拷贝到内网机器即可运行

可以先用下面的命令检查环境，输出 `ok` 即可：

```bash
python -c "import sqlite3; sqlite3.connect(':memory:').execute(\"create virtual table t using fts5(x, tokenize='trigram')\"); print('ok')"
```

如果报 `no such module: fts5` 或不认识 `trigram`，说明系统自带的 SQLite 太旧，可以换用 Python 官方安装包或 conda 环境中的 Python。
