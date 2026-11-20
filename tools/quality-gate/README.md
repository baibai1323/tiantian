# quality-gate · 提交门禁

提交前自动检查：**测试有没有跑过、现在还能不能过、质量问题有没有清零**。不合格就拦住提交。

## 它拦什么

| 检查 | 怎么判 | 为什么 |
|---|---|---|
| tester 凭证 | `.git/quality-gate/tester.json` 存在、`verdict=pass`、指纹与当前工作区一致、12 小时内 | 证明「有人真的跑过测试」 |
| 测试现在过不过 | 门禁**自己再跑一遍** `pytest backend/tests`（约 5 秒） | 凭证是文件，能伪造；命令行的结果不能 |
| quality-engineer 凭证 | 同上的有效性，且 `details.p0 == 0`、`details.p1 == 0` | P2 只记录，不拦提交 |

## 装 / 卸

```powershell
& .venv\Scripts\python.exe tools\quality-gate\install_hooks.py            # 安装
& .venv\Scripts\python.exe tools\quality-gate\install_hooks.py --status   # 看装了没
& .venv\Scripts\python.exe tools\quality-gate\install_hooks.py --uninstall # 卸载
```

hook 只影响当前仓库，不写进版本库，新克隆要重新装一次。

## 三个脚本

| 文件 | 职责 |
|---|---|
| `treehash.py` | 算工作区指纹：`git ls-files -co --exclude-standard` 的路径 + 内容一起哈希 |
| `marker.py` | 写/读/校验凭证，落在 `.git/quality-gate/<agent>.json`（不进 `git status`） |
| `gate.py` | pre-commit 入口，按上表顺序判定，失败时打印「原因 + 下一步」 |

## 手动写凭证（agent 收尾时）

```powershell
& .venv\Scripts\python.exe tools\quality-gate\marker.py write --agent tester --verdict pass --command "pytest backend/tests -q" --summary "198 passed" --p0 0 --p1 0
& .venv\Scripts\python.exe tools\quality-gate\marker.py write --agent quality-engineer --verdict pass --command "四维度审查" --summary "P0=0 P1=0 P2=13" --p0 0 --p1 0 --report "D:\dsh-work\agent开发学习\reports\quality-tiantian-2026-11-20.md"
& .venv\Scripts\python.exe tools\quality-gate\marker.py verify --agent tester   # 自查
```

**凭证记的是写它的那一刻的工作区指纹**。写完凭证之后再动任何文件，凭证立刻失效——这是设计，不是 bug。

## 已知缺口

- `git commit --no-verify` 能绕过，这是 git 自身行为。约定：只在紧急时用，且要在提交信息里写原因。
- 凭证是本地文件，手工伪造 JSON 可以骗过（但骗不过「门禁自己跑测试」这一步）。
- 只覆盖后端 pytest；前端 `npm run test` 目前只在 CI 里跑，没进门禁。
