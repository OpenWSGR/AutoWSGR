#!/usr/bin/env pwsh
<#
.SYNOPSIS
    一键运行所有 UI 控制器 e2e 测试的 PowerShell 包装脚本。

.DESCRIPTION
    直接调用 run_all_e2e.py，支持所有相同的命令行参数。

.EXAMPLE
    # 自动检测设备，运行所有测试
    .\run_all_e2e.ps1

    # 指定设备
    .\run_all_e2e.ps1 -Serial emulator-5554

    # 启用调试，自定义等待时间
    .\run_all_e2e.ps1 -Debug -Pause 2.0

    # 指定汇总报告输出路径
    .\run_all_e2e.ps1 -Output my_report.json
#>

[CmdletBinding()]
param(
    [string]$Serial,
    [switch]$Debug,
    [double]$Pause = 1.5,
    [int]$Parallel = 1,
    [switch]$NoCleanup,
    [string]$Output = "logs/e2e_summary.json"
)

# 获取脚本目录
$ScriptDir = Split-Path -Parent $PSCommandPath

# 构建 Python 命令行参数
$PyArgs = @()

if ($Serial) {
    $PyArgs += "--serial", $Serial
}

if ($Debug) {
    $PyArgs += "--debug"
}

if ($Pause -ne 1.5) {
    $PyArgs += "--pause", $Pause.ToString()
}

if ($Parallel -ne 1) {
    $PyArgs += "--parallel", $Parallel.ToString()
}

if ($NoCleanup) {
    $PyArgs += "--no-cleanup"
}

if ($Output) {
    $PyArgs += "--output", $Output
}

# 运行 Python 脚本
Write-Host "运行 e2e 自动化脚本..."
Write-Host ""

python "$ScriptDir\run_all_e2e.py" @PyArgs
$ExitCode = $LASTEXITCODE

exit $ExitCode
