# 排查 site-packages 里会在 Python 启动时执行的代码

## 目的

据 [StepSecurity 的分析](https://www.stepsecurity.io/blog/litellm-1-107-0-compromised-pypi-backdoored-wheels-credential-stealer)，LiteLLM 1.107.0 的恶意 wheel 会向 site-packages 写入 `cook.pth`、`cook.py` 和 `sitecustomize.py`。Python 的 `site` 模块在每次启动时会执行 `.pth` 文件中以 `import` 开头的行，也会自动导入 `sitecustomize`，所以**不需要 `import litellm`，只要启动解释器**，窃密代码就会运行。

本实验写一个只用标准库的最小扫描器，演示如何把这类「启动钩子」找出来，并说明为什么不能简单地把所有 import 型 `.pth` 都当成恶意。

## 步骤

1. 在临时目录中生成三个样例 site-packages：
   - `clean`：只有路径型 `.pth`（不执行代码）
   - `tooling`：另有一个与 setuptools `distutils-precedence.pth` 同类的 import 行——合法，但确实会在启动时执行
   - `poisoned`：再加上与公开 IoC 同名的 `cook.pth` / `cook.py` 和一个 `sitecustomize.py`（内容均为无害占位）
2. 扫描规则：
   - 与公开 IoC 文件名或 SHA-256 一致 → `CRITICAL`
   - `sitecustomize.py` / `usercustomize.py`、`.pth` 中的 `import` 行 → `REVIEW`（需要人工确认来源）
3. 断言三个样例的分类数量符合预期
4. 附加：扫描当前解释器真实的 site-packages，只打印不断言

运行：

```bash
python main.py
```

程序最后输出 `RESULT: ...`，任一样例分类错误时以非零状态退出。

## 预期结果

- `clean`：0 条
- `tooling`：0 条严重、1 条待复核（说明合法工具也会用 import 型 `.pth`，规则只能提示复核）
- `poisoned`：2 条严重、2 条待复核

注：公开报告中 Linux/macOS 版 `cook.pth` 的哈希恰好与只含一行 `import cook` 的文件一致，所以样例中的 `cook.pth` 会按哈希命中——这也说明恶意 `.pth` 本身可以非常短，真正的载荷在被导入的模块里。

## 局限与可以继续尝试

- 只看文件名、哈希和 import 行，**不分析被导入模块的内容**；攻击者换个文件名就能绕过 IoC 匹配，`REVIEW` 项仍需人工判断
- 没有检查 `*.dist-info/RECORD` 中文件与包的归属关系，可以扩展为「找出不属于任何已安装包记录的启动钩子」
- 真正的应急处置还需要：结束后台进程、轮换凭据、封禁相关域名，见原报告

## 内网复现

- **无需任何第三方依赖**，只用 Python 3.8+ 标准库，无需联网，可直接在内网运行
- 把 `main.py` 拷贝到内网机器执行 `python main.py`；扫描某个虚拟环境时，用该环境的解释器运行即可
- IoC 列表来自公开报告，如需更新需要外网查阅；也可以在内网把哈希清单维护成单独文件
