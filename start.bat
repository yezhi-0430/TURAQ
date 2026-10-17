@echo off
chcp 65001 >nul
setlocal
title TURAQ 一键启动
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo 未找到项目 Python 环境，请先完成 README 中的依赖安装。
    pause
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\launch_turaq.py" %*
if errorlevel 1 (
    echo.
    echo 启动未完成。请查看上方原因和 .local-backups\launcher\ 中的日志。
    pause
    exit /b 1
)
echo.
echo 前后端已在后台运行。关闭此窗口不会停止服务。
timeout /t 3 >nul 2>&1
exit /b 0
