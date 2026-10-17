#!/bin/bash
# 快速部署脚本 - 本地运行

set -e

echo "🚀 TURAQ 快速启动脚本"
echo "======================"
echo ""

# 检查 Python 环境
if ! command -v python &> /dev/null; then
    echo "❌ 未找到 Python，请先安装 Python 3.11+"
    exit 1
fi

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "📦 创建虚拟环境..."
    python -m venv .venv
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate

# 安装依赖
echo "📥 安装依赖..."
pip install -e . -q

# 检查环境变量
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "⚠️  警告: 未设置 ANTHROPIC_API_KEY 环境变量"
    echo "   请设置后再启动: export ANTHROPIC_API_KEY=your_key"
    echo ""
fi

# 获取本机 IP
echo "📍 你的访问地址："
echo "   本地: http://localhost:8000"
if command -v ipconfig &> /dev/null; then
    # Windows
    IP=$(ipconfig | grep "IPv4" | head -1 | awk '{print $NF}')
    echo "   局域网: http://$IP:8000"
elif command -v ifconfig &> /dev/null; then
    # Mac/Linux
    IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | head -1 | awk '{print $2}')
    echo "   局域网: http://$IP:8000"
fi

echo ""
echo "🎯 启动服务器..."
echo "   按 Ctrl+C 停止"
echo ""

# 启动服务器
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
