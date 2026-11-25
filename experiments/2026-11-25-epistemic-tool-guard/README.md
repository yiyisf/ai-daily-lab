# Episteme 工具调用意图声明与离线篡改审计原型

复现论文 [*Episteme: Trustworthy Coding Agents Through Tool Call Intent*](https://arxiv.org/abs/2611.06563) 的核心工程设计：传统编码 Agent 的 Shell 工具只收一条 `command` 字符串，既不说明「为什么调用」，也无法在执行后核对「说要做只读探查，结果是不是偷偷改了测试文件」。Episteme 在工具 Schema 强制加入 `type`（受控意图词表）与 `reason` 两个必填字段，配合执行前护栏与执行后工作区快照比对，生成可审计的取证日志（Journal）。

## 实验内容

1. **受控意图词表与在线护栏（Pre-flight Guardrail）**：
   - 将工具调用划分为只读类（`collect-info`、`run-test`、`inspect-diff`）与改态类（`edit-code`、`edit-config`、`test-hypothesis`、`cleanup`）。
   - 执行前校验 `type` 是否在词表内、`reason` 是否非空；对声明为只读但包含明显破坏/原位修改命令（如 `sed -i`、`rm -rf`、重定向写入）的调用直接拒绝。
2. **执行后工作区哈希比对（Post-flight Forensics）**：
   - 在临时目录维护模拟工作区（`src/calc.py` 与受保护测试 `tests/test_calc.py`），记录调用前后的文件 SHA-256。
   - 若声明为只读却发生文件变更，记录 `contradicted`；若修改了受保护的 `tests/` 文件（例如注释掉失败断言以骗过测试），记录 `protected_tamper`。
3. **6 条合成调用验证**：涵盖 2 条合法调用（只读查代码、正常修源码）与 4 条异常/作弊调用（缺意图声明、只读夹带写入、打着假设测试旗号注释断言、直接篡改测试文件），断言检出召回率 100% 且误报为 0。

## 内网复现

本实验完全离线，仅依赖 Python 3.10+ 标准库，无需安装任何第三方依赖或联网：

```bash
cd experiments/2026-11-25-epistemic-tool-guard
python3 main.py
```

团队在自研 MCP Shell 工具或编码 Agent 钩子（如 `PreToolUse` / `PostToolUse`）中，可直接复用 `EpistemicHarness` 的声明校验与前后快照比对逻辑，拦截模型为凑单测通过而偷偷改测试或删断言的行为。
