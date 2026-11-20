#!/usr/bin/env python3
"""Toy experiment for EGE (arXiv:2611.16378):
Evidence-governed statistical gating for self-generated agent rule updates.
Pure Python standard library, fully offline, deterministic seed.
"""
from __future__ import annotations

import math
import random
import statistics
import sys


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def hoeffding_radius(n: int, alpha: float, span: float = 2.0) -> float:
    """One-sided Hoeffding radius for bounded paired differences in [-1, 1] (span=2)."""
    return span * math.sqrt(math.log(1.0 / alpha) / (2.0 * n))


def simulate_candidate(
    rng: random.Random,
    *,
    n_audit: int,
    n_cal: int,
    true_primary_gain: float,
    true_guard_delta: float,
    eval_optimism_bias: float,
    noise: float = 0.05,
) -> dict:
    """Generate fresh paired audit scores and independent evaluator calibration samples."""
    # Paired differences d_i = cand_i - base_i in [-1, 1]
    primary_diffs_auto = []
    guard_diffs = []
    for _ in range(n_audit):
        base_p = rng.uniform(0.55, 0.75)
        cand_p_true = clamp(base_p + true_primary_gain + rng.gauss(0.0, noise))
        cand_p_auto = clamp(cand_p_true + eval_optimism_bias + rng.gauss(0.0, noise * 0.5))
        primary_diffs_auto.append(cand_p_auto - base_p)

        base_g = rng.uniform(0.75, 0.90)
        cand_g = clamp(base_g + true_guard_delta + rng.gauss(0.0, noise))
        guard_diffs.append(cand_g - base_g)

    # Independent calibration sample: ref_score - auto_score (negative means auto is optimistic)
    cal_diffs = []
    for _ in range(n_cal):
        err = -eval_optimism_bias + rng.gauss(0.0, noise * 0.5)
        cal_diffs.append(max(-1.0, min(1.0, err)))

    return {
        "primary_diffs_auto": primary_diffs_auto,
        "guard_diffs": guard_diffs,
        "cal_diffs": cal_diffs,
    }


def evaluate_ege_gate(
    sample: dict,
    *,
    primary_margin: float = 0.05,
    guard_tol: float = 0.05,
    alpha: float = 0.05,
) -> dict:
    """Apply EGE-style calibrated lower bound + non-inferiority gate."""
    p_diffs = sample["primary_diffs_auto"]
    g_diffs = sample["guard_diffs"]
    c_diffs = sample["cal_diffs"]

    mean_primary_auto = statistics.mean(p_diffs)
    mean_guard = statistics.mean(g_diffs)
    mean_cal = statistics.mean(c_diffs)

    # Split alpha budget across primary audit, calibration, and non-inferiority guard
    r_primary = hoeffding_radius(len(p_diffs), alpha / 3.0, span=2.0)
    r_cal = hoeffding_radius(len(c_diffs), alpha / 3.0, span=2.0)
    r_guard = hoeffding_radius(len(g_diffs), alpha / 3.0, span=2.0)

    # Calibrated simultaneous lower bound on true primary gain
    calibrated_primary_lcb = (mean_primary_auto - r_primary) + (mean_cal - r_cal)
    guard_lcb = mean_guard - r_guard

    pass_naive = mean_primary_auto >= primary_margin
    pass_primary = calibrated_primary_lcb >= primary_margin
    pass_guard = guard_lcb >= -guard_tol
    pass_ege = pass_primary and pass_guard

    return {
        "mean_primary_auto": mean_primary_auto,
        "mean_cal": mean_cal,
        "calibrated_primary_lcb": calibrated_primary_lcb,
        "mean_guard": mean_guard,
        "guard_lcb": guard_lcb,
        "pass_naive": pass_naive,
        "pass_primary": pass_primary,
        "pass_guard": pass_guard,
        "pass_ege": pass_ege,
    }


def main() -> int:
    rng = random.Random(20261119)
    n_audit = 1600
    n_cal = 1600

    candidates = [
        (
            "cand_good",
            dict(true_primary_gain=0.22, true_guard_delta=0.02, eval_optimism_bias=0.00),
            True,
        ),
        (
            "cand_regress",
            dict(true_primary_gain=0.22, true_guard_delta=-0.15, eval_optimism_bias=0.00),
            False,
        ),
        (
            "cand_optimistic",
            dict(true_primary_gain=0.00, true_guard_delta=0.01, eval_optimism_bias=0.20),
            False,
        ),
    ]

    results = {}
    print(f"=== EGE 规则更新统计闸门仿真（n_audit={n_audit}, n_cal={n_cal}, alpha=0.05）===")
    for name, params, _ in candidates:
        sample = simulate_candidate(rng, n_audit=n_audit, n_cal=n_cal, **params)
        res = evaluate_ege_gate(sample, primary_margin=0.05, guard_tol=0.08, alpha=0.05)
        results[name] = res
        print(
            f"- {name}: auto主目标均值={res['mean_primary_auto']:+.3f}, "
            f"校准均值={res['mean_cal']:+.3f}, 校准后下界={res['calibrated_primary_lcb']:+.3f}, "
            f"护栏均值={res['mean_guard']:+.3f}, 护栏下界={res['guard_lcb']:+.3f} | "
            f"无护栏={'放行' if res['pass_naive'] else '拦截'} vs EGE={'放行' if res['pass_ege'] else '拦截'}"
        )

    naive_false_accepts = sum(
        1 for name, _, should_pass in candidates if (not should_pass and results[name]["pass_naive"])
    )
    ege_false_accepts = sum(
        1 for name, _, should_pass in candidates if (not should_pass and results[name]["pass_ege"])
    )
    bad_total = sum(1 for _, _, should_pass in candidates if not should_pass)
    naive_block_rate = 100.0 * (bad_total - naive_false_accepts) / bad_total
    ege_block_rate = 100.0 * (bad_total - ege_false_accepts) / bad_total

    checks = [
        (
            results["cand_good"]["pass_ege"],
            "真改进候选 cand_good 通过 EGE 校准下界与非劣性护栏",
        ),
        (
            results["cand_regress"]["pass_naive"] and (not results["cand_regress"]["pass_guard"]) and (not results["cand_regress"]["pass_ege"]),
            "规范回归候选 cand_regress 骗过了均值判断，但被非劣性护栏拦下",
        ),
        (
            results["cand_optimistic"]["pass_naive"] and (not results["cand_optimistic"]["pass_primary"]) and (not results["cand_optimistic"]["pass_ege"]),
            "乐观评测候选 cand_optimistic 骗过了均值判断，但被评测器校准拦下",
        ),
        (
            ege_false_accepts == 0 and naive_false_accepts == 2,
            "EGE 误放行有害/无效更新数为 0，低于无护栏均值判断的 2 个",
        ),
    ]

    all_ok = True
    for ok, desc in checks:
        tag = "[PASS]" if ok else "[FAIL]"
        print(f"{tag} {desc}")
        if not ok:
            all_ok = False

    print(f"METRIC: 无护栏均值判断有害更新拦截率 = {naive_block_rate:.1f} %")
    print(f"METRIC: EGE 统计闸门有害更新拦截率 = {ege_block_rate:.1f} %")
    print(f"METRIC: cand_good 校准后主目标下界 = {results['cand_good']['calibrated_primary_lcb']:.3f} 分")
    print(f"METRIC: cand_optimistic 校准后主目标下界 = {results['cand_optimistic']['calibrated_primary_lcb']:.3f} 分")
    print(f"METRIC: cand_regress 护栏能力下界 = {results['cand_regress']['guard_lcb']:.3f} 分")

    if not all_ok:
        print("RESULT: 部分统计闸门检查未通过，请排查参数或实现。")
        return 1

    print("RESULT: EGE 三道统计闸门拦截了 100% 的回归与乐观偏差候选（2/2），同时放行了真改进候选。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
