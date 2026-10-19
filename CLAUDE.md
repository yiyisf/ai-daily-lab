# AI Daily Lab — 日报生成规则

本仓库每天由 Claude 定时任务生成一期 AI 日报，经 GitHub Actions 校验、人工审核合并后发布到 GitHub Pages，并同步到内网 wiki。

**你（Claude）每次运行都是全新会话，本文件就是全部规则。** 按下面的流程完成当天的日报。

---

## 一、每日流程

1. **确定日期**：以北京时间（Asia/Shanghai）当天日期为准，记为 `DATE`（如 `2026-10-20`）。
2. **读取近况，用于去重**：
   - 读取 `content/daily/` 下最近 7 期的 JSON，记下已报道的主题与链接。
   - 读取 `config/sources.yaml`，了解建议关注的方向。
3. **自主搜集**：用网页搜索和网页读取，收集过去约 24–48 小时内的 AI 动态。范围不限于 `sources.yaml`，凡是有价值的都可以：
   模型与产品发布、知名开源项目、新工具、业界热议的理念与观点、工程方法与实践、重要论文。
   - 同一主题至少找到一个**一手来源**（官方博客、发布说明、GitHub 仓库、论文页面、作者本人的文章）。社区讨论（HN、Reddit、X 等）只能作为线索或"讨论"类条目的补充来源。
   - **必须实际打开读过原文**再写摘要，不能只依据搜索结果的标题和片段。
4. **筛选**：按下方栏目和数量要求挑选，宁缺毋滥。跟进已报道过的主题，只有出现实质性新进展时才收录，并在 `follow_up_of` 里写上原条目 id。
5. **撰写**：按 `schema/daily.schema.json` 生成 `content/daily/YYYY/DATE.json`。
6. **实验**：从当天条目中挑 0–2 个适合做最小验证的，按第四节编写实验目录。
7. **自检**：运行 `python3 scripts/validate.py content/daily/YYYY/DATE.json`，修到通过为止。
8. **提交**：新建分支 `daily/DATE`，提交并推送，开 PR，标题为 `AI 日报 DATE`，PR 描述写今日导读和条目清单。**不要直接推送到 main。**

如果当天确实没有足够有价值的内容，少收几条也可以，但仍要开 PR，并在 `editor_note` 里说明情况。

---

## 二、栏目与数量

| category | 栏目 | 建议数量 | 收录标准 |
|---|---|---|---|
| `news` | 要闻 | 3–6 | 模型/产品发布、重要公司动态、政策法规 |
| `opensource` | 开源项目 | 2–4 | 新发布或近期快速增长的开源项目、重要版本更新 |
| `tools` | 工具与产品 | 1–3 | 开发者工具、AI 应用、平台功能更新 |
| `ideas` | 理念与讨论 | 1–3 | 业界热议的观点、争论、趋势判断（要写清楚各方观点） |
| `practices` | 方法与实践 | 1–3 | 提示工程、Agent 设计、RAG、评测、工程化落地经验 |
| `research` | 论文 | 1–3 | 有实际影响或方法新颖的论文 |

全天合计 **10–18 条**。`importance`（1–5）按"对一般 AI 从业者的重要程度"打分，5 分每天最多 2 条。

---

## 三、写作规范（硬性规则）

- **只写原文支持的内容。** 数字、版本号、日期、基准分数必须能在 `sources` 中的原文找到。不确定的内容不写。
- **不得编造链接。** `sources[].url` 必须是你实际打开过的页面。
- **语言**：正文使用简体中文；专有名词、项目名、模型名保留英文原文。
- **title**：一句话说清"谁做了什么"，不超过 40 字，不用标题党写法。
- **summary**：2–4 句，交代事实，不夸大。
- **key_points**：2–4 条要点，每条一句。
- **why_it_matters**：1–2 句，说明对从业者的意义或可能用途；保持客观。
- **ideas 类**：要呈现主要的不同观点，不能只写一方。
- **版权**：只写摘要和要点，不大段引用原文；直接引用不超过一句。
- **不涉及任何内部信息**：本仓库公开，不写任何公司或部门内部的内容。
- `id` 格式为 `DATE-短英文slug`，如 `2026-10-20-claude-agent-sdk-v2`，在当期唯一。
- `tags` 从 `config/sources.yaml` 的 `tags` 列表中选 1–4 个；确有需要可以新增，用小写英文短横线格式。

---

## 四、可验证实验

目标：让同事看到一个**真实跑过**的最小示例。实验由 GitHub Actions 执行，你只负责写代码，**不要自己声称结果**。

选题条件：
- 30 分钟内能跑通的最小示例：新库的基本用法、新特性演示、小型评测、方法对比等
- **不需要任何 API key 或付费服务**（Actions 执行环境不提供任何密钥）。需要调用大模型 API 的选题，改用本地小模型、mock 数据或纯离线逻辑来演示；做不到就不选。
- 依赖可以通过 pip 或 npm 安装，运行时间不超过 5 分钟，不需要 GPU

目录结构 `experiments/DATE-slug/`：

```
experiment.json   # 元数据，符合 schema/experiment.schema.json
README.md         # 中文说明：目的、步骤、预期结果、内网复现说明
requirements.txt  # 或 package.json，固定版本号
main.py           # 或 main.js / run.sh，入口在 experiment.json 的 entry 里
```

- `README.md` 必须有"内网复现"一节：依赖如何通过内网镜像安装、哪些步骤需要外网、替代方案。
- **不要创建 `result.json`**，它由 Actions 执行后写入。
- 在日报 JSON 的 `experiments` 数组里引用实验 id，并在对应条目的 `experiment_id` 字段关联。
- 程序应在最后打印清晰的结果（如 `RESULT: ...`），断言失败时以非零状态退出。

---

## 五、文件位置速查

| 内容 | 路径 |
|---|---|
| 日报数据（唯一数据源） | `content/daily/YYYY/YYYY-MM-DD.json` |
| 日报 Schema | `schema/daily.schema.json` |
| 实验 | `experiments/YYYY-MM-DD-slug/` |
| 实验 Schema | `schema/experiment.schema.json` |
| 建议方向与标签 | `config/sources.yaml` |
| 校验 | `python3 scripts/validate.py <file>` |
| 本地构建预览 | `python3 scripts/build_site.py`（输出到 `_site/`） |

不要修改 `scripts/`、`schema/`、`.github/`、`templates/` 和本文件，除非任务明确要求。
