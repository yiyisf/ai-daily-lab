#!/usr/bin/env python3
"""Offline static conformance checker for AGENTS.md path & dependency claims.

Inspired by arXiv:2611.29916 ("Does the Agent's Map Match the Territory?"):
parses path claims and dependency rules from an AGENTS.md / CLAUDE.md file,
inspects the repository filesystem and Python AST imports, and reports stale
paths plus day-0 broken architectural rules.
"""

from __future__ import annotations

import ast
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple


@dataclass(frozen=True)
class DependencyRule:
    kind: str  # "forbid_in_scope", "only_in_scope", "forbid_global"
    target: str
    scope: str = ""
    raw: str = ""


@dataclass(frozen=True)
class Violation:
    kind: str  # "missing_path" or "rule_break"
    subject: str
    detail: str


SAMPLE_AGENTS_MD = """# AGENTS.md

## Project structure
- `src/server/routes/` -- HTTP route handlers
- `src/server/db/` -- database access layer
- `src/client/` -- frontend client helpers
- `src/legacy/billing/` -- old billing module (moved last sprint!)

## Architecture rules
- Never import from `src/server/` in `src/client/`.
- Only `src/server/db/` may import `sqlalchemy`.
- Do not import `moment_compat`; we are replacing it.
"""


def parse_agents_md(text: str) -> Tuple[List[str], List[DependencyRule]]:
    """Extract path claims and structured dependency rules from Markdown."""
    path_claims: List[str] = []
    rules: List[DependencyRule] = []
    section = ""

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("##"):
            section = line.lower()
            continue

        if "structure" in section and line.startswith("-"):
            m = re.search(r"`([A-Za-z0-9_./-]+)`", line)
            if m:
                path_claims.append(m.group(1))
        elif "rule" in section and line.startswith("-"):
            m_never = re.search(
                r"Never import from `([^`]+)` in `([^`]+)`", line, re.IGNORECASE
            )
            m_only = re.search(
                r"Only `([^`]+)` may import `([^`]+)`", line, re.IGNORECASE
            )
            m_ban = re.search(
                r"Do not import `([^`]+)`", line, re.IGNORECASE
            )
            if m_never:
                rules.append(
                    DependencyRule(
                        kind="forbid_in_scope",
                        target=m_never.group(1).strip("/"),
                        scope=m_never.group(2).strip("/"),
                        raw=line,
                    )
                )
            elif m_only:
                rules.append(
                    DependencyRule(
                        kind="only_in_scope",
                        scope=m_only.group(1).strip("/"),
                        target=m_only.group(2).strip("/"),
                        raw=line,
                    )
                )
            elif m_ban:
                rules.append(
                    DependencyRule(
                        kind="forbid_global",
                        target=m_ban.group(1).strip("/"),
                        raw=line,
                    )
                )

    return path_claims, rules


def extract_python_imports(py_file: Path) -> List[str]:
    """Parse Python AST to collect imported module names without comment noise."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    imports: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def matches_target(imported_module: str, target: str) -> bool:
    """Check whether a dotted Python import matches a module or path prefix."""
    dotted_target = target.replace("/", ".").strip(".")
    return imported_module == dotted_target or imported_module.startswith(
        dotted_target + "."
    )


def check_repository(repo_root: Path, agents_md: str) -> List[Violation]:
    """Verify path claims and dependency rules against actual repo files."""
    path_claims, rules = parse_agents_md(agents_md)
    violations: List[Violation] = []

    for claim in path_claims:
        if not (repo_root / claim).exists():
            violations.append(
                Violation(
                    kind="missing_path",
                    subject=claim,
                    detail=f"Path claim '{claim}' does not exist in repository",
                )
            )

    for py_file in sorted(repo_root.rglob("*.py")):
        rel_path = py_file.relative_to(repo_root).as_posix()
        imports = extract_python_imports(py_file)
        for mod in imports:
            for rule in rules:
                if rule.kind == "forbid_in_scope":
                    if rel_path.startswith(rule.scope + "/") and matches_target(
                        mod, rule.target
                    ):
                        violations.append(
                            Violation(
                                kind="rule_break",
                                subject=rel_path,
                                detail=f"Imports '{mod}' violating: {rule.raw}",
                            )
                        )
                elif rule.kind == "only_in_scope":
                    if (
                        matches_target(mod, rule.target)
                        and not rel_path.startswith(rule.scope + "/")
                    ):
                        violations.append(
                            Violation(
                                kind="rule_break",
                                subject=rel_path,
                                detail=f"Imports '{mod}' outside '{rule.scope}/'",
                            )
                        )
                elif rule.kind == "forbid_global":
                    if matches_target(mod, rule.target):
                        violations.append(
                            Violation(
                                kind="rule_break",
                                subject=rel_path,
                                detail=f"Imports banned module '{mod}'",
                            )
                        )

    return violations


def build_synthetic_repo(root: Path) -> Dict[str, str]:
    """Create a realistic repo with 1 stale path and 2 day-0 broken rules."""
    files = {
        "src/server/routes/orders.py": (
            "# Note: do not use moment_compat in comments (must NOT trigger)\n"
            "import sqlalchemy  # DAY-0 VIOLATION: only src/server/db/ allowed\n"
            "def list_orders():\n"
            "    return []\n"
        ),
        "src/server/db/session.py": (
            "import sqlalchemy\n"
            "def get_session():\n"
            "    return sqlalchemy\n"
        ),
        "src/client/dashboard.py": (
            "from src.server.routes import orders  # VIOLATION: client -> server\n"
            "def render():\n"
            "    return orders.list_orders()\n"
        ),
        "src/client/formatters.py": (
            "# Clean file, mentions 'import moment_compat' only in a docstring\n"
            "'''Never write: import moment_compat'''\n"
            "def fmt_date(s: str) -> str:\n"
            "    return s\n"
        ),
    }
    for rel, content in files.items():
        full = root / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    return files


def main() -> int:
    expected_keys: Set[Tuple[str, str]] = {
        ("missing_path", "src/legacy/billing/"),
        ("rule_break", "src/server/routes/orders.py"),
        ("rule_break", "src/client/dashboard.py"),
    }

    with tempfile.TemporaryDirectory(prefix="agents_md_check_") as tmp:
        repo_root = Path(tmp)
        build_synthetic_repo(repo_root)
        path_claims, rules = parse_agents_md(SAMPLE_AGENTS_MD)
        violations = check_repository(repo_root, SAMPLE_AGENTS_MD)

    found_keys = {(v.kind, v.subject) for v in violations}
    tp = len(found_keys & expected_keys)
    fp = len(found_keys - expected_keys)
    fn = len(expected_keys - found_keys)

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)

    print("=== AGENTS.md Map-vs-Territory Static Conformance Checker ===")
    print(f"Parsed {len(path_claims)} path claims and {len(rules)} dependency rules.")
    for v in violations:
        print(f"  [{v.kind}] {v.subject}: {v.detail}")

    print(f"METRIC: path_claims_checked={len(path_claims)}")
    print(f"METRIC: dependency_rules_checked={len(rules)}")
    print(f"METRIC: precision={precision:.4f}")
    print(f"METRIC: recall={recall:.4f}")
    print(f"METRIC: false_positives={fp}")

    assert precision == 1.0 and recall == 1.0 and fp == 0, (
        f"Conformance check mismatch: found={found_keys}, expected={expected_keys}"
    )

    print("[PASS] All stale path claims and day-0 broken dependency rules caught with 0 FP.")
    print(
        f"RESULT: precision={precision*100:.1f}%, recall={recall*100:.1f}%, "
        f"violations={len(violations)} (FP={fp})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
