"""Data-driven visuals built at site-build time (no network, no randomness):

- cover_svg: an issue "cover" — one bubble per item, packed into a cluster; colour = category,
  size = importance. Deterministic for the same issue, adapts to light/dark through CSS variables.
- parse_output: pulls the conclusion (RESULT:), checks ([PASS]/[FAIL]/[OK]) and metrics (METRIC:) out of
  an experiment's real stdout, so the page can chart what actually ran instead of what we expected.
"""
from __future__ import annotations

import math
import re
from html import escape

from markupsafe import Markup

from common import CATEGORY_ORDER

RADIUS = {5: 1.0, 4: 0.84, 3: 0.69, 2: 0.57, 1: 0.48}
GAP = 0.09


def pack(items: list[dict]) -> list[dict]:
    """Greedy spiral packing: biggest first, each bubble takes the first free spot along a spiral."""
    order = sorted(items, key=lambda it: (-it["importance"], CATEGORY_ORDER.index(it["category"])
                                          if it["category"] in CATEGORY_ORDER else 99, it["id"]))
    placed: list[dict] = []
    for it in order:
        r = RADIUS.get(it["importance"], 0.6)
        if not placed:
            placed.append({"x": 0.0, "y": 0.0, "r": r, "it": it})
            continue
        t = 0.0
        while True:
            a, d = t * 0.55, 0.05 * t
            x, y = d * math.cos(a), d * math.sin(a) * 0.82   # slightly wide cluster
            if all(math.hypot(x - p["x"], y - p["y"]) >= r + p["r"] + GAP for p in placed):
                placed.append({"x": x, "y": y, "r": r, "it": it})
                break
            t += 1
    return placed


def cover_svg(items: list[dict], size: int = 140, link: bool = True, label: str = "") -> Markup:
    if not items:
        return Markup("")
    ps = pack(items)
    x0 = min(p["x"] - p["r"] for p in ps); x1 = max(p["x"] + p["r"] for p in ps)
    y0 = min(p["y"] - p["r"] for p in ps); y1 = max(p["y"] + p["r"] for p in ps)
    span = max(x1 - x0, y1 - y0)
    k = 92 / span
    ox, oy = 50 - (x0 + x1) / 2 * k, 50 - (y0 + y1) / 2 * k
    parts = []
    for p in ps:
        it = p["it"]
        c = (f'<circle class="cv cv-{it["category"]}" cx="{ox + p["x"] * k:.2f}" cy="{oy + p["y"] * k:.2f}" '
             f'r="{p["r"] * k:.2f}"/>')
        if link:
            parts.append(f'<a href="#{escape(it["id"])}" class="cv-link"><title>{escape(it["title"])}</title>{c}</a>')
        else:
            parts.append(c)
    aria = label or f"本期 {len(items)} 条内容，每个圆代表一条，颜色表示栏目，大小表示重要度"
    return Markup(f'<svg class="cover" width="{size}" height="{size}" viewBox="0 0 100 100" role="img" '
                  f'aria-label="{escape(aria)}">{"".join(parts)}</svg>')


# ---------------------------------------------------------------- experiment output

CHECK_RE = re.compile(r"^\s*\[(PASS|OK|FAIL|FAILED|ERROR)\]\s*(.+)$")
METRIC_RE = re.compile(r"^\s*METRIC:\s*(.+?)\s*=\s*(-?\d+(?:\.\d+)?)\s*([^\s|]{0,12})\s*$")
RESULT_RE = re.compile(r"^\s*RESULT:\s*(.+)$")


def parse_output(stdout: str) -> dict:
    checks, metrics, result = [], [], None
    for line in (stdout or "").splitlines():
        m = CHECK_RE.match(line)
        if m:
            checks.append({"ok": m.group(1) in ("PASS", "OK"), "text": m.group(2).strip()})
            continue
        m = METRIC_RE.match(line)
        if m and len(metrics) < 12:
            raw = m.group(2)
            metrics.append({"label": m.group(1)[:28], "value": float(raw) if "." in raw else int(raw),
                            "unit": m.group(3)})
            continue
        m = RESULT_RE.match(line)
        if m:
            result = m.group(1).strip()
    return {"result": result, "checks": checks, "metrics": metrics,
            "passed": sum(1 for c in checks if c["ok"]), "total": len(checks)}


def metric_figures(metrics: list[dict]) -> list[dict]:
    """One bar figure per unit, so different units never share a scale."""
    by_unit: dict[str, list[dict]] = {}
    for m in metrics:
        if m["value"] >= 0:
            by_unit.setdefault(m["unit"], []).append(m)
    figs = []
    for unit, ms in by_unit.items():
        if not ms:
            continue
        figs.append({"type": "bars", "title": "实验指标" + (f"（{unit}）" if unit else ""), "series": ["实测值"],
                     "rows": [{"label": m["label"], "values": [m["value"]]} for m in ms], "unit": unit,
                     "caption": "数值取自 GitHub Actions 实际运行输出中的 METRIC 行"})
    return figs
