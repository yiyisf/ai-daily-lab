# 无第三方依赖：只需要 Python 3 标准库
"""「改了更好才收」：用确定性检查器把关自动修复。

受 IBM Research Palette 文章中 check-and-repair harness 的启发：渲染后用几何检查器
找出重叠、越界的文本框，交给编辑模型重写，但只有检查器确认变好了才采用。

本实验不调用任何模型。用固定随机种子生成一批「幻灯片」（若干文本框），
用一个会随机改动的「编辑器」模拟不可靠的修复，比较三种策略：
  - none：   不修复
  - blind：  编辑器给什么就收什么（最多 3 轮）
  - guarded：只有问题数下降才采用（最多 3 轮）
完全离线，运行时间不到 1 秒。
"""
import random
import sys

W, H = 100, 56          # 画布大小（16:9）
N_SLIDES = 300
ROUNDS = 3
SEED = 20261105


def make_slide(rng):
    """生成一页：3-6 个文本框，部分故意摆得过大或靠边，制造问题。"""
    boxes = []
    for _ in range(rng.randint(3, 6)):
        w = rng.randint(15, 45)
        h = rng.randint(6, 16)
        x = rng.randint(0, W - 10)
        y = rng.randint(0, H - 4)
        boxes.append((x, y, w, h))
    return boxes


def overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def issues(boxes):
    """检查器：越界框数 + 重叠框对数。"""
    out = sum(1 for (x, y, w, h) in boxes if x < 0 or y < 0 or x + w > W or y + h > H)
    ov = sum(1 for i in range(len(boxes)) for j in range(i + 1, len(boxes)) if overlap(boxes[i], boxes[j]))
    return out + ov


def editor(boxes, rng):
    """不可靠的编辑器：挑一个框随机挪动或缩放，可能修好，也可能改坏。"""
    new = list(boxes)
    k = rng.randrange(len(new))
    x, y, w, h = new[k]
    if rng.random() < 0.5:
        x += rng.randint(-25, 25)
        y += rng.randint(-15, 15)
    else:
        w = max(5, w + rng.randint(-15, 10))
        h = max(3, h + rng.randint(-6, 4))
    new[k] = (x, y, w, h)
    return new


def run(strategy, slides, seed):
    rng = random.Random(seed)
    finals = []
    for boxes in slides:
        cur = list(boxes)
        for _ in range(ROUNDS):
            if strategy == "none" or issues(cur) == 0:
                break
            cand = editor(cur, rng)
            if strategy == "blind" or issues(cand) < issues(cur):
                cur = cand
        finals.append(cur)
    return finals


def main():
    rng = random.Random(SEED)
    slides = [make_slide(rng) for _ in range(N_SLIDES)]
    before = [issues(s) for s in slides]
    flagged = sum(1 for b in before if b > 0)

    results = {}
    for name in ("none", "blind", "guarded"):
        finals = run(name, slides, SEED + 1)
        after = [issues(s) for s in finals]
        results[name] = {
            "total": sum(after),
            "clean": sum(1 for a in after if a == 0),
            "worse": sum(1 for b, a in zip(before, after) if a > b),
            "better": sum(1 for b, a in zip(before, after) if a < b),
        }

    print(f"幻灯片 {N_SLIDES} 页，检查器标出问题的 {flagged} 页，修复前问题总数 {sum(before)}")
    print(f"{'策略':<8}{'问题总数':>8}{'无问题页':>8}{'变好页':>8}{'变坏页':>8}")
    for name, r in results.items():
        print(f"{name:<10}{r['total']:>8}{r['clean']:>10}{r['better']:>9}{r['worse']:>9}")
    print()

    checks = [
        ("guarded 策略没有让任何一页变坏", results["guarded"]["worse"] == 0),
        ("guarded 的问题总数低于不修复", results["guarded"]["total"] < results["none"]["total"]),
        ("guarded 的问题总数不高于 blind", results["guarded"]["total"] <= results["blind"]["total"]),
        ("blind 策略至少让一页变坏（编辑器确实不可靠）", results["blind"]["worse"] > 0),
    ]
    failed = 0
    for desc, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {desc}")
        failed += 0 if ok else 1
    print()

    for name in ("none", "blind", "guarded"):
        print(f"METRIC: {name} 问题总数 = {results[name]['total']} 个")
    for name in ("blind", "guarded"):
        print(f"METRIC: {name} 变坏页数 = {results[name]['worse']} 页")
    for name in ("blind", "guarded"):
        print(f"METRIC: {name} 变好页数 = {results[name]['better']} 页")

    r_b, r_g = results["blind"], results["guarded"]
    print(
        f"RESULT: 同一个不可靠的编辑器，照单全收时 {r_b['worse']} 页被改坏、剩 {r_b['total']} 个问题；"
        f"只收检查器确认变好的修改时 {r_g['worse']} 页变坏、剩 {r_g['total']} 个问题"
    )
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
