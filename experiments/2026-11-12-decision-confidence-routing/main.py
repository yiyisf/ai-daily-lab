"""玩具实验：复算 decision model 的置信度与期望分，并演示按置信度分流到人工。

不调用模型、不联网，只用 Python 标准库。
第一部分用 Hugging Face《Decision Models in Hugging Face》文章示例里给出的概率复算；
第二部分的工单与概率是本实验构造的，只用来演示「置信度阈值分流」的做法。
"""
import sys

checks = []


def check(ok, msg):
    checks.append(ok)
    print(("[PASS] " if ok else "[FAIL] ") + msg)


def choice_confidence(probs):
    """文章给出的 choice 置信度：(p_max - 1/K) / (1 - 1/K)，K 为选项数。"""
    k = len(probs)
    p_max = max(probs.values())
    return (p_max - 1 / k) / (1 - 1 / k)


def expected_score(probs, levels):
    """score 类问题：按有序刻度求期望值，如 low/medium/high = 0/1/2。"""
    return sum(levels[name] * p for name, p in probs.items())


# ---- 第一部分：用文章里的数字复算 ----
print("== 第一部分：复算文章示例 ==")
billing = {
    "billing": 0.9982666969299316,
    "technical": 0.0010246571619063616,
    "sales": 0.0007087149424478412,
}
conf = choice_confidence(billing)
print(f"choice 示例：p_max={max(billing.values()):.6f}，K=3，复算置信度={conf:.10f}")
check(abs(conf - 0.9974000453948975) < 1e-9, "choice 置信度复算与文章给出的 0.9974000453948975 一致")
check(abs(sum(billing.values()) - 1) < 1e-6, "choice 三个选项概率之和为 1")

urgency = {"low": 0.014908230863511562, "medium": 0.26479458808898926, "high": 0.7202972173690796}
score = expected_score(urgency, {"low": 0, "medium": 1, "high": 2})
print(f"score 示例：low/medium/high 期望值={score:.10f}")
check(abs(score - 1.7053890228271484) < 1e-6, "score 期望值复算与文章给出的 1.7053890228271484 一致")

# K 越大，同样的 p_max 对应的置信度越高：0.6 在 2 选 1 和 5 选 1 里含义不同
c2 = choice_confidence({"a": 0.6, "b": 0.4})
c5 = choice_confidence({"a": 0.6, "b": 0.1, "c": 0.1, "d": 0.1, "e": 0.1})
print(f"p_max=0.6 时：K=2 置信度={c2:.3f}，K=5 置信度={c5:.3f}")
check(c5 > c2, "同样的最大概率，选项越多置信度越高（公式扣掉了随机猜的 1/K）")

# ---- 第二部分：构造的工单，按置信度阈值分流 ----
print("\n== 第二部分：构造工单的分流演示 ==")
# (工单, 模型给出的概率, 人工标注的正确部门) —— 全部为本实验构造
tickets = [
    ("重复扣款要退款", {"billing": 0.97, "technical": 0.02, "sales": 0.01}, "billing"),
    ("登录页一直转圈", {"billing": 0.03, "technical": 0.95, "sales": 0.02}, "technical"),
    ("企业版多少钱", {"billing": 0.10, "technical": 0.02, "sales": 0.88}, "sales"),
    ("发票抬头写错", {"billing": 0.91, "technical": 0.05, "sales": 0.04}, "billing"),
    ("升级套餐后功能不能用", {"billing": 0.30, "technical": 0.45, "sales": 0.25}, "technical"),
    ("试用到期扣了费", {"billing": 0.48, "technical": 0.04, "sales": 0.48}, "billing"),
    ("导出报表报错 500", {"billing": 0.01, "technical": 0.98, "sales": 0.01}, "technical"),
    ("想换年付能便宜吗", {"billing": 0.52, "technical": 0.02, "sales": 0.46}, "sales"),
]

THRESHOLD = 0.6
auto, auto_correct, all_correct = 0, 0, 0
for text, probs, truth in tickets:
    pred = max(probs, key=probs.get)
    c = choice_confidence(probs)
    route = "自动分派" if c >= THRESHOLD else "转人工"
    ok = pred == truth
    all_correct += ok
    if c >= THRESHOLD:
        auto += 1
        auto_correct += ok
    print(f"{text:<14} 预测={pred:<9} 置信度={c:.3f} -> {route}{'' if ok else '（预测错）'}")

n = len(tickets)
acc_all = all_correct / n * 100
acc_auto = auto_correct / auto * 100 if auto else 0.0
auto_rate = auto / n * 100
print(f"METRIC: 全部自动分派准确率 = {acc_all:.1f} %")
print(f"METRIC: 阈值以上自动分派准确率 = {acc_auto:.1f} %")
print(f"METRIC: 自动分派占比 = {auto_rate:.1f} %")
check(acc_auto >= acc_all, f"按置信度 {THRESHOLD} 分流后，自动分派部分的准确率不低于全部自动分派")
check(0 < auto < n, "阈值既放行了一部分工单，也把一部分留给人工")

passed = sum(checks)
print(f"\nRESULT: 文章示例的置信度和期望分复算一致；构造数据上按置信度 {THRESHOLD} 分流，"
      f"{auto}/{n} 张工单自动分派、准确率 {acc_auto:.1f}%，其余转人工")
sys.exit(0 if passed == len(checks) else 1)
