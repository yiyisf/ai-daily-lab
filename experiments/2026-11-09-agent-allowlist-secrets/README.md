# 玩具实验：只认密钥格式的扫描器，会漏掉权限文件里哪些密码

## 目的

Cyber Security News（2026-11-07）转述了 Apiiro 的研究：在 Claude Code 里对一条带凭据的 Bash 命令选「Yes, and don't ask again」，整条命令会作为 `allow` 规则存进 `.claude/settings.local.json`（Claude Code 设置文档也写明了这一点）。研究者在 1,122 个含真实密钥的公开文件里发现，有 215 个 Gitleaks 和 TruffleHog 都没检出，原因是 `PGPASSWORD=`、`sshpass -p`、请求头里的密码没有可识别的格式。

本实验**不调用任何模型、不访问网络**，用固定种子生成假凭据，拼成常见的 allow 规则，比较两种检测器：

- A：只认密钥格式（AWS key、GitHub token、`sk-` 前缀、JWT、私钥头）
- B：A 加上命令上下文规则（`PGPASSWORD=`、`sshpass -p`、`mysql -p`、URL 里的口令、`Authorization: Basic/Bearer`、`curl -u`、`apikey:` 头），并排除 `$VAR`、`${VAR}` 这类变量引用

## 步骤

```bash
python main.py
```

不需要安装第三方包。程序打印各类别的检出情况、`METRIC:` 指标、4 项 `[PASS]/[FAIL]` 检查和最后一行 `RESULT:`；任一检查失败时以非零状态退出。

## 预期结果

- 带固定格式的 token 两种检测器都能检出
- 人设口令类（`PGPASSWORD=` 等）只有 B 能检出
- 使用变量引用、不含口令的命令不被误报

## 局限

- 样本是构造的，类别和比例由本实验自定，不代表真实仓库里的分布，检出率数字只说明规则覆盖了哪些写法
- B 的规则是针对这些写法手写的，换一种写法（如 `--password=`、配置文件里的口令）仍可能漏掉，也可能在真实数据上出现误报
- 只扫描 `permissions.allow`，研究中提到的会话记录、记忆文件等位置没有覆盖

## 启示与可以继续尝试

- 把 B 这类上下文规则补进团队的 pre-commit 或 CI 扫描，专门检查 `.claude/`、`.codex/` 等 Agent 配置目录
- 用 `scan_settings()` 扫描本机项目里的 `.claude/settings.local.json`，先看有没有已经存下的口令（发现后应先轮换凭据）
- 更根本的做法是让命令里只出现变量引用或密钥管理工具的引用，而不是明文口令

## 内网复现

- 无第三方依赖，只需要 Python 3，开发机或内网 CI 镜像一般都有
- 程序完全离线运行，不访问网络，不需要 API key 或 GPU
- 生成的凭据都是随机假值，不对应任何真实账号
