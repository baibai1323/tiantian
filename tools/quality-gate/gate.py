"""pre-commit 门禁：不合格就不让提交。

判定顺序（任一步失败就拦住，并告诉人该怎么办）：
  1. 工作区有没有变化在做「检查」时被漏掉 —— 用哈希证明 marker 与当前代码一致
  2. tester 的检查凭证有效（跑过测试，结论通过）
  3. **自己再跑一遍 pytest** —— marker 只说明「当时跑过」，不说明「现在还能过」
  4. quality-engineer 的凭证有效，且 P0 = 0、P1 = 0
  5. 全部通过 → 退出码 0，提交继续

为什么 gate 要自己跑测试：marker 是文件，谁都能手写一份。真正不能作假的是
「现在这台机器上、这份代码，测试到底过不过」。pytest 跑一遍约 1.5–2 秒，
比冒「提交了一个测试是红的版本」的风险便宜得多。

绕过方式只有 `git commit --no-verify`，这是 git 自身行为，我们不阻止，
但要在团队约定里写清楚：那是紧急逃生口，不是日常路径。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# 让 gate.py 能 import 同目录的 marker / treehash（hook 用 python 直接执行本文件）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from marker import DEFAULT_TTL_HOURS, read_marker, verify  # noqa: E402
from treehash import repo_root, tree_hash  # noqa: E402

# 测试目录与必需的两份凭证，都在这里集中配置，改一处就够
TESTS_DIR = "backend/tests"
REQUIRED_AGENTS = ("tester", "quality-engineer")

# 装帧用的分隔线，让输出在终端里一眼能看出这是门禁而不是测试在报错
RULE = "=" * 62


def _ensure_stream_safe() -> None:
    """保证输出流不会因为编码崩掉。

    git hook 的 stdout 可能是 GBK 控制台或重定向管道，遇到编不进去的字符时
    Python 默认抛 UnicodeEncodeError —— 门禁自己崩了，人只看到一堆 traceback，
    根本不知道是「被拦下」还是「工具坏了」。这里统一把错误降级成 '?'。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def _say(text: str = "") -> None:
    """统一输出入口：flush 保证在 hook 环境里顺序不乱。"""
    print(text, flush=True)


def _fail(reason: str, hint: str = "") -> int:
    """打印失败原因和下一步，返回 1 让 git 中止提交。"""
    _say()
    _say(f"[失败] 提交被拦下：{reason}")
    if hint:
        _say(f"  → {hint}")
    _say(RULE)
    return 1


def run_pytest(root: Path) -> tuple[bool, str, str]:
    """在仓库根目录跑一遍测试。

    返回 (是否全绿, 结果摘要, 实际命令)。
    用 sys.executable 而不是写死路径：hook 已经是由 venv 的 python 启动的。
    加 PYTHONDONTWRITEBYTECODE，避免在仓库里留 __pycache__ 影响工作区哈希。
    """
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, "-m", "pytest", TESTS_DIR, "-q", "-p", "no:cacheprovider"]

    proc = subprocess.run(
        cmd,
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    # pytest 的结论在最后几行，把尾部留下来给人看
    lines = [line for line in proc.stdout.strip().splitlines() if line.strip()]
    summary = lines[-1] if lines else "(pytest 没有输出)"
    return proc.returncode == 0, summary, " ".join(cmd)


def main() -> int:
    _ensure_stream_safe()
    root = repo_root()
    current = tree_hash(root)

    _say(RULE)
    _say("提交门禁 / quality-gate")
    _say(f"仓库：{root}")
    _say(f"代码指纹：{current[:24]}…")
    _say(RULE)

    # ---- 步骤 1：tester 的凭证 ----
    ok, reason = verify(root, "tester", DEFAULT_TTL_HOURS)
    if not ok:
        return _fail(
            reason,
            "先在提交前跑一次 tester：它会写测试、跑全量、通过后写凭证",
        )
    _say(f"[通过] {reason}")

    # ---- 步骤 2：gate 亲自跑测试（不信 marker 的一面之词） ----
    passed, summary, command = run_pytest(root)
    if not passed:
        return _fail(
            f"测试没通过 —— {summary}",
            f"手动复跑看细节：{command}",
        )
    _say(f"[通过] 测试通过：{summary}")

    # ---- 步骤 3：质量工程师的结论 ----
    ok, reason = verify(root, "quality-engineer", DEFAULT_TTL_HOURS)
    if not ok:
        return _fail(
            reason,
            "先跑一次 quality-engineer：它查安全/注释/测试健康度/工程卫生，写凭证",
        )

    marker = read_marker(root, "quality-engineer") or {}
    details = marker.get("details") or {}
    p0 = int(details.get("p0", 0))
    p1 = int(details.get("p1", 0))

    # 严格口径：P0、P1 都必须为 0。P2 只记录，不拦提交。
    if p0 or p1:
        return _fail(
            f"质量问题未清零：P0={p0}，P1={p1}",
            "先修掉 P0/P1 再跑一次 quality-engineer（P2 不拦提交）",
        )
    _say(f"[通过] {reason}（P0=0，P1=0）")

    # ---- 全部通过 ----
    _say(RULE)
    _say("[通过] 门禁通过，提交继续")
    _say(RULE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
