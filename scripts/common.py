"""Shared helpers for AI Daily Lab scripts (stdlib + jsonschema + markdown + pyyaml)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "daily"
WEEKLY_DIR = ROOT / "content" / "weekly"
EXPERIMENTS_DIR = ROOT / "experiments"
SCHEMA_DIR = ROOT / "schema"

CATEGORIES = {
    "news": "要闻",
    "opensource": "开源项目",
    "tools": "工具与产品",
    "kits": "Skill 精选",
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

KIT_KINDS = {
    "skill": "Agent Skill",
    "mcp": "MCP 服务",
    "plugin": "插件",
    "subagent": "子 Agent",
    "hook": "Hook",
    "other": "扩展",
}

# Category colors (light theme); the site uses the CSS variables, share cards and wiki html use these.
CATEGORY_COLORS = {
    "news": "#C2410C", "opensource": "#15803D", "tools": "#1D4ED8", "kits": "#4338CA",
    "ideas": "#7C3AED", "practices": "#0E7490", "skills": "#BE185D", "research": "#A16207",
}

# Line icons on a 24px grid (stroke 1.75, round caps): inner SVG markup per category / skill area.
ICONS = {
    "news": '<path d="M4 5h13v14H6a2 2 0 0 1-2-2z"/><path d="M17 9h3v8a2 2 0 0 1-2 2h-1"/><path d="M7.5 9h6M7.5 12.5h6M7.5 16h4"/>',
    "opensource": '<circle cx="6" cy="5.5" r="2"/><circle cx="6" cy="18.5" r="2"/><circle cx="18" cy="8" r="2"/><path d="M6 7.5v9"/><path d="M18 10c0 4-6 3.5-11 7"/>',
    "tools": '<path d="M14.5 6.5a4 4 0 0 0-5.3 5.1L4 16.8V20h3.2l5.2-5.2a4 4 0 0 0 5.1-5.3l-2.6 2.6-2.6-.6-.6-2.6z"/>',
    "kits": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/>',
    "ideas": '<path d="M3.5 5h11v7h-6l-3 2.5V12h-2z"/><path d="M14.5 9h6v7h-2v2.5L15.5 16h-5v-2"/>',
    "practices": '<rect x="4" y="3.5" width="16" height="17" rx="2"/><path d="M8 8.5l1.3 1.3L12 7.2M8 14l1.3 1.3L12 12.7M14 9h2.5M14 14.5h2.5"/>',
    "skills": '<circle cx="8" cy="7.5" r="3"/><path d="M2.5 19c.6-3.3 2.8-5 5.5-5s4.9 1.7 5.5 5"/><path d="M14 4h7v6h-3l-2 1.7V10h-2z"/>',
    "research": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 11h6M9 14h6M9 17h3.5"/>',
    "goal": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
    "context": '<path d="M12 3.5l8.5 4.5L12 12.5 3.5 8z"/><path d="M3.5 12L12 16.5l8.5-4.5"/><path d="M3.5 16L12 20.5l8.5-4.5"/>',
    "decompose": '<rect x="9" y="3" width="6" height="4.5" rx="1"/><rect x="3" y="16.5" width="6" height="4.5" rx="1"/><rect x="15" y="16.5" width="6" height="4.5" rx="1"/><path d="M12 7.5V12M6 16.5V12h12v4.5"/>',
    "review": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L20.5 20.5"/><path d="M7.8 10.6l1.9 1.9 3.4-3.6"/>',
    "iterate": '<path d="M19.5 12a7.5 7.5 0 0 1-12.8 5.3"/><path d="M4.5 12a7.5 7.5 0 0 1 12.8-5.3"/><path d="M17.5 3.5v3.3h-3.3M6.5 20.5v-3.3h3.3"/>',
    "delegate": '<rect x="3.5" y="9" width="10" height="11" rx="2" stroke-dasharray="3 2.5"/><path d="M10 14L20 4"/><path d="M14 4h6v6"/>',
    "judgment": '<path d="M12 4v16M8 20h8"/><path d="M4.5 7.5h15"/><path d="M6.5 7.5L3.5 14a3 3 0 0 0 6 0z"/><path d="M17.5 7.5L14.5 14a3 3 0 0 0 6 0z"/>',
}


def icon_svg(name: str, size: int = 18, color: str = "currentColor", cls: str = "ic") -> str:
    inner = ICONS.get(name)
    if not inner:
        return ""
    return (f'<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{inner}</svg>')


# Issues from this date on must carry tldr / actionability / a skills item (older issues only warn).
STRICT_FROM = "2026-10-21"
CATEGORY_ORDER = list(CATEGORIES)

# Suggested ranges from CLAUDE.md; outside the range is a warning, not an error.
CATEGORY_RANGE = {
    "news": (3, 6),
    "opensource": (2, 4),
    "tools": (1, 3),
    "kits": (1, 2),
    "ideas": (1, 3),
    "practices": (1, 3),
    "research": (1, 3),
    "skills": (1, 1),
}
TOTAL_RANGE = (12, 20)

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


def weekly_files() -> list[Path]:
    """All weekly report files, oldest first."""
    return sorted(WEEKLY_DIR.glob("*/*.json"), key=lambda p: p.stem)


WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")


def week_id(d: str) -> str:
    """ISO week id of a YYYY-MM-DD date, e.g. 2026-W43."""
    from datetime import date as _date
    y, w, _ = _date.fromisoformat(d).isocalendar()
    return f"{y}-W{w:02d}"


def week_range(wid: str) -> tuple[str, str]:
    """(monday, sunday) of an ISO week id, as YYYY-MM-DD."""
    from datetime import date as _date
    m = WEEK_RE.match(wid)
    if not m:
        raise ValueError(f"bad week id: {wid}")
    y, w = int(m.group(1)), int(m.group(2))
    mon = _date.fromisocalendar(y, w, 1)
    return mon.isoformat(), _date.fromisocalendar(y, w, 7).isoformat()


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
