"""玩具模拟：固定最高「推理强度」 vs 从低档开始、验证失败才升档。

不是论文代码，也不调用任何模型。用随机搜索求解子集和问题来模拟「推理强度」：
- 每个强度档位对应一个固定的搜索预算（类比思考 token），该档位无论是否提前找到答案都会花掉整份预算；
- 验证器只检查答案是否满足约束（类比「运行测试」），不知道正确答案本身；
- 升档策略：先用最低档，验证失败才换下一档，成本累加。
"""
import random
import sys

SEED = 20261030
LEVELS = [("low", 64), ("medium", 512), ("high", 4096)]
SIZES = [6, 10, 14, 18]          # 题目规模越大越难
TASKS_PER_SIZE = 60


def make_task(rng, n):
    items = [rng.randint(1, 10_000) for _ in range(n)]
    planted = [i for i in range(n) if rng.random() < 0.5] or [0]
    return items, sum(items[i] for i in planted)


def verify(items, target, answer):
    return answer is not None and sum(items[i] for i in answer) == target


def solve(items, target, budget, rng):
    """随机抽样 budget 个子集，返回第一个满足约束的；成本固定为 budget。"""
    n = len(items)
    found = None
    for _ in range(budget):
        cand = [i for i in range(n) if rng.random() < 0.5]
        if found is None and verify(items, target, cand):
            found = cand
    return found, budget


def main():
    rng = random.Random(SEED)
    tasks = [(n, *make_task(rng, n)) for n in SIZES for _ in range(TASKS_PER_SIZE)]
    total = len(tasks)

    fixed = {name: {"ok": [], "cost": 0} for name, _ in LEVELS}
    esc_ok, esc_cost, esc_final_level = [], 0, {name: 0 for name, _ in LEVELS}
    verifier_sound = True

    for t_idx, (n, items, target) in enumerate(tasks):
        for name, budget in LEVELS:
            ans, cost = solve(items, target, budget, random.Random(f"{SEED}-{t_idx}-{name}-fixed"))
            if ans is not None and not verify(items, target, ans):
                verifier_sound = False
            fixed[name]["ok"].append(ans is not None)
            fixed[name]["cost"] += cost

        solved = False
        for name, budget in LEVELS:
            ans, cost = solve(items, target, budget, random.Random(f"{SEED}-{t_idx}-{name}-esc"))
            esc_cost += cost
            if verify(items, target, ans):
                solved = True
                esc_final_level[name] += 1
                break
        esc_ok.append(solved)

    def acc(lst):
        return 100.0 * sum(lst) / len(lst)

    hi = fixed["high"]
    easy = [i for i in range(total) if all(fixed[name]["ok"][i] for name, _ in LEVELS)]
    regress = sum(1 for i in range(total) if fixed["low"]["ok"][i] and not hi["ok"][i])

    print(f"任务数: {total}（规模 {SIZES} 各 {TASKS_PER_SIZE} 题）")
    for name, budget in LEVELS:
        f = fixed[name]
        print(f"METRIC: 固定 {name} 档正确率 = {acc(f['ok']):.1f} %")
    print(f"METRIC: 升档策略正确率 = {acc(esc_ok):.1f} %")
    print(f"METRIC: 固定 high 档平均成本 = {hi['cost'] / total:.0f} 次采样")
    print(f"METRIC: 升档策略平均成本 = {esc_cost / total:.0f} 次采样")
    saving = 100.0 * (1 - esc_cost / hi["cost"])
    print(f"METRIC: 升档相对固定 high 节省成本 = {saving:.1f} %")
    print(f"METRIC: 三档都能做对的简单题占比 = {100.0 * len(easy) / total:.1f} %")
    print(f"升档策略最终停在各档的题数: {esc_final_level}")
    print(f"低档做对、固定 high 档却没做对的题数: {regress}")

    checks = [
        (verifier_sound, "验证器只放行满足约束的答案"),
        (acc(esc_ok) >= acc(hi["ok"]) - 2.0, "升档策略正确率比固定 high 档低不超过 2 个百分点"),
        (esc_cost < hi["cost"], "升档策略总成本低于固定 high 档"),
        (len(easy) > 0, "存在三档都能做对的简单题（这些题上高档纯属多花钱）"),
        (esc_final_level["low"] > 0, "有题目在最低档就通过验证，无需升档"),
    ]
    failed = 0
    for ok, desc in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {desc}")
        failed += not ok

    print(f"RESULT: 先低档、验证失败再升档，正确率 {acc(esc_ok):.1f}% 对比固定 high 档 {acc(hi['ok']):.1f}%，成本节省 {saving:.1f}%")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
