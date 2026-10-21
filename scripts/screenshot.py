#!/usr/bin/env python3
"""Take preview screenshots of a built site (used by site-check.yml).

Usage: python3 scripts/screenshot.py _site _site/_preview
Requires: pip install playwright && python -m playwright install chromium
"""
from __future__ import annotations

import functools
import http.server
import json
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEWPORTS = {"desktop": (1280, 900), "mobile": (390, 844)}
# Layout-shift budget (our own target; Google's "good" line is 0.1)
CLS_BUDGET = 0.05
CLS_PROBE = ("window.__cls=0;try{new PerformanceObserver(function(l){l.getEntries().forEach(function(e){"
             "if(!e.hadRecentInput)window.__cls+=e.value;});}).observe({type:'layout-shift',buffered:true});}catch(e){}")
SCHEMES = ("light", "dark")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D401 - keep CI logs clean
        pass


def pages(site: Path) -> dict[str, str]:
    out = {"home": "index.html", "archive": "archive.html", "experiments": "experiments/index.html",
           "tags": "tags/index.html", "saved": "saved.html"}
    tag_pages = sorted((site / "tags").glob("*.html")) if (site / "tags").exists() else []
    if (site / "tags" / "agent.html").exists():
        out["tag"] = "tags/agent.html"
    elif [t for t in tag_pages if t.name != "index.html"]:
        out["tag"] = "tags/" + [t for t in tag_pages if t.name != "index.html"][0].name
    manifest = json.loads((site / "data" / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("latest"):
        out["day"] = f"daily/{manifest['latest']}.html"
    exps = sorted((site / "experiments").glob("20*.html"))
    if exps:
        out["experiment"] = f"experiments/{exps[-1].name}"
    # an item page, preferring one with an experiment attached
    pkg = site / "data" / f"{manifest['latest']}.json" if manifest.get("latest") else None
    if pkg and pkg.exists():
        items = json.loads(pkg.read_text(encoding="utf-8")).get("items", [])
        pick = next((i for i in items if i.get("experiment_id")), items[0] if items else None)
        if pick and (site / "item" / f"{pick['id']}.html").exists():
            out["item"] = f"item/{pick['id']}.html"
    return out


def main() -> int:
    site, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(QuietHandler, directory=str(site))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}/"

    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for vname, (w, h) in VIEWPORTS.items():
            for scheme in SCHEMES:
                ctx = browser.new_context(viewport={"width": w, "height": h}, color_scheme=scheme,
                                          service_workers="block")
                ctx.add_init_script(CLS_PROBE)
                page = ctx.new_page()
                for name, path in pages(site).items():
                    page.goto(base + path)
                    page.wait_for_timeout(300)
                    cls = page.evaluate("window.__cls || 0")
                    if cls > CLS_BUDGET:
                        problems.append(f"{path} 在 {vname}/{scheme} 下布局偏移 CLS={cls:.3f}（目标 ≤ {CLS_BUDGET}）")
                    page.screenshot(path=str(out / f"{name}-{vname}-{scheme}.png"), full_page=True)
                    sw = page.evaluate("document.documentElement.scrollWidth")
                    if sw > w:
                        problems.append(f"{path} 在 {vname} 宽度下出现横向滚动（{sw}px > {w}px）")
                ctx.close()
        browser.close()
    httpd.shutdown()
    print(f"screenshots → {out}")
    for p_ in problems:
        print("WARN:", p_)
    return 0


if __name__ == "__main__":
    sys.exit(main())
