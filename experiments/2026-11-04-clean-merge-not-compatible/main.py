"""文本合并干净 ≠ 两个任务兼容：用 git merge-file 合并两个"Agent"各自的改动，
再分别跑两个任务自己的验收测试，看「只看有没有合并冲突」会漏掉多少问题。

完全离线：只需要 Python 3 标准库和本机的 git 命令。
"""
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

BASE = {
    "pricing.py": textwrap.dedent("""\
        RATE = 0.9  # 默认九折


        def shipping(amount):
            return 0 if amount >= 100 else 10


        def final_price(amount):
            return round(amount * RATE, 2)
        """),
}

# 每个场景：两个任务各自在 BASE 上做的改动（只列出改过或新增的文件）+ 各自的验收测试
SCENARIOS = [
    {
        "name": "independent",
        "desc": "互不相关：A 调整包邮门槛，B 新增一个格式化函数",
        "a": {"pricing.py": BASE["pricing.py"].replace("amount >= 100", "amount >= 120")},
        "b": {"pricing.py": BASE["pricing.py"] + textwrap.dedent("""\


            def fmt(amount):
                return f"¥{amount:.2f}"
            """)},
        "test_a": "import pricing; assert pricing.shipping(110) == 10; assert pricing.shipping(130) == 0",
        "test_b": "import pricing; assert pricing.fmt(3) == '¥3.00'",
    },
    {
        "name": "same-line",
        "desc": "直接矛盾：A 把折扣改成八折，B 改成八五折（同一行）",
        "a": {"pricing.py": BASE["pricing.py"].replace("RATE = 0.9  # 默认九折", "RATE = 0.8  # 改为八折")},
        "b": {"pricing.py": BASE["pricing.py"].replace("RATE = 0.9  # 默认九折", "RATE = 0.85  # 改为八五折")},
        "test_a": "import pricing; assert pricing.final_price(100) == 80.0",
        "test_b": "import pricing; assert pricing.final_price(100) == 85.0",
    },
    {
        "name": "hidden-semantic",
        "desc": "隐性冲突：A 把包邮门槛提到 200，B 让总价含运费（按旧门槛写验收）",
        "a": {"pricing.py": BASE["pricing.py"].replace("amount >= 100", "amount >= 200")},
        "b": {"pricing.py": BASE["pricing.py"].replace(
            "return round(amount * RATE, 2)",
            "return round(amount * RATE + shipping(amount), 2)")},
        "test_a": "import pricing; assert pricing.shipping(150) == 10; assert pricing.shipping(250) == 0",
        "test_b": "import pricing; assert pricing.final_price(150) == 135.0; assert pricing.final_price(50) == 55.0",
    },
    {
        "name": "interface-mismatch",
        "desc": "接口没对齐：A 新文件调用 discount_for(code)，B 实现的却叫 get_discount_rate(code)（A 依赖 B 的接口，单独无法验收）",
        "a": {"coupons.py": textwrap.dedent("""\
            import pricing


            def apply_coupon(amount, code):
                return round(amount * pricing.discount_for(code), 2)
            """)},
        "b": {"pricing.py": BASE["pricing.py"] + textwrap.dedent("""\


            def get_discount_rate(code):
                return 0.7 if code == "VIP" else RATE
            """)},
        "test_a": "import coupons; assert coupons.apply_coupon(100, 'VIP') == 70.0",
        "test_b": "import pricing; assert pricing.get_discount_rate('VIP') == 0.7",
    },
]


def merge(base: dict, a: dict, b: dict, work: Path):
    """逐文件三方合并。返回 (合并后的文件, 冲突块数)。"""
    merged, conflicts = {}, 0
    for name in sorted(set(base) | set(a) | set(b)):
        o = base.get(name, "")
        x = a.get(name, o)
        y = b.get(name, o)
        paths = []
        for tag, text in (("ours", x), ("base", o), ("theirs", y)):
            p = work / f"{tag}_{name}"
            p.write_text(text, encoding="utf-8")
            paths.append(str(p))
        r = subprocess.run(["git", "merge-file", "-p", *paths], capture_output=True, text=True)
        if r.returncode < 0 or r.returncode > 127:
            raise RuntimeError(f"git merge-file 出错：{r.stderr}")
        conflicts += r.returncode
        merged[name] = r.stdout
    return merged, conflicts


def run_test(files: dict, code: str, work: Path) -> bool:
    d = work / "tree"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir()
    for name, text in files.items():
        (d / name).write_text(text, encoding="utf-8")
    r = subprocess.run([sys.executable, "-c", code], cwd=d, capture_output=True, text=True)
    return r.returncode == 0


def main():
    if shutil.which("git") is None:
        print("[FAIL] 本机没有 git 命令，无法运行三方合并")
        print("RESULT: 缺少 git，实验未运行")
        sys.exit(1)

    rows = {}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for sc in SCENARIOS:
            a_files = {**BASE, **sc["a"]}
            b_files = {**BASE, **sc["b"]}
            # 先确认：每个任务单独看都是对的
            alone_a = run_test(a_files, sc["test_a"], work)
            alone_b = run_test(b_files, sc["test_b"], work)
            merged, conflicts = merge(BASE, sc["a"], sc["b"], work)
            if conflicts:
                ta = tb = False
            else:
                ta = run_test(merged, sc["test_a"], work)
                tb = run_test(merged, sc["test_b"], work)
            rows[sc["name"]] = dict(alone=alone_a and alone_b, conflicts=conflicts, ta=ta, tb=tb)
            print(f"- {sc['name']}: {sc['desc']}")
            print(f"    单独验收 A={alone_a} B={alone_b} | 合并冲突块={conflicts} | 合并后验收 A={ta} B={tb}")

    checks = []

    def check(ok, msg):
        checks.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {msg}")

    check(all(r["alone"] for k, r in rows.items() if k != "interface-mismatch"),
          "前三个场景里，两个任务各自单独都能通过自己的验收测试")
    r = rows["independent"]
    check(r["conflicts"] == 0 and r["ta"] and r["tb"], "互不相关的改动：合并无冲突，合并后两边测试都通过")
    r = rows["same-line"]
    check(r["conflicts"] > 0, "同一行的直接矛盾：git 报告合并冲突，能被合并检查拦下")
    r = rows["hidden-semantic"]
    check(r["conflicts"] == 0 and not (r["ta"] and r["tb"]), "隐性语义冲突：合并无冲突，但合并后至少一边验收失败")
    r = rows["interface-mismatch"]
    check(r["conflicts"] == 0 and not (r["ta"] and r["tb"]), "接口没对齐：合并无冲突，但合并后至少一边验收失败")

    clean = sum(1 for r in rows.values() if r["conflicts"] == 0)
    both_ok = sum(1 for r in rows.values() if r["conflicts"] == 0 and r["ta"] and r["tb"])
    missed = clean - both_ok
    print(f"METRIC: 场景总数 = {len(rows)} 个")
    print(f"METRIC: 合并无冲突的场景 = {clean} 个")
    print(f"METRIC: 合并后双方验收都通过 = {both_ok} 个")
    print(f"METRIC: 只看合并冲突会漏掉的场景 = {missed} 个")

    if all(checks):
        print(f"RESULT: {clean} 个合并无冲突的场景里有 {missed} 个合并后验收失败，并行 Agent 的改动要合并后重跑双方测试")
    else:
        print("RESULT: 有检查未通过，结果与预期不符，见上方 [FAIL]")
        sys.exit(1)


if __name__ == "__main__":
    main()
