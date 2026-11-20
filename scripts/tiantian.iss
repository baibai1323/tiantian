; 天天记账 Windows 安装包脚本（Inno Setup 6）
; 用法：先运行 scripts\build_windows.ps1，或用 ISCC.exe 编译本文件。

#define MyAppName "天天记账"
; 版本号由 build_windows.ps1 从 backend/app/config.py 读取后通过 /DMyAppVersion 传入；
; 直接双击 ISCC 编译时才用下面的兜底值，避免脚本单独跑时报「未定义」。
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppPublisher "TianTian"
#define MyAppExeName "TianTianJiZhang.exe"

[Setup]
AppId={{8E4B6F2A-3C1D-4A6B-9E7F-2D5C8A1B3E64}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\TianTianJiZhang
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=TianTianJiZhang-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\TianTianJiZhang\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
