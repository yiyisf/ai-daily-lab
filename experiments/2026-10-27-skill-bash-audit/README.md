# 离线审查 SKILL.md：找出不受限 Bash 授权并给出收窄规则

## 目的

[agent-skills-state-2026](https://github.com/alexar76/agent-skills-state-2026) 的 10 月 26 日跟进报告 [Skills with unscoped Bash](https://github.com/alexar76/agent-skills-state-2026/blob/main/docs/skills-with-unscoped-bash.md) 分析了在 `allowed-tools` 里申请裸 `Bash` 或 `Bash(*)` 的公开技能，发现不少授权根本没用上，用到的命令也往往只有几条。报告建议：没有命令和脚本的技能直接删掉 Bash；其余改成只允许文档中出现的命令，例如 `Bash(git status:*)`。

本实验把这几条建议写成一个只用正则和 YAML 解析的小审查器，在 8 个脚本内置的 mock 技能上跑一遍，看它能否：

1. 识别前言（front matter）缺失或无法解析，例如 `description: Use when: ...` 这种未加引号的冒号
2. 区分不受限授权（`Bash`、`Bash(*)`）和已收窄的授权（`Bash(git status:*)`）
3. 找出「申请了 Bash，但正文没有 shell 命令、也不带脚本」的技能
4. 标记较高风险命令：管道下载到 shell、直接 HTTP、安装包、递归删除、`eval`、推送/发布、`sudo`、读取 `.env` 等
5. 按正文命令给出收窄后的 `Bash(命令:*)` 规则，并检查这些规则覆盖了每一条命令

注意：风险规则是本实验自己写的近似版本，不是报告原文的 9 条规则；样本是人工构造的 mock 数据，**不复现报告中的任何数字**。

## 步骤

```bash
pip install -r requirements.txt
python main.py
```

程序打印每个技能的审查结论、`[PASS]/[FAIL]` 检查、`METRIC:` 指标和最后一行 `RESULT:`，任一检查失败时以非零状态退出。

## 预期结果

- 8 个 mock 技能的判定都与脚本里人工写定的期望标签一致
- `bad-yaml` 被判为前言解析失败，`no-frontmatter` 被判为缺少前言
- `unused-bash` 被判为授权未用上，建议直接删除 Bash
- 其余不受限授权都能给出收窄规则，且规则覆盖正文中的全部命令

## 启示与可以继续尝试

- 把团队已装技能的 `SKILL.md` 内容替换进 `SKILLS`，看看有多少授权可以删掉或收窄
- 收窄建议只按命令的前一两个词生成；像 `eval`、`sudo`、管道下载这类命令，更合适的做法是改写技能本身，而不是把它们加进白名单
- 报告提醒：审查只看页面和技能目录里的脚本，Agent 运行时可能执行别的命令；技能目录外的脚本也要读
- 宿主对 `allowed-tools` 的写法（逗号分隔字符串或列表）可能不同，以所用 Agent 的文档为准

## 内网复现

- 依赖只有 `PyYAML`，可通过内网 PyPI 镜像安装：`pip install -i <内网镜像地址> -r requirements.txt`
- 程序完全离线运行，不访问任何网络，也不需要 API key
- 如果内网镜像没有 PyYAML，可以把审查器里的 `yaml.safe_load` 换成只解析 `key: value` 的简单实现，但这样就测不出「未加引号的冒号」这类前言错误
- 报告原文和数据集在 GitHub 上，需要外网或内网 Git 镜像获取；本实验不依赖它们
