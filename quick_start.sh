#!/bin/bash

# TURAQ 后端快速启动脚本

echo "=================================================="
echo "TURAQ - A 股智能研究平台"
echo "快速启动脚本"
echo "=================================================="

# 定义颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 第一步：进入项目目录
echo ""
echo -e "${YELLOW}第一步：进入项目目录...${NC}"
cd "$(dirname "$0")" || exit 1
echo -e "${GREEN}✓ 已进入项目目录${NC}"

# 第二步：激活虚拟环境
echo ""
echo -e "${YELLOW}第二步：激活虚拟环境...${NC}"
if [ -d ".venv" ]; then
    source .venv/Scripts/activate
    echo -e "${GREEN}✓ 虚拟环境已激活${NC}"
else
    echo -e "${RED}✗ 虚拟环境不存在${NC}"
    exit 1
fi

# 第三步：初始化数据库
echo ""
echo -e "${YELLOW}第三步：初始化数据库...${NC}"
python << 'EOF'
try:
    from app.database import create_tables
    print("正在创建数据库表...")
    create_tables()
    print("✓ 数据库初始化成功！")
except Exception as e:
    print(f"✗ 数据库初始化失败: {e}")
    exit(1)
EOF

# 第四步：启动服务
echo ""
echo -e "${YELLOW}第四步：启动后端服务...${NC}"
echo -e "${GREEN}服务启动在 http://127.0.0.1:9001${NC}"
echo ""
echo "其他有用的 URL:"
echo "  - Swagger UI: http://127.0.0.1:9001/docs"
echo "  - ReDoc: http://127.0.0.1:9001/redoc"
echo ""
echo -e "${YELLOW}按 Ctrl+C 停止服务${NC}"
echo ""

python -m uvicorn app.main:app --host 127.0.0.1 --port 9001
