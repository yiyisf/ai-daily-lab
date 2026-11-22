#!/usr/bin/env python3
"""Toy experiment for arXiv:2611.11455 (Coding Agents Propagate Vulnerabilities):
Incremental unified-diff static lint gate that blocks newly propagated insecure/non-compliant
neighbor patterns without tripping on legacy context lines.
Pure Python standard library, fully offline.
"""
from __future__ import annotations

import re
import sys

RULES = [
    ("SQL_INTERP", re.compile(r'execute\(\s*f["\']|execute\([^)]*\+'), "禁止拼接 SQL 字符串，请改用参数化查询"),
    ("UNSAFE_EVAL", re.compile(r"\beval\s*\("), "禁止新增 eval() 调用"),
    ("SHELL_TRUE", re.compile(r"subprocess\.\w+\([^)]*shell\s*=\s*True"), "禁止 subprocess 使用 shell=True"),
    ("HARDCODED_SECRET", re.compile(r'(?i)(api_key|secret_token)\s*=\s*["\'][A-Za-z0-9_\-]{12,}["\']'), "禁止硬编码密钥，请改读环境变量"),
    ("RAW_DIV_BUTTON", re.compile(r"<div\b[^>]*\bonClick="), "禁止手写 <div onClick> 伪按钮，请复用 <UiButton>"),
]

DIFF_CASES = [
    {
        "name": "PR-01-propagated-sql-interp",
        "should_block": True,
        "diff": """
--- a/app/orders.py
+++ b/app/orders.py
@@ -10,4 +10,6 @@
 # legacy neighbor code (must not trigger false positive):
 cursor.execute(f"SELECT * FROM legacy_orders WHERE id = {old_id}")
+def get_order_by_user(cursor, user_id):
+    return cursor.execute(f"SELECT * FROM orders WHERE user_id = {user_id}")
""",
    },
    {
        "name": "PR-02-propagated-eval",
        "should_block": True,
        "diff": """
--- a/app/calc.py
+++ b/app/calc.py
@@ -1,3 +1,5 @@
 # legacy neighbor:
 old_val = eval(legacy_expr)
+def parse_discount(expr):
+    return eval(expr)
""",
    },
    {
        "name": "PR-03-propagated-shell-true",
        "should_block": True,
        "diff": """
--- a/app/runner.py
+++ b/app/runner.py
@@ -5,3 +5,5 @@
 subprocess.run("ls -la", shell=True)
+def run_report(arg):
+    return subprocess.run(f"report {arg}", shell=True)
""",
    },
    {
        "name": "PR-04-propagated-secret",
        "should_block": True,
        "diff": """
--- a/app/client.py
+++ b/app/client.py
@@ -1,2 +1,4 @@
 LEGACY_KEY = "old_placeholder"
+def init_partner():
+    api_key = "sk_live_9988776655443322"
+    return api_key
""",
    },
    {
        "name": "PR-05-propagated-raw-div-button",
        "should_block": True,
        "diff": """
--- a/web/OrderList.tsx
+++ b/web/OrderList.tsx
@@ -20,3 +20,5 @@
 <div onClick={legacyClose}>Old Close</div>
+export function FilterAction({ onOpen }) {
+  return <div onClick={onOpen} className="btn">筛选</div>;
+}
""",
    },
    {
        "name": "PR-06-clean-sql-despite-legacy-neighbor",
        "should_block": False,
        "diff": """
--- a/app/orders.py
+++ b/app/orders.py
@@ -10,4 +10,6 @@
 cursor.execute(f"SELECT * FROM legacy_orders WHERE id = {old_id}")
+def get_order_safe(cursor, user_id):
+    return cursor.execute("SELECT * FROM orders WHERE user_id = ?", (user_id,))
""",
    },
    {
        "name": "PR-07-clean-subprocess-despite-legacy-neighbor",
        "should_block": False,
        "diff": """
--- a/app/runner.py
+++ b/app/runner.py
@@ -5,3 +5,5 @@
 subprocess.run("ls -la", shell=True)
+def run_report_safe(arg):
+    return subprocess.run(["report", arg], check=True)
""",
    },
    {
        "name": "PR-08-clean-uibutton-despite-legacy-neighbor",
        "should_block": False,
        "diff": """
--- a/web/OrderList.tsx
+++ b/web/OrderList.tsx
@@ -20,3 +20,5 @@
 <div onClick={legacyClose}>Old Close</div>
+export function FilterAction({ onOpen }) {
+  return <UiButton variant="primary" onClick={onOpen}>筛选</UiButton>;
+}
""",
    },
]


def scan_added_lines(unified_diff: str) -> list[tuple[str, str]]:
    """Scan only added lines ('+' excluding '+++') against RULES."""
    hits: list[tuple[str, str]] = []
    for line in unified_diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        code = line[1:]
        for rule_id, pattern, msg in RULES:
            if pattern.search(code):
                hits.append((rule_id, msg))
    return hits


def main() -> int:
    bad_total = sum(1 for c in DIFF_CASES if c["should_block"])
    clean_total = sum(1 for c in DIFF_CASES if not c["should_block"])
    bad_blocked = 0
    clean_allowed = 0
    false_positives = 0

    print("=== 增量 Diff 静态门禁离线对照（5 份违规扩散 PR + 3 份含旧坏邻近代码的合规 PR）===")
    for case in DIFF_CASES:
        hits = scan_added_lines(case["diff"])
        blocked = len(hits) > 0
        if case["should_block"] and blocked:
            bad_blocked += 1
        elif (not case["should_block"]) and (not blocked):
            clean_allowed += 1
        elif (not case["should_block"]) and blocked:
            false_positives += 1

        detail = ", ".join(r for r, _ in hits) if hits else "无命中"
        print(f"- {case['name']}: {'拦截' if blocked else '放行'} ({detail})")

    block_rate = 100.0 * bad_blocked / bad_total
    clean_pass_rate = 100.0 * clean_allowed / clean_total
    fp_rate = 100.0 * false_positives / clean_total

    checks = [
        (bad_blocked == bad_total, f"新增行中照抄的 5 类不安全/违规写法全部被拦截（{bad_blocked}/{bad_total}）"),
        (clean_allowed == clean_total, f"含历史坏邻近代码的 3 份合规 PR 全部放行（{clean_allowed}/{clean_total}）"),
        (false_positives == 0, "历史上下文旧漏洞未触发任何误报（0 误报）"),
    ]

    all_ok = True
    for ok, desc in checks:
        print(f"{'[PASS]' if ok else '[FAIL]'} {desc}")
        if not ok:
            all_ok = False

    print(f"METRIC: 违规扩散新增代码拦截率 = {block_rate:.1f} %")
    print(f"METRIC: 含旧坏邻近代码的合规 PR 放行率 = {clean_pass_rate:.1f} %")
    print(f"METRIC: 历史上下文误报率 = {fp_rate:.1f} %")

    if not all_ok:
        print("RESULT: 增量 Diff 静态门禁检查未通过，请排查规则实现。")
        return 1

    print("RESULT: 增量 Diff 静态门禁拦截了 100% 新扩散的不安全与违规写法（5/5），且对历史遗留上下文零误报。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
