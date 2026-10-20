"""Structure figures for items (`item.figure`): rendered at build time as HTML for the site
and as Markdown for wiki packages. Two types:

- steps: 2–5 steps in order, optional loop back to step 1, optional shared base
- bars:  1–2 series of numbers per row (e.g. old vs new version), common scale
"""
from __future__ import annotations

from html import escape

from markupsafe import Markup

LOOP_ICON = ('<svg class="ic" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
             'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
             '<path d="M19.5 12a7.5 7.5 0 0 1-12.8 5.3"/><path d="M4.5 12a7.5 7.5 0 0 1 12.8-5.3"/>'
             '<path d="M17.5 3.5v3.3h-3.3M6.5 20.5v-3.3h3.3"/></svg>')


def fmt(v: float) -> str:
    if isinstance(v, float):
        return repr(v)
    return str(v)


def decimals(v: float) -> int:
    s = fmt(v)
    return len(s.split(".")[1]) if "." in s else 0


def delta(a: float, b: float) -> str:
    d = round(b - a, max(decimals(a), decimals(b)))
    places = max(decimals(a), decimals(b))
    s = f"{abs(d):.{places}f}"
    return ("+" if d > 0 else "−" if d < 0 else "±") + s


def _steps_html(fig: dict) -> str:
    out = ['<ol class="fig-flow">']
    for i, s in enumerate(fig["steps"], 1):
        sub = f'<span class="fig-sub">{escape(s["sub"])}</span>' if s.get("sub") else ""
        out.append(f'<li class="fig-step"><span class="fig-n">{i}</span><b>{escape(s["label"])}</b>{sub}</li>')
    out.append("</ol>")
    if fig.get("loop"):
        out.append(f'<div class="fig-loop">{LOOP_ICON}<span>{escape(fig["loop"])}</span></div>')
    if fig.get("base"):
        b = fig["base"]
        sub = f'<span class="fig-sub">{escape(b["sub"])}</span>' if b.get("sub") else ""
        out.append(f'<div class="fig-base"><b>{escape(b["label"])}</b>{sub}</div>')
    return "".join(out)


def _bars_html(fig: dict) -> str:
    series = fig["series"]
    unit = fig.get("unit", "")
    top = max((v for r in fig["rows"] for v in r["values"]), default=0) or 1
    out = []
    if len(series) > 1:
        out.append('<div class="fig-legend">' + "".join(
            f'<span><i class="fig-sw s{i}"></i>{escape(s)}</span>' for i, s in enumerate(series)) + "</div>")
    out.append('<div class="fig-rows">')
    for r in fig["rows"]:
        vals = r["values"]
        bars = "".join(
            f'<span class="fig-bar s{i}" style="--w:{max(v / top * 100, 1.5):.1f}%">'
            f'<em>{fmt(v)}{escape(unit)}</em></span>' for i, v in enumerate(vals))
        d = f'<span class="fig-delta">{delta(vals[0], vals[1])}</span>' if len(vals) == 2 else ""
        label = escape(r["label"])
        aria = escape("，".join(f"{s} {fmt(v)}{unit}" for s, v in zip(series, vals)))
        out.append(f'<div class="fig-row" role="group" aria-label="{label}：{aria}">'
                   f'<span class="fig-label">{label}</span><span class="fig-track">{bars}</span>{d}</div>')
    out.append("</div>")
    return "".join(out)


def figure_html(fig: dict | None) -> Markup:
    if not fig:
        return Markup("")
    body = _steps_html(fig) if fig["type"] == "steps" else _bars_html(fig)
    note = f'<p class="fig-note">{escape(fig["caption"])}</p>' if fig.get("caption") else ""
    return Markup(f'<figure class="fig fig-{fig["type"]}"><figcaption class="fig-title">{escape(fig["title"])}</figcaption>'
                  f'{body}{note}</figure>')


def figure_markdown(fig: dict | None) -> str:
    """Plain Markdown version for wiki packages (no styling dependency)."""
    if not fig:
        return ""
    lines = [f"**图：{fig['title']}**", ""]
    if fig["type"] == "steps":
        for i, s in enumerate(fig["steps"], 1):
            lines.append(f"{i}. **{s['label']}**" + (f" — {s['sub']}" if s.get("sub") else ""))
        if fig.get("loop"):
            lines += ["", f"↻ {fig['loop']}"]
        if fig.get("base"):
            b = fig["base"]
            lines += ["", f"底座：**{b['label']}**" + (f" — {b['sub']}" if b.get("sub") else "")]
    else:
        series, unit = fig["series"], fig.get("unit", "")
        head = ["项目", *series] + (["变化"] if len(series) == 2 else [])
        lines += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        for r in fig["rows"]:
            cells = [r["label"], *[f"{fmt(v)}{unit}" for v in r["values"]]]
            if len(r["values"]) == 2:
                cells.append(delta(*r["values"]))
            lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    if fig.get("caption"):
        lines += ["", f"*{fig['caption']}*"]
    return "\n".join(lines)
