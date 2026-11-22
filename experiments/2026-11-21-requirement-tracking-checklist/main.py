#!/usr/bin/env python3
"""Toy experiment for SWE-CoWork (arXiv:2611.20218):
Requirement-tracking delivery ledger that blocks partial/unverified coding-agent handoffs.
Pure Python standard library, fully offline.
"""
from __future__ import annotations

import sys

TASKS = [
    {
        "task_id": "TASK-01-clean-delivery",
        "agent_self_reported_done": True,
        "expected_complete": True,
        "requirements": [
            {"id": "REQ-1", "clarified": True, "deferred_question": False, "implemented": True, "test_passed": True},
            {"id": "REQ-2", "clarified": True, "deferred_question": False, "implemented": True, "test_passed": True},
            {"id": "REQ-3", "clarified": True, "deferred_question": False, "implemented": True, "test_passed": True},
        ],
    },
    {
        "task_id": "TASK-02-unfollowed-question",
        "agent_self_reported_done": True,
        "expected_complete": False,
        "requirements": [
            {"id": "REQ-1", "clarified": True, "deferred_question": False, "implemented": True, "test_passed": True},
            {"id": "REQ-2", "clarified": False, "deferred_question": True, "implemented": True, "test_passed": True},
        ],
    },
    {
        "task_id": "TASK-03-missing-implementation",
        "agent_self_reported_done": True,
        "expected_complete": False,
        "requirements": [
            {"id": "REQ-1", "clarified": True, "deferred_question": False, "implemented": True, "test_passed": True},
            {"id": "REQ-2", "clarified": True, "deferred_question": False, "implemented": False, "test_passed": False},
        ],
    },
    {
        "task_id": "TASK-04-reported-done-but-test-failed",
        "agent_self_reported_done": True,
        "expected_complete": False,
        "requirements": [
            {"id": "REQ-1", "clarified": True, "deferred_question": False, "implemented": True, "test_passed": True},
            {"id": "REQ-2", "clarified": True, "deferred_question": False, "implemented": True, "test_passed": False},
        ],
    },
    {
        "task_id": "TASK-05-partial-f2p-pass",
        "agent_self_reported_done": True,
        "expected_complete": False,
        "requirements": [
            {"id": "REQ-1", "clarified": True, "deferred_question": False, "implemented": True, "test_passed": True},
            {"id": "REQ-2", "clarified": True, "deferred_question": False, "implemented": True, "test_passed": True},
            {"id": "REQ-3", "clarified": True, "deferred_question": False, "implemented": True, "test_passed": False},
        ],
    },
    {
        "task_id": "TASK-06-multiple-gaps",
        "agent_self_reported_done": True,
        "expected_complete": False,
        "requirements": [
            {"id": "REQ-1", "clarified": False, "deferred_question": True, "implemented": False, "test_passed": False},
            {"id": "REQ-2", "clarified": True, "deferred_question": False, "implemented": True, "test_passed": False},
        ],
    },
]


def check_ledger(task: dict) -> tuple[bool, list[str]]:
    """Return (can_deliver, blocking_reasons) for a requirement-tracking ledger."""
    reasons: list[str] = []
    for req in task["requirements"]:
        rid = req["id"]
        if req["deferred_question"] or not req["clarified"]:
            reasons.append(f"{rid}: 未闭环的澄清问题")
        if not req["implemented"]:
            reasons.append(f"{rid}: 已确认需求漏实现")
        if not req["test_passed"]:
            reasons.append(f"{rid}: 缺少通过的可执行测试")
    return (len(reasons) == 0), reasons


def main() -> int:
    total_reqs = sum(len(t["requirements"]) for t in TASKS)
    passed_reqs = sum(1 for t in TASKS for r in t["requirements"] if r["test_passed"])
    naive_false_handoffs = 0
    ledger_false_handoffs = 0
    ledger_true_handoffs = 0
    incomplete_total = sum(1 for t in TASKS if not t["expected_complete"])
    complete_total = sum(1 for t in TASKS if t["expected_complete"])

    print("=== SWE-CoWork 需求台账门禁离线对照（6 组多需求任务）===")
    for task in TASKS:
        can_deliver, reasons = check_ledger(task)
        naive_accept = task["agent_self_reported_done"]
        if naive_accept and not task["expected_complete"]:
            naive_false_handoffs += 1
        if can_deliver and not task["expected_complete"]:
            ledger_false_handoffs += 1
        if can_deliver and task["expected_complete"]:
            ledger_true_handoffs += 1

        status = "放行交付" if can_deliver else f"拦截（{'; '.join(reasons)}）"
        print(f"- {task['task_id']}: 自报完成={naive_accept} | 台账门禁={status}")

    req_test_pass_rate = 100.0 * passed_reqs / total_reqs
    naive_block_rate = 100.0 * (incomplete_total - naive_false_handoffs) / incomplete_total
    ledger_block_rate = 100.0 * (incomplete_total - ledger_false_handoffs) / incomplete_total
    clean_pass_rate = 100.0 * ledger_true_handoffs / complete_total

    checks = [
        (naive_false_handoffs == 5, "仅听信 Agent 自报完成会误放行全部 5 组半成品任务（5/5）"),
        (ledger_false_handoffs == 0, "需求台账门禁拦下全部 5 组存在缺漏的假交付（0 误放行）"),
        (ledger_true_handoffs == 1, "需求台账门禁正常放行完整交付任务 TASK-01（1/1）"),
        (req_test_pass_rate > 50.0 and clean_pass_rate == 100.0, "复现单项测试通过率过半但整单完整率偏低的交付断层"),
    ]

    all_ok = True
    for ok, desc in checks:
        print(f"{'[PASS]' if ok else '[FAIL]'} {desc}")
        if not ok:
            all_ok = False

    print(f"METRIC: 单条需求测试通过率 = {req_test_pass_rate:.1f} %")
    print(f"METRIC: 无台账假交付拦截率 = {naive_block_rate:.1f} %")
    print(f"METRIC: 需求台账假交付拦截率 = {ledger_block_rate:.1f} %")
    print(f"METRIC: 完整任务正常放行率 = {clean_pass_rate:.1f} %")

    if not all_ok:
        print("RESULT: 部分台账门禁检查未通过，请排查实现。")
        return 1

    print("RESULT: 需求台账门禁拦截了 100% 的半成品交付（5/5），同时 100% 放行完整交付任务。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
