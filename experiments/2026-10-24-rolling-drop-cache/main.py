"""Agent 上下文管理的两种做法：改写前缀（摘要）vs 直接管理 KV 缓存（滚动丢弃）。

受论文 Cache Engineering for Agents (arXiv:2610.28577) 启发。论文指出：上下文工程
（裁剪或摘要历史）会改动前缀，迫使推理引擎重新预填充（re-prefill）保留下来的内容；
缓存工程则直接丢弃指定的 KV 条目、调整位置编码，不需要重新预填充。

本脚本用固定随机种子模拟一个 60 轮的工具调用 Agent（全部为模拟，不复现论文数字），
比较三种策略的「累计预填充 token 数」（近似预填充计算成本）和「峰值活跃缓存」：
- full：保留全部历史，只增量预填充新内容
- summarize：活跃上下文超过阈值时，把历史压缩成摘要，之后要重新预填充「系统提示 + 摘要」
- rolling_drop：只保留最近 K 个工具返回的 KV，较早的工具返回从缓存里丢弃；不重写前缀，
  因而不需要重新预填充
最后演示论文提到的「历史依赖」：同样的最终消息序列，经过不同的缓存操作顺序，
活跃缓存内容不同，所以只按前缀匹配复用缓存是不够的。
"""
from __future__ import annotations

import random
import sys

SEED = 24
TURNS = 60
SYSTEM = 2_000
THRESHOLD = 40_000  # summarize 的触发阈值
SUMMARY = 3_000
KEEP_TOOL = 4  # rolling_drop 保留最近几个工具返回


def make_trajectory(rng: random.Random):
    turns = []
    for _ in range(TURNS):
        assistant = rng.randint(150, 600)
        tool = int(rng.lognormvariate(7.6, 0.8))  # 工具返回长度偏长尾
        turns.append((assistant, tool))
    return turns


def full(turns):
    prefill, active, peak = SYSTEM, SYSTEM, SYSTEM
    for a, t in turns:
        prefill += a + t
        active += a + t
        peak = max(peak, active)
    return prefill, peak


def summarize(turns):
    prefill, active, peak, resets = SYSTEM, SYSTEM, SYSTEM, 0
    for a, t in turns:
        prefill += a + t
        active += a + t
        peak = max(peak, active)
        if active > THRESHOLD:
            # 前缀被改写：系统提示 + 摘要都要重新预填充
            active = SYSTEM + SUMMARY
            prefill += SYSTEM + SUMMARY
            resets += 1
    return prefill, peak, resets


def rolling_drop(turns):
    prefill, peak = SYSTEM, SYSTEM
    kept_assistant = 0
    tools = []
    for a, t in turns:
        prefill += a + t  # 只增量预填充新内容
        kept_assistant += a
        tools.append(t)
        if len(tools) > KEEP_TOOL:
            tools.pop(0)  # 直接丢弃最早工具返回的 KV，不重写前缀
        active = SYSTEM + kept_assistant + sum(tools)
        peak = max(peak, active)
    return prefill, peak


def history_dependence():
    """同一最终消息序列 [S, A1, T1, A2, T2]，两种操作顺序得到不同的活跃缓存。"""
    # 顺序 1：先丢 T1，再追加 A2、T2 -> A2 生成时看不到 T1
    cache1 = ["S", "A1", "T1"]
    cache1.remove("T1")
    cache1 += ["A2(未见T1)", "T2"]
    # 顺序 2：先追加 A2、T2，再丢 T1 -> A2 的 KV 是在看过 T1 的情况下算出来的
    cache2 = ["S", "A1", "T1", "A2(见过T1)", "T2"]
    cache2.remove("T1")
    same_tokens = [c.split("(")[0] for c in cache1] == [c.split("(")[0] for c in cache2]
    return same_tokens, cache1 != cache2


def main() -> int:
    turns = make_trajectory(random.Random(SEED))
    f_prefill, f_peak = full(turns)
    s_prefill, s_peak, resets = summarize(turns)
    r_prefill, r_peak = rolling_drop(turns)
    re_prefill = s_prefill - f_prefill
    same_tokens, diff_cache = history_dependence()

    print(f"设定：{TURNS} 轮工具调用，摘要阈值 {THRESHOLD} token，滚动保留最近 {KEEP_TOOL} 个工具返回")
    print(f"METRIC: full 峰值活跃缓存 = {f_peak / 1000:.1f} 千token")
    print(f"METRIC: summarize 峰值活跃缓存 = {s_peak / 1000:.1f} 千token")
    print(f"METRIC: rolling_drop 峰值活跃缓存 = {r_peak / 1000:.1f} 千token")
    print(f"METRIC: summarize 额外重新预填充 = {re_prefill / 1000:.1f} 千token")
    print(f"METRIC: rolling_drop 额外重新预填充 = {(r_prefill - f_prefill) / 1000:.1f} 千token")
    print(f"METRIC: summarize 触发次数 = {resets} 次")

    checks = [
        (r_peak < f_peak, "滚动丢弃的峰值活跃缓存小于保留全部历史"),
        (r_prefill == f_prefill, "滚动丢弃不需要任何重新预填充"),
        (resets > 0 and re_prefill > 0, "摘要策略在阈值触发后需要重新预填充"),
        (same_tokens and diff_cache, "同一消息序列经不同操作顺序得到不同的缓存状态（历史依赖）"),
    ]
    ok = True
    for passed, desc in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {desc}")
        ok &= passed

    print(
        f"RESULT: 模拟中滚动丢弃把峰值缓存从 {f_peak / 1000:.1f} 降到 {r_peak / 1000:.1f} 千token 且无需重新预填充，"
        f"摘要触发 {resets} 次、额外预填充 {re_prefill / 1000:.1f} 千token"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
