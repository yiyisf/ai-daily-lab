"""压缩工具输出：直接截断 vs 保留异常项的结构化摘要。

受 Headroom（headroomlabs-ai/headroom）README 的启发：它在工具输出进入模型之前压缩
JSON、日志等内容，压缩 JSON 数组时保留错误项和统计离群值，并把原文缓存在本地，
需要时可以按哈希取回（README 称为 CCR，可逆压缩）。

本实验不安装、不调用 Headroom，也不调用任何模型，只用纯 Python 演示这条思路：
  - none：     原样交给模型
  - truncate： 只保留前 N 条（常见的「截断到上下文能放下」做法）
  - smart：    字段摘要 + 计数 + 全部 ERROR/WARN 项 + 延迟离群值 + 少量样例，
               原文按哈希存入本地缓存，可以原样取回
在固定种子生成的两类模拟工具输出上，比较压缩后的大小，以及关键条目（「针」）是否还在。
完全离线，运行时间不到 1 秒。
"""
import hashlib
import json
import random
import statistics
import sys

SEED = 20261106
TRUNCATE_KEEP = 20
SAMPLE_KEEP = 3
Z_OUTLIER = 3.0

CACHE = {}  # 哈希 -> 原文，模拟「可逆压缩」的本地缓存


def approx_tokens(text):
    """粗略估算 token 数：按 4 个字符约 1 个 token。"""
    return max(1, len(text) // 4)


def make_service_logs(rng):
    """模拟一次「查询服务日志」工具调用：400 条记录，少量错误和一个延迟离群值。"""
    services = ["auth", "orders", "billing", "search", "gateway"]
    records = []
    for i in range(400):
        records.append({
            "ts": f"2026-11-06T08:{i // 60:02d}:{i % 60:02d}Z",
            "service": rng.choice(services),
            "level": "INFO",
            "latency_ms": round(rng.gauss(120, 15), 1),
            "msg": "request handled",
            "request_id": f"req-{rng.randrange(10**8):08d}",
        })
    needles = []
    for pos, (level, msg) in zip(rng.sample(range(40, 400), 5), [
        ("ERROR", "db connection pool exhausted"),
        ("ERROR", "upstream timeout from billing"),
        ("WARN", "retry budget almost used up"),
        ("ERROR", "null pointer in order serializer"),
        ("WARN", "token refresh took longer than expected"),
    ]):
        records[pos]["level"] = level
        records[pos]["msg"] = msg
        needles.append(records[pos]["request_id"])
    spike = rng.randrange(60, 400)
    records[spike]["latency_ms"] = 2480.0
    needles.append(records[spike]["request_id"])
    return records, needles


def make_test_report(rng):
    """模拟一次「运行测试」工具调用：250 个用例，3 个失败散落在后半段。"""
    cases = []
    for i in range(250):
        cases.append({
            "id": f"test_{i:03d}",
            "file": f"tests/test_mod{i % 17}.py",
            "status": "passed",
            "duration_ms": round(abs(rng.gauss(35, 8)), 1),
            "message": "",
        })
    needles = []
    for pos, msg in zip(rng.sample(range(120, 250), 3), [
        "AssertionError: expected 200, got 500",
        "TimeoutError: fixture db_ready not ready in 5s",
        "KeyError: 'currency'",
    ]):
        cases[pos]["status"] = "failed"
        cases[pos]["message"] = msg
        needles.append(cases[pos]["id"])
    return cases, needles


def is_flagged(item):
    level = str(item.get("level", "")).upper()
    status = str(item.get("status", "")).lower()
    return level in ("ERROR", "WARN") or status in ("failed", "error")


def numeric_outliers(items):
    """对每个数值字段做 z-score，返回离群项的下标集合。"""
    idx = set()
    keys = [k for k, v in items[0].items() if isinstance(v, (int, float))]
    for k in keys:
        vals = [it[k] for it in items]
        if len(vals) < 3:
            continue
        mu, sd = statistics.mean(vals), statistics.pstdev(vals)
        if sd == 0:
            continue
        for i, v in enumerate(vals):
            if abs(v - mu) / sd > Z_OUTLIER:
                idx.add(i)
    return idx


def compress_none(items):
    return json.dumps(items, ensure_ascii=False)


def compress_truncate(items):
    head = items[:TRUNCATE_KEEP]
    note = {"note": f"truncated: showing {len(head)} of {len(items)} items"}
    return json.dumps(head + [note], ensure_ascii=False)


def compress_smart(items):
    raw = json.dumps(items, ensure_ascii=False)
    key = hashlib.sha256(raw.encode()).hexdigest()[:12]
    CACHE[key] = raw

    summary = {"total": len(items), "fields": list(items[0].keys())}
    for field in ("level", "status", "service"):
        if field in items[0]:
            counts = {}
            for it in items:
                counts[it[field]] = counts.get(it[field], 0) + 1
            summary[f"count_by_{field}"] = counts
    for k, v in items[0].items():
        if isinstance(v, (int, float)):
            vals = [it[k] for it in items]
            summary[f"{k}_p50"] = round(statistics.median(vals), 1)
            summary[f"{k}_max"] = max(vals)

    keep = {i for i, it in enumerate(items) if is_flagged(it)}
    keep |= numeric_outliers(items)
    keep |= set(range(min(SAMPLE_KEEP, len(items))))
    kept = [items[i] for i in sorted(keep)]
    out = {
        "summary": summary,
        "kept_items": kept,
        "omitted": len(items) - len(kept),
        "retrieve": f"full output cached as {key}",
    }
    return json.dumps(out, ensure_ascii=False), key


def needle_recall(text, needles):
    return sum(1 for n in needles if n in text) / len(needles)


def main():
    rng = random.Random(SEED)
    scenarios = {
        "服务日志": make_service_logs(rng),
        "测试报告": make_test_report(rng),
    }

    checks = []
    metrics = []
    rows = []
    reversible = True
    for name, (items, needles) in scenarios.items():
        base = compress_none(items)
        trunc = compress_truncate(items)
        smart, key = compress_smart(items)
        if CACHE.get(key) != base:
            reversible = False
        t_base, t_trunc, t_smart = map(approx_tokens, (base, trunc, smart))
        r_trunc = needle_recall(trunc, needles)
        r_smart = needle_recall(smart, needles)
        saved_smart = 100 * (1 - t_smart / t_base)
        saved_trunc = 100 * (1 - t_trunc / t_base)
        rows.append((name, t_base, t_trunc, t_smart, r_trunc, r_smart, len(needles)))
        metrics.append(f"METRIC: {name} smart 节省 = {saved_smart:.1f} %")
        metrics.append(f"METRIC: {name} truncate 节省 = {saved_trunc:.1f} %")
        metrics.append(f"METRIC: {name} smart 关键条目保留率 = {100 * r_smart:.1f} %")
        metrics.append(f"METRIC: {name} truncate 关键条目保留率 = {100 * r_trunc:.1f} %")
        checks.append((saved_smart >= 50, f"{name}：smart 压缩后约省下一半以上 token（{saved_smart:.1f}%）"))
        checks.append((r_smart == 1.0, f"{name}：smart 保留了全部 {len(needles)} 个关键条目"))
        checks.append((r_trunc < 1.0, f"{name}：只截断前 {TRUNCATE_KEEP} 条会丢掉关键条目（保留 {100 * r_trunc:.0f}%）"))

    checks.append((reversible, "smart 缓存的原文可以按哈希原样取回"))

    print(f"{'场景':<6}{'原样':>8}{'截断':>8}{'smart':>8}  截断保留  smart保留")
    for name, tb, tt, ts, rt, rs, n in rows:
        print(f"{name:<6}{tb:>8}{tt:>8}{ts:>8}  {rt * n:>4.0f}/{n}    {rs * n:>4.0f}/{n}")
    print("(数字为估算 token 数，按 4 字符约 1 token 计)")
    print()

    ok_all = True
    for ok, desc in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {desc}")
        ok_all &= ok
    print()
    for m in metrics:
        print(m)

    if ok_all:
        print("RESULT: 保留错误项和离群值的结构化摘要，在大幅缩短工具输出的同时没有丢掉关键条目；简单截断则会漏掉排在后面的错误")
        return 0
    print("RESULT: 有检查未通过，结构化摘要在本组模拟数据上没有同时做到「更短」和「不丢关键条目」")
    return 1


if __name__ == "__main__":
    sys.exit(main())
