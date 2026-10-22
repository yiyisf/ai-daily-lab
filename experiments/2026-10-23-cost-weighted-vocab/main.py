"""按「成本」而不是「频次」挑选宏 token 的最小演示。

受 Dharma-AI 的 VocabX 文章启发：同样新增 K 个宏 token（把一段重复的词序列合并成一个 token），
如果按「省下的 token 数」挑，会优先压缩最常出现的输入片段；
如果按「省下的钱」挑（输出 token 单价是输入的 7.4 倍），会优先压缩模型输出里的重复结构。

语料是本脚本用固定随机种子生成的模拟「作文评分」请求，不是真实数据；
分词用空格切词近似，不涉及真实模型或分词器。
"""
from __future__ import annotations

import random
import sys
from collections import Counter

OUTPUT_PRICE = 7.4  # 一个输出 token 的价格（以输入 token 为 1）
INPUT_PRICE = 1.0
BUDGETS = (4, 8, 16)  # 允许新增的宏 token 个数
MAX_N = 6

SYSTEM = (
    "you are a strict essay grader . read the essay and return a json object "
    "with the grade and short feedback . grade from 0 to 10 ."
)
TOPICS = ["school", "family", "travel", "science", "music", "sport", "city", "nature"]
ADJ = ["clear", "weak", "strong", "vague", "good", "poor"]
ISSUES = ["the argument is", "the structure is", "the conclusion is", "the grammar is"]


def make_corpus(n: int, seed: int = 7):
    rng = random.Random(seed)
    records = []
    for _ in range(n):
        topic = rng.choice(TOPICS)
        words = [rng.choice(TOPICS + ADJ + ["the", "a", "is", "and", "my", "i", "we"]) for _ in range(rng.randint(30, 60))]
        user = f"essay about {topic} : " + " ".join(words)
        grade = rng.randint(0, 10)
        fb = " ; ".join(f"{rng.choice(ISSUES)} {rng.choice(ADJ)}" for _ in range(rng.randint(2, 3)))
        resp = f'{{ " grade " : {grade} , " feedback " : " {fb} " }}'
        records.append({"system": SYSTEM.split(), "user": user.split(), "response": resp.split()})
    return records


WEIGHT = {"system": INPUT_PRICE, "user": INPUT_PRICE, "response": OUTPUT_PRICE}


def totals(records):
    tok = sum(len(r[f]) for r in records for f in WEIGHT)
    cost = sum(len(r[f]) * WEIGHT[f] for r in records for f in WEIGHT)
    return tok, cost


def count_ngrams(records):
    """返回 {ngram: {field: 出现次数}}，只统计不跨字段的 n-gram。"""
    stats: dict[tuple, Counter] = {}
    for r in records:
        for f in WEIGHT:
            seq = r[f]
            for n in range(2, MAX_N + 1):
                for i in range(len(seq) - n + 1):
                    g = tuple(seq[i:i + n])
                    stats.setdefault(g, Counter())[f] += 1
    return stats


def replace(seq, gram, sym):
    out, i, n = [], 0, len(gram)
    while i < len(seq):
        if tuple(seq[i:i + n]) == gram:
            out.append(sym)
            i += n
        else:
            out.append(seq[i])
            i += 1
    return out


def build(records, mode: str, budget: int):
    recs = [{f: list(r[f]) for f in WEIGHT} for r in records]
    chosen = []
    for k in range(budget):
        stats = count_ngrams(recs)
        best, best_score = None, 0.0
        for g, c in stats.items():
            saved = len(g) - 1
            if mode == "frequency":
                score = saved * sum(c.values())
            else:
                score = saved * sum(cnt * WEIGHT[f] for f, cnt in c.items())
            if score > best_score:
                best, best_score = g, score
        if best is None:
            break
        sym = f"<M{k}>"
        chosen.append(" ".join(best))
        for r in recs:
            for f in WEIGHT:
                r[f] = replace(r[f], best, sym)
    return recs, chosen


def main() -> int:
    records = make_corpus(300)
    base_tok, base_cost = totals(records)
    base_resp = sum(len(r["response"]) for r in records) / len(records)
    print(f"语料：{len(records)} 条请求，原始 {base_tok} 个 token，加权成本 {base_cost:.0f}，平均回复 {base_resp:.1f} token")

    names = {"frequency": "按频次", "cost": "按成本"}
    res = {}
    for budget in BUDGETS:
        for mode in ("frequency", "cost"):
            recs, chosen = build(records, mode, budget)
            tok, cost = totals(recs)
            resp = sum(len(r["response"]) for r in recs) / len(recs)
            res[(budget, mode)] = ((1 - tok / base_tok) * 100, (1 - cost / base_cost) * 100, resp)
            print(f"K={budget:>2} {names[mode]}：token 减少 {res[(budget, mode)][0]:.1f}%，"
                  f"加权成本减少 {res[(budget, mode)][1]:.1f}%，平均回复 {resp:.1f} token；前 2 个宏 token {chosen[:2]}")

    for budget in BUDGETS:
        for mode in ("frequency", "cost"):
            print(f"METRIC: K={budget} {names[mode]} 加权成本减少 = {res[(budget, mode)][1]:.1f} %")
    for budget in BUDGETS:
        for mode in ("frequency", "cost"):
            print(f"METRIC: K={budget} {names[mode]} 平均回复长度 = {res[(budget, mode)][2]:.1f} token")

    ok = True
    for budget in BUDGETS:
        f, c = res[(budget, "frequency")], res[(budget, "cost")]
        checks = [
            (f[0] >= c[0], f"K={budget}：按频次挑选省下的 token 总数不少于按成本挑选"),
            (c[1] > f[1], f"K={budget}：按成本挑选省下的加权成本更多"),
        ]
        for passed, msg in checks:
            print(f"[{'PASS' if passed else 'FAIL'}] {msg}")
            ok &= passed
    gaps = [res[(b, "cost")][1] - res[(b, "frequency")][1] for b in BUDGETS]
    shrinking = all(a > b for a, b in zip(gaps, gaps[1:]))
    print(f"[{'PASS' if shrinking else 'FAIL'}] 预算越紧，两种挑法的成本差距越大")
    ok &= shrinking
    print(f"RESULT: 宏 token 预算为 {'/'.join(map(str, BUDGETS))} 时，按成本挑选比按频次多省 "
          f"{'/'.join(f'{g:.1f}' for g in gaps)} 个百分点的加权成本")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
