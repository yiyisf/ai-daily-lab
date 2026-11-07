"""玩具实验：用 BestRand 思路压缩评测集，和纯随机抽题比较估分误差。

不调用任何模型。用固定种子生成一个「模型 × 题目」的 0/1 得分矩阵（类 IRT：
模型能力、题目难度、区分度），一部分模型当作「探针模型」（已经跑过全量的旧模型），
其余当作「目标模型」（新模型，只想跑一小部分题）。

两种选题方法，预算都是 k 道题：
- random：从全量题目里随机抽 k 道
- bestrand：先随机抽 min(4k, N) 道题作为候选池，在池内随机抽 128 个大小为 k 的子集，
  选「探针模型平均得分向量」与池平均最接近（平方 L2 距离）的那个子集。
  目标模型的分数只在选题之后使用。

对每个方法重复多个随机种子，统计目标模型「子集估分 - 全量真实分」的绝对误差，
看平均误差和尾部（P95、最大）误差。
"""
import sys

import numpy as np

N_ITEMS = 2000
N_PROBE = 8
N_TARGET = 24
BUDGETS = [50, 100, 200]
N_SEEDS = 400
N_CANDIDATES = 128
POOL_MULT = 4


def make_matrix(rng):
    n_models = N_PROBE + N_TARGET
    ability = rng.normal(0.0, 1.0, n_models)
    difficulty = rng.normal(0.0, 1.2, N_ITEMS)
    discrim = rng.lognormal(0.0, 0.35, N_ITEMS)
    # 一部分题目带「题型」偏好：某些模型在某类题上额外强/弱
    n_types = 5
    item_type = rng.integers(0, n_types, N_ITEMS)
    type_skill = rng.normal(0.0, 0.6, (n_models, n_types))
    logits = discrim[None, :] * (ability[:, None] - difficulty[None, :]) + type_skill[:, item_type]
    p = 1.0 / (1.0 + np.exp(-logits))
    return (rng.random(p.shape) < p).astype(np.float64)


def select_random(rng, k):
    return rng.choice(N_ITEMS, size=k, replace=False)


def select_bestrand(rng, probe_scores, k):
    pool_size = min(POOL_MULT * k, N_ITEMS)
    pool = rng.choice(N_ITEMS, size=pool_size, replace=False)
    pool_scores = probe_scores[:, pool]  # [probe, pool]
    pool_mean = pool_scores.mean(axis=1)
    best, best_d = None, None
    for _ in range(N_CANDIDATES):
        idx = rng.choice(pool_size, size=k, replace=False)
        d = float(np.sum((pool_scores[:, idx].mean(axis=1) - pool_mean) ** 2))
        if best_d is None or d < best_d:
            best, best_d = idx, d
    return pool[best]


def errors(scores, target_rows, subset):
    full = scores[target_rows].mean(axis=1)
    est = scores[np.ix_(target_rows, subset)].mean(axis=1)
    return np.abs(est - full) * 100.0  # 百分点


def main():
    data_rng = np.random.default_rng(20261108)
    scores = make_matrix(data_rng)
    probe_rows = np.arange(N_PROBE)
    target_rows = np.arange(N_PROBE, N_PROBE + N_TARGET)
    probe_scores = scores[probe_rows]

    full_target = scores[target_rows].mean(axis=1) * 100
    print(f"题目数 {N_ITEMS}，探针模型 {N_PROBE} 个，目标模型 {N_TARGET} 个，每种设置 {N_SEEDS} 个种子")
    print(f"目标模型全量得分范围 {full_target.min():.1f}% ~ {full_target.max():.1f}%")
    print()
    print(f"{'k':>5} | {'方法':<9} | {'平均误差':>8} | {'P95误差':>8} | {'最大误差':>8} | {'>5分占比':>8}")

    summary = {}
    for k in BUDGETS:
        for method in ("random", "bestrand"):
            rng = np.random.default_rng(1000 + k)
            errs = []
            for _ in range(N_SEEDS):
                if method == "random":
                    subset = select_random(rng, k)
                else:
                    subset = select_bestrand(rng, probe_scores, k)
                errs.append(errors(scores, target_rows, subset))
            errs = np.concatenate(errs)
            stats = {
                "mean": float(errs.mean()),
                "p95": float(np.percentile(errs, 95)),
                "max": float(errs.max()),
                "over5": float((errs > 5.0).mean() * 100),
            }
            summary[(k, method)] = stats
            print(f"{k:>5} | {method:<9} | {stats['mean']:>7.2f}  | {stats['p95']:>7.2f}  | {stats['max']:>7.2f}  | {stats['over5']:>7.2f}%")
    print()

    checks = []
    for k in BUDGETS:
        r, b = summary[(k, "random")], summary[(k, "bestrand")]
        checks.append((b["mean"] < r["mean"], f"k={k}: BestRand 平均误差低于纯随机（{b['mean']:.2f} vs {r['mean']:.2f} 分）"))
        checks.append((b["p95"] < r["p95"], f"k={k}: BestRand P95 误差低于纯随机（{b['p95']:.2f} vs {r['p95']:.2f} 分）"))
    r200 = summary[(200, "random")]
    r50 = summary[(50, "random")]
    checks.append((r200["mean"] < r50["mean"], "纯随机：预算从 50 题增加到 200 题，平均误差下降"))

    ok = True
    for passed, msg in checks:
        print(("[PASS] " if passed else "[FAIL] ") + msg)
        ok = ok and passed
    print()

    for k in BUDGETS:
        print(f"METRIC: k={k} 纯随机 P95 误差 = {summary[(k, 'random')]['p95']:.2f} 分")
        print(f"METRIC: k={k} BestRand P95 误差 = {summary[(k, 'bestrand')]['p95']:.2f} 分")
    k = 100
    r, b = summary[(k, "random")], summary[(k, "bestrand")]
    print(f"METRIC: k=100 纯随机误差超过5分的占比 = {r['over5']:.2f} %")
    print(f"METRIC: k=100 BestRand 误差超过5分的占比 = {b['over5']:.2f} %")

    reduction = (1 - b["p95"] / r["p95"]) * 100
    print(f"RESULT: 在这份模拟数据上，100 题预算下 BestRand 把 P95 估分误差从 {r['p95']:.2f} 分降到 {b['p95']:.2f} 分（约降 {reduction:.0f}%），只多用了探针模型在候选池上的分数")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
