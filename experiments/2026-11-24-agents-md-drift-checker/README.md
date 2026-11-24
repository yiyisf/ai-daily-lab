# AGENTS.md 路径声明与依赖规则静态一致性校验器

复现论文 [*Does the Agent's Map Match the Territory?*](https://arxiv.org/abs/2611.29916) 的核心工程发现：在 3,346 个开源项目的上下文文件（`AGENTS.md` / `CLAUDE.md`）中，路径声明大概率准确（错误率约 2.2%），但依赖规则有 **18%** 在写下当天就已被存量代码打破——上下文文件写的是「团队理想中的架构」，而不是「代码库真实的样子」。

本实验提供一个纯 Python 标准库静态校验原型，用来在 CI 或提 PR 前自动把 `AGENTS.md` 中的**路径声明（Map）**和**依赖规则（Rulebook）**编译成可执行检查，防止编码 Agent 被过期文档误导。

## 实验内容

1. **解析 `AGENTS.md` 两类架构声明**：
   - 路径声明：从项目结构段落提取反引号包裹的文件/目录路径（如 `` `src/server/routes/` ``）。
   - 三类依赖规则：
     - `Never import from '<target>' in '<scope>'`（禁止特定目录导入目标模块）
     - `Only '<scope>' may import '<target>'`（仅允许白名单目录导入某库/模块）
     - `Do not import '<target>'`（全仓禁止导入已弃用依赖）
2. **基于 `ast` 的真实导入扫描**：在临时目录构造包含正常代码、失效路径与存量违规导入的合成 Python 仓库，用标准库 `ast` 精准解析 `import` / `from ... import ...` 语句（避免注释或字符串误报）。
3. **一致性比对与指标断言**：核对检测到的路径失效数与依赖违规数是否与预设真值 100% 匹配（精确率 1.0、召回率 1.0、误报 0）。

## 内网复现

本实验完全离线，仅依赖 Python 3.10+ 标准库，无需安装任何第三方依赖或访问外网：

```bash
cd experiments/2026-11-24-agents-md-drift-checker
python3 main.py
```

如需在团队内网仓库直接复用，可将 `check_repository(repo_root, agents_md_text)` 接入 `pre-commit` 或 GitLab CI，每次修改 `AGENTS.md` 或移动目录时自动校验文档与代码是否同步。
