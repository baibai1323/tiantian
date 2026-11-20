"""把提交门禁装进（或卸出）当前仓库的 .git/hooks。

用法：
    python tools/quality-gate/install_hooks.py            # 安装
    python tools/quality-gate/install_hooks.py --uninstall # 卸载
    python tools/quality-gate/install_hooks.py --status    # 只查询

为什么需要安装脚本，而不是让人手动 copy：
- hook 必须用 LF 换行，Windows 上手动复制极易变成 CRLF，导致 sh 报错
- 新克隆的仓库不会带 .git/hooks（它不进版本库），得有个可重复执行的入口
- 卸载时要知道原来装的是什么，留一份备份便于回滚
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# 本脚本所在目录 = tools/quality-gate
HERE = Path(__file__).resolve().parent
HOOK_SOURCE = HERE / "hooks" / "pre-commit"


def repo_root() -> Path:
    """仓库根目录 = 本文件往上两层（tools/quality-gate → 仓库根）。"""
    return HERE.parent.parent


def hook_target(root: Path) -> Path:
    return root / ".git" / "hooks" / "pre-commit"


def _is_ours(path: Path) -> bool:
    """判断某个 hook 文件是不是本门禁装的（忽略换行差异）。

    为什么需要这个：重复安装时，磁盘上的 hook 可能已经是「我们自己的」，
    这时再备份就等于把门禁拷成备份，用户原本的 hook 被顶掉、再也找不回来。
    """
    if not path.is_file():
        return False
    try:
        current = path.read_bytes().replace(b"\r\n", b"\n")
        source = HOOK_SOURCE.read_bytes().replace(b"\r\n", b"\n")
    except OSError:
        return False
    return current == source


def install(root: Path) -> int:
    target = hook_target(root)

    if not HOOK_SOURCE.is_file():
        print(f"找不到 hook 源文件：{HOOK_SOURCE}")
        return 1

    if not (root / ".git").is_dir():
        print(f"{root} 不是 git 仓库（没有 .git 目录）")
        return 1

    # 备份只在「原有 hook 不是我们的」且「还没备份过」时做一次，
    # 保证用户原 hook 永远不会被门禁自己的副本顶掉。
    backup = target.with_suffix(".bak")
    if target.is_file() and not _is_ours(target):
        if backup.is_file():
            print(f"已有 hook，备份已存在（{backup.name}），保留最早那份")
        else:
            shutil.copyfile(target, backup)
            print(f"已有 hook，已备份到 {backup.name}")

    # 关键：按字节写，并把换行统一成 LF
    content = HOOK_SOURCE.read_text(encoding="utf-8").replace("\r\n", "\n")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8"))

    print(f"已安装：{target}")
    print("试试提交一次，应该能看到门禁输出。卸载：--uninstall")
    return 0


def uninstall(root: Path) -> int:
    target = hook_target(root)
    backup = target.with_suffix(".bak")

    if not target.is_file() and not backup.is_file():
        print("当前仓库没有装 hook，无需卸载")
        return 0

    # 存在的 hook 既不是我们装的、也没有备份 —— 那是别人（或用户自己）的东西，别碰。
    if target.is_file() and not _is_ours(target) and not backup.is_file():
        print("当前 hook 不是门禁装的，不做改动")
        return 0

    if target.is_file():
        target.unlink()

    # 有备份就恢复；但如果备份本身就是门禁（旧版本重复安装造成的），直接扔掉。
    if backup.is_file():
        if _is_ours(backup):
            backup.unlink()
            print("已卸载（备份是门禁自身，没有需要恢复的原 hook）")
        else:
            shutil.copyfile(backup, target)
            backup.unlink()
            print("已卸载，并恢复原 hook（来自备份）")
    else:
        print("已卸载")

    return 0


def status(root: Path) -> int:
    target = hook_target(root)
    if target.is_file():
        print(f"已安装：{target}")
        print("----- 内容 -----")
        print(target.read_text(encoding="utf-8"))
    else:
        print("未安装")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="安装/卸载提交门禁 hook")
    parser.add_argument("--uninstall", action="store_true", help="卸载 hook")
    parser.add_argument("--status", action="store_true", help="查看当前状态")
    args = parser.parse_args(argv)

    root = repo_root()

    if args.status:
        return status(root)
    if args.uninstall:
        return uninstall(root)
    return install(root)


if __name__ == "__main__":
    sys.exit(main())
