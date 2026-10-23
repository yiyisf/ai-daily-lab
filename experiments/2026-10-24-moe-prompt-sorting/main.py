"""给 MoE 批推理的提示词排个序：按领域分组能少读多少专家？

受 Hugging Face 社区文章 "Sort your prompts: a free speed-up for MoE batch inference" 启发。
文章的机制：MoE 每个解码步要读取批内所有请求路由到的专家权重；同一领域的提示词倾向于
使用重叠的专家，把同领域请求放进同一批，可以减少每步读取的不同专家数。

本脚本用标准库和固定随机种子模拟这一机制（全部为模拟数据，不复现文章数字）：
- 128 个专家、每个 token 选 8 个（与文章中 Qwen3-30B-A3B 的配置相同，仅作设定）
- 6 个领域，每个领域对专家有不同的偏好分布（少数专家被频繁选中）
- 比较两种排批方式下每个解码步触达的不同专家数：随机打乱 vs 按领域排序
- 另比较 32 个专家（粗粒度 MoE）时节省比例是否更小
"""
from __future__ import annotations

import random
import sys

SEED = 24
N_PROMPTS = 768
N_DOMAINS = 6
BATCH = 32
STEPS = 20  # 每批模拟的解码步数


def make_domain_prefs(rng: random.Random, n_experts: int):
    """每个领域：随机挑一部分「偏好专家」，赋予较大权重，其余专家权重较小。"""
    prefs = []
    hot = max(4, n_experts // 4)
    for _ in range(N_DOMAINS):
        weights = [1.0] * n_experts
        for e in rng.sample(range(n_experts), hot):
            weights[e] = 12.0
        prefs.append(weights)
    return prefs


def route(rng: random.Random, weights, k: int):
    """按权重无放回抽 k 个专家，模拟一个 token 的 top-k 路由。"""
    chosen = set()
    w = list(weights)
    for _ in range(k):
        total = sum(w)
        r = rng.random() * total
        acc = 0.0
        for e, x in enumerate(w):
            acc += x
            if acc >= r:
                chosen.add(e)
                w[e] = 0.0
                break
    return chosen


def avg_experts_per_step(rng, domains, prefs, k, steps=STEPS):
    counts = []
    for start in range(0, len(domains), BATCH):
        batch = domains[start:start + BATCH]
        for _ in range(steps):
            touched = set()
            for d in batch:
                touched |= route(rng, prefs[d], k)
            counts.append(len(touched))
    return sum(counts) / len(counts)


def top_quarter_share(rng, prefs, n_experts, k, samples=400):
    """单个领域内，最常被选中的 1/4 专家占全部路由决策的比例。"""
    shares = []
    for d in range(N_DOMAINS):
        freq = [0] * n_experts
        for _ in range(samples):
            for e in route(rng, prefs[d], k):
                freq[e] += 1
        freq.sort(reverse=True)
        shares.append(sum(freq[: n_experts // 4]) / sum(freq))
    return sum(shares) / len(shares) * 100


def run(n_experts: int, k: int, seed: int):
    rng = random.Random(seed)
    prefs = make_domain_prefs(rng, n_experts)
    domains = [i % N_DOMAINS for i in range(N_PROMPTS)]
    shuffled = domains[:]
    rng.shuffle(shuffled)
    sorted_ = sorted(shuffled)  # 稳定排序：按领域分组
    mixed = avg_experts_per_step(random.Random(seed + 1), shuffled, prefs, k)
    grouped = avg_experts_per_step(random.Random(seed + 1), sorted_, prefs, k)
    share = top_quarter_share(random.Random(seed + 2), prefs, n_experts, k)
    saving = (mixed - grouped) / mixed * 100
    return mixed, grouped, saving, share


def main() -> int:
    mixed, grouped, saving, share = run(128, 8, SEED)
    mixed32, grouped32, saving32, _ = run(32, 4, SEED)

    print(f"设定：{N_PROMPTS} 条提示词、{N_DOMAINS} 个领域、批大小 {BATCH}")
    print(f"METRIC: 随机批 每步触达专家数 (128 专家) = {mixed:.1f} 个")
    print(f"METRIC: 按领域排序 每步触达专家数 (128 专家) = {grouped:.1f} 个")
    print(f"METRIC: 少读专家比例 (128 专家) = {saving:.1f} %")
    print(f"METRIC: 少读专家比例 (32 专家) = {saving32:.1f} %")
    print(f"METRIC: 单领域前 1/4 专家所占路由比例 = {share:.1f} %")

    checks = [
        (grouped < mixed, "按领域排序后，每步触达的不同专家数少于随机打乱"),
        (saving > 5, "128 专家配置下少读专家比例超过 5%"),
        (saving32 < saving, "粗粒度 MoE（32 专家）的节省比例小于细粒度（128 专家）"),
        (share > 25, "单领域内前 1/4 专家所占路由比例高于均匀路由的 25%"),
    ]
    ok = True
    for passed, desc in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {desc}")
        ok &= passed

    print(
        f"RESULT: 模拟中按领域排序让每步读取的专家从 {mixed:.1f} 个降到 {grouped:.1f} 个"
        f"（少 {saving:.1f}%），专家越少的 MoE 节省越小（{saving32:.1f}%）"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
