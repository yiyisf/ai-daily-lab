"""玩具实验：检查 AGENTS.md 里引用的路径和命令是否已经过期。

不调用模型、不访问网络，只用 Python 标准库。
在临时目录里构造一个小仓库，其 AGENTS.md 里有 3 条已经过期的说明
（对应论文 arXiv:2611.09802 研究的三类：测试命令、代码位置、新增组件的流程），
再写一个最小检查器，看能否把它们找出来、并给出可能的新位置。
"""
import json
import os
import re
import sys
import tempfile

AGENTS_MD = """# 项目说明（给编码 Agent）

## 运行测试
- 单元测试：`npm run test:unit`
- 代码检查：`npm run lint`

## 代码位置
- 通用按钮组件在 `src/components/Button.tsx`，新页面请复用它
- 接口封装在 `src/api/user.ts`
- 路由表在 `src/router/index.ts`

## 新增组件的流程
1. 运行 `scripts/new-component.sh 组件名` 生成模板
2. 在 `src/ui/index.ts` 里导出
3. 补一个故事文件到 `stories/` 目录
"""

PACKAGE_JSON = {
    "name": "demo-admin",
    "scripts": {"test": "vitest run", "lint": "eslint src", "gen:component": "plop component"},
}

FILES = [
    "src/ui/Button.tsx",          # 按钮组件已从 components 挪到 ui
    "src/ui/index.ts",
    "src/api/user.ts",
    "src/router/index.ts",
    "stories/Button.stories.tsx",
    "plopfile.js",                # 生成脚本已换成 plop，旧 shell 脚本删除
]

# 构造时就知道的「真相」：哪些引用已经过期
EXPECTED_STALE = {"npm run test:unit", "src/components/Button.tsx", "scripts/new-component.sh"}

PATH_RE = re.compile(r"`([A-Za-z0-9_.\-/]+/[A-Za-z0-9_.\-/]*)`")
NPM_RE = re.compile(r"`npm run ([A-Za-z0-9:_\-]+)`")
SCRIPT_RE = re.compile(r"`((?:\./)?[A-Za-z0-9_.\-/]+\.(?:sh|py|js))(?:\s[^`]*)?`")


def build_repo(root):
    for rel in FILES:
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("// demo\n")
    with open(os.path.join(root, "package.json"), "w", encoding="utf-8") as f:
        json.dump(PACKAGE_JSON, f)
    with open(os.path.join(root, "AGENTS.md"), "w", encoding="utf-8") as f:
        f.write(AGENTS_MD)


def all_files(root):
    out = []
    for d, _, names in os.walk(root):
        for n in names:
            out.append(os.path.relpath(os.path.join(d, n), root).replace(os.sep, "/"))
    return out


def check(root):
    text = open(os.path.join(root, "AGENTS.md"), encoding="utf-8").read()
    scripts = json.load(open(os.path.join(root, "package.json"), encoding="utf-8"))["scripts"]
    files = all_files(root)
    refs, stale = [], []

    for name in NPM_RE.findall(text):
        ref = f"npm run {name}"
        refs.append(ref)
        if name not in scripts:
            # 按名字前缀找相近的脚本作为建议
            prefix = name.split(":")[0]
            hint = [s for s in scripts if s.split(":")[0] == prefix]
            stale.append((ref, "package.json 里没有这个脚本", hint))

    seen = set()
    for m in list(SCRIPT_RE.findall(text)) + list(PATH_RE.findall(text)):
        ref = m.rstrip("/")
        if ref in seen or ref.startswith("npm"):
            continue
        seen.add(ref)
        refs.append(ref)
        if not os.path.exists(os.path.join(root, ref)):
            base = os.path.basename(ref)
            hint = [f for f in files if os.path.basename(f) == base]
            stale.append((ref, "路径不存在", hint))
    return refs, stale


def main():
    with tempfile.TemporaryDirectory() as root:
        build_repo(root)
        refs, stale = check(root)

    print("== AGENTS.md 中提取到的引用 ==")
    for r in refs:
        print("  ", r)
    print("\n== 判定为过期的引用 ==")
    for ref, why, hint in stale:
        print(f"   {ref}  ->  {why}；可能的新位置：{hint or '无'}")

    found = {s[0] for s in stale}
    hints = {s[0]: s[2] for s in stale}
    tp = len(found & EXPECTED_STALE)
    fp = len(found - EXPECTED_STALE)

    print()
    print(f"METRIC: 提取到的引用 = {len(refs)} 条")
    print(f"METRIC: 判定过期 = {len(found)} 条")
    print(f"METRIC: 正确找出的过期引用 = {tp} 条")
    print(f"METRIC: 误报 = {fp} 条")

    checks = [
        (tp == len(EXPECTED_STALE), "三条过期说明（测试命令、代码位置、生成脚本）全部找出"),
        (fp == 0, "仍然有效的路径和命令没有被误报"),
        (hints.get("src/components/Button.tsx") == ["src/ui/Button.tsx"], "挪走的按钮组件能按文件名给出新位置 src/ui/Button.tsx"),
        (hints.get("npm run test:unit") == ["test"], "改名的测试命令能按前缀提示现有脚本 test"),
        (hints.get("scripts/new-component.sh") == [], "换了实现方式的生成脚本给不出建议，只能人工确认"),
    ]
    ok = True
    print()
    for passed, desc in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {desc}")
        ok = ok and passed
    print()
    if ok:
        print(f"RESULT: 纯文本检查在构造仓库里找出全部 {tp} 条过期引用、0 误报，其中 {sum(1 for h in hints.values() if h)} 条能给出候选，其余需人工改")
    else:
        print("RESULT: 检查结果与预期不符，见上方 FAIL 项")
        sys.exit(1)


if __name__ == "__main__":
    main()
