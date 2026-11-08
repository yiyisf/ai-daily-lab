"""扫描 Agent 权限文件的 allow 规则：只认密钥格式的扫描器会漏掉什么。

背景（Cyber Security News 2026-11-07 转述 Apiiro 的研究，以及 Claude Code 设置文档）：
  - 在 Claude Code 里对一条 Bash 命令选「Yes, and don't ask again」，整条命令会作为 allow 规则
    存进 .claude/settings.local.json；命令里带的密码也会原样存进去
  - 1,122 个含真实密钥的公开文件中，有 215 个 Gitleaks 和 TruffleHog 都没检出，
    原因是 PGPASSWORD=、sshpass -p、请求头里的密码没有可识别的格式
本实验不调用模型、不访问网络：用固定种子生成「假」凭据，拼成常见的 allow 规则，
比较两种检测器：
  A. 只认密钥格式（云厂商 key、GitHub token、JWT 等前缀/形状）
  B. 格式 + 上下文（看凭据出现在命令的什么位置：PGPASSWORD=、-p、Authorization 头、URL 里的口令）
所有凭据都是运行时随机生成的假值，不对应任何真实账号。
"""
import json
import random
import re
import string
import sys

rng = random.Random(20261109)


def rand(chars, n):
    return "".join(rng.choice(chars) for _ in range(n))


ALNUM = string.ascii_letters + string.digits
UPPER_DIGIT = string.ascii_uppercase + string.digits


def fake_password():
    # 人设的口令：没有固定前缀，长度和字符集都很普通
    words = ["summer", "Prod", "admin", "Welcome", "db", "Spring", "team"]
    return rng.choice(words) + rand(string.digits, rng.randint(2, 4)) + rng.choice("!@#_")


# ---------- 构造正例：带凭据的 allow 规则 ----------
def positives():
    cases = []
    # 1) 有固定格式的 token（格式扫描器擅长的）
    for _ in range(6):
        kind = rng.choice(["aws", "gh", "sk", "jwt"])
        if kind == "aws":
            tok = "AKIA" + rand(UPPER_DIGIT, 16)
            cmd = f"Bash(AWS_ACCESS_KEY_ID={tok} aws s3 ls s3://backup)"
        elif kind == "gh":
            tok = "ghp_" + rand(ALNUM, 36)
            cmd = f"Bash(git clone https://{tok}@github.com/acme/app.git)"
        elif kind == "sk":
            tok = "sk-" + rand(ALNUM, 40)
            cmd = f"Bash(curl https://api.example.com/v1/models -H 'x-api-key: {tok}')"
        else:
            seg = lambda n: rand(ALNUM + "-_", n)
            tok = "eyJ" + seg(30) + "." + "eyJ" + seg(40) + "." + seg(43)
            cmd = f"Bash(curl https://supabase.example.co/rest/v1/users -H 'apikey: {tok}')"
        cases.append(("格式化 token", cmd))
    # 2) 人设口令，只能靠上下文判断（原文说扫描器常漏的那类）
    for _ in range(3):
        cases.append(("PGPASSWORD=", f"Bash(PGPASSWORD={fake_password()} psql -h db.internal -U app -c 'select 1')"))
    for _ in range(3):
        cases.append(("sshpass -p", f"Bash(sshpass -p {fake_password()} ssh root@10.0.0.{rng.randint(2, 250)})"))
    for _ in range(3):
        cases.append(("mysql -p", f"Bash(mysql -u root -p{fake_password()} -h 127.0.0.1 shop)"))
    for _ in range(3):
        cases.append(("URL 内口令", f"Bash(psql postgresql://app:{fake_password()}@db.internal:5432/orders)"))
    for _ in range(3):
        cases.append(("Basic 认证头", f"Bash(curl -H 'Authorization: Basic {rand(ALNUM, 24)}=' https://jira.internal/rest/api/2/myself)"))
    for _ in range(3):
        cases.append(("curl -u", f"Bash(curl -u deploy:{fake_password()} https://nexus.internal/service/rest/v1/status)"))
    return cases


# ---------- 构造反例：不含凭据的 allow 规则 ----------
NEGATIVES = [
    "Bash(npm run test *)",
    "Bash(npm run lint)",
    "Bash(git status)",
    "Bash(git log --oneline -20)",
    "Bash(pytest -q tests/)",
    "Bash(PGPASSWORD=$PGPASSWORD psql -h db.internal -U app)",
    "Bash(PGPASSWORD=\"${DB_PASS}\" pg_dump orders)",
    "Bash(sshpass -f ~/.ssh/pass.txt ssh deploy@10.0.0.5)",
    "Bash(mysql -u root -p -h 127.0.0.1 shop)",
    "Bash(curl -H \"Authorization: Bearer $TOKEN\" https://api.internal/health)",
    "Bash(curl -u deploy:$NEXUS_PASS https://nexus.internal/service/rest/v1/status)",
    "Bash(psql postgresql://app:${DB_PASS}@db.internal:5432/orders)",
    "Read(./.env)",
    "Bash(docker compose up -d)",
    "Bash(kubectl get pods -n staging)",
]


# ---------- 检测器 ----------
FORMAT_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]

# 值不能是变量引用或占位符：$X、${X}、<X>、***
VALUE = r"(?![$<*\"']*\$)(?!<)(?!\*{3})[^\s'\"$]{4,}"
CONTEXT_PATTERNS = [
    re.compile(r"\b(?:PGPASSWORD|MYSQL_PWD|PASSWORD|PASSWD|SECRET|TOKEN)=" + VALUE),
    re.compile(r"\bsshpass\s+-p\s*" + VALUE),
    re.compile(r"\bmysql\b[^)]*\s-p(?!\s)" + VALUE),
    re.compile(r"://[^/\s:@]+:" + VALUE.replace("[^\\s'\\\"$]", "[^\\s'\"$@]") + r"@"),
    re.compile(r"Authorization:\s*(?:Basic|Bearer)\s+" + VALUE, re.I),
    re.compile(r"\bcurl\b[^)]*\s-u\s+[^\s:]+:" + VALUE),
    re.compile(r"(?:x-api-key|apikey):\s*" + VALUE, re.I),
]


def detect_format(rule):
    return any(p.search(rule) for p in FORMAT_PATTERNS)


def detect_context(rule):
    return detect_format(rule) or any(p.search(rule) for p in CONTEXT_PATTERNS)


def scan_settings(obj, detector):
    """返回一个设置文件里被判为含凭据的 allow 规则。"""
    allow = obj.get("permissions", {}).get("allow", [])
    return [r for r in allow if detector(r)]


def main():
    pos = positives()
    checks = []

    def check(ok, msg):
        checks.append(ok)
        print(("[PASS] " if ok else "[FAIL] ") + msg)

    fmt_hit = [detect_format(c) for _, c in pos]
    ctx_hit = [detect_context(c) for _, c in pos]
    fmt_fp = [r for r in NEGATIVES if detect_format(r)]
    ctx_fp = [r for r in NEGATIVES if detect_context(r)]

    # 按类别统计 A 的漏检
    print("各类别检出情况（A=只认格式，B=格式+上下文）：")
    cats = []
    for cat, _ in pos:
        if cat not in cats:
            cats.append(cat)
    for cat in cats:
        idx = [i for i, (c, _) in enumerate(pos) if c == cat]
        a = sum(fmt_hit[i] for i in idx)
        b = sum(ctx_hit[i] for i in idx)
        print(f"  {cat:<10} 共 {len(idx)} 条  A 检出 {a}  B 检出 {b}")

    for r in ctx_fp:
        print("  B 误报：", r)

    n = len(pos)
    rec_a = 100.0 * sum(fmt_hit) / n
    rec_b = 100.0 * sum(ctx_hit) / n
    print(f"METRIC: 只认格式的检出率 = {rec_a:.1f} %")
    print(f"METRIC: 格式+上下文的检出率 = {rec_b:.1f} %")
    print(f"METRIC: 只认格式的误报数 = {len(fmt_fp)} 条")
    print(f"METRIC: 格式+上下文的误报数 = {len(ctx_fp)} 条")

    token_idx = [i for i, (c, _) in enumerate(pos) if c == "格式化 token"]
    check(all(fmt_hit[i] for i in token_idx), "只认格式的检测器能检出全部有固定格式的 token")
    check(sum(ctx_hit) >= sum(fmt_hit), "加上下文规则后检出数不少于只认格式")
    check(len(ctx_fp) == 0, "变量引用（$VAR、${VAR}）和不带口令的命令不被误报")

    # 端到端：把规则写进一个模拟的 settings.local.json，再扫描
    settings = {"permissions": {"allow": [c for _, c in pos[:4]] + NEGATIVES[:5] + [pos[6][1]]}}
    text = json.dumps(settings, ensure_ascii=False)
    found = scan_settings(json.loads(text), detect_context)
    check(len(found) == 5, f"模拟 settings.local.json 中找出 {len(found)} 条含凭据的 allow 规则（应为 5）")

    passed = sum(checks)
    print(f"RESULT: 检出率 只认格式 {rec_a:.1f}% / 格式+上下文 {rec_b:.1f}%，检查 {passed}/{len(checks)} 通过")
    sys.exit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
