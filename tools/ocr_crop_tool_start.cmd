@echo off
chcp 65001 >nul
cd /d "%~dp0"
main.exe --help
echo.
echo 当前目录已经切换到工具目录，可以输入 main.exe adb、main.exe team 或 main.exe pool。
echo.
%COMSPEC% /k
