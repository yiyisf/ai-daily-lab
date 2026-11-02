"""玩具实验：用「按张量名重新生成」识别伪造的模型权重。

思路来自 CellCog 对 Hugging Face 上「14T Mythos 泄露」仓库的核查：
那份权重的每个张量都能用「张量名 → SHA-256 → 作为 PCG64 种子 → 正态分布 → 缩放 → 舍入到 bfloat16」重新生成。
原文没有给出哈希转种子的具体字节用法和缩放系数，本实验自己选了一种（见 seed_from_name），
只演示检测方法本身，不下载、不复现那个仓库。
"""
import hashlib
import sys

import numpy as np


def seed_from_name(name: str, algo: str = "sha256") -> int:
    # 假设：取哈希摘要前 8 字节（小端）作为种子。真实仓库的细节以原文为准。
    digest = hashlib.new(algo, name.encode()).digest()
    return int.from_bytes(digest[:8], "little")


def to_bf16(x: np.ndarray) -> np.ndarray:
    """把 float32 按「就近舍入」截成 bfloat16 精度，再转回 float32 方便计算。"""
    u = x.astype(np.float32).view(np.uint32)
    rounding = ((u >> 16) & 1) + 0x7FFF
    u = ((u + rounding) >> 16) << 16
    return u.astype(np.uint32).view(np.float32)


def fake_tensor(name, shape, scale=0.02, algo="sha256"):
    rng = np.random.Generator(np.random.PCG64(seed_from_name(name, algo)))
    return to_bf16(rng.standard_normal(shape) * scale)


def trained_like_tensor(name, shape, rng):
    """模拟训练过的权重：norm 权重围绕 1 分布，其他矩阵带低秩结构。"""
    if "norm" in name:
        return to_bf16(1.0 + 0.1 * rng.standard_normal(shape))
    rows, cols = shape
    a = rng.standard_normal((rows, 4))
    b = rng.standard_normal((4, cols))
    return to_bf16(0.02 * (a @ b) / 2 + 0.005 * rng.standard_normal(shape))


def sign_match(name, tensor):
    """按张量名重新生成，比较符号一致的比例（与缩放系数无关）。"""
    regen = fake_tensor(name, tensor.shape, scale=1.0)
    return float(np.mean(np.sign(regen) == np.sign(tensor)))


SHAPES = {
    "model.layers.0.input_layernorm.weight": (256,),
    "model.layers.0.self_attn.q_proj.weight": (64, 128),
    "model.layers.0.mlp.down_proj.weight": (128, 64),
    "model.layers.1.post_attention_layernorm.weight": (256,),
    "model.layers.1.self_attn.o_proj.weight": (96, 96),
    "lm_head.weight": (100, 64),
}
THRESHOLD = 0.99


def main():
    rng = np.random.default_rng(20261103)
    fake = {n: fake_tensor(n, s) for n, s in SHAPES.items()}
    trained = {n: trained_like_tensor(n, s, rng) for n, s in SHAPES.items()}
    other_recipe = {n: fake_tensor(n, s, algo="md5") for n, s in SHAPES.items()}

    results = {}
    for label, ckpt in [("伪造（同一配方）", fake), ("模拟训练权重", trained), ("伪造（换了哈希）", other_recipe)]:
        scores = {n: sign_match(n, t) for n, t in ckpt.items()}
        flagged = [n for n, v in scores.items() if v >= THRESHOLD]
        results[label] = (scores, flagged)
        print(f"== {label}: {len(flagged)}/{len(scores)} 个张量被判为可按名重新生成")
        for n, v in scores.items():
            print(f"   {n:<50} 符号一致 {v * 100:6.2f}%")

    fake_scores, fake_flagged = results["伪造（同一配方）"]
    tr_scores, tr_flagged = results["模拟训练权重"]
    oth_scores, oth_flagged = results["伪造（换了哈希）"]

    norm_names = [n for n in SHAPES if "norm" in n]
    fake_norm_mean = float(np.mean([fake[n].mean() for n in norm_names]))
    trained_norm_mean = float(np.mean([trained[n].mean() for n in norm_names]))

    checks = [
        (len(fake_flagged) == len(SHAPES), "同一配方伪造的全部张量都能按名重新生成（舍入到 bf16 后符号仍一致）"),
        (len(tr_flagged) == 0, "模拟训练权重没有任何张量被误判"),
        (len(oth_flagged) == 0, "换一种哈希的伪造权重查不出来：此方法只能证伪，不能证明权重是真的"),
        (abs(fake_norm_mean) < 0.01 and trained_norm_mean > 0.5,
         "辅助线索：伪造的 norm 权重均值接近 0，训练过的 RMSNorm 权重通常围绕 1"),
    ]
    ok = True
    for passed, desc in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {desc}")
        ok &= passed

    print(f"METRIC: 同配方伪造 平均符号一致率 = {np.mean(list(fake_scores.values())) * 100:.2f} %")
    print(f"METRIC: 模拟训练权重 平均符号一致率 = {np.mean(list(tr_scores.values())) * 100:.2f} %")
    print(f"METRIC: 换哈希伪造 平均符号一致率 = {np.mean(list(oth_scores.values())) * 100:.2f} %")
    print(f"METRIC: 伪造 norm 权重均值 = {fake_norm_mean:.4f}")
    print(f"METRIC: 训练 norm 权重均值 = {trained_norm_mean:.4f}")

    if ok:
        print("RESULT: 知道生成配方时，按张量名重新生成能一眼识破伪造权重；配方一变就失效，最终仍要靠厂商一手确认")
    else:
        print("RESULT: 部分检查未通过，见上方 [FAIL]")
        sys.exit(1)


if __name__ == "__main__":
    main()
