"""用「三臂证明 + 回归检查」验收一个补丁。

受 Trail of Bits patching-bugs / regression-hunt 插件启发：
  三臂证明：原代码上复现检查应失败 → 打补丁后应通过 → 撤回补丁后应再次失败
  回归检查：原来通过的既有行为，打补丁后仍应通过

样例：parse_amount() 解析金额字符串，原版不支持千位分隔符（bug 报告：'1,234.50' 报错）。
两个候选补丁都能修好 bug，但其中一个顺手破坏了负数解析。
只用 Python 标准库，所有代码都在本文件中。
"""
from __future__ import annotations

import sys

ORIGINAL = '''
def parse_amount(s):
    return float(s.strip())
'''

# 候选补丁 A：用正则校验格式，修好了千位分隔符，但正则漏掉了负号
PATCH_A = '''
import re
_PAT = re.compile(r"^\\d{1,3}(,\\d{3})*(\\.\\d+)?$|^\\d+(\\.\\d+)?$")
def parse_amount(s):
    s = s.strip()
    if not _PAT.match(s):
        raise ValueError("bad amount: " + s)
    return float(s.replace(",", ""))
'''

# 候选补丁 B：同样校验格式，保留可选负号
PATCH_B = '''
import re
_PAT = re.compile(r"^-?(\\d{1,3}(,\\d{3})*|\\d+)(\\.\\d+)?$")
def parse_amount(s):
    s = s.strip()
    if not _PAT.match(s):
        raise ValueError("bad amount: " + s)
    return float(s.replace(",", ""))
'''

# bug 报告对应的复现检查
BUG_CHECK = ("1,234.50", 1234.5)

# 既有的、原本就支持的行为（相当于已有的测试集）
EXISTING = [
    ("12.5", 12.5),
    (" 7 ", 7.0),
    ("-3", -3.0),
    ("0.25", 0.25),
    ("1000", 1000.0),
]


def load(src: str):
    ns: dict = {}
    exec(src, ns)  # noqa: S102 —— 只执行本文件内的固定代码
    return ns["parse_amount"]


def passes(fn, case) -> bool:
    inp, want = case
    try:
        return abs(fn(inp) - want) < 1e-9
    except Exception:  # noqa: BLE001
        return False


def three_arm(patch: str) -> tuple[bool, list[str]]:
    arms = [
        ("原代码", ORIGINAL, False),
        ("打补丁", patch, True),
        ("撤回补丁", ORIGINAL, False),
    ]
    log, ok = [], True
    for name, src, want in arms:
        got = passes(load(src), BUG_CHECK)
        good = got == want
        ok &= good
        log.append(f"{name}: 复现检查{'通过' if got else '失败'}（期望{'通过' if want else '失败'}）{'✓' if good else '✗'}")
    return ok, log


def regressions(patch: str) -> list[str]:
    before, after = load(ORIGINAL), load(patch)
    return [inp for inp, want in EXISTING if passes(before, (inp, want)) and not passes(after, (inp, want))]


def main() -> int:
    results = {}
    for name, patch in (("补丁 A", PATCH_A), ("补丁 B", PATCH_B)):
        ok, log = three_arm(patch)
        regs = regressions(patch)
        results[name] = (ok, regs)
        print(f"== {name} ==")
        for line in log:
            print("  " + line)
        print(f"  三臂证明：{'成立' if ok else '不成立'}")
        print(f"  回归：{len(regs)} 个" + (f"，原本支持、现在失败的输入：{regs!r}" if regs else ""))
        verdict = "可接受" if ok and not regs else "拒绝"
        print(f"  结论：{verdict}\n")

    a_ok, a_regs = results["补丁 A"]
    b_ok, b_regs = results["补丁 B"]
    checks = [
        ("两个补丁都通过三臂证明", a_ok and b_ok),
        ("补丁 A 被回归检查拦下（负数解析被破坏）", a_regs == ["-3"]),
        ("补丁 B 没有回归", b_regs == []),
    ]
    for desc, good in checks:
        print(f"[{'PASS' if good else 'FAIL'}] {desc}")
    all_ok = all(g for _, g in checks)
    print("\nRESULT:", "只看 bug 是否修好会接受补丁 A；加上回归检查后只接受补丁 B" if all_ok else "检查未全部通过")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
