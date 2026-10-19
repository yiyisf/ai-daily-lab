# AI Daily Lab

每日 AI 资讯、开源项目、业界讨论、方法实践与**可验证实验**。内容由 Claude 自动搜集整理，经 GitHub Actions 校验和人工审核后发布。

- 站点：https://yiyisf.github.io/ai-daily-lab/
- 同步数据：https://yiyisf.github.io/ai-daily-lab/data/manifest.json

## 工作流程

```
06:00  Claude 定时任务 ── 按 CLAUDE.md 搜集、撰写、写实验 ──► 推送 daily/DATE 分支并开 PR
         │
         ├─ validate.yml     校验 Schema / 规则 / 链接，结果评论到 PR
         └─ experiments.yml  在隔离环境执行实验，result.json 提交回 PR，结果评论到 PR
         │
       人工审核 → 合并到 main
         │
         └─ deploy.yml       构建站点 + 同步数据包 → GitHub Pages
08:30  watchdog.yml          当天没有日报 PR 时自动开 issue 提醒
```

## 目录

| 路径 | 说明 |
|---|---|
| `CLAUDE.md` | 日报生成规则（Claude 每次运行时读取） |
| `config/sources.yaml` | 建议关注方向与标签词表（不限定范围） |
| `content/daily/YYYY/YYYY-MM-DD.json` | 日报数据，唯一数据源 |
| `experiments/YYYY-MM-DD-slug/` | 实验代码与说明；`result.json` 由 Actions 写入 |
| `schema/` | 日报与实验的 JSON Schema |
| `scripts/` | 校验、构建、实验执行脚本 |
| `templates/` | 站点模板与样式 |

## 本地使用

```bash
pip install -r requirements.txt
python3 scripts/validate.py --all                 # 校验全部日报
python3 scripts/build_site.py                     # 构建到 _site/
python3 -m http.server -d _site 8000              # 预览
python3 scripts/run_experiment.py experiments/<id> --out /tmp/r.json   # 本地跑实验
```

## 内网同步数据格式

`data/manifest.json`：

```json
{
  "latest": "2026-10-20",
  "wiki_root": "AI日报",
  "issues": [
    { "date": "2026-10-20", "package": "data/2026-10-20.json", "sha256": "…", "bytes": 41234, "items": 14, "experiments": 1 }
  ]
}
```

`data/YYYY-MM-DD.json` 中的 `pages` 数组每项对应一个 wiki 页面：

| 字段 | 说明 |
|---|---|
| `key` | 稳定唯一键，用于幂等 upsert |
| `path` | 父子页面路径，如 `["AI日报", "2026", "2026-10", "2026-10-20"]`，实验页挂在当天页面下 |
| `title` | 页面标题 |
| `markdown` / `html` | 页面内容，两种格式任选 |

同步程序流程：读取 manifest → 对比本地已同步记录 → 下载缺失日期的数据包并校验 sha256 → 按 `path` 逐级确保父页面存在 → 按 `key` 创建或更新页面。

## 安全设计

- 实验在只读权限、无 secrets、无 git 凭证的 job 中执行；结果由另一个不执行代码的 job 提交
- 来自 fork 的 PR 不会获得写权限，也不会被提交实验结果
- 仓库公开，不包含任何内部信息
