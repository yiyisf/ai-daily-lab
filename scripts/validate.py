#!/usr/bin/env python3
"""Validate daily issue files.

Usage:
  python3 scripts/validate.py content/daily/2026/2026-10-20.json [...]
  python3 scripts/validate.py --all
  python3 scripts/validate.py --changed-since origin/main      # files changed vs a git ref
Options:
  --check-links      also request every source URL (warnings only)
  --report PATH      write a Markdown report (used as a PR comment)

Exit code 1 when any error is found. Warnings never fail the run.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    CATEGORIES, CATEGORY_RANGE, CONTENT_DIR, EXPERIMENTS_DIR, ROOT, SCHEMA_DIR,
    HANDS_ON_FROM, SKILL_AREAS, STRICT_FROM, TOTAL_RANGE, WEEK_RE, WEEKLY_DIR, issue_files, load_json, week_range, weekly_files,
)
from weekly import item_index, item_text, numbers, week_issues  # noqa: E402

DAILY_SCHEMA = Draft202012Validator(load_json(SCHEMA_DIR / "daily.schema.json"))
EXP_SCHEMA = Draft202012Validator(load_json(SCHEMA_DIR / "experiment.schema.json"))
WEEKLY_SCHEMA = Draft202012Validator(load_json(SCHEMA_DIR / "weekly.schema.json"))
UA = "Mozilla/5.0 (compatible; ai-daily-lab-linkcheck/1.0)"


class Report:
    def __init__(self, name: str):
        self.name = name
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def err(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)


def recent_urls(current: date, days: int = 7) -> dict[str, str]:
    """url -> item id for issues in the `days` before `current`."""
    seen: dict[str, str] = {}
    lo = current - timedelta(days=days)
    for p in issue_files():
        try:
            d = date.fromisoformat(p.stem)
        except ValueError:
            continue
        if not (lo <= d < current):
            continue
        for item in load_json(p).get("items", []):
            for s in item.get("sources", []):
                seen[normalize_url(s.get("url", ""))] = item.get("id", "")
    return seen


def normalize_url(u: str) -> str:
    u = u.strip().split("#", 1)[0]
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            u = u[len(prefix):]
    if u.startswith("www."):
        u = u[4:]
    return u.rstrip("/").lower()


def check_link(url: str) -> str | None:
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status < 400:
                    return None
        except urllib.error.HTTPError as e:
            # Many sites reject HEAD or bots; only report after GET also fails.
            if method == "GET":
                return f"HTTP {e.code}"
        except Exception as e:  # noqa: BLE001
            if method == "GET":
                return type(e).__name__
    return "unreachable"


def validate_experiment(exp_id: str, rep: Report, issue_ids: set[str]):
    d = EXPERIMENTS_DIR / exp_id
    if not d.is_dir():
        rep.err(f"实验目录不存在：`experiments/{exp_id}/`")
        return
    meta_path = d / "experiment.json"
    if not meta_path.exists():
        rep.err(f"`experiments/{exp_id}/experiment.json` 缺失")
        return
    meta = load_json(meta_path)
    for e in sorted(EXP_SCHEMA.iter_errors(meta), key=lambda e: list(e.path)):
        loc = "/".join(str(x) for x in e.path) or "(root)"
        rep.err(f"实验 `{exp_id}` 元数据 `{loc}`：{e.message}")
    if meta.get("id") != exp_id:
        rep.err(f"实验 `{exp_id}` 的 id 字段与目录名不一致")
    if meta.get("related_item") and meta["related_item"] not in issue_ids:
        rep.err(f"实验 `{exp_id}` 的 related_item `{meta['related_item']}` 不在当期条目中")
    readme = d / "README.md"
    if not readme.exists():
        rep.err(f"实验 `{exp_id}` 缺少 README.md")
    elif "内网复现" not in readme.read_text(encoding="utf-8"):
        rep.err(f"实验 `{exp_id}` 的 README.md 缺少「内网复现」一节")
    entry = meta.get("entry", "")
    runtime = meta.get("runtime")
    if runtime == "python" and not (d / "requirements.txt").exists():
        rep.warn(f"实验 `{exp_id}` 没有 requirements.txt（若无依赖可忽略）")
    if runtime == "node" and not (d / "package.json").exists():
        rep.warn(f"实验 `{exp_id}` 没有 package.json（若无依赖可忽略）")
    first_file = next((tok for tok in entry.split() if "." in tok and "/" not in tok), None)
    if first_file and not (d / first_file).exists():
        rep.err(f"实验 `{exp_id}` 的入口文件 `{first_file}` 不存在")


def number_forms(v: float) -> set[str]:
    forms = {repr(v), f"{v:g}", f"{v:,}", f"{v:,g}"}
    if isinstance(v, float) and v.is_integer():
        forms |= {str(int(v)), f"{int(v):,}"}
    return forms


def check_figure(it: dict, rep: Report):
    fig = it.get("figure")
    if not fig:
        return
    iid = it["id"]
    other = {"steps": ("series", "rows", "unit"), "bars": ("steps", "loop", "base")}[fig["type"]]
    extra = [k for k in other if k in fig]
    if extra:
        rep.err(f"`{iid}` 结构图类型是 {fig['type']}，不应包含字段：{', '.join(extra)}")
    if fig["type"] == "bars":
        n = len(fig["series"])
        text = " ".join([it["title"], it["summary"], it["why_it_matters"], *it["key_points"]])
        for row in fig["rows"]:
            if len(row["values"]) != n:
                rep.err(f"`{iid}` 结构图「{row['label']}」有 {len(row['values'])} 个数值，应与 series 数量 {n} 一致")
            for v in row["values"]:
                if v < 0:
                    rep.err(f"`{iid}` 结构图数值不能为负：{v}")
                if not any(re.search(rf"(?<![\d.,]){re.escape(f)}(?![\d])", text) for f in number_forms(v)):
                    rep.err(f"`{iid}` 结构图中的数值 {v:g}（{row['label']}）没有出现在标题、摘要或要点中；图里的数字必须是正文写过的")
        if n == 1 and len(fig["rows"]) < 2:
            rep.warn(f"`{iid}` 柱状图只有 1 个数值，不如直接写在正文里")


def validate_issue(path: Path, check_links: bool) -> Report:
    rel = path.resolve().relative_to(ROOT) if path.resolve().is_relative_to(ROOT) else path
    rep = Report(str(rel))
    try:
        data = load_json(path)
    except Exception as e:  # noqa: BLE001
        rep.err(f"JSON 解析失败：{e}")
        return rep

    for e in sorted(DAILY_SCHEMA.iter_errors(data), key=lambda e: list(e.path)):
        loc = "/".join(str(x) for x in e.path) or "(root)"
        rep.err(f"Schema `{loc}`：{e.message}")
    if rep.errors:
        return rep  # structural problems; further checks would be noise

    d = data["date"]
    if path.stem != d:
        rep.err(f"文件名 `{path.name}` 与 date `{d}` 不一致")
    if path.parent.name != d[:4]:
        rep.err(f"文件应放在 `content/daily/{d[:4]}/` 目录下")

    items = data["items"]
    ids = [it["id"] for it in items]
    for dup, n in Counter(ids).items():
        if n > 1:
            rep.err(f"条目 id 重复：`{dup}`")
    for it in items:
        if not it["id"].startswith(d + "-"):
            rep.err(f"条目 id `{it['id']}` 应以日期 `{d}-` 开头")

    # 今日三件事 & 实用度
    strict = d >= STRICT_FROM
    tldr = data.get("tldr")
    if not tldr:
        (rep.err if strict else rep.warn)("缺少 tldr（今日三件事）")
    else:
        refs = [t["item_id"] for t in tldr]
        for r in refs:
            if r not in ids:
                rep.err(f"tldr 引用的条目 `{r}` 不在当期条目中")
        if len(set(refs)) != len(refs):
            rep.err("tldr 中有重复引用的条目")
        if len(tldr) < 3 and len(items) >= 3:
            rep.warn(f"tldr 只有 {len(tldr)} 句，建议 3 句")
    # 今天可以试
    by_id = {it["id"]: it for it in items}
    hands_on = data.get("hands_on")
    if not hands_on:
        if d >= HANDS_ON_FROM:
            rep.warn("缺少 hands_on（今天可以试）；当天确实没有能动手的条目时可以不写，但要在 editor_note 里说明")
    else:
        refs = [h["item_id"] for h in hands_on]
        if len(set(refs)) != len(refs):
            rep.err("hands_on 中有重复引用的条目")
        for r in refs:
            if r not in by_id:
                rep.err(f"hands_on 引用的条目 `{r}` 不在当期条目中")
            elif by_id[r].get("actionability") != "try":
                rep.err(f"hands_on 引用的条目 `{r}` 的 actionability 不是 try，只能挑可动手的条目")
    missing_act = [it["id"] for it in items if "actionability" not in it]
    if missing_act:
        (rep.err if strict else rep.warn)(f"{len(missing_act)} 条缺少 actionability（实用度）：" + "、".join(f"`{i}`" for i in missing_act[:5])
                 + ("…" if len(missing_act) > 5 else ""))

    # AI 软技能
    for it in items:
        if it["category"] == "skills" and "skill" not in it:
            rep.err(f"`{it['id']}` 属于 AI 软技能，但缺少 skill（场景与好坏对比）")
        if it["category"] != "skills" and "skill" in it:
            rep.err(f"`{it['id']}` 不是 AI 软技能条目，不应包含 skill 字段")
    for it in items:
        if it["category"] == "kits" and "kit" not in it:
            rep.err(f"`{it['id']}` 属于 Skill 精选，但缺少 kit（能力、亮点、安装方式）")
        if it["category"] != "kits" and "kit" in it:
            rep.err(f"`{it['id']}` 不是 Skill 精选条目，不应包含 kit 字段")
        if it.get("kit", {}).get("changes") and not it.get("follow_up_of") and not it["kit"].get("version"):
            rep.warn(f"`{it['id']}` 写了版本更新（kit.changes），建议同时填写 kit.version")
        check_figure(it, rep)
    n_fig = sum(1 for it in items if it.get("figure"))
    if n_fig > 3:
        rep.warn(f"本期有 {n_fig} 张结构图，建议最多 3 张，只给最需要的条目配图")
    areas_today = [it["skill"]["area"] for it in items if it.get("skill")]
    if areas_today:
        recent_areas = []
        try:
            cur = date.fromisoformat(d)
            for p_ in issue_files():
                try:
                    pd = date.fromisoformat(p_.stem)
                except ValueError:
                    continue
                if cur - timedelta(days=3) <= pd < cur:
                    recent_areas += [it["skill"]["area"] for it in load_json(p_).get("items", []) if it.get("skill")]
        except ValueError:
            pass
        for a in areas_today:
            if a in recent_areas:
                rep.warn(f"AI 软技能方向「{SKILL_AREAS[a]}」近 3 天已出现过，建议换一个方向")

    # Category balance (warnings)
    counts = Counter(it["category"] for it in items)
    for cat, (lo, hi) in CATEGORY_RANGE.items():
        if cat in ("skills", "kits") and not strict:
            continue  # category introduced on STRICT_FROM
        n = counts.get(cat, 0)
        if not lo <= n <= hi:
            want = f"{lo}" if lo == hi else f"{lo}–{hi}"
            rep.warn(f"栏目「{CATEGORIES[cat]}」{n} 条，建议 {want} 条")
    if not TOTAL_RANGE[0] <= len(items) <= TOTAL_RANGE[1]:
        rep.warn(f"共 {len(items)} 条，建议 {TOTAL_RANGE[0]}–{TOTAL_RANGE[1]} 条")
    top = [it["id"] for it in items if it["importance"] == 5]
    if len(top) > 2:
        rep.err(f"importance=5 的条目有 {len(top)} 条，每天最多 2 条")

    # Sources
    try:
        prev = recent_urls(date.fromisoformat(d))
    except ValueError:
        prev = {}
    all_urls: list[str] = []
    for it in items:
        kinds = {s["kind"] for s in it["sources"]}
        if "primary" not in kinds:
            msg = f"`{it['id']}` 没有一手来源（kind=primary）"
            (rep.warn if it["category"] == "ideas" else rep.err)(msg)
        for s in it["sources"]:
            all_urls.append(s["url"])
            n = normalize_url(s["url"])
            if n in prev and not it.get("follow_up_of"):
                rep.warn(f"`{it['id']}` 的来源在近 7 天已报道过（`{prev[n]}`），如属跟进请填写 follow_up_of")
            if s["url"].startswith("http://"):
                rep.warn(f"`{it['id']}` 使用了 http 链接：{s['url']}")

    # Experiments
    exp_ids = set(data["experiments"])
    item_ids = set(ids)
    for it in items:
        if it.get("experiment_id") and it["experiment_id"] not in exp_ids:
            rep.err(f"`{it['id']}` 关联的实验 `{it['experiment_id']}` 不在 experiments 列表中")
    for exp_id in data["experiments"]:
        if not exp_id.startswith(d + "-"):
            rep.err(f"实验 id `{exp_id}` 应以日期 `{d}-` 开头")
        validate_experiment(exp_id, rep, item_ids)

    if check_links:
        uniq = sorted(set(all_urls))
        with ThreadPoolExecutor(max_workers=8) as pool:
            for url, problem in zip(uniq, pool.map(check_link, uniq)):
                if problem:
                    rep.warn(f"链接访问异常（{problem}）：{url}")
        rep.info.append(f"已检查 {len(uniq)} 个链接")

    rep.info.append(
        f"{len(items)} 条（" + "、".join(f"{CATEGORIES[c]} {counts.get(c, 0)}" for c in CATEGORIES)
        + f"），实验 {len(exp_ids)} 个"
    )
    return rep


def validate_weekly(path: Path) -> Report:
    rel = path.resolve().relative_to(ROOT) if path.resolve().is_relative_to(ROOT) else path
    rep = Report(str(rel))
    try:
        wk = load_json(path)
    except Exception as e:  # noqa: BLE001
        rep.err(f"JSON 解析失败：{e}")
        return rep
    errs = sorted(WEEKLY_SCHEMA.iter_errors(wk), key=lambda e: list(e.path))
    for e in errs:
        loc = "/".join(str(x) for x in e.path) or "(根)"
        rep.err(f"Schema `{loc}`：{e.message}")
    if errs:
        return rep
    wid = wk["week"]
    if path.stem != wid:
        rep.err(f"文件名 `{path.name}` 与 week `{wid}` 不一致")
    if path.parent.name != wid[:4]:
        rep.err(f"文件应放在 `content/weekly/{wid[:4]}/` 目录下")
    if not WEEK_RE.match(wid):
        return rep
    issues = [load_json(p) for p in issue_files()]
    w_issues = week_issues(wid, issues)
    a, b = week_range(wid)
    if not w_issues:
        rep.err(f"{a} 至 {b} 没有任何日报，无法生成周报")
        return rep
    idx = item_index(w_issues)
    rep.info.append(f"{a} 至 {b}：{len(w_issues)} 期日报、{len(idx)} 条可引用")
    if len(w_issues) < 5:
        rep.warn(f"本周只有 {len(w_issues)} 期日报，建议在 editor_note 里说明")

    def known(i: str, where: str) -> dict | None:
        it = idx.get(i)
        if not it:
            rep.err(f"{where} 引用的 `{i}` 不是本周（{a} 至 {b}）日报里的条目")
        return it

    def check_numbers(text: str, refs: list[dict], where: str):
        pool = " ".join(item_text(r) for r in refs)
        for n in numbers(text):
            if n not in pool:
                rep.warn(f"{where} 中的数字「{n}」没有出现在所引条目里，请确认不是新事实")

    seen_theme: dict[str, str] = {}
    for n, t in enumerate(wk["themes"], 1):
        refs = [r for r in (known(i, f"主线 {n}") for i in t["item_ids"]) if r]
        if len(set(t["item_ids"])) != len(t["item_ids"]):
            rep.err(f"主线 {n}「{t['title']}」里有重复条目")
        if len({r["date"] for r in refs}) < 2 and len(refs) >= 2:
            rep.warn(f"主线 {n}「{t['title']}」的条目都来自同一天，主线最好串起不同日期的内容")
        for i in t["item_ids"]:
            if i in seen_theme:
                rep.warn(f"`{i}` 同时出现在主线「{seen_theme[i]}」和「{t['title']}」")
            seen_theme[i] = t["title"]
        check_numbers(t["title"] + " " + t["summary"], refs, f"主线 {n}")

    pick_ids = [p["item_id"] for p in wk["picks"]]
    if len(set(pick_ids)) != len(pick_ids):
        rep.err("本周必读里有重复条目")
    for p in wk["picks"]:
        it = known(p["item_id"], "本周必读")
        if it:
            if it["importance"] <= 2:
                rep.warn(f"必读 `{it['id']}` 的重要度只有 {it['importance']}，确认是否合适")
            check_numbers(p["reason"], [it], f"必读 `{it['id']}` 的理由")
    for p in wk.get("hands_on", []):
        it = known(p["item_id"], "值得动手")
        if it:
            if it.get("actionability") != "try":
                rep.err(f"值得动手 `{it['id']}` 的实用度是 {it.get('actionability') or '未填'}，只能选 try（可动手）的条目")
            check_numbers(p["reason"], [it], f"值得动手 `{it['id']}` 的理由")
    for w in wk.get("watch_next", []):
        refs = [r for r in (known(i, "下周关注") for i in w["item_ids"]) if r]
        check_numbers(w["text"], refs, "下周关注")
    check_numbers(wk["title"] + " " + wk["lede"], list(idx.values()), "标题或导语")
    quiz = wk.get("quiz", [])
    if not quiz:
        rep.warn("没有写本周小测（quiz），建议 3–5 题")
    for n, q in enumerate(quiz, 1):
        it = known(q["item_id"], f"小测第 {n} 题")
        if q["answer"] >= len(q["options"]):
            rep.err(f"小测第 {n} 题的 answer={q['answer']} 超出选项范围（共 {len(q['options'])} 个）")
        if len(set(q["options"])) != len(q["options"]):
            rep.err(f"小测第 {n} 题有重复选项")
        if it and q["answer"] < len(q["options"]):
            check_numbers(q["question"] + " " + q["options"][q["answer"]] + " " + q["explanation"], [it], f"小测第 {n} 题")
    if len({q["item_id"] for q in quiz}) < len(quiz):
        rep.warn("小测有多道题出自同一个条目，建议覆盖不同条目")
    return rep


def changed_issue_files(ref: str) -> list[Path]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AM", f"{ref}...HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    files = {ROOT / f for f in out if f.startswith(("content/daily/", "content/weekly/")) and f.endswith(".json")}
    # An experiment change alone should still validate its issue.
    for f in out:
        if f.startswith("experiments/"):
            exp_id = f.split("/")[1]
            day = exp_id[:10]
            p = CONTENT_DIR / day[:4] / f"{day}.json"
            if p.exists():
                files.add(p)
    return sorted(files)


def render_markdown(reports: list[Report]) -> str:
    lines = ["## 🔎 内容校验结果", ""]
    if not reports:
        lines.append("本次没有改动日报文件。")
    for r in reports:
        icon = "❌" if r.errors else ("⚠️" if r.warnings else "✅")
        lines.append(f"### {icon} `{r.name}`")
        lines += [f"- {m}" for m in r.info]
        if r.errors:
            lines += ["", "**错误（必须修复）**"] + [f"- {m}" for m in r.errors]
        if r.warnings:
            lines += ["", "**提醒**"] + [f"- {m}" for m in r.warnings]
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--changed-since")
    ap.add_argument("--check-links", action="store_true")
    ap.add_argument("--report")
    args = ap.parse_args()

    if args.all:
        files = issue_files() + weekly_files()
    elif args.changed_since:
        files = changed_issue_files(args.changed_since)
    else:
        files = [Path(f) for f in args.files]
    if not files and not (args.all or args.changed_since):
        ap.error("没有指定要校验的文件")

    reports = [validate_weekly(Path(f)) if WEEK_RE.match(Path(f).stem) else validate_issue(Path(f), args.check_links)
               for f in files]
    md = render_markdown(reports)
    print(md)
    if args.report:
        Path(args.report).write_text(md, encoding="utf-8")
    return 1 if any(r.errors for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
