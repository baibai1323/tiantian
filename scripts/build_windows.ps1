# Windows 打包脚本：构建前端 -> PyInstaller 目录版 -> Inno Setup 安装包（可选）
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    throw "找不到虚拟环境：$Python。请先按 README 创建 .venv 并安装依赖。"
}

Write-Host '==> 1/4 安装/更新打包依赖' -ForegroundColor Cyan
& $Python -m pip install -r backend\requirements-dev.txt

Write-Host '==> 2/4 构建前端' -ForegroundColor Cyan
Push-Location frontend
& npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw '前端构建失败' }
Pop-Location

Write-Host '==> 3/4 PyInstaller 打包' -ForegroundColor Cyan
$PyInstaller = Join-Path $Root '.venv\Scripts\pyinstaller.exe'
& $PyInstaller --noconfirm --clean --windowed --name TianTianJiZhang --onedir `
    --add-data "frontend/dist;frontend/dist" `
    --paths backend `
    --hidden-import uvicorn.logging `
    --hidden-import uvicorn.loops.auto `
    --hidden-import uvicorn.protocols.http.auto `
    --hidden-import uvicorn.protocols.websockets.auto `
    --hidden-import uvicorn.lifespan.on `
    --collect-submodules webview `
    run.py

if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 打包失败' }

# 非系统盘（如 D:）会被 .NET 判定为远程来源，exe 旁放配置以允许加载程序集。
$ExeConfig = Join-Path $Root 'dist\TianTianJiZhang\TianTianJiZhang.exe.config'
@'
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <runtime>
    <loadFromRemoteSources enabled="true" />
  </runtime>
</configuration>
'@ | Set-Content -Path $ExeConfig -Encoding UTF8

Write-Host '==> 4/4 Inno Setup 安装包' -ForegroundColor Cyan
$Iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
if (-not $Iscc) {
    $Candidates = @(
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        'C:\Program Files\Inno Setup 6\ISCC.exe'
    )
    $Iscc = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if ($Iscc) {
    New-Item -ItemType Directory -Force -Path release | Out-Null
    & $Iscc 'scripts\tiantian.iss'
} else {
    Write-Warning '未找到 Inno Setup，跳过安装包。目录版已生成：dist\TianTianJiZhang\'
}

Write-Host '完成。' -ForegroundColor Green
Write-Host '免安装目录版：dist\TianTianJiZhang\TianTianJiZhang.exe'
if ($Iscc) { Write-Host '安装包：release\' }
