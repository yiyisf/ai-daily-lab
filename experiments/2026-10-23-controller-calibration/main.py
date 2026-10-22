"""「排序好」不等于「建议好」：校准偏差如何让 Agent 控制器白白多花钱。

受论文 Good Judgment, Bad Advice (arXiv:2610.24649) 启发。论文发现：一个专用决策模型
在离线排序（AUROC）上优于规则和小模型，但输出的「已完成概率」系统性偏低，
导致 Agent 做了许多不必要的验证，成本上升而通过率不变。

本脚本用固定随机种子模拟这一机制（全部数据为模拟，不复现论文数字）：
- 每个 run 有真实结果：87% 已完成（与论文报告的通过比例同量级，仅作设定）
- 控制器 A（模拟专用决策模型）：区分能力强，但概率整体偏低
- 控制器 B（模拟简单规则）：区分能力弱，但概率大致校准
- 策略：若控制器给出的已完成概率 < 0.5，就让 Agent 再做一轮验证（额外成本 0.4）
- 验证只会确认结果，不改变通过率（与论文「通过率无可检测差异」的设定一致）
最后演示：只用少量带标签的 run 对 A 做简单的保序校准，不必要的验证会大幅减少。
"""
from __future__ import annotations

import math
import random
import sys

SEED = 23
N = 4000
P_DONE = 0.87
THRESHOLD = 0.5
VERIFY_COST = 0.4  # 相对一次基础尝试成本 1.0


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def simulate(rng: random.Random):
    runs = []
    for _ in range(N):
        done = rng.random() < P_DONE
        # A：信号强（均值差大），但整体向下偏移 -> 概率偏低
        a = sigmoid((1.6 if done else -1.6) + rng.gauss(0, 1.5) - 1.7)
        # B：信号弱，但没有偏移
        b = sigmoid((0.6 if done else -0.6) + rng.gauss(0, 1.5) + 1.9)
        runs.append((done, a, b))
    return runs


def auroc(labels, scores) -> float:
    pos = [s for l, s in zip(labels, scores) if l]
    neg = [s for l, s in zip(labels, scores) if not l]
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    for r, i in enumerate(order, 1):
        ranks[i] = r
    pos_rank = sum(ranks[i] for i, l in enumerate(labels) if l)
    return (pos_rank - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def evaluate(labels, probs):
    verify = [p < THRESHOLD for p in probs]
    unnecessary = sum(v and l for v, l in zip(verify, labels)) / sum(labels)
    cost = sum(1 + (VERIFY_COST if v else 0) for v in verify) / len(labels)
    passed = sum(labels) / len(labels)  # 验证不改变结果
    return cost, unnecessary, passed


def isotonic_calibrate(train_scores, train_labels, n_bins: int = 10):
    """按分位数分箱后做保序（单调）平均，返回校准函数。"""
    pairs = sorted(zip(train_scores, train_labels))
    size = math.ceil(len(pairs) / n_bins)
    bins = [pairs[i:i + size] for i in range(0, len(pairs), size)]
    edges = [b[-1][0] for b in bins]
    rates = [sum(l for _, l in b) / len(b) for b in bins]
    for i in range(1, len(rates)):  # 简单的单调修正
        rates[i] = max(rates[i], rates[i - 1])

    def f(s: float) -> float:
        for e, r in zip(edges, rates):
            if s <= e:
                return r
        return rates[-1]

    return f


def main() -> int:
    rng = random.Random(SEED)
    runs = simulate(rng)
    labels = [d for d, _, _ in runs]
    a = [x for _, x, _ in runs]
    b = [x for _, _, x in runs]

    auc_a, auc_b = auroc(labels, a), auroc(labels, b)
    mean_a, mean_b = sum(a) / N, sum(b) / N
    cost_a, unn_a, pass_a = evaluate(labels, a)
    cost_b, unn_b, pass_b = evaluate(labels, b)

    # 用前 200 个带标签 run 校准 A，在其余 run 上评估
    k = 200
    cal = isotonic_calibrate(a[:k], labels[:k])
    a_cal = [cal(s) for s in a[k:]]
    cost_c, unn_c, _ = evaluate(labels[k:], a_cal)
    _, unn_a_rest, _ = evaluate(labels[k:], a[k:])

    print(f"模拟 {N} 个 run，真实完成比例 {sum(labels) / N * 100:.1f}%")
    print(f"METRIC: 控制器 A AUROC = {auc_a:.3f}")
    print(f"METRIC: 控制器 B AUROC = {auc_b:.3f}")
    print(f"METRIC: 控制器 A 平均完成概率 = {mean_a * 100:.1f} %")
    print(f"METRIC: 控制器 B 平均完成概率 = {mean_b * 100:.1f} %")
    print(f"METRIC: 控制器 A 不必要验证比例 = {unn_a * 100:.1f} %")
    print(f"METRIC: 控制器 B 不必要验证比例 = {unn_b * 100:.1f} %")
    print(f"METRIC: A 校准后不必要验证比例 = {unn_c * 100:.1f} %")
    print(f"METRIC: 控制器 A 每次尝试成本 = {cost_a:.3f} 倍")
    print(f"METRIC: 控制器 B 每次尝试成本 = {cost_b:.3f} 倍")
    print(f"METRIC: A 校准后每次尝试成本 = {cost_c:.3f} 倍")

    checks = [
        (auc_a > auc_b, "控制器 A 的离线排序（AUROC）优于 B"),
        (mean_a < sum(labels) / N - 0.2, "控制器 A 的平均完成概率明显低于真实完成比例（校准偏差）"),
        (cost_a > cost_b, "按同一阈值行动时，A 触发更多验证、成本更高"),
        (pass_a == pass_b, "两种控制器下通过率相同（验证不改变结果）"),
        (unn_c < unn_a_rest / 2, "少量标签做保序校准后，A 的不必要验证减少一半以上"),
    ]
    ok = True
    for passed, msg in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {msg}")
        ok &= passed
    print(f"RESULT: A 排序更准（AUROC {auc_a:.2f} vs {auc_b:.2f}），但因概率偏低让 {unn_a * 100:.0f}% 已完成的 run 被要求验证；"
          f"校准后降到 {unn_c * 100:.0f}%")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
