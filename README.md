# 天天记账 · TianTian

[![Build](https://github.com/baibai1323/tiantian/actions/workflows/build.yml/badge.svg)](https://github.com/baibai1323/tiantian/actions/workflows/build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 一个「只记支出」的桌面记账应用：人民币、两级分类、数据全部留在本机。
> 一套 Vue 3 代码同时服务 Windows 与 macOS，PyWebView 做原生窗口，FastAPI + SQLite 做本地后端。

**它解决的问题**：市面上的记账 App 要么强制登录、要么把账单传到云端、要么功能臃肿。天天记账把“记一笔”压缩到 3 步（金额 → 分类 → 保存），数据只存在你自己的电脑里，每次启动自动备份。

**技术栈**：FastAPI · SQLModel · SQLite · Vue 3 · Element Plus · PyWebView · PyInstaller · GitHub Actions

**产品文档**：[`dsh.md`](dsh.md)——需求、分类体系、每个技术决策的备选方案与取舍理由都在里面。

## 项目亮点

- **一套代码，三种窗口形态**：≥1024px 左侧导航、768–1023px 图标栏、<768px 底部 Tab；没有第二套移动端代码
- **本地优先**：SQLite 单文件，免安装、免登录、断网可用；启动自动备份，保留最近 7 份
- **完整的账单生命周期**：新增 / 编辑 / 软删除（移入独立回收站）/ 恢复 / 彻底删除 / 一键清空，删除与清空都有二次确认
- **CSV 双向**：导出带 UTF-8 BOM（Excel 不乱码），导入按「日期+金额+分类+备注」自动去重，可重复导入
- **可扩展分类**：内置 10 个一级、67 个二级分类；用户可新增、改名、删除自己的分类，删除时账单自动迁到「其他 / 未分类」
- **工程化交付**：PyInstaller 免安装包（Windows）、GitHub Actions 三平台构建（Windows + macOS 双架构）、启动日志与异常兜底

## 界面预览

| 首页 | 账单 |
| --- | --- |
| ![首页](docs/screenshots/home.png) | ![账单](docs/screenshots/bills.png) |

| 统计 | 记一笔 |
| --- | --- |
| ![统计](docs/screenshots/stats.png) | ![记一笔](docs/screenshots/dialog.png) |

| 回收站 | 导入结果 |
| --- | --- |
| ![回收站](docs/screenshots/trash.png) | ![导入](docs/screenshots/import.png) |

| 分类管理 | 删除确认 |
| --- | --- |
| ![分类管理](docs/screenshots/categories.png) | ![删除确认](docs/screenshots/trash-confirm.png) |

## 目录结构

```
tiantian/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI 入口、静态文件、SPA 回退
│   │   ├── config.py        # 数据目录、版本
│   │   ├── db.py            # SQLite、启动备份、建表
│   │   ├── models.py        # Category / Expense / Setting
│   │   ├── schemas.py       # 请求与响应结构
│   │   ├── seed.py          # 10 个一级、67 个二级分类
│   │   ├── services.py      # 共用查询与序列化
│   │   └── routers/         # categories / expenses / stats / export
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/           # 首页、账单、统计、设置
│   │   ├── components/      # 记一笔弹窗
│   │   ├── api.js           # 接口封装
│   │   └── state.js         # 全局状态
│   └── package.json
├── scripts/
│   ├── build_windows.ps1    # Windows 打包
│   └── tiantian.iss         # Inno Setup 安装包脚本
├── run.py                   # 一键启动（内置服务 + 桌面窗口）
└── README.md
```

## 架构

```
┌────────────── 桌面窗口（PyWebView）──────────────┐
│  Vue 3 + Element Plus（构建产物由 FastAPI 托管） │
└───────────────────────┬─────────────────────────┘
                        │ fetch /api/*
┌───────────────────────▼─────────────────────────┐
│ FastAPI（与窗口同进程的线程）                    │
│  routers: categories / expenses / stats /        │
│           export / importer                      │
│  SQLModel ── SQLite（tiantian.db）               │
│  启动时：建表 + 写入默认分类 + 自动备份           │
└──────────────────────────────────────────────────┘
```

**为什么这么选**：

- 桌面壳用 PyWebView：直接复用 Web 界面，安装包约 23 MB，不捆绑 Chromium
- 后端与窗口同进程：用户只需双击一个 exe，没有“先启动服务、再开界面”这一步
- SQLite 单文件：备份 = 复制文件，迁移 = 拷走目录，不需要安装数据库

## 一、准备环境

需要安装：

1. **Python 3.12**（本项目固定用 3.12；**不要用 3.14**，PyWebView 依赖的 pythonnet 在 3.14 下无法加载原生窗口）
2. **Node.js 20 或更高**（自带 npm）

检查：

```powershell
python --version
node --version
npm --version
```

> Windows PowerShell 如果提示「npm.ps1 无法加载」，请把命令里的 `npm` 换成 `npm.cmd`。

## 二、安装依赖

### 1. 后端

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

macOS：

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r backend/requirements.txt
```

### 2. 前端

```powershell
cd frontend
npm.cmd install
cd ..
```

## 三、开发模式

开两个终端。

终端 A（后端，改代码会自动重载）：

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

终端 B（前端，改代码会自动刷新）：

```powershell
cd frontend
npm.cmd run dev
```

浏览器打开 <http://127.0.0.1:5173>。

也可以只用一个命令（后端 + 桌面窗口，前端仍需另开 `npm run dev`）：

```powershell
.\.venv\Scripts\python.exe run.py --dev
```

## 四、正式运行

先构建前端，再启动：

```powershell
cd frontend
npm.cmd run build
cd ..

.\.venv\Scripts\python.exe run.py
```

`run.py` 会自动找一个空闲端口启动内置服务，然后打开桌面窗口。关闭窗口即退出。

只启动后端（不开窗口）：

```powershell
.\.venv\Scripts\python.exe run.py --no-window
```

## 五、数据与备份

| 内容 | 位置 |
| --- | --- |
| 数据库 | `<数据目录>\tiantian.db` |
| 自动备份 | `<数据目录>\backups\`，最多 7 份 |
| 导出 CSV | 设置页或账单页点「导出 CSV」，导出当前月份 |
| 导入 CSV | 设置页「导入账单」，选择本应用导出的 CSV；重复记录自动跳过 |
| 自定义分类 | 设置页「分类管理」，可新增一级/二级分类；自己建的能改名、删除，删除时账单归入「其他 / 未分类」 |
| 回收站 | 侧栏「回收站」，删除的记录先来这里，可恢复、彻底删除或一键清空 |

- 每次启动会自动备份一次数据库。
- 想换位置，可设置环境变量 `TIANTIAN_DATA_DIR` 指向新目录。
- 备份文件是完整数据库副本，改名成 `tiantian.db` 放回数据目录即可恢复。

## 六、打包成安装包

### Windows

前置：安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php)。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

产物：

- `dist\TianTianJiZhang\`：免安装目录版，双击 `TianTianJiZhang.exe` 即可运行
- `release\TianTianJiZhang-Setup-0.5.0.exe`：安装包（需先装 Inno Setup）

当前已构建并验证的免安装包：`release\TianTianJiZhang-0.5.0-win64-portable.zip`（约 23 MB）。v0.5.0 把回收站做成独立页面（侧栏入口、笔数与合计、恢复 / 彻底删除 / 一键清空），删除确认明确写“移入回收站，不是永久删除”；v0.4.0 新增「分类管理」（自定义一级/二级分类，可改名、可删除，删除时账单一并迁到「其他 / 未分类」）；v0.3.1 修复前端文案文件编码损坏导致的构建失败，并新增“彻底删除”；v0.2.0 新增 CSV 导入；v0.1.1 修复了无控制台打包时 `Unable to configure formatter 'default'`（`sys.stderr` 为 None）的启动崩溃。

> Windows 10/11 一般自带 WebView2 运行时；如果窗口白屏，请安装
> [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)。

### macOS

**推荐：用 GitHub Actions 在云端 Mac 上打包**（不需要自己有 Mac 开发环境）

1. 把本目录推到 GitHub 仓库（见下一节）。
2. 打开仓库的 **Actions** 页 → 左侧「Build Desktop App」→ 右侧「Run workflow」。
3. 等约 5–10 分钟，任务完成后在该次运行页面底部下载：
   - `TianTian-macOS-AppleSilicon`：Apple 芯片（M1/M2/M3/M4）用
   - `TianTian-macOS-Intel`：Intel 芯片用
   下载得到的 zip 里还套着一层同名 zip（GitHub 会自动再压一次），解压两层就是 `TianTianJiZhang.app`。
4. 解压得到 `TianTianJiZhang.app`，拖进「应用程序」文件夹。

> 仓库里的 `release/mac/` 已放好这两个包（`apple.zip` / `intel.zip`），不用再自己跑 Actions。
> 两个包已在 Windows 上校验：zip 结构完整，主程序分别是 arm64 / x86_64；尚未在真机 Mac 上启动过。

> 这个包没有 Apple 开发者签名，第一次打开会被 macOS 拦下。解决办法：
> 右键点 App →「打开」→ 再点「打开」；或到「系统设置 → 隐私与安全性」点「仍要打开」。
> 若提示“已损坏”，在终端执行：`xattr -dr com.apple.quarantine /Applications/TianTianJiZhang.app`

**备选：直接在 Mac 上从源码运行/打包**

```bash
cd frontend && npm install && npm run build && cd ..
python3 -m venv .venv
./.venv/bin/python -m pip install -r backend/requirements.txt pyinstaller
./.venv/bin/pyinstaller --noconfirm --clean --windowed --name TianTianJiZhang \
  --add-data "frontend/dist:frontend/dist" --paths backend run.py
```

产物在 `dist/TianTianJiZhang.app`。只运行不打包也可以：`./.venv/bin/python run.py`。

### 用 GitHub Actions 自动构建

仓库里已带 `.github/workflows/build.yml`：推送到 GitHub 后，在 Actions 页面手动运行
「Build Desktop App」，会同时产出 Windows、Apple 芯片 macOS、Intel macOS 三个压缩包。

## 七、常见问题

**1. 打开窗口一片空白**
先确认 `frontend/dist/index.html` 存在（执行过 `npm run build`）。开发模式请访问 5173，而不是后端端口。

**2. 端口被占用**
`run.py` 会自动选空闲端口；开发模式的 8000/5173 被占用时，换端口并同步修改 `vite.config.js` 的代理。

**3. 后端依赖装不上**
把 pip 缓存和临时目录指到项目内，或使用国内镜像：

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**4. 数据库想推倒重来**
关闭应用，删除数据目录里的 `tiantian.db`，下次启动会重新建表并写入默认分类（备份里仍有旧数据）。

**5. Windows 报 `0x80131515` / “从网络位置加载程序集”**
如果项目放在某些非系统盘（本机 D: 就是这种情况），.NET Framework 会把程序集当成“远程来源”拒绝加载。在 Python 解释器旁边放一个 `python.exe.config`，内容：

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <runtime>
    <loadFromRemoteSources enabled="true" />
  </runtime>
</configuration>
```

放到 `.venv\Scripts\python.exe` 和基础 Python 的 `python.exe` 旁边（打包后放到 `TianTianJiZhang.exe` 旁边）。装在 C: 盘通常不需要这一步。

**6. 桌面窗口打不开、自动跳浏览器**
说明 PyWebView 的原生后端加载失败。先确认 Python 是 3.12；仍失败时用 `run.py --no-window` 走浏览器模式，功能完全一样。

**7. 双击 exe 弹 `Unhandled exception ... Unable to configure formatter 'default'`**
v0.1.0 的打包版在“无控制台”模式下启动时会踩到 uvicorn 日志组件的一个问题（`sys.stderr` 为 None）。v0.1.1 起已修复：启动时把 stdout/stderr 接到空设备，并让启动备份失败不阻断应用。请使用 `release\TianTianJiZhang-0.2.0-win64-portable.zip`。

**8. 导入 CSV 时提示“缺少列”或很多无效行**
请用本应用「导出 CSV」得到的文件，不要自己改列名。必填列是：`日期,一级分类,二级分类,金额(元)`，`备注` 可选；日期支持 `2026-11-16`、`2026/11/16`、`2026.11.16`。分类名必须和设置页里的完全一致；对不上的会归入「其他 / 未分类」并在结果里提示。

**9. 同一个 CSV 导入两次会翻倍吗**
不会。按「日期 + 金额 + 一级分类 + 二级分类 + 备注」判断，已存在的记录会跳过，结果框里会显示跳过了多少条。

**10. 能自己加分类吗？删掉分类后账单会怎样**
能。设置页 →「分类管理」可以新增一级/二级分类；系统自带的 10 个大类只能看，不能改名或删除；自己建的可以改名、删除。删除分类时，挂在它下面的账单会迁到「其他 / 未分类」，不会丢，确认框里会先告诉你有几笔。

**11. 删除的账单去哪了？怎么彻底删掉**
不会立刻消失。删除只是移进侧栏的「回收站」，随时可以点「恢复」拿回来；确认不要了，在回收站里点「彻底删除」，或点右上角「清空回收站」一次性抹掉，这两步都无法撤销。

## 八、接口速查

启动后端后打开 <http://127.0.0.1:8000/docs> 可看交互式接口文档。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查、数据目录 |
| GET | `/api/categories` | 两级分类树 |
| GET | `/api/categories/manage` | 分类管理视图（含每类账单数） |
| POST | `/api/categories` | 新增分类（`parent_id` 为空即一级） |
| PATCH | `/api/categories/{id}` | 改名（系统分类 403） |
| DELETE | `/api/categories/{id}` | 删除自定义分类，账单迁到「其他 / 未分类」（系统分类 403） |
| GET | `/api/expenses?month=YYYY-MM` | 账单列表（支持分类、搜索、分页，不含已删除） |
| POST | `/api/expenses` | 新增一笔 |
| PATCH | `/api/expenses/{id}` | 修改 |
| DELETE | `/api/expenses/{id}` | 软删除（移进回收站，可恢复） |
| GET | `/api/expenses/trash` | 回收站列表（按删除时间倒序，含笔数与合计） |
| DELETE | `/api/expenses/trash` | 清空回收站（全部彻底删除） |
| POST | `/api/expenses/{id}/restore` | 恢复（从回收站拿回来） |
| DELETE | `/api/expenses/{id}/permanent` | 彻底删除（仅限已进回收站的记录，不可恢复） |
| GET | `/api/stats/summary?month=YYYY-MM` | 月度汇总、分类占比、二级排行 |
| GET | `/api/stats/trend?months=6` | 近 N 月趋势 |
| GET | `/api/export/csv?month=YYYY-MM` | 导出 CSV |
| POST | `/api/import/csv` | 导入 CSV（JSON 传 `{"content": "..."}`） |

## 九、License

MIT License，见 [LICENSE](LICENSE)。可自由使用、修改、分发，保留版权声明即可。
