"""离线校验「审计发现」记录的小示例。

规则来自 cloudflare/security-audit-skill README 的描述：
- confirmed 需要完整的源码追踪和有限的观察结果
- needs_validation 需要写明未解决的具体事实，且不带严重度
- 验证者不能是发现者本人

字段名、记录内容都是本实验自己构造的 mock，不是该技能 findings.json 的真实 schema。
"""
import sys

SEVERITIES = {"low", "medium", "high", "critical"}

# (记录, 期望的违规原因集合；空集合表示应当通过)
RECORDS = [
    ({"id": "F1", "status": "confirmed", "severity": "high", "finder": "hunter-1",
      "verifier": "verifier-2", "trace": ["routes.py:12", "db.py:40"],
      "observed": "payload 触发了 SQL 报错，仅限本地沙箱"}, set()),
    ({"id": "F2", "status": "confirmed", "severity": "high", "finder": "hunter-1",
      "verifier": "hunter-1", "trace": ["a.py:1"], "observed": "复现成功"},
     {"self-verified"}),
    ({"id": "F3", "status": "confirmed", "severity": "medium", "finder": "hunter-2",
      "verifier": "verifier-1", "trace": [], "observed": "复现成功"},
     {"missing-trace"}),
    ({"id": "F4", "status": "confirmed", "severity": "medium", "finder": "hunter-2",
      "verifier": "verifier-1", "trace": ["b.py:9"], "observed": ""},
     {"missing-observation"}),
    ({"id": "F5", "status": "needs_validation", "finder": "hunter-3",
      "unresolved": "未确认 admin 路由是否在网关层已鉴权"}, set()),
    ({"id": "F6", "status": "needs_validation", "severity": "high", "finder": "hunter-3",
      "unresolved": "未确认配置是否生效"}, {"severity-on-unvalidated"}),
    ({"id": "F7", "status": "needs_validation", "finder": "hunter-3", "unresolved": ""},
     {"missing-unresolved-fact"}),
    ({"id": "F8", "status": "rejected", "finder": "hunter-4", "verifier": "verifier-2",
      "reason": "输入在上游已被白名单过滤"}, set()),
]


def check(rec):
    problems = set()
    status = rec["status"]
    if status == "confirmed":
        if rec.get("severity") not in SEVERITIES:
            problems.add("bad-severity")
        if not rec.get("trace"):
            problems.add("missing-trace")
        if not rec.get("observed"):
            problems.add("missing-observation")
        if rec.get("verifier") == rec.get("finder"):
            problems.add("self-verified")
    elif status == "needs_validation":
        if "severity" in rec:
            problems.add("severity-on-unvalidated")
        if not rec.get("unresolved"):
            problems.add("missing-unresolved-fact")
    return problems


def main():
    passed = 0
    flagged = 0
    for rec, expected in RECORDS:
        got = check(rec)
        if got:
            flagged += 1
        ok = got == expected
        passed += ok
        tag = "[PASS]" if ok else "[FAIL]"
        print(f"{tag} {rec['id']} ({rec['status']}): 违规={sorted(got) or '无'}")
    print(f"METRIC: 校验结论与标注一致 = {passed} 条")
    print(f"METRIC: 被标出违规的记录 = {flagged} 条")
    if passed != len(RECORDS):
        print("RESULT: 有记录的校验结论与标注不一致")
        sys.exit(1)
    print(f"RESULT: {len(RECORDS)} 条 mock 记录全部判定正确，其中 {flagged} 条违规被指出具体原因")


if __name__ == "__main__":
    main()
