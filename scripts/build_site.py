#!/usr/bin/env python3
"""Build the static site and the wiki sync packages into _site/.

Output:
  _site/index.html                    latest issue
  _site/daily/YYYY-MM-DD.html         each issue
  _site/item/<item id>.html           one page per item
  _site/archive.html
  _site/experiments/index.html, <id>.html
  _site/feed.xml                      Atom feed
  _site/data/manifest.json            index for intranet sync
  _site/data/YYYY-MM-DD.json          per-day wiki package (Markdown + HTML pages)

Usage: python3 scripts/build_site.py [--out _site] [--site-url https://owner.github.io/repo/]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape as html_escape
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.util import ClassNotFound

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    CATEGORIES, CATEGORY_ORDER, EXPERIMENTS_DIR, ROOT, STATUS_LABEL,
    experiment_status, issue_files, load_experiment, load_issue,
)

SOURCE_KINDS = {"primary": "原文", "secondary": "报道", "discussion": "讨论"}
ACT_LABELS = {"try": "可动手", "watch": "值得关注", "know": "了解即可"}
BADGE_LABEL = {"passed": "已验证", "partial": "部分可用", "failed": "复现失败", "pending": "待执行"}
WIKI_ROOT = "AI日报"
WEEKDAYS = "一二三四五六日"
CODE_EXTS = {".py", ".js", ".mjs", ".ts", ".sh", ".txt", ".json", ".toml", ".yaml", ".yml"}
TAG_WINDOW = 7          # issues used for "hot tags"
OUTPUT_TAIL = 14        # stdout lines shown on item pages


def date_cn(d: str, weekday: bool = True) -> str:
    dt = date.fromisoformat(d)
    s = f"{dt.month}月{dt.day}日"
    return f"{s} 周{WEEKDAYS[dt.weekday()]}" if weekday else s


def md_to_html(text: str) -> str:
    return markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])


def brief(summary: str, limit: int = 90) -> str:
    """First sentence of a summary, for share snippets."""
    m = re.match(r"(.+?[。！？])", summary)
    s = m.group(1) if m else summary
    return s if len(s) <= limit else s[: limit - 1] + "…"


def host(url: str) -> str:
    h = urlparse(url).netloc
    return h[4:] if h.startswith("www.") else h


def render_output(stdout: str, tail: int | None = None) -> Markup:
    lines = (stdout or "（无输出）").rstrip("\n").splitlines()
    if tail and len(lines) > tail:
        lines = ["…"] + lines[-tail:]
    out = []
    for line in lines:
        esc = str(html_escape(line))
        esc = re.sub(r"^\[(PASS|OK)\]", r'<span class="ok">[\1]</span>', esc)
        esc = re.sub(r"^(RESULT:)", r'<span class="key">\1</span>', esc)
        out.append(esc)
    return Markup("\n".join(out))


# ---------------------------------------------------------------- Markdown for wiki

def issue_markdown(issue: dict, exps: list[dict], site_url: str) -> str:
    d = issue["date"]
    out = [f"# AI 日报 {d}", "", f"> {issue['editor_note']}", ""]
    if issue.get("tldr"):
        out += ["**今日三件事**", ""]
        out += [f"{i}. {t['text']}" for i, t in enumerate(issue["tldr"], 1)]
        out.append("")
    by_cat = group_items(issue["items"])
    out.append("**目录**：" + " · ".join(f"{CATEGORIES[c]}（{len(v)}）" for c, v in by_cat))
    out.append("")
    for cat, items in by_cat:
        out += [f"## {CATEGORIES[cat]}", ""]
        for it in items:
            stars = "★" * it["importance"] + "☆" * (5 - it["importance"])
            out += [f"### {it['title']}", ""]
            meta = f"重要度 {stars}"
            if it.get("actionability"):
                meta += f"　实用度：{ACT_LABELS[it['actionability']]}"
            meta += "　标签：" + " ".join(f"`{t}`" for t in it["tags"])
            if it.get("follow_up_of"):
                meta += "　（跟进报道）"
            out += [meta, "", it["summary"], ""]
            out += [f"- {p}" for p in it["key_points"]]
            out += ["", f"**为什么值得关注**：{it['why_it_matters']}", ""]
            if it.get("experiment_id"):
                out += [f"🧪 配套实验：见子页面「实验：{exp_title(exps, it['experiment_id'])}」", ""]
            out.append("来源：")
            for s in it["sources"]:
                pub = f"（{s['publisher']}）" if s.get("publisher") else ""
                out.append(f"- [{SOURCE_KINDS[s['kind']]}] [{s['title']}]({s['url']}){pub}")
            out.append("")
    if exps:
        out += ["## 可验证实验", ""]
        for e in exps:
            out.append(f"- {STATUS_LABEL[e['status']]}　**{e['title']}**：{e['goal']}")
        out.append("")
    if site_url:
        out += ["---", f"外网原文页面：{site_url}daily/{d}.html", ""]
    return "\n".join(out)


def item_markdown(it: dict) -> str:
    """Markdown snippet for the "copy as Markdown" button; {{URL}} is filled in by app.js."""
    out = [f"### [{it['title']}]({{{{URL}}}})", "", it["summary"], ""]
    out += [f"- {p}" for p in it["key_points"]]
    out += ["", f"**为什么值得关注**：{it['why_it_matters']}", ""]
    out.append("来源：" + "；".join(f"[{s['title']}]({s['url']})" for s in it["sources"]))
    return "\n".join(out)


def exp_title(exps: list[dict], exp_id: str) -> str:
    for e in exps:
        if e["id"] == exp_id:
            return e["title"]
    return exp_id


def experiment_markdown(e: dict) -> str:
    out = [f"# 实验：{e['title']}", ""]
    out += [f"**状态**：{STATUS_LABEL[e['status']]}　**运行环境**：{e['runtime']}　**入口**：`{e['entry']}`", ""]
    res = e.get("result")
    if res:
        out += [f"实际运行：{res.get('ran_at', '')} UTC，耗时 {res.get('duration_seconds', '?')} 秒"
                + (f"，{res['runtime_version']}" if res.get("runtime_version") else "")
                + (f"，**{res['failure']}**" if res.get("failure") else ""), ""]
    readme = e.get("readme", "")
    lines = readme.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    out += ["\n".join(lines).strip(), ""]
    if res:
        out += ["## 实际运行输出", "", "```text", (res.get("stdout") or "（无输出）").rstrip(), "```", ""]
        if res.get("stderr"):
            out += ["<details><summary>stderr</summary>", "", "```text", res["stderr"].rstrip(), "```", "", "</details>", ""]
    out += ["## 代码", ""]
    d = EXPERIMENTS_DIR / e["id"]
    for name in e["files"]:
        p = d / name
        if p.suffix in CODE_EXTS and name != "README.md":
            lang = {"py": "python", "js": "javascript", "mjs": "javascript", "ts": "typescript", "sh": "bash"}.get(p.suffix[1:], "")
            out += [f"**{name}**", "", f"```{lang}", p.read_text(encoding="utf-8").rstrip(), "```", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- helpers

def group_items(items: list[dict]) -> list[tuple[str, list[dict]]]:
    groups = []
    for cat in CATEGORY_ORDER:
        sel = sorted((i for i in items if i["category"] == cat), key=lambda i: -i["importance"])
        if sel:
            groups.append((cat, sel))
    return groups


def experiment_view(exp_id: str) -> dict | None:
    e = load_experiment(exp_id)
    if not e:
        return None
    e["status"] = experiment_status(e)
    return e


def code_files_html(e: dict) -> list[dict]:
    fmt = HtmlFormatter(cssclass="highlight")
    out = []
    d = EXPERIMENTS_DIR / e["id"]
    for name in e["files"]:
        p = d / name
        if name == "README.md" or p.suffix not in CODE_EXTS:
            continue
        try:
            lexer = get_lexer_for_filename(name)
        except ClassNotFound:
            lexer = TextLexer()
        src = p.read_text(encoding="utf-8")
        out.append({"name": name, "html": highlight(src, lexer, fmt), "lines": len(src.splitlines())})
    entry_tokens = e.get("entry", "").split()
    out.sort(key=lambda f: (f["name"] not in entry_tokens, f["name"]))
    return out


def pygments_css() -> str:
    light = HtmlFormatter(style="friendly").get_style_defs(".highlight")
    dark_forced = HtmlFormatter(style="monokai").get_style_defs(':root[data-theme="dark"] .highlight')
    dark_system = HtmlFormatter(style="monokai").get_style_defs(':root:not([data-theme="light"]) .highlight')
    return (f"\n/* pygments */\n{light}\n{dark_forced}\n"
            f"@media (prefers-color-scheme: dark) {{\n{dark_system}\n}}\n"
            ".highlight, .highlight pre { background: none !important; }\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atom_feed(issues: list[dict], site_url: str, now: str) -> str:
    base = site_url or ""
    entries = []
    for i in issues[:30]:
        url = f"{base}daily/{i['date']}.html"
        entries.append(
            f"<entry><title>AI 日报 {i['date']}</title><link href=\"{escape(url)}\"/>"
            f"<id>{escape(url)}</id><updated>{i['date']}T06:00:00+08:00</updated>"
            f"<summary>{escape(i['editor_note'])}</summary></entry>"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        f"<title>AI Daily Lab</title><link href=\"{escape(base)}\"/><id>{escape(base or 'ai-daily-lab')}</id>"
        f"<updated>{now}</updated>" + "".join(entries) + "</feed>\n"
    )


def related_items(it: dict, all_items: list[dict], limit: int = 4) -> list[dict]:
    mine = set(it["tags"])
    scored = []
    for other in all_items:
        if other["id"] == it["id"]:
            continue
        shared = [t for t in other["tags"] if t in mine]
        if shared:
            scored.append((len(shared), other["date"], other, shared))
    # more shared tags first; on a tie prefer other days (same-day items are listed separately), newest first
    scored.sort(key=lambda x: (-x[0], x[1] == it["date"], -int(x[1].replace("-", ""))))
    return [{"id": o["id"], "title": o["title"], "date": d, "shared": sh} for _, d, o, sh in scored[:limit]]


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "_site"))
    ap.add_argument("--site-url", default="", help="public base URL ending with /")
    args = ap.parse_args()
    site_url = args.site_url
    if site_url and not site_url.endswith("/"):
        site_url += "/"

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    for sub in ("assets", "daily", "item", "experiments", "data"):
        (out / sub).mkdir(parents=True)

    now = datetime.now(timezone.utc)
    build_time = now.astimezone().strftime("%Y-%m-%d %H:%M")
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
    env.filters["format_tag"] = lambda t: f"#{t}"
    env.filters["dur"] = lambda v: "不到 0.1s" if v is not None and v < 0.1 else f"{v}s"
    common = dict(categories=CATEGORIES, source_kinds=SOURCE_KINDS, status_label=BADGE_LABEL,
                  act_labels=ACT_LABELS, build_time=build_time)

    (out / "assets" / "style.css").write_text(
        (ROOT / "templates" / "style.css").read_text(encoding="utf-8") + pygments_css(), encoding="utf-8")
    shutil.copyfile(ROOT / "templates" / "app.js", out / "assets" / "app.js")

    paths = issue_files()
    issues = [load_issue(p) for p in paths]
    dates = [i["date"] for i in issues]

    # global item index (for related items)
    all_items = []
    for issue in issues:
        for it in issue["items"]:
            it["date"] = issue["date"]
            it["brief"] = brief(it["summary"])
            all_items.append(it)

    manifest_entries, all_exps, archive = [], [], []
    tpl_day, tpl_item = env.get_template("day.html"), env.get_template("item.html")

    for idx, issue in enumerate(issues):
        d = issue["date"]
        exps = [e for e in (experiment_view(x) for x in issue["experiments"]) if e]
        exp_status = {e["id"]: e["status"] for e in exps}
        all_exps += exps
        groups = group_items(issue["items"])
        ordered = [it for _, its in groups for it in its]

        tldr = issue.get("tldr")
        tldr_auto = not tldr
        if tldr_auto:
            top = sorted(issue["items"], key=lambda i: -i["importance"])[:3]
            tldr = [{"text": i["title"], "item_id": i["id"]} for i in top]

        window = issues[max(0, idx - TAG_WINDOW + 1): idx + 1]
        counter = Counter(t for iss in window for it in iss["items"] for t in it["tags"])
        today_tags = {t for it in issue["items"] for t in it["tags"]}
        recent_tags = [(t, n) for t, n in counter.most_common() if t in today_tags][:8]

        cat_counts = [{"key": c, "name": CATEGORIES[c], "count": len(its)} for c, its in groups]
        ctx = dict(common, issue=issue, date_cn=date_cn(d), groups=groups, exps=exps, exp_status=exp_status,
                   tldr=tldr, tldr_auto=tldr_auto, cat_counts=cat_counts, issue_no=idx + 1,
                   try_count=sum(1 for i in issue["items"] if i.get("actionability") == "try"),
                   top_count=sum(1 for i in issue["items"] if i["importance"] >= 4),
                   recent_tags=recent_tags, tags_window=f"近 {len(window)} 期",
                   prev=dates[idx - 1] if idx > 0 else None,
                   next=dates[idx + 1] if idx + 1 < len(dates) else None)
        (out / "daily" / f"{d}.html").write_text(tpl_day.render(ctx, root="../", nav="archive"), encoding="utf-8")
        if idx == len(issues) - 1:
            (out / "index.html").write_text(tpl_day.render(ctx, root="", nav="today"), encoding="utf-8")

        # item pages
        exp_by_id = {e["id"]: e for e in exps}
        for pos, it in enumerate(ordered):
            exp = exp_by_id.get(it.get("experiment_id"))
            sources = [dict(s, host=host(s["url"])) for s in it["sources"]]
            ictx = dict(common, it=dict(it, sources=sources), date=d, date_cn=date_cn(d),
                        exp=exp, exp_output=render_output(exp["result"]["stdout"], OUTPUT_TAIL) if exp and exp.get("result") else None,
                        related=related_items(it, all_items),
                        same_cat=[o for o in ordered if o["category"] == it["category"] and o["id"] != it["id"]][:5],
                        prev_item=ordered[pos - 1] if pos > 0 else None,
                        next_item=ordered[pos + 1] if pos + 1 < len(ordered) else None,
                        md_src=item_markdown(it))
            (out / "item" / f"{it['id']}.html").write_text(
                tpl_item.render(ictx, root="../", nav="archive"), encoding="utf-8")

        # wiki package
        y, m, _ = d.split("-")
        day_md = issue_markdown(issue, exps, site_url)
        pages = [{"key": d, "path": [WIKI_ROOT, y, f"{y}-{m}", d], "title": f"AI 日报 {d}",
                  "markdown": day_md, "html": md_to_html(day_md)}]
        for e in exps:
            emd = experiment_markdown(e)
            pages.append({"key": e["id"], "path": [WIKI_ROOT, y, f"{y}-{m}", d, f"实验：{e['title']}"],
                          "title": f"实验：{e['title']}", "markdown": emd, "html": md_to_html(emd),
                          "status": e["status"]})
        clean_items = [{k: v for k, v in it.items() if k not in ("date", "brief")} for it in issue["items"]]
        package = {"schema_version": 1, "date": d, "editor_note": issue["editor_note"],
                   "tldr": issue.get("tldr", []), "pages": pages, "items": clean_items}
        pkg_path = out / "data" / f"{d}.json"
        pkg_path.write_text(json.dumps(package, ensure_ascii=False, indent=1), encoding="utf-8")
        manifest_entries.append({"date": d, "items": len(issue["items"]), "experiments": len(exps),
                                 "package": f"data/{d}.json", "sha256": sha256(pkg_path),
                                 "bytes": pkg_path.stat().st_size})
        archive.append({"date": d, "short": date_cn(d, weekday=False), "weekday": "周" + WEEKDAYS[date.fromisoformat(d).weekday()],
                        "editor_note": issue["editor_note"], "tldr": issue.get("tldr"),
                        "count": len(issue["items"]), "exp_count": len(exps)})

    if not issues:
        (out / "index.html").write_text("<!doctype html><meta charset=utf-8><p>还没有日报。</p>", encoding="utf-8")

    archive.reverse()
    (out / "archive.html").write_text(
        env.get_template("archive.html").render(common, issues=archive, root="", nav="archive"), encoding="utf-8")

    all_exps.sort(key=lambda e: e["id"], reverse=True)
    (out / "experiments" / "index.html").write_text(
        env.get_template("experiments.html").render(common, exps=all_exps, root="../", nav="experiments"),
        encoding="utf-8")
    for e in all_exps:
        readme = e.get("readme", "")
        lines = readme.splitlines()
        if lines and lines[0].startswith("# "):
            readme = "\n".join(lines[1:])
        (out / "experiments" / f"{e['id']}.html").write_text(
            env.get_template("experiment.html").render(
                common, e=e, readme_html=md_to_html(readme), code_files=code_files_html(e),
                output=render_output(e["result"]["stdout"]) if e.get("result") else "",
                root="../", nav="experiments"),
            encoding="utf-8")

    manifest = {"schema_version": 1, "generated_at": now.isoformat(timespec="seconds"), "site_url": site_url,
                "wiki_root": WIKI_ROOT, "latest": dates[-1] if dates else None,
                "issues": list(reversed(manifest_entries))}
    (out / "data" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "feed.xml").write_text(atom_feed(list(reversed(issues)), site_url, now.isoformat(timespec="seconds")),
                                  encoding="utf-8")
    (out / ".nojekyll").write_text("")
    print(f"built {len(issues)} issue(s), {len(all_items)} item page(s), {len(all_exps)} experiment(s) → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
