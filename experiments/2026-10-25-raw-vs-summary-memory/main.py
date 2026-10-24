"""保留原文 vs 写入时摘要：两种 Agent 记忆对「必要证据覆盖率」的影响

受论文 "Is Complex Agentic Memory Always Needed? Naive RAG Is Stronger Than We Thought"
（arXiv:2610.30755）启发。论文的观点：直接对原始对话历史做检索（Raw-RAG）常常比先把历史
加工成结构化记忆更好，因为加工会丢掉回答问题所需的证据；证据覆盖率高，可以抵消利用率低。

本脚本全部为构造数据（固定随机种子），只演示机制，不复现论文任何数字：
- 生成一段多轮对话历史：若干项目的属性（上线日期、负责人、预算）会被多次修改，
  修改原因在另一条消息里单独说明，中间穿插大量无关闲聊
- 三类问题：当前值（latest）、上一次的值（previous）、修改原因（reason）
- 三种记忆：
  A. 覆盖式摘要：每个 (项目, 属性) 只保留最新值
  B. 带历史的摘要：保留每个 (项目, 属性) 的全部取值，但不记录原因
  C. Raw-RAG：对原始消息做 BM25 检索，取 top-k 条原文
- 指标：回答所需的全部证据是否出现在交给「阅读模型」的上下文里（证据覆盖率），
  以及上下文的大致长度（词数）
"""
from __future__ import annotations

import math
import random
import re
import sys
from collections import Counter

SEED = 25
PROJECTS = ["Atlas", "Borealis", "Cobalt", "Dune", "Ember", "Fjord", "Granite", "Harbor",
            "Iris", "Juniper", "Kestrel", "Lumen"]
ATTRS = {
    "launch date": ["March 3", "March 10", "April 2", "April 18", "May 6", "May 21", "June 9"],
    "owner": ["Priya", "Marco", "Lena", "Tomas", "Aiko", "Omar", "Sofia"],
    "budget": ["40k", "55k", "62k", "75k", "80k", "95k", "120k"],
}
REASONS = ["the vendor shipped late", "legal asked for another review", "the team was reorganized",
           "finance cut the quarterly plan", "a key customer requested changes",
           "the pilot showed performance issues"]
CHATTER = ["Lunch is at noon today.", "Remember to submit expense reports by Friday.",
           "The office wifi was flaky this morning.", "Great demo yesterday, everyone.",
           "Who has the spare HDMI adapter?", "Coffee machine on floor 3 is fixed.",
           "Please update your calendar for the holiday.", "The quarterly survey is open."]

checks: list[tuple[bool, str]] = []


def check(ok: bool, msg: str) -> None:
    checks.append((ok, msg))
    print(f"[{'PASS' if ok else 'FAIL'}] {msg}")


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def build_history(rng: random.Random):
    """返回消息列表与问题列表。每个问题记录所需证据的消息编号。"""
    msgs: list[str] = []
    events = []  # (project, attr, value, msg_id, reason_msg_id or None)
    for _ in range(90):
        if rng.random() < 0.45:
            msgs.append(rng.choice(CHATTER))
            continue
        p = rng.choice(PROJECTS)
        a = rng.choice(list(ATTRS))
        v = rng.choice(ATTRS[a])
        msgs.append(f"Update: the {a} for {p} is now {v}.")
        mid = len(msgs) - 1
        rid = None
        prev = [e for e in events if e[0] == p and e[1] == a]
        if prev and rng.random() < 0.8:
            # 原因单独一条，夹在若干闲聊之后
            for _ in range(rng.randint(0, 2)):
                msgs.append(rng.choice(CHATTER))
            msgs.append(f"Context on {p}: we changed the {a} because {rng.choice(REASONS)}.")
            rid = len(msgs) - 1
        events.append((p, a, v, mid, rid))

    questions = []
    keys = sorted({(e[0], e[1]) for e in events})
    for p, a in keys:
        hist = [e for e in events if e[0] == p and e[1] == a]
        last = hist[-1]
        questions.append({"type": "latest", "q": f"What is the current {a} for {p}?",
                          "need": {last[3]}, "key": (p, a), "answer": last[2]})
        if len(hist) >= 2:
            questions.append({"type": "previous", "q": f"What was the {a} for {p} before the last change?",
                              "need": {hist[-2][3]}, "key": (p, a), "answer": hist[-2][2]})
            if last[4] is not None:
                questions.append({"type": "reason", "q": f"Why did the {a} for {p} change most recently?",
                                  "need": {last[4]}, "key": (p, a), "answer": None})
    return msgs, events, questions


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.toks = [tokenize(d) for d in docs]
        self.avg = sum(len(t) for t in self.toks) / len(self.toks)
        self.df = Counter(w for t in self.toks for w in set(t))
        self.n = len(docs)
        self.k1, self.b = k1, b

    def search(self, query: str, k: int) -> list[int]:
        q = tokenize(query)
        scores = []
        for i, t in enumerate(self.toks):
            tf = Counter(t)
            s = 0.0
            for w in q:
                if w not in tf:
                    continue
                idf = math.log(1 + (self.n - self.df[w] + 0.5) / (self.df[w] + 0.5))
                s += idf * tf[w] * (self.k1 + 1) / (tf[w] + self.k1 * (1 - self.b + self.b * len(t) / self.avg))
            scores.append((s, -i))  # 同分时偏向较新的消息
        scores.sort(reverse=True)
        return [-i for _, i in scores[:k]]


def main() -> int:
    rng = random.Random(SEED)
    msgs, events, questions = build_history(rng)
    print(f"历史消息 {len(msgs)} 条，属性修改 {len(events)} 次，问题 {len(questions)} 个")

    # A. 覆盖式摘要：只保留最新值（证据视为「最新那条更新」）
    latest_store = {}
    for p, a, v, mid, _ in events:
        latest_store[(p, a)] = (v, {mid})
    # B. 带历史的摘要：保留全部取值，不记录原因
    hist_store: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for p, a, v, mid, _ in events:
        hist_store.setdefault((p, a), []).append((v, mid))

    def covered_A(q):
        return q["need"] <= latest_store[q["key"]][1]

    def covered_B(q):
        return q["need"] <= {mid for _, mid in hist_store[q["key"]]}

    bm = BM25(msgs)

    def covered_C(q, k):
        return q["need"] <= set(bm.search(q["q"], k))

    types = ["latest", "previous", "reason"]
    by_type = {t: [q for q in questions if q["type"] == t] for t in types}

    def rate(fn, qs):
        return sum(1 for q in qs if fn(q)) / len(qs) * 100 if qs else 0.0

    overall = {}
    overall["覆盖式摘要"] = rate(covered_A, questions)
    overall["带历史摘要"] = rate(covered_B, questions)
    for k in (3, 8):
        overall[f"Raw-RAG top-{k}"] = rate(lambda q, k=k: covered_C(q, k), questions)

    for name, val in overall.items():
        print(f"METRIC: {name} 总体证据覆盖率 = {val:.1f} %")
    for t in ("previous", "reason"):
        print(f"METRIC: 覆盖式摘要 {t} 类覆盖率 = {rate(covered_A, by_type[t]):.1f} %")
        print(f"METRIC: Raw-RAG top-8 {t} 类覆盖率 = {rate(lambda q: covered_C(q, 8), by_type[t]):.1f} %")

    # 上下文长度：摘要给出一条键值；Raw-RAG 给出 k 条原文
    avg_msg_words = sum(len(tokenize(m)) for m in msgs) / len(msgs)
    print(f"METRIC: Raw-RAG top-8 平均上下文长度 = {8 * avg_msg_words:.0f} 词")
    entries = [f"{p} {a}: {v}" for (p, a), (v, _) in latest_store.items()]
    avg_entry = sum(len(tokenize(e)) for e in entries) / len(entries)
    print(f"METRIC: 覆盖式摘要平均上下文长度 = {avg_entry:.0f} 词")

    check(rate(covered_A, by_type["latest"]) == 100.0, "覆盖式摘要能覆盖全部「当前值」问题")
    check(rate(covered_A, by_type["previous"]) == 0.0, "覆盖式摘要写入时丢了旧值，「上一次的值」问题全部缺证据")
    check(rate(covered_B, by_type["reason"]) == 0.0, "带历史的摘要仍不记录原因，「修改原因」问题全部缺证据")
    check(overall["Raw-RAG top-8"] > overall["带历史摘要"], "Raw-RAG top-8 的总体证据覆盖率高于带历史的摘要")
    check(overall["Raw-RAG top-8"] >= overall["Raw-RAG top-3"], "检索条数从 3 增加到 8，覆盖率不下降")

    failed = [m for ok, m in checks if not ok]
    if failed:
        print(f"RESULT: 有 {len(failed)} 项检查未通过")
        return 1
    print(f"RESULT: 构造数据中，Raw-RAG top-8 证据覆盖率 {overall['Raw-RAG top-8']:.1f}%，"
          f"覆盖式摘要 {overall['覆盖式摘要']:.1f}%——摘要省上下文，但写入时没留的信息事后无法找回")
    return 0


if __name__ == "__main__":
    sys.exit(main())
