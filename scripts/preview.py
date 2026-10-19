#!/usr/bin/env python3
"""Render changed issues as a Markdown preview for a PR comment.

Usage: python3 scripts/preview.py --changed-since origin/main --out preview.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_site import experiment_view, issue_markdown  # noqa: E402
from validate import changed_issue_files  # noqa: E402
from common import load_issue  # noqa: E402

MARKER = "<!-- ai-daily-preview -->"
LIMIT = 60_000  # GitHub comment limit is 65,536 chars


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--changed-since", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--artifact-url", default="")
    args = ap.parse_args()

    parts = [MARKER, "## 👀 内容预览", ""]
    if args.artifact_url:
        parts += [f"完整站点预览：下载 [site-preview 构建产物]({args.artifact_url})，解压后用浏览器打开 `index.html`。", ""]
    files = changed_issue_files(args.changed_since)
    if not files:
        parts.append("本次没有改动日报文件。")
    for f in files:
        issue = load_issue(f)
        exps = [e for e in (experiment_view(x) for x in issue["experiments"]) if e]
        md = issue_markdown(issue, exps, "")
        # Demote headings by one level so they nest under the comment title.
        md = "\n".join("#" + l if l.startswith("#") else l for l in md.splitlines())
        parts += ["<details open>", f"<summary><b>{issue['date']}</b>（{len(issue['items'])} 条）</summary>", "", md, "", "</details>", ""]
    text = "\n".join(parts)
    if len(text) > LIMIT:
        text = text[:LIMIT] + "\n\n…（内容过长已截断，请下载构建产物查看完整页面）\n\n</details>"
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"preview: {len(files)} issue(s), {len(text)} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
