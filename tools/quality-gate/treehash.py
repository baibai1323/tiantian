"""工作区内容哈希：把「检查结果」和「当时的代码」绑在一起。

为什么需要它：agent 检查完代码后，如果代码又被改过，检查结果就失效了。
marker 里存一份哈希，提交前重算一遍，对不上就说明「检查之后代码动过」，
必须重跑检查。没有这个绑定，marker 文件只是一句空口承诺。

哈希口径（都算进去）：
- 已跟踪文件的工作区内容（不是 HEAD 里的版本，是磁盘上的）
- 未被 .gitignore 忽略的新文件
不算的：.git 目录本身、被忽略的文件（venv、dist、__pycache__ 等）。
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path


def _git(*args: str, cwd: Path) -> bytes:
    """跑一条 git 命令并返回原始字节输出；失败直接抛异常，不静默吞掉。"""
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} 失败：{result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return result.stdout


def repo_root(start: Path | None = None) -> Path:
    """找到仓库根目录。

    依次尝试：调用方指定的目录 → 当前工作目录 → 本文件所在目录。
    加最后一个是为人跑方便：在任意目录执行 `python tools/quality-gate/gate.py`
    也能定位到仓库，不用先 cd。
    """
    candidates = [start] if start else [Path.cwd(), Path(__file__).resolve().parent]

    for candidate in candidates:
        try:
            return Path(_git("rev-parse", "--show-toplevel", cwd=candidate).decode().strip())
        except RuntimeError:
            continue

    raise RuntimeError("找不到 git 仓库：请在仓库目录下运行，或把 tools/quality-gate 放进仓库")


def list_files(root: Path) -> list[bytes]:
    """列出要参与哈希的文件：已跟踪 + 未跟踪但没被忽略。

    -c 是 cached（已跟踪），-o 是 others（未跟踪），--exclude-standard 让 .gitignore 生效。
    -z 用 NUL 分隔，避免中文/空格文件名被转义。
    """
    raw = _git("ls-files", "-co", "--exclude-standard", "-z", cwd=root)
    return sorted(part for part in raw.split(b"\0") if part)


def tree_hash(root: Path | None = None) -> str:
    """返回 "sha256:xxxx" 形式的工作区哈希。"""
    root = Path(root) if root else repo_root()
    digest = hashlib.sha256()

    for raw_rel in list_files(root):
        rel = os.fsdecode(raw_rel)
        # 先喂路径，再喂内容：这样「两个文件互换内容」也会得到不同哈希。
        digest.update(raw_rel)
        digest.update(b"\0")

        path = root / rel
        if path.is_file():
            digest.update(path.read_bytes())
        else:
            # 已跟踪但被删掉的文件（工作区删除、还没 add）也要体现在哈希里。
            digest.update(b"<deleted>")
        digest.update(b"\0")

    return "sha256:" + digest.hexdigest()


if __name__ == "__main__":
    # 直接运行时打印哈希，方便人工排查
    print(tree_hash(sys.argv[1] if len(sys.argv) > 1 else None))
