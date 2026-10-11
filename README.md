# TURAQ - A 股智能研究平台

## 项目概述

TURAQ 是一个基于 AI Agent 的 A 股智能研究平台，集成了行情监控、风险分析、智能对话等功能。

## 技术栈

### 后端
- **FastAPI** - Web 框架
- **SQLAlchemy** - ORM
- **Anthropic Claude / OpenAI** - LLM 服务
- **Python 3.11+**

### 前端
- **纯 HTML/CSS/JavaScript** - 无框架依赖
- **黑金配色设计**
- **响应式布局**

## 快速开始

### 1. 后端启动

```bash
# 进入项目目录
cd C:\Users\LENOVO\Documents\Codex\2026-09-20\n\outputs\a-share-risk-agent

# 激活虚拟环境
.venv\Scripts\activate

# 已有数据库先升级（Day 13 新增审计来源列；可重复运行）
python -m app.schema_upgrade

# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

详细说明见 [START_BACKEND.md](./START_BACKEND.md)

### 2. 前端访问

直接用浏览器打开：
```
frontend/index.html
```

或者使用简单的 HTTP 服务器：
```bash
cd frontend
python -m http.server 3000
```

然后访问 `http://localhost:3000`

## 核心功能

### ✅ 已实现

1. **AI 研究助手**
   - 自然语言对话
   - 工具调用（计算变化率、查询股票、查询日线数据）
   - 实时显示工具执行过程

2. **自选股管理**
   - 创建自选组
   - 添加/删除股票
   - 查询自选股列表

3. **行情数据**
   - 股票基本信息
   - 日线数据导入/查询

### 🚧 待完善

1. **行情驾驶舱** - 实时行情监控面板
2. **风险监控** - 风险指标计算和预警
3. **模拟交易** - 回测和模拟交易功能
4. **系统设置** - 用户偏好设置

## API 文档

启动后端后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 主要端点

```
POST /api/v1/agent/chat          # AI 对话
GET  /api/v1/watchlists           # 获取自选组列表
POST /api/v1/watchlists           # 创建自选组
GET  /api/v1/stocks               # 搜索股票
POST /api/v1/stocks/{symbol}/daily-prices  # 导入日线数据
```

## 项目结构

```
a-share-risk-agent/
├── app/
│   ├── main.py              # FastAPI 应用入口
│   ├── agent_api.py         # Agent 对话 API
│   ├── agent_loop.py        # Agent 执行循环
│   ├── llm_client.py        # LLM 客户端
│   ├── database.py          # 数据库模型
│   ├── tools/
│   │   ├── market_data.py   # 市场数据工具
│   │   ├── calculations.py  # 计算工具
│   │   └── executor.py      # 工具执行器
│   └── watchlists/          # 自选股模块
├── frontend/
│   └── index.html           # 单文件前端应用
├── .env                     # 环境变量（需创建）
└── START_BACKEND.md         # 后端启动指南
```

## 环境配置

创建 `.env` 文件：

```env
# 使用 Anthropic Claude
ANTHROPIC_API_KEY=your_anthropic_api_key

# 或者使用 OpenAI
OPENAI_API_KEY=your_openai_api_key
```

## 开发建议

### 前端开发
1. 修改 `frontend/index.html`
2. 刷新浏览器查看效果
3. 使用浏览器开发者工具调试

### 后端开发
1. 修改 `app/` 目录下的 Python 文件
2. FastAPI 会自动重载（使用 `--reload` 参数）
3. 查看 Swagger 文档测试 API

### 数据库
```bash
# 查看数据库
sqlite3 data/watchlists.db

# 常用命令
.tables          # 查看所有表
.schema stocks   # 查看表结构
SELECT * FROM stocks;  # 查询数据
```

## 设计特点

### 黑金配色
- **主色调**：#0A0A0A (纯黑)
- **金色强调**：#D4AF37 (古典金)
- **亮金色**：#FFD700
- **表面层**：#141414, #1E1E1E

### 交互效果
- 80 个金色漂浮粒子
- 径向渐变背景跟随鼠标
- 网格背景缓慢移动动画
- 标题呼吸灯发光效果

## 部署建议

### 后端部署
```bash
# 使用 gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker

# 使用 Docker
docker build -t turaq-backend .
docker run -p 8000:8000 turaq-backend
```

### 前端部署
- 静态文件托管（Nginx、Apache）
- CDN 加速
- 或集成到后端（FastAPI 静态文件服务）

## 贡献指南

1. Fork 本项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可证

MIT License

## 联系方式

项目维护者：[Your Name]

---

**注意**：本项目仅供学习和研究使用，不构成任何投资建议。
