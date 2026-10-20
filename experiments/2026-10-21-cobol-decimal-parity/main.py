#!/usr/bin/env python3
"""COBOL 定点运算「截断 vs 四舍五入」的迁移等价性小实验。

OpenAI 在介绍 COBOL 迁移评测时举例：COBOL 的定点运算默认截断多余小数位，
除非显式写 ROUNDED；把它改写成「四舍五入」的版本能正常运行，却会算出不同的金额。
本实验用 Python decimal 模拟一段简化的计息逻辑（PIC 9(7)V99），
对比两种迁移写法与「参考实现」的逐字节输出是否一致。

参考实现与数据均为本实验自拟，不是 OpenAI 评测中的程序。
"""
import sys
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

CENT = Decimal("0.01")

# 模拟 COBOL: COMPUTE WS-INTEREST = WS-BALANCE * WS-RATE / 12
# 目标字段 PIC 9(7)V99 —— 不带 ROUNDED，多余位截断
def cobol_reference(balance: Decimal, annual_rate: Decimal) -> Decimal:
    return (balance * annual_rate / Decimal(12)).quantize(CENT, rounding=ROUND_DOWN)


# 迁移写法 A：忠实保留截断语义
def migrated_truncate(balance: Decimal, annual_rate: Decimal) -> Decimal:
    return (balance * annual_rate / Decimal(12)).quantize(CENT, rounding=ROUND_DOWN)


# 迁移写法 B：「看起来更合理」的四舍五入（常见的错误改写）
def migrated_round(balance: Decimal, annual_rate: Decimal) -> Decimal:
    return (balance * annual_rate / Decimal(12)).quantize(CENT, rounding=ROUND_HALF_UP)


# 迁移写法 C：用浮点数再格式化（另一种常见改写）
def migrated_float(balance: Decimal, annual_rate: Decimal) -> Decimal:
    return Decimal(f"{float(balance) * float(annual_rate) / 12:.2f}")


def accounts():
    """确定性生成 1000 个账户：余额 100.00~99999.99，年利率 0.0125~0.0800。"""
    rates = [Decimal("0.0125"), Decimal("0.0199"), Decimal("0.0350"), Decimal("0.0475"), Decimal("0.0800")]
    seed = 20261021
    for i in range(1000):
        seed = (seed * 1103515245 + 12345) % (2 ** 31)
        cents = 10000 + seed % 9990000
        yield Decimal(cents) / 100, rates[i % len(rates)]


def render(fn) -> bytes:
    """输出成 COBOL 风格的定长报表行，用于逐字节比较。"""
    lines = []
    for i, (bal, rate) in enumerate(accounts()):
        interest = fn(bal, rate)
        lines.append(f"{i:06d}{int(bal * 100):09d}{int(interest * 100):09d}")
    return ("\n".join(lines) + "\n").encode("ascii")


def main() -> int:
    ref = render(cobol_reference)
    ok = True
    results = {}
    for name, fn in [("truncate", migrated_truncate), ("round_half_up", migrated_round), ("float", migrated_float)]:
        out = render(fn)
        ref_lines, out_lines = ref.splitlines(), out.splitlines()
        diff = sum(1 for a, b in zip(ref_lines, out_lines) if a != b)
        cents = sum(int(b[-9:]) - int(a[-9:]) for a, b in zip(ref_lines, out_lines))
        results[name] = (out == ref, diff, cents)
        print(f"{name:14s} byte_parity={out == ref!s:5s} diff_rows={diff:4d}/1000 total_delta_cents={cents:+d}")

    # 检查：忠实迁移必须逐字节一致；四舍五入版本应能被逐字节对比发现
    if not results["truncate"][0]:
        print("FAIL: 保留截断语义的迁移应当与参考实现逐字节一致")
        ok = False
    if results["round_half_up"][0]:
        print("FAIL: 四舍五入版本竟与参考一致，样本不足以暴露差异")
        ok = False
    if results["round_half_up"][2] <= 0:
        print("FAIL: 四舍五入版本的总金额应高于截断版本")
        ok = False

    t, r, f = results["truncate"], results["round_half_up"], results["float"]
    print(
        f"RESULT: truncate parity={t[0]}; round_half_up parity={r[0]} "
        f"({r[1]} rows differ, +{r[2]} cents); float parity={f[0]} ({f[1]} rows differ)"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
