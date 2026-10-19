"""用 SQLite FTS5 + BM25 + RRF 复现「会话记忆检索」的核心思路。

背景：context-mode 等工具把编码 Agent 的会话事件（改了哪些文件、执行了哪些
git 操作、用户做了哪些决定）写进 SQLite，并用 FTS5 建全文索引；上下文被压缩后，
Agent 只需按需检索几条相关记录，而不是把全部历史塞回上下文。

本实验只用 Python 标准库（sqlite3），完全离线：
  1. 构造一段模拟的会话事件日志
  2. 分别用 porter（词干）和 trigram（三字符片段）两种分词器建 FTS5 索引
  3. 用 BM25 排序，再用 Reciprocal Rank Fusion (RRF) 融合两路结果
  4. 对一组「压缩后 Agent 可能会问的问题」检查 Top-3 是否命中正确事件
  5. 粗略对比「全量回放历史」与「只取 Top-3」的上下文体积
"""
from __future__ import annotations

import sqlite3
import sys

# ---------------------------------------------------------------- 1. 模拟会话事件
EVENTS = [
    ("decision", "User decided to use PostgreSQL instead of MySQL for the orders service because of JSONB support"),
    ("edit", "Edited src/orders/repository.py: added upsert_order() using INSERT ... ON CONFLICT"),
    ("git", "git checkout -b feature/order-upsert"),
    ("test", "pytest tests/test_orders.py failed: test_upsert_idempotent AssertionError duplicate rows"),
    ("edit", "Edited src/orders/repository.py: fixed conflict target to (tenant_id, external_id)"),
    ("test", "pytest tests/test_orders.py passed: 14 passed in 2.31s"),
    ("decision", "User said: never log customer email addresses, mask them as ***@domain"),
    ("edit", "Edited src/common/logging.py: added mask_email() filter to the root logger"),
    ("git", "git commit -m 'orders: idempotent upsert keyed by tenant and external id'"),
    ("edit", "Edited config/settings.toml: raised http client timeout from 5s to 15s for the payment gateway"),
    ("note", "Payment gateway sandbox returns HTTP 429 when more than 10 requests per second are sent"),
    ("edit", "Edited src/payments/client.py: added token bucket rate limiter, 8 requests per second"),
    ("decision", "User prefers Chinese comments in new code but English identifiers"),
    ("test", "ruff check src/ found 3 issues: unused import in src/payments/client.py"),
    ("edit", "Edited src/payments/client.py: removed unused import json"),
    ("git", "git rebase origin/main resolved conflict in src/common/logging.py"),
    ("note", "CI pipeline uses Python 3.12 and runs migrations with alembic upgrade head"),
    ("edit", "Edited migrations/versions/20261019_add_external_id.py: unique index on orders(tenant_id, external_id)"),
    ("decision", "User wants the feature behind flag ORDERS_UPSERT_V2, default off in production"),
    ("edit", "Edited src/orders/service.py: read ORDERS_UPSERT_V2 from feature flag client"),
    ("test", "pytest -q passed: 212 passed, 3 skipped in 41.7s"),
    ("note", "Staging deploy is triggered by pushing a tag that matches staging-*"),
    ("git", "git push origin feature/order-upsert"),
    ("note", "Reviewer asked to add a retry with exponential backoff around payment refund calls"),
    ("edit", "Edited src/payments/refund.py: retry up to 4 times with exponential backoff 0.5s,1s,2s,4s"),
]

# 「压缩之后」Agent 可能要回答的问题 → 期望命中的事件下标
QUERIES = [
    ("which database did the user choose", 0),
    ("how should email addresses appear in logs", 6),
    ("payment gateway rate limit", 10),
    ("feature flag for upsert", 18),
    ("refund retry backoff", 24),
    ("how to deploy to staging", 21),
    ("upsert test failed duplicate", 3),
    ("timeout for payment", 9),
]

K_RRF = 60      # RRF 常数，常见取值
TOP_K = 3


def build_index(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE events(id INTEGER PRIMARY KEY, kind TEXT, body TEXT)")
    conn.execute("CREATE VIRTUAL TABLE ev_porter USING fts5(body, content='events', content_rowid='id', tokenize='porter unicode61')")
    conn.execute("CREATE VIRTUAL TABLE ev_tri USING fts5(body, content='events', content_rowid='id', tokenize='trigram')")
    for i, (kind, body) in enumerate(EVENTS):
        conn.execute("INSERT INTO events(id, kind, body) VALUES (?,?,?)", (i, kind, body))
    conn.execute("INSERT INTO ev_porter(ev_porter) VALUES('rebuild')")
    conn.execute("INSERT INTO ev_tri(ev_tri) VALUES('rebuild')")


def fts_query(words: list[str], table: str) -> str:
    if table == "ev_tri":
        # trigram 需要 ≥3 个字符的片段；用 OR 组合每个词
        terms = [f'"{w}"' for w in words if len(w) >= 3]
    else:
        terms = [w for w in words if w.isalnum()]
    return " OR ".join(terms) or '""'


STOPWORDS = {"which", "did", "the", "how", "should", "appear", "in", "to", "for", "what", "a", "is"}


def search(conn, table: str, q: str, limit: int = 10) -> list[int]:
    words = [w.lower() for w in q.split() if w.lower() not in STOPWORDS]
    sql = f"SELECT rowid FROM {table} WHERE {table} MATCH ? ORDER BY bm25({table}) LIMIT ?"
    return [r[0] for r in conn.execute(sql, (fts_query(words, table), limit))]


def rrf(*rankings: list[int]) -> list[int]:
    score: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            score[doc] = score.get(doc, 0.0) + 1.0 / (K_RRF + rank)
    return sorted(score, key=lambda d: -score[d])


def approx_tokens(text: str) -> int:
    # 粗略估算：英文约 4 字符 ≈ 1 token。只用于数量级对比，不代表任何模型的真实计数。
    return max(1, len(text) // 4)


def main() -> int:
    conn = sqlite3.connect(":memory:")
    build_index(conn)
    print(f"SQLite {sqlite3.sqlite_version}，事件数 {len(EVENTS)}\n")

    hits = {"porter": 0, "trigram": 0, "rrf": 0}
    for q, expected in QUERIES:
        p = search(conn, "ev_porter", q)
        t = search(conn, "ev_tri", q)
        fused = rrf(p, t)
        res = {"porter": p[:TOP_K], "trigram": t[:TOP_K], "rrf": fused[:TOP_K]}
        marks = []
        for name, top in res.items():
            ok = expected in top
            hits[name] += ok
            marks.append(f"{name}={'✓' if ok else '✗'}")
        print(f"Q: {q}")
        print(f"   期望 #{expected}: {EVENTS[expected][1][:70]}")
        print(f"   RRF Top-1 #{fused[0] if fused else '-'}  " + "  ".join(marks))

    n = len(QUERIES)
    print("\nTop-3 命中率：")
    for name in ("porter", "trigram", "rrf"):
        print(f"  {name:<8} {hits[name]}/{n}")

    full = sum(approx_tokens(b) for _, b in EVENTS)
    per_query = []
    for q, _ in QUERIES:
        fused = rrf(search(conn, "ev_porter", q), search(conn, "ev_tri", q))[:TOP_K]
        per_query.append(sum(approx_tokens(EVENTS[i][1]) for i in fused))
    top3 = sum(per_query) / len(per_query)
    print(f"\n上下文体积（粗略估算）：全量回放 ≈ {full} tokens，单次检索 Top-3 平均 ≈ {top3:.0f} tokens"
          f"（约 {top3 / full:.0%}）")
    print("说明：事件越多，全量回放线性增长，而检索 Top-K 基本不变。")

    misses = [q for q, e in QUERIES if e not in rrf(search(conn, "ev_porter", q), search(conn, "ev_tri", q))[:TOP_K]]
    if misses:
        print("未命中的问题（词面不重合，属于纯词法检索的固有局限）：")
        for q in misses:
            print(f"  - {q}")

    recall = hits["rrf"] / n
    print(f"\nRESULT: RRF Top-3 recall = {recall:.2f} ({hits['rrf']}/{n})")
    if recall < 0.75:
        print("RRF 融合检索命中率低于 0.75，实验未达到预期", file=sys.stderr)
        return 1
    if hits["rrf"] < max(hits["porter"], hits["trigram"]):
        print("STATUS: partial")
        print("说明：融合结果不如单路检索，需要调整查询构造或 RRF 参数")
    return 0


if __name__ == "__main__":
    sys.exit(main())
