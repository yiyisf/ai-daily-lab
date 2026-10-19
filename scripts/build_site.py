#!/usr/bin/env python3
"""Build the static site and the wiki sync packages into _site/.

Output:
  _site/index.html                    latest issue
  _site/daily/YYYY-MM-DD.html         each issue
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
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape
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
WIKI_ROOT = "AI日报"
WEEKDAYS = "一二三四五六日"
CODE_EXTS = {".py", ".js", ".mjs", ".ts", ".sh", ".txt", ".json", ".toml", ".yaml", ".yml"}


def date_cn(d: str) -> str:
    dt = date.fromisoformat(d)
    return f"{dt.year}年{dt.month}月{dt.day}日 周{WEEKDAYS[dt.weekday()]}"


def md_to_html(text: str) -> str:
    return markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])


# ---------------------------------------------------------------- Markdown for wiki

def issue_markdown(issue: dict, exps: list[dict], site_url: str) -> str:
    d = issue["date"]
    out = [f"# AI 日报 {d}", "", f"> {issue['editor_note']}", ""]
    by_cat = group_items(issue["items"])
    out.append("**目录**：" + " · ".join(f"{CATEGORIES[c]}（{len(v)}）" for c, v in by_cat))
    out.append("")
    for cat, items in by_cat:
        out += [f"## {CATEGORIES[cat]}", ""]
        for it in items:
            stars = "★" * it["importance"] + "☆" * (5 - it["importance"])
            out += [f"### {it['title']}", ""]
            meta = f"重要度 {stars}　标签：" + " ".join(f"`{t}`" for t in it["tags"])
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
    # Drop README's own H1 to avoid two titles.
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
        out.append({"name": name, "html": highlight(p.read_text(encoding="utf-8"), lexer, fmt)})
    # entry file first
    entry_tokens = e.get("entry", "").split()
    out.sort(key=lambda f: (f["name"] not in entry_tokens, f["name"]))
    return out


def pygments_css() -> str:
    light = HtmlFormatter(style="friendly").get_style_defs(".highlight")
    dark = HtmlFormatter(style="monokai").get_style_defs(".highlight")
    return (f"\n/* pygments */\n{light}\n.highlight {{ background: none !important; }}\n"
            f"@media (prefers-color-scheme: dark) {{\n{dark}\n.highlight {{ background: none !important; }}\n}}\n")


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
    (out / "assets").mkdir(parents=True)
    (out / "daily").mkdir()
    (out / "experiments").mkdir()
    (out / "data").mkdir()

    now = datetime.now(timezone.utc)
    build_time = now.astimezone().strftime("%Y-%m-%d %H:%M")
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
    common = dict(categories=CATEGORIES, source_kinds=SOURCE_KINDS, status_label=STATUS_LABEL, build_time=build_time)

    (out / "assets" / "style.css").write_text(
        (ROOT / "templates" / "style.css").read_text(encoding="utf-8") + pygments_css(), encoding="utf-8")

    paths = issue_files()
    issues = [load_issue(p) for p in paths]
    dates = [i["date"] for i in issues]
    manifest_entries = []
    all_exps: list[dict] = []
    archive = []

    for idx, issue in enumerate(issues):
        d = issue["date"]
        issue["date_cn"] = date_cn(d)
        exps = [e for e in (experiment_view(x) for x in issue["experiments"]) if e]
        all_exps += exps
        groups = group_items(issue["items"])
        highlights = sorted(issue["items"], key=lambda i: -i["importance"])[:3]
        highlights = [h for h in highlights if h["importance"] >= 4]
        ctx = dict(common, issue=issue, groups=groups, exps=exps, highlights=highlights,
                   prev=dates[idx - 1] if idx > 0 else None,
                   next=dates[idx + 1] if idx + 1 < len(dates) else None)
        tpl = env.get_template("day.html")
        (out / "daily" / f"{d}.html").write_text(tpl.render(ctx, root="../", nav="archive"), encoding="utf-8")
        if idx == len(issues) - 1:
            (out / "index.html").write_text(tpl.render(ctx, root="", nav="today"), encoding="utf-8")

        # Wiki package
        y, m, _ = d.split("-")
        day_md = issue_markdown(issue, exps, site_url)
        pages = [{
            "key": d,
            "path": [WIKI_ROOT, y, f"{y}-{m}", d],
            "title": f"AI 日报 {d}",
            "markdown": day_md,
            "html": md_to_html(day_md),
        }]
        for e in exps:
            emd = experiment_markdown(e)
            pages.append({
                "key": e["id"],
                "path": [WIKI_ROOT, y, f"{y}-{m}", d, f"实验：{e['title']}"],
                "title": f"实验：{e['title']}",
                "markdown": emd,
                "html": md_to_html(emd),
                "status": e["status"],
            })
        package = {
            "schema_version": 1,
            "date": d,
            "editor_note": issue["editor_note"],
            "pages": pages,
            "items": issue["items"],
        }
        pkg_path = out / "data" / f"{d}.json"
        pkg_path.write_text(json.dumps(package, ensure_ascii=False, indent=1), encoding="utf-8")
        manifest_entries.append({
            "date": d,
            "items": len(issue["items"]),
            "experiments": len(exps),
            "package": f"data/{d}.json",
            "sha256": sha256(pkg_path),
            "bytes": pkg_path.stat().st_size,
        })
        archive.append({"date": d, "editor_note": issue["editor_note"],
                        "count": len(issue["items"]), "exp_count": len(exps)})

    if not issues:
        (out / "index.html").write_text("<!doctype html><meta charset=utf-8><p>还没有日报。</p>", encoding="utf-8")

    archive.reverse()
    (out / "archive.html").write_text(
        env.get_template("archive.html").render(common, issues=archive, root="", nav="archive"), encoding="utf-8")

    # Experiments
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
                root="../", nav="experiments"),
            encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "generated_at": now.isoformat(timespec="seconds"),
        "site_url": site_url,
        "wiki_root": WIKI_ROOT,
        "latest": dates[-1] if dates else None,
        "issues": list(reversed(manifest_entries)),
    }
    (out / "data" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "feed.xml").write_text(atom_feed(list(reversed(issues)), site_url, now.isoformat(timespec="seconds")),
                                  encoding="utf-8")
    (out / ".nojekyll").write_text("")
    print(f"built {len(issues)} issue(s), {len(all_exps)} experiment(s) → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
