# AgentPRO 风格工作流编译优化与运行时守卫仿真

复现论文 [*AgentPRO: Coordinating Compiler Optimizations for LLM Agent Workflows*](https://arxiv.org/abs/2611.00628) 的核心工程洞察：多轮 Agent 之所以反复重算上下文、烧掉大量 token，是因为传统框架默认「每执行一步工具，都要把结果原封不动塞回 LLM 观测再生成下一步」。但实际上，许多中间值只被后续工具执行需要，并不需要被 LLM 重新观测。

本实验用纯 Python 标准库实现一个精简版工作流编译优化器，验证三件事：
1. **冗余读消除（Redundant Read Elimination）**：在无写入干扰的区间内复用已读取资源，省去重复工具调用与重复上下文注入。
2. **生成区融合（Region Fusion）**：一旦中间冗余读被消除且动作不需要额外观测反馈，相邻的模型生成步骤即可合并为单次 LLM 批处理规划。
3. **运行时状态守卫（Runtime Guard + Fallback）**：执行融合计划前校验资源版本号；若外部并发写入导致版本漂移，自动回退到未融合的安全基线路径，保证最终业务状态 100% 一致。

## 内网复现

本实验完全离线，仅依赖 Python 3.10+ 标准库，无需安装任何第三方依赖或访问模型接口：

```bash
cd experiments/2026-11-26-agent-workflow-compiler-opt
python3 main.py
```

团队在编排固定多步 Agent 流水线（如拉取工单 → 查多份配置 → 批量校验 → 回写状态）时，可直接套用「读缓存 + 独立写动作批处理 + 版本号守卫」模式，在有限上下文窗口下大幅减少重复 prefill 与往返延迟。
