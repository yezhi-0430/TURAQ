@echo off
REM TURAQ 后端快速启动脚本 (Windows)

echo.
echo ==================================================
echo TURAQ - A 股智能研究平台
echo 快速启动脚本 (Windows)
echo ==================================================
echo.

REM 第一步：进入项目目录
echo [第一步] 进入项目目录...
cd /d "%~dp0"
echo [✓] 已进入项目目录
echo.

REM 第二步：激活虚拟环境
echo [第二步] 激活虚拟环境...
if exist ".venv" (
    call .venv\Scripts\activate.bat
    echo [✓] 虚拟环境已激活
) else (
    echo [✗] 虚拟环境不存在
    pause
    exit /b 1
)
echo.

REM 第三步：初始化数据库
echo [第三步] 初始化数据库...
python << 'EOF'
try:
    from app.database import create_tables
    print("正在创建数据库表...")
    create_tables()
    print("[✓] 数据库初始化成功！")
except Exception as e:
    print(f"[✗] 数据库初始化失败: {e}")
    input("按 Enter 键退出...")
    exit(1)
EOF
echo.

REM 第四步：启动服务
echo [第四步] 启动后端服务...
echo.
echo [✓] 服务启动在 http://127.0.0.1:9001
echo.
echo 其他有用的 URL:
echo   - Swagger UI: http://127.0.0.1:9001/docs
echo   - ReDoc: http://127.0.0.1:9001/redoc
echo.
echo [提示] 按 Ctrl+C 停止服务
echo.

python -m uvicorn app.main:app --host 127.0.0.1 --port 9001

pause
