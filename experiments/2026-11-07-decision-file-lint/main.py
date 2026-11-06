"""检查待办文件和决策文件是否符合「验收句 + 提问集中」的规则。

规则整理自 Tobias Zimmergren《Agentic AI engineering: What the humans do, what the agents do,
and where the hard lines are》（2026-11-04）：
  - 每个待办写明「完成」的含义（本实验约定为一行里有「验收：」）
  - Agent 需要人决定的问题只写进决策文件，并附上 Agent 的建议（本实验约定为「建议：」）
  - 决策文件只列待决问题，回答后删除（本实验约定：出现「已回答」即视为未删除）
本实验不调用模型，只用正则检查内置的好、坏两组示例，演示这些规则可以机械化检查。
"""
import re
import sys

GOOD = {
    "backlog/auth.md": """# auth 工作流
- 登录页接入短信验证码 | 阻塞：无 | 依据：D-12 | 验收：输入正确验证码后 3 秒内跳转首页，错误码提示与设计稿一致
- 删除旧版记住密码逻辑 | 阻塞：等待 D-14 | 依据：D-9 | 验收：仓库中 grep remember_pwd 无结果，登录相关测试全部通过
""",
    "DECISIONS.md": """# 待决问题
- D-14：旧版记住密码的用户数据是否需要迁移？ 建议：不迁移，下次登录时提示重新勾选
""",
}

BAD = {
    "backlog/auth.md": """# auth 工作流
- 登录页接入短信验证码，做得健壮一点
- 删除旧版记住密码逻辑 | 验收：登录相关测试全部通过
- 优化登录速度，不确定要不要加缓存？
""",
    "backlog/search.md": """# search 工作流
- 搜索结果分页 | 验收：每页 20 条，翻页后 URL 带 page 参数
- 是否需要支持拼音搜索？
""",
    "DECISIONS.md": """# 待决问题
- D-14：旧版记住密码的用户数据是否需要迁移？
- D-12：验证码有效期多长？ 建议：5 分钟 | 已回答：5 分钟
""",
}

DECISION_FILE = "DECISIONS.md"


def lint(files):
    problems = []
    for path, text in files.items():
        items = [ln[2:].strip() for ln in text.splitlines() if ln.startswith("- ")]
        for it in items:
            asks = bool(re.search(r"[?？]", it))
            if path == DECISION_FILE:
                if "建议：" not in it:
                    problems.append(("decision-no-recommendation", path, it))
                if "已回答" in it:
                    problems.append(("decision-answered-not-removed", path, it))
            else:
                if asks:
                    problems.append(("question-outside-decisions", path, it))
                if "验收：" not in it and not asks:
                    problems.append(("missing-pass-line", path, it))
    return problems


def main():
    good = lint(GOOD)
    bad = lint(BAD)
    kinds = {}
    for k, path, it in bad:
        kinds[k] = kinds.get(k, 0) + 1
        print(f"  {k:<32} {path}: {it}")
    expected = {
        "missing-pass-line": 1,
        "question-outside-decisions": 2,
        "decision-no-recommendation": 1,
        "decision-answered-not-removed": 1,
    }
    checks = [
        (len(good) == 0, f"符合规则的示例没有报出问题（{len(good)} 个）"),
    ]
    for k, n in expected.items():
        checks.append((kinds.get(k, 0) == n, f"违规示例中 {k} 检出 {kinds.get(k, 0)} 处，应为 {n} 处"))
    failed = 0
    for ok, desc in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {desc}")
        failed += not ok
    total_bad_items = sum(len([ln for ln in t.splitlines() if ln.startswith("- ")]) for t in BAD.values())
    flagged = len({(p, it) for _, p, it in bad})
    print(f"METRIC: 坏示例文件中的条目数 = {total_bad_items} 条")
    print(f"METRIC: 被检出的条目数 = {flagged} 条")
    print(f"METRIC: 检出问题总数 = {len(bad)} 个")
    print(f"RESULT: 好示例 0 问题，坏示例文件 {total_bad_items} 条中 {flagged} 条违规全部检出，其余 {total_bad_items - flagged} 条合规，四类规则都能机械检查")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
