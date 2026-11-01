# 仅使用 Python 标准库，无需安装依赖
"""玩具实验：在上线量化模型之前，用「两段式验收门」筛出不能用的文件。

思路来自 quantcheck（论文 Broken on Arrival 的配套工具）README 里描述的筛查规则，
但这里不下载任何模型、不调用推理服务，只对手写的模拟数据运行同样的判定逻辑：

  第一段：15 道编程题冒烟测试，通过数低于 9 的标为「可疑」
  第二段：与同一模型变体的高精度版本（q6_K / q8_0 / fp16）的中位数比较；
          只有自身 ≤ 2 且组基线 ≥ 8 时才判为「不能用」，组基线 < 8 时不下结论

另外实现了 README 中的重复度指标 rep6：最常见的 6 词片段出现次数 × 6 ÷ 总词数，
用来观察「输出在原地打转」这类症状。

所有分数都是手写的模拟值，只用来演示判定逻辑，与真实模型无关。
"""
import statistics
import sys
from collections import Counter

SCREEN_TASKS = 15
STAGE1_FLAG_BELOW = 9
SUSPECT_MAX = 2
BASELINE_MIN = 8
BASELINE_QUANTS = ("q6_K", "q8_0", "fp16")

# (模型变体, 量化级别, 冒烟测试通过数, 人工标注：是否真的不能用)
INVENTORY = [
    # 变体 A：中等模型，低比特量化后完全失效
    ("coder-a:3b", "fp16", 15, False),
    ("coder-a:3b", "q8_0", 15, False),
    ("coder-a:3b", "q6_K", 14, False),
    ("coder-a:3b", "q4_K_M", 13, False),
    ("coder-a:3b", "q3_K_M", 0, True),
    ("coder-a:3b", "q2_K", 1, True),
    # 变体 B：低比特量化只是变弱，仍然可用
    ("coder-b:7b", "fp16", 15, False),
    ("coder-b:7b", "q8_0", 15, False),
    ("coder-b:7b", "q4_K_M", 14, False),
    ("coder-b:7b", "q3_K_S", 7, False),
    ("coder-b:7b", "q2_K", 5, False),
    # 变体 C：小模型本身就弱，连 fp16 都只有几题，组基线不足以下结论
    ("coder-c:1b", "fp16", 5, False),
    ("coder-c:1b", "q8_0", 4, False),
    ("coder-c:1b", "q4_K_M", 3, False),
    ("coder-c:1b", "q2_K", 1, False),
]


def rep6(text):
    """README 定义的重复度：6 × 最常见 6 词片段次数 ÷ 词数；不是比例，可以超过 1。"""
    words = text.split()
    if len(words) < 6:
        return 0.0
    grams = Counter(tuple(words[i:i + 6]) for i in range(len(words) - 5))
    return 6 * grams.most_common(1)[0][1] / len(words)


def baselines(inventory):
    groups = {}
    for variant, quant, score, _ in inventory:
        if quant in BASELINE_QUANTS:
            groups.setdefault(variant, []).append(score)
    return {v: statistics.median(s) for v, s in groups.items()}


def judge(variant, quant, score, base):
    if score >= STAGE1_FLAG_BELOW:
        return "pass"
    b = base.get(variant)
    if b is None or b < BASELINE_MIN:
        return "unjudged"
    if score <= SUSPECT_MAX:
        return "non-functional"
    return "degraded"


def main():
    base = baselines(INVENTORY)
    results = []
    print(f"{'变体':<12}{'量化':<8}{'通过':>4}  {'组基线':>6}  判定")
    for variant, quant, score, broken in INVENTORY:
        verdict = judge(variant, quant, score, base)
        results.append((variant, quant, score, broken, verdict))
        print(f"{variant:<12}{quant:<8}{score:>4}  {base.get(variant, '-'):>6}  {verdict}")

    naive = [r for r in results if r[2] < STAGE1_FLAG_BELOW]
    gate = [r for r in results if r[4] == "non-functional"]
    truly_broken = [r for r in results if r[3]]
    naive_fp = [r for r in naive if not r[3]]
    gate_fp = [r for r in gate if not r[3]]
    unjudged = [r for r in results if r[4] == "unjudged"]

    looping = "def add(a, b):\n" + "return a + b " * 40
    normal = ("def add(a, b):\n    \"\"\"Return the sum of two numbers.\"\"\"\n"
              "    if not isinstance(a, (int, float)):\n        raise TypeError('a must be a number')\n"
              "    return a + b")
    r_loop, r_norm = rep6(looping), rep6(normal)

    checks = [
        (all(r in gate for r in truly_broken), "两段式门拦下了全部真正不能用的模拟文件"),
        (len(gate_fp) == 0, "两段式门没有把「变弱但能用」的低比特文件判为不能用"),
        (len(naive_fp) > len(gate_fp), "只用「低于 9 题」一条阈值时，误报比两段式门多"),
        (all(r[0] == "coder-c:1b" for r in unjudged) and len(unjudged) > 0,
         "组基线不足 8 题的小模型变体被标为「不下结论」，而不是误判"),
        (r_loop > 1 > r_norm, "rep6 对原地打转的输出明显偏高（可超过 1），对正常代码很低"),
    ]
    ok = True
    for passed, desc in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {desc}")
        ok &= passed

    print(f"METRIC: 单阈值标记数 = {len(naive)} 个")
    print(f"METRIC: 两段式判为不能用 = {len(gate)} 个")
    print(f"METRIC: 单阈值误报 = {len(naive_fp)} 个")
    print(f"METRIC: 两段式误报 = {len(gate_fp)} 个")
    print(f"METRIC: 不下结论 = {len(unjudged)} 个")
    print(f"METRIC: 打转输出 rep6 = {r_loop:.2f} 倍")
    print(f"METRIC: 正常输出 rep6 = {r_norm:.2f} 倍")
    if ok:
        print(f"RESULT: 两段式门在 {len(INVENTORY)} 个模拟文件上拦下 {len(gate)} 个不能用的，"
              f"单阈值多出 {len(naive_fp)} 个误报，组基线不足时不下结论")
    else:
        print("RESULT: 有检查未通过，判定逻辑需要修正")
        sys.exit(1)


if __name__ == "__main__":
    main()
