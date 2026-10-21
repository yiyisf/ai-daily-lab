"""扫描 site-packages 中会在 Python 启动时自动执行的代码（.pth 的 import 行、sitecustomize 等）。

背景：LiteLLM 1.107.0 的恶意 wheel 向 site-packages 写入 cook.pth / cook.py / sitecustomize.py，
无需 import litellm，每次启动解释器就会运行。本实验在临时目录中构造三个"假"环境，
验证一个只用标准库的扫描器能否区分：
  - 正常的路径型 .pth（不执行代码）
  - 常见工具也会用到的 import 型 .pth（需要人工复核，但不应报为已知恶意）
  - 与公开 IoC 文件名一致的启动钩子（应报为严重）

所有样例文件均由本脚本生成，不包含任何真实恶意代码。
"""
from __future__ import annotations

import hashlib
import site
import sys
import sysconfig
import tempfile
from dataclasses import dataclass
from pathlib import Path

# 公开报告（StepSecurity, 2026-10-21）中的文件名与部分 SHA-256（Linux/macOS 版本）
IOC_FILENAMES = {"cook.pth", "cook.py"}
IOC_SHA256 = {
    "7f191632e7320705d154b85204f1ae546b543acbd7e8861229b76f5042b92bdb": "cook.pth",
    "9dd0a3926f96a37eb86cf1ee2310d9be93139cc4ebef3ef9e2efe9531390be25": "cook.py",
    "34bef04fe88ac9d0aae0475630b1738681d15b94f233ac8aa46eacf5968305fa": "sitecustomize.py",
}
STARTUP_MODULES = {"sitecustomize.py", "usercustomize.py"}


@dataclass
class Finding:
    level: str  # CRITICAL / REVIEW
    path: str
    reason: str


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def scan(site_dir: Path) -> list[Finding]:
    out: list[Finding] = []
    for p in sorted(site_dir.iterdir()):
        if not p.is_file():
            continue
        digest = sha256(p)
        if digest in IOC_SHA256:
            out.append(Finding("CRITICAL", p.name, f"哈希与已知恶意文件 {IOC_SHA256[digest]} 一致"))
            continue
        if p.name in IOC_FILENAMES:
            out.append(Finding("CRITICAL", p.name, "文件名与 LiteLLM 投毒事件公开 IoC 一致"))
            continue
        if p.name in STARTUP_MODULES:
            out.append(Finding("REVIEW", p.name, "site-packages 中的启动模块，每次启动解释器都会执行"))
            continue
        if p.suffix == ".pth":
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                s = line.strip()
                # site.py 规则：以 "import " 或 "import\t" 开头的行会被 exec
                if s.startswith(("import ", "import\t")):
                    out.append(Finding("REVIEW", f"{p.name}:{n}", "启动时会执行的 import 行：" + s[:60]))
    return out


def make_env(root: Path, kind: str) -> Path:
    d = root / kind
    d.mkdir()
    (d / "mypkg.pth").write_text("/opt/extra/libs\n# comment\n", encoding="utf-8")
    if kind in ("tooling", "poisoned"):
        # 与 setuptools 的 distutils-precedence.pth 同类：合法但会执行代码
        (d / "distutils-precedence.pth").write_text(
            "import os; var = 'SETUPTOOLS_USE_DISTUTILS'; enabled = os.environ.get(var, 'local') == 'local'\n",
            encoding="utf-8",
        )
    if kind == "poisoned":
        # 仅模拟文件名与结构，内容是无害的占位
        (d / "cook.pth").write_text("import cook\n", encoding="utf-8")
        (d / "cook.py").write_text("# harmless placeholder for the experiment\n", encoding="utf-8")
        (d / "sitecustomize.py").write_text("# harmless placeholder\n", encoding="utf-8")
    return d


def main() -> int:
    expected = {"clean": (0, 0), "tooling": (0, 1), "poisoned": (2, 2)}
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        for kind, (want_crit, want_review) in expected.items():
            env = make_env(Path(tmp), kind)
            fs = scan(env)
            crit = sum(f.level == "CRITICAL" for f in fs)
            rev = sum(f.level == "REVIEW" for f in fs)
            status = "PASS" if (crit, rev) == (want_crit, want_review) else "FAIL"
            ok &= status == "PASS"
            print(f"[{status}] {kind:9s} CRITICAL={crit} (期望 {want_crit})  REVIEW={rev} (期望 {want_review})")
            for f in fs:
                print(f"           {f.level:8s} {f.path}  {f.reason}")

    # 附加：扫描当前解释器真实的 site-packages（只打印，不做断言）
    dirs = {sysconfig.get_paths()["purelib"], *getattr(site, "getsitepackages", lambda: [])()}
    print(f"\n当前解释器 {sys.version.split()[0]} 的 site-packages 扫描（仅供参考）：")
    for d in sorted(dirs):
        p = Path(d)
        if not p.is_dir():
            continue
        fs = scan(p)
        crit = [f for f in fs if f.level == "CRITICAL"]
        print(f"  {d}: CRITICAL={len(crit)} REVIEW={len(fs) - len(crit)}")
        for f in fs:
            print(f"    {f.level:8s} {f.path}  {f.reason}")

    print("\nRESULT:", "3/3 样例环境分类正确" if ok else "存在分类错误")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
