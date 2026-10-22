"""Weekly report helpers shared by build_site / validate / preview.

A weekly file (content/weekly/YYYY/YYYY-Www.json) only holds editorial choices that point at items of that
week's daily issues. Everything countable (stats, AI 软技能 / Skill 精选 recap, experiments, tag heat) is
derived here from the daily issues, so the weekly cannot drift from what was actually published.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta

from common import CATEGORIES, KIT_KINDS, SKILL_AREAS, STATUS_LABEL, week_range

WEEKDAYS = "一二三四五六日"
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*%?")


def week_label(wid: str) -> str:
    y, w = wid.split("-W")
    return f"{y} 年第 {int(w)} 周"


def range_label(wid: str) -> str:
    a, b = (date.fromisoformat(x) for x in week_range(wid))
    return f"{a.month}月{a.day}日 – {b.month}月{b.day}日"


def week_issues(wid: str, issues: list[dict]) -> list[dict]:
    a, b = week_range(wid)
    return [i for i in issues if a <= i["date"] <= b]


def item_index(issues: list[dict]) -> dict[str, dict]:
    out = {}
    for iss in issues:
        for it in iss["items"]:
            out[it["id"]] = dict(it, date=iss["date"])
    return out


def item_text(it: dict) -> str:
    return " ".join([it["title"], it["summary"], it["why_it_matters"], *it["key_points"]])


def numbers(text: str) -> list[str]:
    return [n.rstrip("%") for n in NUM_RE.findall(text)]


def week_view(weekly: dict, issues: list[dict], exp_view, prev_issues: list[dict]) -> dict:
    """Everything the weekly page / markdown needs. `exp_view(id)` returns an experiment dict or None."""
    wid = weekly["week"]
    w_issues = week_issues(wid, issues)
    idx = item_index(w_issues)
    items = [idx[k] for k in idx]
    ref = lambda i: idx.get(i)  # noqa: E731

    a, _ = week_range(wid)
    monday = date.fromisoformat(a)
    by_date = {i["date"]: i for i in w_issues}
    days = []
    for n in range(7):
        d = (monday + timedelta(days=n)).isoformat()
        iss = by_date.get(d)
        its = sorted(iss["items"], key=lambda x: -x["importance"]) if iss else []
        days.append({"date": d, "label": f"周{WEEKDAYS[n]}", "day": int(d[8:]), "has": bool(iss),
                     "dots": [{"cat": x["category"], "imp": x["importance"], "id": x["id"], "title": x["title"]} for x in its]})

    exps = []
    for iss in w_issues:
        for eid in iss.get("experiments", []):
            e = exp_view(eid)
            if e:
                exps.append(e)

    tags_now = Counter(t for it in items for t in it["tags"])
    tags_prev = Counter(t for iss in prev_issues for it in iss["items"] for t in it["tags"])
    has_prev = bool(prev_issues)
    tags = [{"name": t, "count": n, "delta": n - tags_prev.get(t, 0) if has_prev else 0,
             "new": has_prev and t not in tags_prev} for t, n in tags_now.most_common(10)]

    cats = Counter(it["category"] for it in items)
    return {
        "week": wid, "label": week_label(wid), "range": range_label(wid),
        "title": weekly["title"], "lede": weekly["lede"], "editor_note": weekly.get("editor_note", ""),
        "stats": {"issues": len(w_issues), "items": len(items), "exps": len(exps),
                  "passed": sum(1 for e in exps if e["status"] == "passed"),
                  "try": sum(1 for it in items if it.get("actionability") == "try")},
        "cats": [{"key": c, "name": CATEGORIES[c], "count": cats[c]} for c in CATEGORIES if cats.get(c)],
        "days": days,
        "themes": [dict(t, items=[ref(i) for i in t["item_ids"] if ref(i)]) for t in weekly["themes"]],
        "picks": [dict(p, item=ref(p["item_id"])) for p in weekly["picks"] if ref(p["item_id"])],
        "hands_on": [dict(p, item=ref(p["item_id"])) for p in weekly.get("hands_on", []) if ref(p["item_id"])],
        "watch_next": [dict(w, items=[ref(i) for i in w["item_ids"] if ref(i)]) for w in weekly.get("watch_next", [])],
        "quiz": [dict(q, item=ref(q["item_id"]), n=n) for n, q in enumerate(weekly.get("quiz", []), 1) if ref(q["item_id"])],
        "skills": sorted((it for it in items if it.get("skill")), key=lambda x: x["date"]),
        "kits": sorted((it for it in items if it.get("kit")), key=lambda x: x["date"]),
        "exps": exps,
        "tags": tags,
        "has_prev": has_prev,
    }


def weekly_markdown(v: dict, site_url: str) -> str:
    st = v["stats"]
    out = [f"# AI 周报 {v['label']}（{v['range']}）", "", f"**{v['title']}**", "", f"> {v['lede']}", "",
           f"本周 {st['issues']} 期 · {st['items']} 条 · 可动手 {st['try']} 条 · 实验 {st['exps']} 个（已验证 {st['passed']}）", ""]
    if v["editor_note"]:
        out += [f"*{v['editor_note']}*", ""]
    out += ["## 本周主线", ""]
    for n, t in enumerate(v["themes"], 1):
        out += [f"### {n}. {t['title']}", "", t["summary"], ""]
        out += [f"- {it['title']}（{it['date'][5:]}，{CATEGORIES[it['category']]}）" for it in t["items"]] + [""]
    out += ["## 本周必读", ""]
    out += [f"{n}. **{p['item']['title']}** — {p['reason']}" for n, p in enumerate(v["picks"], 1)] + [""]
    if v["hands_on"]:
        out += ["## 值得动手", ""] + [f"- **{p['item']['title']}** — {p['reason']}" for p in v["hands_on"]] + [""]
    if v["skills"]:
        out += ["## 本周 AI 软技能", ""]
        out += [f"- 【{SKILL_AREAS[it['skill']['area']]}】{it['title']}" for it in v["skills"]] + [""]
    if v["kits"]:
        out += ["## 本周 Skill 精选", ""]
        out += [f"- {KIT_KINDS[it['kit']['kind']]} `{it['kit']['name']}`" + (f" {it['kit']['version']}" if it["kit"].get("version") else "")
                + f" — {it['title']}" for it in v["kits"]] + [""]
    if v["exps"]:
        out += ["## 本周实验", ""] + [f"- {STATUS_LABEL[e['status']]} {e['title']}" for e in v["exps"]] + [""]
    if v["tags"]:
        out += ["## 标签热度", "", " · ".join(f"`{t['name']}` {t['count']}" + (f"（+{t['delta']}）" if t["delta"] > 0 else "")
                                              for t in v["tags"]), ""]
    if v["quiz"]:
        out += ["## 本周小测", ""]
        for q in v["quiz"]:
            out += [f"**{q['n']}. {q['question']}**", ""] + [f"- {'ABCD'[i]}. {o}" for i, o in enumerate(q["options"])] + [""]
        out += ["<details><summary>答案</summary>", ""]
        out += [f"{q['n']}. {'ABCD'[q['answer']]}：{q['explanation']}（出自「{q['item']['title']}」）" for q in v["quiz"]]
        out += ["", "</details>", ""]
    if v["watch_next"]:
        out += ["## 下周关注", ""] + [f"- {w['text']}" for w in v["watch_next"]] + [""]
    if site_url:
        out += ["---", f"外网原文页面：{site_url}weekly/{v['week']}.html", ""]
    return "\n".join(out)
