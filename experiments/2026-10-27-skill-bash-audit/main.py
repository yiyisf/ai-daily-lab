"""离线审查 SKILL.md：找出不受限的 Bash 授权、没用上的授权和较高风险命令。

规则参考 agent-skills-state-2026 的 10 月 26 日跟进报告（skills-with-unscoped-bash.md）：
- 裸 `Bash` 或 `Bash(*)` 视为不受限；`Bash(git status:*)` 这类视为已收窄
- 正文没有 shell 命令、也不带脚本的技能，Bash 授权等于没用上
- 用正则标记几类较高风险行为

报告原文用 9 条正则规则，这里的规则是本实验自己写的近似版本，样本也是脚本内置的
mock 技能，只演示审查方法，不复现报告中的任何数字。
"""
from __future__ import annotations

import re
import sys

import yaml

# ---------------------------------------------------------------------------
# mock 技能：name -> (SKILL.md 文本, 是否带脚本, 期望标签)
# 期望标签由人工写定，用来检查审查器的判断是否正确
# ---------------------------------------------------------------------------
SKILLS = {
    "scoped-git": (
        """---
name: scoped-git
description: Summarize the working tree before a commit.
allowed-tools: Bash(git status:*), Bash(git diff:*)
---
Run these and summarize:

```bash
git status
git diff --stat
```
""",
        False,
        {"parse": "ok", "grant": "scoped", "risks": set()},
    ),
    "unused-bash": (
        """---
name: unused-bash
description: Review a pull request description for clarity.
allowed-tools: Read, Bash
---
Read the PR description and point out unclear sentences. Suggest a rewrite.
""",
        False,
        {"parse": "ok", "grant": "unscoped", "unused": True, "risks": set()},
    ),
    "formatter": (
        """---
name: formatter
description: Format the project.
allowed-tools: Bash(*)
---
```sh
npx prettier --write .
```
""",
        False,
        {"parse": "ok", "grant": "unscoped", "unused": False, "risks": {"install"}},
    ),
    "release": (
        """---
name: release
description: Build and publish a release.
allowed-tools: [Read, Bash]
---
```bash
rm -rf dist
npm run build
git push origin main --tags
npm publish
```
""",
        False,
        {"parse": "ok", "grant": "unscoped", "unused": False, "risks": {"delete", "publish"}},
    ),
    "bootstrap": (
        """---
name: bootstrap
description: Set up the toolchain on a new machine.
allowed-tools: Bash
---
```bash
curl -fsSL https://example.com/install.sh | sh
sudo cp ./bin/tool /usr/local/bin/
```
""",
        False,
        {"parse": "ok", "grant": "unscoped", "unused": False,
         "risks": {"pipe-shell", "http", "sudo"}},
    ),
    "env-loader": (
        """---
name: env-loader
description: Load environment for local runs.
allowed-tools: Bash
---
```bash
cat .env
eval "$(./scripts/print-env.sh)"
```
""",
        True,
        {"parse": "ok", "grant": "unscoped", "unused": False, "risks": {"credential", "eval"}},
    ),
    "bad-yaml": (
        """---
name: bad-yaml
description: Use when: the user asks for a changelog
allowed-tools: Bash(git log:*)
---
```bash
git log --oneline -20
```
""",
        False,
        {"parse": "error"},
    ),
    "no-frontmatter": (
        """# Notes skill

Write meeting notes in the team template.
""",
        False,
        {"parse": "missing"},
    ),
}

SHELL_LANGS = {"bash", "sh", "shell", "zsh", "console"}
FENCE = re.compile(r"```([A-Za-z0-9_-]*)\n(.*?)```", re.S)

# 本实验的近似规则（不是报告原文的规则）
RISK_RULES = {
    "pipe-shell": re.compile(r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z)?sh\b"),
    "http": re.compile(r"\b(curl|wget)\b|\bhttps?://"),
    "install": re.compile(r"\b(pip|pip3|npm|pnpm|yarn)\s+(install|add)\b|\bnpx\s|\buvx\s|\bapt(-get)?\s+install\b|\bbrew\s+install\b"),
    "delete": re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\b|\bgit\s+reset\s+--hard\b|\bgit\s+clean\s+-[a-zA-Z]*f"),
    "eval": re.compile(r"\beval\b"),
    "publish": re.compile(r"\bgit\s+push\b|\bnpm\s+publish\b|\btwine\s+upload\b"),
    "sudo": re.compile(r"\b(sudo|doas)\b"),
    "credential": re.compile(r"(^|\s)\.env\b|\.aws/credentials|\.netrc\b"),
    "sysconfig": re.compile(r"\s/etc/|\bsystemctl\b"),
}


def split_front_matter(text: str):
    """返回 (状态, 元数据)；状态为 ok / error / missing。"""
    if not text.startswith("---\n"):
        return "missing", None
    end = text.find("\n---", 4)
    if end == -1:
        return "error", None
    try:
        meta = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return "error", None
    return ("ok", meta) if isinstance(meta, dict) else ("error", None)


def tool_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value]
    # 逗号分隔的字符串；括号里的逗号不拆
    return [t.strip() for t in re.split(r",\s*(?![^()]*\))", str(value)) if t.strip()]


def grant_kind(tools: list[str]) -> str:
    bash = [t for t in tools if t == "Bash" or t.startswith("Bash(")]
    if not bash:
        return "none"
    if any(t in ("Bash", "Bash(*)") for t in bash):
        return "unscoped"
    return "scoped"


def shell_lines(text: str) -> list[str]:
    lines = []
    for lang, body in FENCE.findall(text):
        if lang.lower() not in SHELL_LANGS:
            continue
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("$ "):
                line = line[2:]
            if line and not line.startswith("#"):
                lines.append(line)
    return lines


def suggest_rule(line: str) -> str:
    """按命令的前一到两个词给出收窄后的规则。"""
    words = line.split()
    head = words[0]
    if len(words) > 1 and re.fullmatch(r"[a-z][a-z0-9-]*", words[1]):
        head = f"{words[0]} {words[1]}"
    return f"Bash({head}:*)"


def audit(text: str, has_scripts: bool) -> dict:
    status, meta = split_front_matter(text)
    out = {"parse": status}
    if status != "ok":
        return out
    out["grant"] = grant_kind(tool_list(meta.get("allowed-tools")))
    lines = shell_lines(text)
    out["commands"] = sorted({suggest_rule(l) for l in lines})
    out["unused"] = out["grant"] == "unscoped" and not lines and not has_scripts
    joined = "\n".join(lines)
    out["risks"] = {name for name, rx in RISK_RULES.items() if rx.search(joined)}
    return out


def main() -> int:
    results = {name: audit(text, scripts) for name, (text, scripts, _) in SKILLS.items()}
    checks: list[tuple[bool, str]] = []

    for name, (_, _, expect) in SKILLS.items():
        got = results[name]
        ok = all(got.get(k) == v for k, v in expect.items())
        detail = ", ".join(f"{k}={got.get(k)!r}" for k in expect)
        checks.append((ok, f"{name}: {detail}"))

    print("\n== 审查结果 ==")
    for name, r in results.items():
        if r["parse"] != "ok":
            print(f"- {name}: 前言 {r['parse']}，宿主可能读不到技能头部，先修前言")
            continue
        line = f"- {name}: 授权 {r['grant']}"
        if r["unused"]:
            line += "；正文无命令且无脚本 → 建议从副本中删掉 Bash"
        elif r["grant"] == "unscoped":
            line += f"；建议改为 {', '.join(r['commands'])}"
        if r["risks"]:
            line += f"；风险：{', '.join(sorted(r['risks']))}"
        print(line)

    parsed = [r for r in results.values() if r["parse"] == "ok"]
    unscoped = [r for r in parsed if r["grant"] == "unscoped"]
    unused = [r for r in unscoped if r["unused"]]
    used = [r for r in unscoped if not r["unused"]]
    risky = [r for r in unscoped if r["risks"]]
    few = [r for r in used if len(r["commands"]) <= 3]
    total = len(SKILLS)

    # 收窄后的规则应覆盖正文里的每一条命令
    for name, r in results.items():
        if r.get("grant") != "unscoped" or r["unused"]:
            continue
        text = SKILLS[name][0]
        covered = all(
            any(l.startswith(rule[5:-3]) for rule in r["commands"]) for l in shell_lines(text)
        )
        checks.append((covered, f"{name}: 收窄后的规则覆盖了正文中的全部命令"))

    print("\n== 检查 ==")
    for ok, msg in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {msg}")

    print()
    print(f"METRIC: 技能总数 = {total} 个")
    print(f"METRIC: 前言无法解析或缺失 = {total - len(parsed)} 个")
    print(f"METRIC: 不受限 Bash 授权 = {len(unscoped)} 个")
    print(f"METRIC: 授权未用上 = {len(unused)} 个")
    print(f"METRIC: 带较高风险命令 = {len(risky)} 个")
    print(f"METRIC: 不受限授权中未用上的比例 = {100 * len(unused) / len(unscoped):.1f} %")
    print(f"METRIC: 用到的不同命令不超过 3 个的比例 = {100 * len(few) / len(used):.1f} %")

    failed = [m for ok, m in checks if not ok]
    if failed:
        print(f"RESULT: {len(failed)} 项检查未通过，审查规则需要调整")
        return 1
    print(
        f"RESULT: {len(unscoped)} 个不受限 Bash 授权中 {len(unused)} 个可直接删除，"
        f"其余 {len(used)} 个都能收窄到 3 条以内的具体命令规则"
        if len(few) == len(used)
        else f"RESULT: {len(unscoped)} 个不受限 Bash 授权中 {len(unused)} 个可直接删除，其余可按命令收窄"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
