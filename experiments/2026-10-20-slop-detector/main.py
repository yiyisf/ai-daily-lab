#!/usr/bin/env python3
"""最小「AI 腔」(slop) 检测器。

参考 deslop 项目公开的评估思路：用正则规则统计常见的模型写作习惯，
按每 1000 词归一化。规则与权重为本实验自拟，不是原项目的检测器。
样例文本均为本实验自行编写的合成文本。
"""
import re
import sys

RULES = {
    # 名称: (正则, 权重)
    "em_dash": (re.compile(r"—|(?<=\w) -- (?=\w)"), 1.0),
    "not_x_but_y": (re.compile(r"\b(?:it's|it is|this is|that's)?\s*not (?:just |only |merely )?[\w' -]{1,40}?[,;—-]+\s*(?:but|it's|it is)\b", re.I), 2.0),
    "rule_of_three": (re.compile(r"\b\w+, \w+,? and \w+\b"), 0.5),
    "buzzwords": (re.compile(r"\b(?:delve|tapestry|testament|seamless(?:ly)?|leverag(?:e|ing)|landscape|unlock|game[- ]changer|navigate the|in today's fast-paced)\b", re.I), 1.5),
    "hype_opener": (re.compile(r"(?:^|\n)\s*(?:great question|absolutely|certainly)[!,.]", re.I), 2.0),
}


def words(text):
    return re.findall(r"[A-Za-z0-9']+", text)


def score(text):
    n = max(len(words(text)), 1)
    hits = {name: len(rx.findall(text)) for name, (rx, _) in RULES.items()}
    weighted = sum(hits[name] * w for name, (_, w) in RULES.items())
    return weighted * 1000 / n, hits, n


SLOPPY = """Great question! Remote work is not just a trend — it's a fundamental shift.
In today's fast-paced landscape, teams must navigate the challenges of focus, trust, and communication.
It's not about where you work, but how you work. Tools like chat, video, and docs seamlessly connect people —
and that's a game-changer. Ultimately, remote work is a testament to flexibility, resilience, and innovation.
Leveraging the right habits can unlock productivity, creativity, and balance — for everyone."""

PLAIN = """I have worked from home for three years. The first winter was hard because I stopped
leaving the flat, so now I walk to a cafe two mornings a week. My team meets on video at ten.
We write most decisions down in a shared doc, which saves us from repeating the same argument.
The main cost is that new people take longer to learn how things are done here. We pair them with
someone for their first month, and that seems to help. I would not go back to commuting every day."""

# 把 SLOPPY 里的破折号换成句号：只去掉一个表面特征
SLOPPY_NO_DASH = SLOPPY.replace(" — ", ". ").replace(" —\n", ".\n")


def main():
    samples = [("sloppy", SLOPPY), ("sloppy_no_dash", SLOPPY_NO_DASH), ("plain", PLAIN)]
    results = {}
    print(f"{'sample':<16}{'words':>6}{'score/1k':>10}  hits")
    for name, text in samples:
        s, hits, n = score(text)
        results[name] = (s, hits)
        print(f"{name:<16}{n:>6}{s:>10.1f}  {hits}")

    s_sloppy, h_sloppy = results["sloppy"]
    s_nodash, h_nodash = results["sloppy_no_dash"]
    s_plain, _ = results["plain"]

    checks = [
        ("sloppy 得分 > 3 × plain", s_sloppy > 3 * max(s_plain, 1)),
        ("plain 得分 < 15（参考原文所说人类文本通常 <15/千词）", s_plain < 15),
        ("去掉破折号后 em_dash 计数为 0", h_nodash["em_dash"] == 0),
        ("去掉破折号后得分下降，但仍高于 plain", s_plain < s_nodash < s_sloppy),
    ]
    ok = True
    for desc, passed in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {desc}")
        ok &= passed

    print("\n说明：只删破折号这类表面后处理，句式和用词层面的特征仍会被规则捕获。")
    print(f"RESULT: sloppy={s_sloppy:.1f} no_dash={s_nodash:.1f} plain={s_plain:.1f} per 1k words; "
          f"{'all checks passed' if ok else 'some checks failed'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
