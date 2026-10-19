#!/usr/bin/env python3
"""Run one experiment in isolation and write its result JSON.

Usage:
  python3 scripts/run_experiment.py experiments/2026-10-20-foo --out results/2026-10-20-foo.json

Designed to run in a GitHub Actions job that has NO secrets and a read-only token.
The result is written outside the experiment directory; a separate job commits it.

Status rules:
  passed   exit code 0
  partial  exit code 0 and stdout contains a line "STATUS: partial"
  failed   non-zero exit, install failure or timeout
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

MAX_OUTPUT_CHARS = 12_000
INSTALL_TIMEOUT = 600


def tail(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return "…（前面省略 %d 字符）\n" % (len(text) - limit) + text[-limit:]


def run(cmd, cwd, env, timeout):
    t0 = time.monotonic()
    try:
        p = subprocess.run(
            cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
            shell=isinstance(cmd, str),
        )
        return p.returncode, p.stdout, p.stderr, time.monotonic() - t0, False
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        return -1, out, err, time.monotonic() - t0, True


def version_of(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("exp_dir")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    src = Path(args.exp_dir).resolve()
    meta = json.loads((src / "experiment.json").read_text(encoding="utf-8"))
    runtime = meta["runtime"]
    timeout = int(meta.get("timeout_seconds", 120))

    # Work on a copy so nothing written by the experiment leaks back into the repo.
    work = Path(tempfile.mkdtemp(prefix="exp-")) / src.name
    shutil.copytree(src, work, ignore=shutil.ignore_patterns("result.json"))

    # Minimal environment: no inherited secrets or tokens.
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(work.parent),
        "LANG": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "CI": "true",
    }

    result: dict = {
        "id": meta["id"],
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runner": f"{platform.system()} {platform.machine()}",
        "runtime": runtime,
        "entry": meta["entry"],
    }
    logs: list[str] = []

    # 1) install dependencies
    install_cmd = None
    if runtime == "python":
        venv = work.parent / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        env["PATH"] = f"{venv / 'bin'}:{env['PATH']}"
        env["VIRTUAL_ENV"] = str(venv)
        result["runtime_version"] = version_of([str(venv / "bin" / "python"), "--version"])
        if (work / "requirements.txt").exists():
            install_cmd = [str(venv / "bin" / "pip"), "install", "-q", "-r", "requirements.txt"]
    elif runtime == "node":
        result["runtime_version"] = version_of(["node", "--version"])
        if (work / "package.json").exists():
            install_cmd = ["npm", "install", "--no-audit", "--no-fund", "--ignore-scripts"]
    else:
        result["runtime_version"] = version_of(["bash", "--version"]).splitlines()[0] if shutil.which("bash") else ""

    if install_cmd:
        code, out, err, dur, timed_out = run(install_cmd, work, env, INSTALL_TIMEOUT)
        result["install_seconds"] = round(dur, 1)
        if code != 0:
            result.update(
                status="failed", exit_code=code, duration_seconds=0,
                failure="依赖安装超时" if timed_out else "依赖安装失败",
                stdout=tail(out), stderr=tail(err),
            )
            write(result, args.out)
            print(f"[{meta['id']}] install failed", file=sys.stderr)
            return 0

    if runtime == "python":
        frz = subprocess.run([str(Path(env["VIRTUAL_ENV"]) / "bin" / "pip"), "freeze"],
                             capture_output=True, text=True, env=env)
        result["packages"] = [l for l in frz.stdout.splitlines() if l and not l.startswith("#")][:60]

    # 2) run entry
    code, out, err, dur, timed_out = run(shlex.split(meta["entry"]), work, env, timeout)
    status = "passed" if code == 0 else "failed"
    if code == 0 and any(l.strip().upper() == "STATUS: PARTIAL" for l in out.splitlines()):
        status = "partial"
    result.update(
        status=status, exit_code=code, duration_seconds=round(dur, 1),
        stdout=tail(out), stderr=tail(err),
    )
    if timed_out:
        result["failure"] = f"运行超时（{timeout} 秒）"
    elif code != 0:
        result["failure"] = f"退出码 {code}"
    write(result, args.out)
    print(f"[{meta['id']}] {status} in {dur:.1f}s")
    return 0


def write(result: dict, out: str) -> None:
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
