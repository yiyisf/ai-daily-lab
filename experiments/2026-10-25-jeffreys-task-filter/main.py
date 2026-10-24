"""先探测、再筛题：用 Jeffreys 后验给 RL 训练任务估难度，能少掉多少「无梯度」的组？

受 Microsoft / Hugging Face 博客 "Turning Database Grading into RL Rewards: Post-Training
Agents with ThinkingBox" 启发。文章的做法：训练前用基座策略对每个候选任务反复试做，
用 Jeffreys 后验 Beta(k + 1/2, n - k + 1/2) 估计成功率，按 0.08 / 0.40 / 0.60 / 0.90
分桶，丢掉几乎做不出（< 0.08）和几乎总能做对（>= 0.90）的任务；GRPO 中一组 rollout
奖励全相同时没有学习信号，这类任务就是在浪费算力。

本脚本全部为模拟数据（固定随机种子），只演示机制，不复现文章任何数字：
- 构造 600 个候选任务，「真实」成功率来自一个偏向两端的分布（很多题太难或太简单）
- 每个任务用基座策略探测 n=8 次，得到成功次数 k
- 用 Jeffreys 后验均值 (k + 0.5) / (n + 1) 作为难度估计（取均值是本实验的选择，
  原文没有说明取后验的哪个统计量），按上述边界分桶并筛掉两端
- 对比筛选前后：模拟 GRPO 每组 8 条 rollout 时，奖励全 0 或全 1（零方差）组的比例
"""
from __future__ import annotations

import random
import sys

SEED = 25
N_TASKS = 600
N_PROBE = 8          # 每个任务的探测次数
GROUP = 8            # GRPO 每组 rollout 数（与原文一致，仅作设定）
N_GROUPS = 4000      # 模拟抽取的训练组数
BOUNDS = (0.08, 0.40, 0.60, 0.90)

checks: list[tuple[bool, str]] = []


def check(ok: bool, msg: str) -> None:
    checks.append((ok, msg))
    print(f"[{'PASS' if ok else 'FAIL'}] {msg}")


def sample_true_p(rng: random.Random) -> float:
    """偏向两端的真实成功率：约 35% 很难、30% 很简单、35% 中等。"""
    r = rng.random()
    if r < 0.35:
        return rng.betavariate(0.6, 12)   # 很难
    if r < 0.65:
        return rng.betavariate(12, 0.6)   # 很简单
    return rng.betavariate(2.5, 2.5)      # 中等


def jeffreys_mean(k: int, n: int) -> float:
    return (k + 0.5) / (n + 1.0)


def bucket(p_hat: float) -> str:
    lo, mid_lo, mid_hi, hi = BOUNDS
    if p_hat < lo:
        return "drop-hard"
    if p_hat < mid_lo:
        return "hard"
    if p_hat < mid_hi:
        return "medium"
    if p_hat < hi:
        return "easy"
    return "drop-easy"


def zero_variance_rate(rng: random.Random, pool: list[float]) -> float:
    zero = 0
    for _ in range(N_GROUPS):
        p = rng.choice(pool)
        s = sum(1 for _ in range(GROUP) if rng.random() < p)
        if s == 0 or s == GROUP:
            zero += 1
    return zero / N_GROUPS


def main() -> int:
    rng = random.Random(SEED)
    tasks = []
    for _ in range(N_TASKS):
        p = sample_true_p(rng)
        k = sum(1 for _ in range(N_PROBE) if rng.random() < p)
        tasks.append({"p": p, "k": k, "jeff": jeffreys_mean(k, N_PROBE), "mle": k / N_PROBE})

    counts: dict[str, int] = {}
    for t in tasks:
        t["bucket"] = bucket(t["jeff"])
        counts[t["bucket"]] = counts.get(t["bucket"], 0) + 1
    print("分桶结果：", {b: counts.get(b, 0) for b in ["drop-hard", "hard", "medium", "easy", "drop-easy"]})

    kept = [t for t in tasks if not t["bucket"].startswith("drop")]
    keep_rate = len(kept) / len(tasks) * 100

    all_pool = [t["p"] for t in tasks]
    kept_pool = [t["p"] for t in kept]
    zv_all = zero_variance_rate(random.Random(SEED + 1), all_pool) * 100
    zv_kept = zero_variance_rate(random.Random(SEED + 1), kept_pool) * 100

    mle_extreme = sum(1 for t in tasks if t["mle"] in (0.0, 1.0)) / len(tasks) * 100
    jeff_min = min(t["jeff"] for t in tasks)
    jeff_max = max(t["jeff"] for t in tasks)

    # 被丢掉的任务里，真实成功率确实落在两端的比例（筛选「准不准」）
    dropped = [t for t in tasks if t["bucket"].startswith("drop")]
    truly_extreme = sum(1 for t in dropped if t["p"] < 0.08 or t["p"] >= 0.90)
    drop_precision = truly_extreme / len(dropped) * 100 if dropped else 0.0

    print(f"METRIC: 保留任务比例 = {keep_rate:.1f} %")
    print(f"METRIC: 筛选前零方差组比例 = {zv_all:.1f} %")
    print(f"METRIC: 筛选后零方差组比例 = {zv_kept:.1f} %")
    print(f"METRIC: 被丢任务中真实落在两端的比例 = {drop_precision:.1f} %")
    print(f"METRIC: 最大似然估计为 0 或 1 的任务比例 = {mle_extreme:.1f} %")

    check(zv_kept < zv_all, "筛选后零方差（无学习信号）组的比例低于筛选前")
    check(0.0 < jeff_min and jeff_max < 1.0, "Jeffreys 后验均值不会给出 0 或 1 这样的极端估计")
    check(10.0 < keep_rate < 90.0, "筛选只去掉两端，保留了相当一部分任务")
    check(drop_precision > 50.0, "被丢掉的任务多数确实是过难或过易的")

    failed = [m for ok, m in checks if not ok]
    if failed:
        print(f"RESULT: 有 {len(failed)} 项检查未通过")
        return 1
    print(f"RESULT: 模拟中按 Jeffreys 后验筛题后，零方差组从 {zv_all:.1f}% 降到 {zv_kept:.1f}%，保留 {keep_rate:.1f}% 的任务")
    return 0


if __name__ == "__main__":
    sys.exit(main())
