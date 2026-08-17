param(
    [string]$PackageRoot = "C:\ShiinaKuroko\01.Project\temp\AutoWSGR-OCR-Crop-Tool"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BuildRoot = Join-Path $RepoRoot ".tmp\ocr-crop-tool"
$DistRoot = Join-Path $BuildRoot "dist"
$WorkRoot = Join-Path $BuildRoot "work"
$AdbRoot = Join-Path $RepoRoot ".venv\Lib\site-packages\adbutils\binaries"
$EntryPoint = Join-Path $PSScriptRoot "ocr_crop_tool.py"

if (Test-Path $PackageRoot) {
    throw "目标目录已经存在，请先确认并移走旧版本：$PackageRoot"
}

$RequiredAdbFiles = @(
    "adb.exe",
    "AdbWinApi.dll",
    "AdbWinUsbApi.dll"
)
foreach ($FileName in $RequiredAdbFiles) {
    $FilePath = Join-Path $AdbRoot $FileName
    if (-not (Test-Path $FilePath)) {
        throw "缺少 ADB 文件：$FilePath"
    }
}

New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null

$PyInstallerArgs = @(
    "run",
    "--with",
    "pyinstaller==6.16.0",
    "pyinstaller",
    "--noconfirm",
    "--clean",
    "--onedir",
    "--console",
    "--noupx",
    "--name",
    "main",
    "--distpath",
    $DistRoot,
    "--workpath",
    $WorkRoot,
    "--specpath",
    $BuildRoot,
    "--collect-all",
    "autowsgr_native",
    "--hidden-import",
    "autowsgr_native._native",
    "--add-binary",
    "$(Join-Path $AdbRoot 'adb.exe');adb",
    "--add-binary",
    "$(Join-Path $AdbRoot 'AdbWinApi.dll');adb",
    "--add-binary",
    "$(Join-Path $AdbRoot 'AdbWinUsbApi.dll');adb",
    $EntryPoint
)

Write-Host "正在生成 main.exe..."
& uv @PyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 打包失败，退出码：$LASTEXITCODE"
}

$GeneratedRoot = Join-Path $DistRoot "main"
if (-not (Test-Path (Join-Path $GeneratedRoot "main.exe"))) {
    throw "打包完成但未找到 main.exe"
}

Move-Item -Path $GeneratedRoot -Destination $PackageRoot
Copy-Item `
    -Path (Join-Path $PSScriptRoot "ocr_crop_tool_README.txt") `
    -Destination (Join-Path $PackageRoot "使用说明.txt")
Copy-Item `
    -Path (Join-Path $PSScriptRoot "ocr_crop_tool_start.cmd") `
    -Destination (Join-Path $PackageRoot "start-tool.cmd")

Write-Host "工具已生成：$PackageRoot"
