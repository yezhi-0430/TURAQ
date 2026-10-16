@echo off
chcp 65001 >nul
setlocal
title TURAQ 停止服务
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\launch_turaq.py" --stop
if errorlevel 1 (
    pause
    exit /b 1
)
timeout /t 3 >nul 2>&1
exit /b 0
