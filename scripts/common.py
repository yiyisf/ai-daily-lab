"""Shared helpers for AI Daily Lab scripts (stdlib + jsonschema + markdown + pyyaml)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "daily"
EXPERIMENTS_DIR = ROOT / "experiments"
SCHEMA_DIR = ROOT / "schema"

CATEGORIES = {
    "news": "要闻",
    "opensource": "开源项目",
    "tools": "工具与产品",
    "ideas": "理念与讨论",
    "practices": "方法与实践",
    "skills": "AI 软技能",
    "research": "论文",
}

SKILL_AREAS = {
    "goal": "目标表达",
    "context": "上下文供给",
    "decompose": "任务拆解",
    "review": "审查验证",
    "iterate": "反馈迭代",
    "delegate": "委派与边界",
    "judgment": "判断与取舍",
}

# Issues from this date on must carry tldr / actionability / a skills item (older issues only warn).
STRICT_FROM = "2026-10-21"
CATEGORY_ORDER = list(CATEGORIES)

# Suggested ranges from CLAUDE.md; outside the range is a warning, not an error.
CATEGORY_RANGE = {
    "news": (3, 6),
    "opensource": (2, 4),
    "tools": (1, 3),
    "ideas": (1, 3),
    "practices": (1, 3),
    "research": (1, 3),
    "skills": (1, 1),
}
TOTAL_RANGE = (11, 19)

STATUS_LABEL = {
    "passed": "✅ 已验证",
    "partial": "⚠️ 部分可用",
    "failed": "❌ 复现失败",
    "pending": "⏳ 待执行",
}

DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def dump_json(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def issue_files() -> list[Path]:
    """All daily issue files, oldest first."""
    return sorted(CONTENT_DIR.glob("*/*.json"), key=lambda p: p.stem)


def load_issue(path: Path) -> dict:
    return load_json(path)


def load_experiment(exp_id: str) -> dict | None:
    d = EXPERIMENTS_DIR / exp_id
    meta = d / "experiment.json"
    if not meta.exists():
        return None
    exp = load_json(meta)
    result_path = d / "result.json"
    exp["result"] = load_json(result_path) if result_path.exists() else None
    readme = d / "README.md"
    exp["readme"] = readme.read_text(encoding="utf-8") if readme.exists() else ""
    exp["files"] = sorted(
        p.name for p in d.iterdir()
        if p.is_file() and p.name not in {"experiment.json", "result.json"}
    )
    return exp


def experiment_status(exp: dict) -> str:
    res = exp.get("result")
    return res.get("status", "pending") if res else "pending"
