# 离线校验审计发现记录：confirmed 须有证据且不能自己验证自己

## 目的

Cloudflare 开源的 [security-audit-skill](https://github.com/cloudflare/security-audit-skill) 在 README 中写明：发现由一个 Agent 提出，必须由另一个全新的 Agent 去尝试推翻；`confirmed` 需要完整的源码追踪和有限的观察结果，`needs_validation` 要写清未解决的具体事实且不带严重度，并用零依赖的 Node.js 校验器检查 `findings.json`。

本实验把这几条规则写成一个只用标准库的小校验器，在 8 条 mock 记录上演示：缺证据的 confirmed、自己验证自己、给未验证结论打严重度，都能被机械地挡住。

注意：字段名和记录内容是本实验自己构造的 mock，**不是该技能 findings.json 的真实 schema**，也不代表其校验器的实现。

## 步骤

```bash
python main.py
```

程序对每条记录打印 `[PASS]/[FAIL]`、`METRIC:` 指标和最后一行 `RESULT:`；有记录的结论与人工标注不一致时以非零状态退出。

## 预期结果

- F1、F5、F8 通过校验
- F2 被判为「自己验证自己」，F3 缺源码追踪，F4 缺观察结果
- F6 在未验证状态下带了严重度，F7 没写未解决的事实

## 启示与可以继续尝试

- 想让团队的 Agent 产出可信的审查结论，可以先给「结论」定一个带必填证据的格式，再用脚本检查，而不是靠人逐条读
- 把真实审查输出的字段映射进 `check()`，看看有多少条结论其实缺证据

## 内网复现

- 只用 Python 标准库，不需要安装任何依赖，`requirements.txt` 仅作说明
- 程序完全离线运行，不访问网络，也不需要 API key
- 技能本身需要外网或内网 Git 镜像获取，本实验不依赖它
