# Git 常用操作速查（天天记账专用）

> 仓库位置：`D:\dsh-work\tiantian`　分支：`main`　远端：`origin` → GitHub 私有仓库
> 在 PowerShell 里执行，路径先切到项目：

```powershell
cd D:\dsh-work\tiantian
```

---

## 一、先理解四个词

| 词 | 白话 |
| --- | --- |
| 工作区 | 你现在看到的文件，改了但还没记录 |
| 暂存区 | 你挑出来、准备放进这次快照的改动（`git add` 之后） |
| 本地仓库 | 已经拍好的快照，存在 `.git` 里（`git commit` 之后） |
| 远端 | GitHub 上的副本（`git push` 之后） |

一次完整的保存 = `add`（挑改动）→ `commit`（拍快照）→ `push`（传云端）。

---

## 二、每天必用的 7 条

```powershell
git status                 # 现在改了哪些文件（最常用，迷路就问它）
git diff                   # 具体改了哪几行
git add .                  # 把当前目录所有改动放进暂存区
git add backend/app/main.py # 只挑一个文件
git commit -m "修复：首页金额不刷新"   # 拍快照，说明写清楚
git log --oneline          # 看历史快照（一行一条）
git push                   # 传到 GitHub
```

拉取别人的改动（换电脑、或在 GitHub 网页上改过东西时）：

```powershell
git pull
```

> 口诀：**改完先 status，看 diff，add，commit，push。**

---

## 三、撤销：按“改到哪一步”选

### 1. 改了，但还没 add —— 想丢弃

```powershell
git restore backend/app/main.py   # 丢弃这个文件的改动
git restore .                     # 丢弃所有未暂存的改动（小心）
```

### 2. 已经 add，但还没 commit —— 想拿出来

```powershell
git restore --staged backend/app/main.py
```

### 3. 已经 commit，但还没 push —— 想改说明或补文件

```powershell
git add 忘了的文件.py
git commit --amend -m "新的说明"
```

### 4. 已经 commit 也想 push 了，但想撤销这次提交

安全做法（新增一次“反向提交”，历史保留）：

```powershell
git log --oneline          # 找到要撤销的那次，复制开头 7 位
git revert 3f2a1bc
```

### 5. 想整个项目回到某次提交（危险，会丢之后的改动）

```powershell
git reset --hard 3f2a1bc   # 本地回到那次提交，之后的改动全没
```

> 做这一步之前先 `git status` 确认没有没提交的东西，或者先 `git stash`。
> 已经 push 过的提交不要随便 reset，否则推送会被拒绝；用 `revert` 更安全。

### 6. 只想把某个文件恢复成旧版本

```powershell
git log --oneline -- backend/app/main.py   # 看这个文件的历史
git checkout 3f2a1bc -- backend/app/main.py
```

---

## 四、临时存一下（改到一半要切走）

```powershell
git stash          # 把没提交的改动收进抽屉
git stash list     # 看抽屉里有什么
git stash pop      # 拿出来继续
```

---

## 五、分支（试验新功能时用）

```powershell
git switch -c feature-import   # 新建并切到分支
# ……改代码、add、commit……
git switch main                # 回主线
git merge feature-import       # 把分支合进来
git branch -d feature-import   # 合完删掉分支
```

个人小项目可以直接在 `main` 上做，分支不是必须的。

---

## 六、标签（标记“这个版本能交付”）

```powershell
git tag -a v0.3.0 -m "v0.3.0：新增预算功能"
git push origin v0.3.0
git tag                        # 看所有标签
```

---

## 七、和 GitHub 打交道

```powershell
git remote -v                  # 看远端地址
git push -u origin main        # 第一次推送时绑定
git clone https://github.com/用户名/仓库.git   # 换电脑时拉下来
```

登录方式：

- 现在用的是 **PAT（个人访问令牌）**，Windows 凭据管理器已经记住
- GitHub 不支持用账号密码推代码；令牌泄露要立刻去 GitHub 撤销
- 不想敲命令，可以装 **GitHub Desktop**，图形界面点按钮就行

网页上能做的事：

- 建仓库、改可见性（私有/公开）
- 看提交历史、对比差异
- 在 Actions 页看自动打包进度、下载安装包
- 在 Settings → Developer settings 管理令牌

---

## 八、哪些东西绝对不能提交

- 密码、令牌、`gh_token.txt` 这类文件
- 数据库文件（本项目存在 `%APPDATA%`，本来就不在仓库里）
- `release/` 安装包、`node_modules/`、`.venv/`、`dist/`、`build/`

这些已经写进 `.gitignore`。如果发现敏感文件被提交了：

```powershell
git rm --cached 文件名     # 从 Git 里移除，但保留本地文件
```

然后**立刻去撤销对应的密码/令牌**，因为历史里已经有了。

---

## 九、出错了怎么办

| 症状 | 处理 |
| --- | --- |
| 不知道自己改了啥 | `git status` + `git diff` |
| 提交说明写错 | `git commit --amend`（没 push 时） |
| 想撤销某次提交 | `git revert <hash>` |
| push 被拒绝（non-fast-forward） | 先 `git pull`，有冲突就解决，再 `git push` |
| 冲突了 | 打开冲突文件，找 `<<<<<<<`，保留要的代码，删掉标记，`git add` → `git commit` |
| 误删文件 | `git restore 文件名` |
| 想看看某次提交改了什么 | `git show <hash>` |

---

## 十、每天 30 秒的固定动作

```powershell
cd D:\dsh-work\tiantian
git status
git add .
git commit -m "一句话说明这次改了什么"
git push
```

养成“完成一个小功能就提交一次”的习惯，比攒一周再提交安全得多。
