"""代码地图 vs grep：定位函数定义和调用方时，各要读多少内容。

受论文 How Should Agents See Code?（arXiv:2611.07286）启发：论文发现给编码 Agent 提供
AST、调用图等「仓库地图」后，定位类任务的 token 用量明显下降。

本实验不调用任何模型，只用 Python 标准库：
  1. 用固定种子生成一个模拟仓库（若干模块、函数、相互调用，外加只在注释/字符串里
     提到函数名的「诱饵」文件）
  2. grep 方式：搜函数名，把所有命中的文件整份读进来（模拟 Agent 常见的 grep + cat）
  3. map 方式：用 ast 建一份「定义位置 + 调用边」的代码地图，先读地图里与目标相关的
     条目，再只读目标函数和调用它的函数的源码
比较两种方式读取内容的估算 token 数，以及找到的定义和调用方是否正确。完全离线。
"""
import ast
import random
import sys

SEED = 20261107
N_MODULES = 40
FUNCS_PER_MODULE = 6
N_TARGETS = 8


def approx_tokens(text):
    """粗略估算 token 数：按 4 个字符约 1 个 token。"""
    return max(1, len(text) // 4)


def make_repo(rng):
    """生成 {文件名: 源码}，以及真实的定义位置和调用关系。"""
    names = [f"m{m:02d}_f{f}" for m in range(N_MODULES) for f in range(FUNCS_PER_MODULE)]
    module_of = {n: f"pkg/mod{int(n[1:3]):02d}.py" for n in names}
    callers = {n: set() for n in names}
    repo = {}
    for m in range(N_MODULES):
        path = f"pkg/mod{m:02d}.py"
        lines = [f'"""模块 {m:02d}：模拟业务逻辑。"""', ""]
        for f in range(FUNCS_PER_MODULE):
            name = f"m{m:02d}_f{f}"
            callees = rng.sample([n for n in names if n != name], 2)
            for c in callees:
                callers[c].add(name)
            body = [f"def {name}(x):",
                    f'    """处理步骤 {name}，返回变换后的值。"""',
                    "    total = 0",
                    "    for i in range(3):",
                    "        total += (x + i) * 2",
                    f"    total += {callees[0]}(total) if total < 0 else 0",
                    f"    total += {callees[1]}(total) if total < -1 else 0",
                    "    return total", ""]
            lines.extend(body)
        repo[path] = "\n".join(lines)
    return repo, names, module_of, callers


def add_decoys(rng, repo, targets):
    """诱饵：只在注释、字符串、文档里提到目标函数名的文件。"""
    for k, t in enumerate(targets):
        for j in range(2):
            path = f"docs/notes_{k}_{j}.py"
            filler = "\n".join(f"# 历史说明第 {i} 行：与 {t} 无关的背景描述" if i == 3 else f"# 历史说明第 {i} 行" for i in range(60))
            repo[path] = f'{filler}\nMESSAGE = "旧版曾经调用 {t}，现已废弃"\n'


def grep_locate(repo, target):
    """grep 后把所有命中的文件整份读入，再从中找定义和调用方。"""
    hits = [p for p, src in repo.items() if target in src]
    read = sum(approx_tokens(repo[p]) for p in hits)
    found_def, found_callers = None, set()
    for p in hits:
        tree = ast.parse(repo[p])
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name == target:
                    found_def = p
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call) and getattr(sub.func, "id", None) == target:
                        found_callers.add(node.name)
    return found_def, found_callers, read, len(hits)


def build_map(repo):
    """代码地图：每个函数的定义位置、行号范围和它调用了谁。"""
    defs, calls = {}, {}
    for p, src in repo.items():
        tree = ast.parse(src)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                defs[node.name] = (p, node.lineno, node.end_lineno)
                calls[node.name] = sorted({s.func.id for s in ast.walk(node)
                                           if isinstance(s, ast.Call) and isinstance(s.func, ast.Name)})
    return defs, calls


def map_locate(repo, defs, calls, target):
    """先读地图中相关的行，再只读目标函数和调用方函数的源码。"""
    callers = {f for f, cs in calls.items() if target in cs}
    map_lines = [f"{target} -> {defs[target][0]}:{defs[target][1]}"]
    map_lines += [f"{c} calls {target} @ {defs[c][0]}:{defs[c][1]}" for c in sorted(callers)]
    read = approx_tokens("\n".join(map_lines))
    for f in [target, *callers]:
        p, a, b = defs[f]
        read += approx_tokens("\n".join(repo[p].splitlines()[a - 1:b]))
    return defs[target][0], callers, read


def main():
    rng = random.Random(SEED)
    repo, names, module_of, truth_callers = make_repo(rng)
    targets = rng.sample(names, N_TARGETS)
    add_decoys(rng, repo, targets)
    defs, calls = build_map(repo)
    map_build_tokens = approx_tokens("\n".join(f"{f} {v[0]}:{v[1]} calls {','.join(calls[f])}" for f, v in defs.items()))

    print(f"模拟仓库：{len(repo)} 个文件，{len(names)} 个函数，{N_TARGETS} 个定位目标，每个目标配 2 个诱饵文件")
    print(f"{'目标':<10}{'grep 命中文件':>12}{'grep 读入':>10}{'map 读入':>10}  定义/调用方正确")
    g_total = m_total = 0
    g_ok = m_ok = 0
    decoy_hits = 0
    for t in targets:
        gd, gc, gr, nh = grep_locate(repo, t)
        md, mc, mr = map_locate(repo, defs, calls, t)
        g_good = gd == module_of[t] and gc == truth_callers[t]
        m_good = md == module_of[t] and mc == truth_callers[t]
        g_ok += g_good
        m_ok += m_good
        g_total += gr
        m_total += mr
        decoy_hits += sum(1 for p in repo if p.startswith("docs/") and t in repo[p])
        print(f"{t:<10}{nh:>12}{gr:>10}{mr:>10}  grep={'是' if g_good else '否'} map={'是' if m_good else '否'}")

    saving = 100 * (1 - m_total / g_total)
    print()
    checks = [
        (g_ok == N_TARGETS, f"grep 方式找到全部 {N_TARGETS} 个目标的定义和调用方（{g_ok}/{N_TARGETS}）"),
        (m_ok == N_TARGETS, f"代码地图方式找到全部 {N_TARGETS} 个目标的定义和调用方（{m_ok}/{N_TARGETS}）"),
        (m_total < g_total, f"代码地图方式读入的估算 token 少于 grep 方式（{m_total} < {g_total}）"),
        (decoy_hits == 2 * N_TARGETS, f"grep 命中了全部 {2 * N_TARGETS} 个只在注释/字符串里提到名字的诱饵文件"),
    ]
    failed = 0
    for ok, desc in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {desc}")
        failed += not ok
    print(f"METRIC: grep 方式读入 = {g_total} token")
    print(f"METRIC: 代码地图方式读入 = {m_total} token")
    print(f"METRIC: 建一次完整代码地图 = {map_build_tokens} token")
    print(f"METRIC: 每次定位节省 = {saving:.1f} %")
    print(f"RESULT: {N_TARGETS} 个定位任务两种方式都找对，代码地图方式少读约 {saving:.1f}% 的估算 token（不含建图）")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
