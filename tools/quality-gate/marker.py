"""读写检查凭证（marker）。

每个 agent 干完活写一份 JSON 到 .git/quality-gate/<agent>.json，
pre-commit hook 提交前读它，判断「这套代码是否真的被检查过」。

放在 .git/ 里的原因：不会出现在 git status 里，也不会被误提交进仓库，
更不会因为 .gitignore 漏配而污染工作区。

一条 marker 长这样：
    {
      "version": 1,
      "agent": "tester",
      "verdict": "pass",            # pass / fail
      "tree": "sha256:9f3a...",     # 检查结束时的工作区哈希，gate 会重算比对
      "head": "fab7f62",            # 当时的 HEAD，便于排查
      "command": "pytest ...",      # 实际执行的命令，可复现
      "summary": "195 passed in 2.1s",
      "details": {"p0": 0, "p1": 0, "report": "..."},
      "finished_at": "2026-11-20T14:20:00+08:00"
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 允许直接 `python marker.py` 运行：把它自己所在的目录加进搜索路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from treehash import repo_root, tree_hash  # noqa: E402

MARKER_VERSION = 1
MARKER_DIR = Path(".git") / "quality-gate"
DEFAULT_TTL_HOURS = 12


def marker_path(root: Path, agent: str) -> Path:
    """marker 的落盘位置：<仓库>/.git/quality-gate/<agent>.json"""
    return Path(root) / MARKER_DIR / f"{agent}.json"


def write_marker(
    root: Path,
    agent: str,
    verdict: str,
    command: str,
    summary: str,
    details: dict | None = None,
) -> Path:
    """写一份 marker。tree 和 head 在这里现算，agent 不需要自己拼。"""
    if verdict not in ("pass", "fail"):
        raise ValueError(f"verdict 只能是 pass 或 fail，收到 {verdict!r}")

    path = marker_path(root, agent)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": MARKER_VERSION,
        "agent": agent,
        "verdict": verdict,
        "tree": tree_hash(root),
        "head": _head_sha(root),
        "command": command,
        "summary": summary,
        "details": details or {},
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    # ensure_ascii=False 让中文原样存，方便人直接打开看
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _head_sha(root: Path) -> str:
    """取当前 HEAD 的短哈希；空仓库（还没有提交）时返回空串。"""
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def read_marker(root: Path, agent: str) -> dict | None:
    """读 marker；文件不存在或 JSON 坏了都返回 None，由调用方决定怎么报错。"""
    path = marker_path(root, agent)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def verify(
    root: Path, agent: str, ttl_hours: int = DEFAULT_TTL_HOURS
) -> tuple[bool, str]:
    """校验一份 marker 是否仍然有效。

    返回 (是否通过, 原因)。原因永远是中文短句，gate 会原样打到终端上，
    所以要写成人能看懂、知道下一步该干嘛的话。
    """
    marker = read_marker(root, agent)
    if marker is None:
        return False, f"没有找到 {agent} 的检查凭证，请先跑一次 {agent}"

    if marker.get("version") != MARKER_VERSION:
        return False, f"{agent} 的凭证版本过旧（{marker.get('version')}），请重跑 {agent}"

    if marker.get("verdict") != "pass":
        return False, f"{agent} 上次的结论是 {marker.get('verdict')}，不是 pass"

    # 关键一步：把「凭证记录的哈希」和「现在的哈希」比一比
    current = tree_hash(root)
    if marker.get("tree") != current:
        return False, (
            f"代码在 {agent} 检查之后又被改过"
            f"（凭证 {marker.get('tree', '?')[:20]}… / 现在 {current[:20]}…），请重跑 {agent}"
        )

    # 时间兜底：哈希对得上说明内容没变，但如果凭证是三天前的，仍要求重跑
    try:
        finished = datetime.fromisoformat(marker["finished_at"])
    except (KeyError, ValueError):
        return False, f"{agent} 的凭证缺少合法的 finished_at，请重跑 {agent}"

    if datetime.now().astimezone() - finished > timedelta(hours=ttl_hours):
        return False, f"{agent} 的凭证已超过 {ttl_hours} 小时，请重跑 {agent}"

    return True, f"{agent}: {marker.get('summary', '通过')}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="写/读/校验检查凭证（marker）")
    sub = parser.add_subparsers(dest="action", required=True)

    write = sub.add_parser("write", help="写一份凭证")
    write.add_argument("--agent", required=True)
    write.add_argument("--verdict", default="pass", choices=["pass", "fail"])
    write.add_argument("--command", default="")
    write.add_argument("--summary", default="")
    write.add_argument("--p0", type=int, default=0, help="质量问题里 P0 的条数")
    write.add_argument("--p1", type=int, default=0, help="质量问题里 P1 的条数")
    write.add_argument("--report", default="", help="报告文件路径（可选）")

    check = sub.add_parser("verify", help="校验一份凭证")
    check.add_argument("--agent", required=True)
    check.add_argument("--ttl-hours", type=int, default=DEFAULT_TTL_HOURS)

    show = sub.add_parser("show", help="打印凭证内容")
    show.add_argument("--agent", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = repo_root()

    if args.action == "write":
        details = {"p0": args.p0, "p1": args.p1}
        if args.report:
            details["report"] = args.report
        path = write_marker(root, args.agent, args.verdict, args.command, args.summary, details)
        print(f"已写入凭证：{path}")
        return 0

    if args.action == "verify":
        ok, reason = verify(root, args.agent, args.ttl_hours)
        print(reason)
        return 0 if ok else 1

    if args.action == "show":
        marker = read_marker(root, args.agent)
        if marker is None:
            print(f"没有 {args.agent} 的凭证")
            return 1
        print(json.dumps(marker, ensure_ascii=False, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
