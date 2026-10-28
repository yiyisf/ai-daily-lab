"""
离线玩具模型：复现「被拒绝的超长请求仍进入 decode」这一类 KV 缓存跨请求泄露，
并对比三种修复：引擎在入口按 rejected 拦截、把 KV 池扩到不小于上下文长度、用 canary 检测输出。

这不是 SGLang 的代码，只是按 Cloudflare 事故复盘中描述的机制写的最小模拟。
完全离线、只用标准库。
"""
import random
import sys

CONTEXT_LEN = 1024          # 对外声明的上下文长度（按比例缩小）
POOL_SMALL = 665            # 约为上下文长度的 0.65 倍，对应复盘里 681,280 / 1,048,576
POOL_LARGE = 2 * CONTEXT_LEN  # 复盘里修复后的做法：池子约为上下文长度的两倍
N_REQUESTS = 400
SEED = 20261029


class KVPool:
    """按 token 槽位记录「这个槽位里是谁的数据」。释放时不清零，模拟页面被复用前仍留着旧数据。"""

    def __init__(self, size):
        self.size = size
        self.owner = [None] * size
        self.cursor = 0

    def alloc(self, n):
        # 环形分配：从 cursor 开始取 n 个槽位
        slots = [(self.cursor + i) % self.size for i in range(n)]
        self.cursor = (self.cursor + n) % self.size
        return slots

    def write(self, slots, rid):
        for s in slots:
            self.owner[s] = rid


def run(pool_size, engine_fix, requests):
    """返回每个请求的 (http_status, 读到的数据归属集合)。"""
    pool = KVPool(pool_size)
    results = {}
    for rid, length in requests:
        if length > CONTEXT_LEN:
            results[rid] = (400, set())          # 网关按声明的上下文长度拒绝
            continue
        rejected = length > pool.size             # prefill 节点放不下
        if rejected:
            if engine_fix:
                # 修复：在入口按 rejected 直接返回错误，不做任何 KV 传输
                results[rid] = (400, set())
                continue
            # 缺陷路径：换成 1 个 token 的占位，标记 finished=True、rejected=True
            placeholder = pool.alloc(1)
            pool.write(placeholder, rid)
            finished = True
            # 入口只检查 finished，于是请求被放行到 decode；
            # decode 按原始长度读取页面，读到的是池子里残留的旧数据
            if finished:
                slots = [(placeholder[0] + i) % pool.size for i in range(min(length, pool.size))]
                seen = {pool.owner[s] for s in slots if pool.owner[s] is not None}
                results[rid] = (200, seen)
            continue
        slots = pool.alloc(length)
        pool.write(slots, rid)
        seen = {pool.owner[s] for s in slots}
        results[rid] = (200, seen)
    return results


def leaked(results):
    return sorted(rid for rid, (status, seen) in results.items() if status == 200 and seen - {rid})


def status_only_test(results):
    """只看状态码的测试：所有可服务长度的请求都返回 200 就算通过。"""
    return [rid for rid, (status, _) in results.items() if status != 200 and status != 400]


def canary_test(results):
    """canary 测试：每个请求写入自己的标记，输出里出现别人的标记就报警。"""
    return [rid for rid, (status, seen) in results.items() if status == 200 and seen - {rid}]


def main():
    rng = random.Random(SEED)
    # 大部分请求较短，少量接近上下文上限，模拟「看起来像正常长上下文使用」
    requests = []
    for rid in range(N_REQUESTS):
        if rng.random() < 0.1:
            length = rng.randint(600, CONTEXT_LEN)
        else:
            length = rng.randint(20, 300)
        requests.append((rid, length))
    over_pool = sum(1 for _, l in requests if POOL_SMALL < l <= CONTEXT_LEN)

    configs = [
        ("小池子 + 原始引擎", POOL_SMALL, False),
        ("小池子 + 引擎修复", POOL_SMALL, True),
        ("大池子 + 原始引擎", POOL_LARGE, False),
        ("大池子 + 引擎修复", POOL_LARGE, True),
    ]
    ok = True
    print(f"请求数 {N_REQUESTS}，其中长度超过小池子但未超过上下文长度的 {over_pool} 个")
    leak_counts = {}
    for name, size, fix in configs:
        res = run(size, fix, requests)
        lk = leaked(res)
        leak_counts[name] = len(lk)
        print(f"METRIC: 泄露响应数（{name}） = {len(lk)} 个")

    base = run(POOL_SMALL, False, requests)
    base_leaks = leaked(base)
    status_alerts = status_only_test(base)
    canary_alerts = canary_test(base)
    print(f"METRIC: 只看状态码的测试报警数 = {len(status_alerts)} 个")
    print(f"METRIC: canary 测试报警数 = {len(canary_alerts)} 个")

    def check(cond, msg):
        nonlocal ok
        print(("[PASS] " if cond else "[FAIL] ") + msg)
        ok = ok and cond

    check(over_pool > 0 and leak_counts["小池子 + 原始引擎"] > 0,
          "池子小于上下文长度且引擎只查 finished 时，会出现返回 200 但带着别人数据的响应")
    check(all(base[r][0] == 200 for r in base_leaks),
          "泄露的响应全部是 HTTP 200，只看状态码发现不了")
    check(len(status_alerts) == 0, "只看状态码的测试全部通过（这正是问题所在）")
    check(sorted(canary_alerts) == base_leaks, "canary 测试能找出每一条泄露的响应")
    check(leak_counts["小池子 + 引擎修复"] == 0, "引擎在入口按 rejected 拦截后，不再泄露")
    check(leak_counts["大池子 + 原始引擎"] == 0, "池子不小于上下文长度时，拒绝路径根本走不到")
    check(POOL_LARGE >= CONTEXT_LEN and POOL_SMALL < CONTEXT_LEN,
          "启动时检查「KV 池容量 ≥ 上下文长度」能提前发现小池子配置")

    if ok:
        print("RESULT: 玩具模型中泄露只发生在「池子小于上下文 + 引擎只查 finished」的组合，状态码测试全过而 canary 测试全部抓到")
        return 0
    print("RESULT: 有检查未通过，见上方 [FAIL]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
