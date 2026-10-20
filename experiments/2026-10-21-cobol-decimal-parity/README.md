# COBOL 截断 vs 四舍五入：迁移后逐字节对比

## 目的

OpenAI 在 [Advancing coding in low-resource programming languages](https://openai.com/index/low-resource-programming-languages/) 中介绍了一个 COBOL 迁移评测：隐藏测试要求迁移后的程序在可观察输出上**逐字节一致**，全部通过才算成功。文中举例：COBOL 的定点运算默认会截断多余的小数位，除非显式要求四舍五入（`ROUNDED`）；改写成四舍五入的版本能正常运行，却会算出不同的金额。

本实验用 Python 标准库 `decimal` 复现这个陷阱，直观感受「能跑」和「行为等价」之间的差距，以及逐字节对比为什么能抓住它。

注意：参考实现、数据和报表格式都是本实验自拟的简化版本，**不是** OpenAI 评测中的程序或测试。

## 步骤

1. 用 `ROUND_DOWN` 模拟 COBOL 不带 `ROUNDED` 的 `COMPUTE`（目标字段两位小数），作为参考实现
2. 准备三种「迁移后」的写法：保留截断、改为四舍五入（`ROUND_HALF_UP`）、改用浮点数再格式化
3. 用确定性伪随机数生成 1000 个账户，把结果输出成定长报表，与参考实现逐字节比较
4. 检查：截断写法必须完全一致；四舍五入写法必须被发现不一致，且总金额偏高

运行：

```bash
python main.py
```

程序最后输出 `RESULT: ...`，任一检查失败时以非零状态退出。

## 预期结果

- `truncate`：逐字节一致，差异行数为 0
- `round_half_up`、`float`：程序都能正常跑完，但有相当比例的行相差 1 分钱，单笔差异小、累计起来不可忽略

## 局限与可以继续尝试

- 真实 COBOL 还涉及 `COMP-3` 打包十进制、符号位、溢出截断（`ON SIZE ERROR`）等，本实验只模拟了小数截断一点
- 可以把同样的逐字节对比思路用到自己的迁移项目：先用旧系统跑一批真实输入固定「黄金输出」，再让 AI 迁移后的程序对照
- 可以尝试让手头的编码 Agent 把 `cobol_reference` 翻译成其他语言，看它是否保留了截断语义

## 内网复现

- **无需任何第三方依赖**，只用 Python 3.8+ 标准库（`decimal`），无需联网，可直接在内网运行
- 把 `main.py` 拷贝到内网机器执行 `python main.py` 即可
- 如需参考 OpenAI 公开的 MultiLangBench（github.com/openai/MultiLangBench），需要外网或内网的 GitHub 镜像；没有镜像时本实验不受影响
