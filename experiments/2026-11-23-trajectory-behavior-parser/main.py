#!/usr/bin/env python3
"""Offline deterministic behavioral trajectory parser for coding agents.

Inspired by arXiv:2611.17440 (Interpreting Coding Agents Through Their
Behavioral Trajectories): maps heterogeneous raw tool traces into high-level
actions (search / edit / test / other), retrieves agent scaffold profiles from
behavior-only vectors (without tool names or outcomes), and flags anti-patterns
such as blind edits and search thrashing.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple


SEARCH_PATTERNS = [
    r"\b(rg|ripgrep|grep|ag|find|fd|ls|tree|cat|head|tail|sed\s+-n|awk|git\s+(status|log|diff|grep|show))\b",
    r"\b(read_file|view_file|list_dir|glob|search_code|find_by_name)\b",
    r"query=|pattern=|path=.*--read-only",
]

EDIT_PATTERNS = [
    r"(?:^|[;&|]\s*)(apply_patch|patch\s+-p|sed\s+-i|tee\b|mv\b|cp\b|rm\b|touch\b|git\s+(apply|checkout\s+--))",
    r"\b(write_file|edit_file|replace_file|str_replace|create_file|insert_lines)\b",
    r">>\s*\S+|cat\s+<<\s*['\"]?EOF",
]

TEST_PATTERNS = [
    r"\b(pytest|unittest|jest|vitest|mocha|playwright|cypress|go\s+test|cargo\s+test|mvn\s+test|npm\s+test|pnpm\s+test|yarn\s+test|npm\s+run\s+(test|lint|typecheck|build)|tsc\s+--noEmit|ruff\s+check|flake8|mypy)\b",
]


def parse_action(payload: str) -> str:
    """Map raw command/argument text to {search, edit, test, other}."""
    text = payload.strip()
    if any(re.search(p, text, re.IGNORECASE) for p in TEST_PATTERNS):
        return "test"
    if any(re.search(p, text, re.IGNORECASE) for p in EDIT_PATTERNS):
        return "edit"
    if any(re.search(p, text, re.IGNORECASE) for p in SEARCH_PATTERNS):
        return "search"
    return "other"


@dataclass
class Trajectory:
    trace_id: str
    scaffold: str
    repo: str
    anomaly_truth: str  # "none", "blind_edit", "search_thrash"
    events: List[Tuple[str, str]]  # (raw_payload, ground_truth_action)


def build_synthetic_corpus() -> List[Trajectory]:
    """Synthetic multi-scaffold traces across disjoint repositories."""
    return [
        # --- Scaffold A: Search-First Disciplined (explore -> edit -> verify) ---
        Trajectory(
            trace_id="A-repo1-normal",
            scaffold="search_first",
            repo="frontend-ui",
            anomaly_truth="none",
            events=[
                ("rg 'ButtonProps' src/components/", "search"),
                ("cat src/components/Button.tsx", "search"),
                ("git log -n 5 --oneline src/components/Button.tsx", "search"),
                ("edit_file src/components/Button.tsx --replace disabled", "edit"),
                ("npm run typecheck", "test"),
                ("vitest run src/components/Button.test.tsx", "test"),
            ],
        ),
        Trajectory(
            trace_id="A-repo2-normal",
            scaffold="search_first",
            repo="billing-api",
            anomaly_truth="none",
            events=[
                ("fd invoice src/", "search"),
                ("sed -n '1,80p' src/invoice.py", "search"),
                ("grep -rn 'calc_tax' tests/", "search"),
                ("apply_patch src/invoice.py", "edit"),
                ("pytest tests/test_invoice.py", "test"),
                ("ruff check src/invoice.py", "test"),
            ],
        ),
        Trajectory(
            trace_id="A-repo3-normal",
            scaffold="search_first",
            repo="auth-service",
            anomaly_truth="none",
            events=[
                ("git grep 'verify_jwt' pkg/", "search"),
                ("head -n 60 pkg/jwt.go", "search"),
                ("ls pkg/middleware/", "search"),
                ("str_replace pkg/jwt.go", "edit"),
                ("go test ./pkg/...", "test"),
                ("go test -race ./pkg/jwt", "test"),
            ],
        ),
        # --- Scaffold B: Fast-Patcher (minimal search, heavy edit, light test) ---
        Trajectory(
            trace_id="B-repo1-normal",
            scaffold="fast_patcher",
            repo="frontend-ui",
            anomaly_truth="none",
            events=[
                ("cat src/pages/Login.tsx", "search"),
                ("write_file src/pages/Login.tsx", "edit"),
                ("edit_file src/pages/Login.css", "edit"),
                ("edit_file src/pages/Login.tsx", "edit"),
                ("npm test -- Login", "test"),
            ],
        ),
        Trajectory(
            trace_id="B-repo2-blind",
            scaffold="fast_patcher",
            repo="billing-api",
            anomaly_truth="blind_edit",
            events=[
                ("write_file src/tax.py", "edit"),
                ("sed -i 's/0.05/0.08/g' src/tax.py", "edit"),
                ("edit_file src/config.py", "edit"),
                ("echo 'done updating tax'", "other"),
            ],
        ),
        Trajectory(
            trace_id="B-repo3-blind",
            scaffold="fast_patcher",
            repo="auth-service",
            anomaly_truth="blind_edit",
            events=[
                ("cat pkg/session.go", "search"),
                ("apply_patch pkg/session.go", "edit"),
                ("apply_patch pkg/cookie.go", "edit"),
                ("echo 'finished patch'", "other"),
            ],
        ),
        # --- Scaffold C: Heavy-Explorer (deep search, rare edits, sometimes thrashes) ---
        Trajectory(
            trace_id="C-repo1-normal",
            scaffold="heavy_explorer",
            repo="frontend-ui",
            anomaly_truth="none",
            events=[
                ("find src -maxdepth 3", "search"),
                ("rg 'useModal' src/", "search"),
                ("cat src/hooks/useModal.ts", "search"),
                ("cat src/components/Modal.tsx", "search"),
                ("git diff HEAD~2 src/components/Modal.tsx", "search"),
                ("edit_file src/components/Modal.tsx", "edit"),
                ("playwright test tests/modal.spec.ts", "test"),
            ],
        ),
        Trajectory(
            trace_id="C-repo2-thrash",
            scaffold="heavy_explorer",
            repo="billing-api",
            anomaly_truth="search_thrash",
            events=[
                ("rg 'discount_rate' src/", "search"),
                ("rg 'discount_rate' src/", "search"),
                ("find src -name '*.py'", "search"),
                ("rg 'discount_rate' src/", "search"),
                ("cat src/pricing.py", "search"),
                ("rg 'discount_rate' src/", "search"),
                ("echo 'context limit reached'", "other"),
            ],
        ),
        Trajectory(
            trace_id="C-repo3-thrash",
            scaffold="heavy_explorer",
            repo="auth-service",
            anomaly_truth="search_thrash",
            events=[
                ("git grep 'oauth_state' pkg/", "search"),
                ("ls -la pkg/oauth/", "search"),
                ("git grep 'oauth_state' pkg/", "search"),
                ("cat pkg/oauth/handler.go", "search"),
                ("git grep 'oauth_state' pkg/", "search"),
                ("head -n 40 pkg/oauth/state.go", "search"),
            ],
        ),
    ]


def extract_features(actions: List[str]) -> List[float]:
    """Extract 6D behavior-only feature vector without tool names or outcomes."""
    n = max(len(actions), 1)
    search_ratio = actions.count("search") / n
    edit_ratio = actions.count("edit") / n
    test_ratio = actions.count("test") / n
    other_ratio = actions.count("other") / n

    # Normalized search steps before first edit
    first_edit_idx = actions.index("edit") if "edit" in actions else len(actions)
    pre_edit_search = sum(1 for a in actions[:first_edit_idx] if a == "search") / n

    # Whether at least one test occurs after the last edit
    if "edit" in actions:
        last_edit_idx = len(actions) - 1 - actions[::-1].index("edit")
        post_edit_tested = 1.0 if "test" in actions[last_edit_idx + 1 :] else 0.0
    else:
        post_edit_tested = 0.0

    return [
        search_ratio,
        edit_ratio,
        test_ratio,
        other_ratio,
        pre_edit_search,
        0.25 * post_edit_tested,
    ]


def detect_anomaly(payloads: List[str], actions: List[str]) -> str:
    """Detect blind-edit or search-thrashing patterns from parsed actions."""
    # Search thrash: >= 5 consecutive searches AND repeated query payload
    streak = 0
    max_streak = 0
    for a in actions:
        if a == "search":
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    search_payloads = [p for p, a in zip(payloads, actions) if a == "search"]
    has_repeat = len(search_payloads) > len(set(search_payloads))
    if max_streak >= 5 and has_repeat:
        return "search_thrash"

    # Blind edit: edited files without prior search OR without any post-edit test
    if "edit" in actions:
        first_edit = actions.index("edit")
        last_edit = len(actions) - 1 - actions[::-1].index("edit")
        no_prior_search = "search" not in actions[:first_edit]
        no_post_test = "test" not in actions[last_edit + 1 :]
        if no_prior_search or no_post_test:
            return "blind_edit"

    return "none"


def euclidean(a: List[float], b: List[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def main() -> int:
    corpus = build_synthetic_corpus()

    total_events = 0
    correct_events = 0
    anomaly_tp = 0
    anomaly_fn = 0
    anomaly_fp = 0

    parsed_records = []
    for traj in corpus:
        payloads = [p for p, _ in traj.events]
        truth_actions = [a for _, a in traj.events]
        pred_actions = [parse_action(p) for p in payloads]

        for pred, truth in zip(pred_actions, truth_actions):
            total_events += 1
            if pred == truth:
                correct_events += 1

        pred_anomaly = detect_anomaly(payloads, pred_actions)
        if traj.anomaly_truth != "none":
            if pred_anomaly == traj.anomaly_truth:
                anomaly_tp += 1
            else:
                anomaly_fn += 1
        elif pred_anomaly != "none":
            anomaly_fp += 1

        feat = extract_features(pred_actions)
        parsed_records.append((traj, pred_actions, pred_anomaly, feat))

    # Leave-one-repo-out cross-repository scaffold retrieval via nearest centroid
    retrieval_correct = 0
    for test_traj, _, _, test_feat in parsed_records:
        by_scaffold: Dict[str, List[List[float]]] = {}
        for tr, _, _, feat in parsed_records:
            if tr.repo == test_traj.repo:
                continue  # disjoint repository evaluation
            by_scaffold.setdefault(tr.scaffold, []).append(feat)

        centroids = {
            sc: [sum(col) / len(col) for col in zip(*vecs)]
            for sc, vecs in by_scaffold.items()
        }
        pred_scaffold = min(centroids, key=lambda sc: euclidean(test_feat, centroids[sc]))
        if pred_scaffold == test_traj.scaffold:
            retrieval_correct += 1

    action_acc = correct_events / total_events
    anomaly_recall = anomaly_tp / max(anomaly_tp + anomaly_fn, 1)
    retrieval_acc = retrieval_correct / len(parsed_records)

    print("=== Coding Agent Behavioral Trajectory Parser ===")
    for traj, actions, anomaly, feat in parsed_records:
        print(
            f"  {traj.trace_id:16s} | scaffold={traj.scaffold:14s} "
            f"| S={feat[0]:.2f} E={feat[1]:.2f} T={feat[2]:.2f} "
            f"| anomaly={anomaly}"
        )

    print(f"METRIC: action_parse_accuracy={action_acc:.4f}")
    print(f"METRIC: anomaly_recall={anomaly_recall:.4f}")
    print(f"METRIC: anomaly_false_positives={anomaly_fp}")
    print(f"METRIC: cross_repo_scaffold_retrieval={retrieval_acc:.4f}")

    assert action_acc == 1.0, f"Expected 100% action parse accuracy, got {action_acc}"
    assert anomaly_recall == 1.0 and anomaly_fp == 0, "Anomaly detection failed"
    assert retrieval_acc >= 0.85, f"Low scaffold retrieval accuracy: {retrieval_acc}"

    print("[PASS] Deterministic trajectory parser and anomaly detector verified.")
    print(
        f"RESULT: action_acc={action_acc*100:.1f}%, "
        f"anomaly_recall={anomaly_recall*100:.1f}% (FP={anomaly_fp}), "
        f"cross_repo_retrieval={retrieval_acc*100:.1f}% ({retrieval_correct}/{len(parsed_records)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
