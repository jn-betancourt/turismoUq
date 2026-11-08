@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_interface.ps1" %*
set "launcher_exit_code=%errorlevel%"
if not "%launcher_exit_code%"=="0" pause
exit /b %launcher_exit_code%
