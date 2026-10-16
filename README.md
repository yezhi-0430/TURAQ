# TURAQ - A 股智能研究平台

## 项目概述

TURAQ 是一个基于 AI Agent 的 A 股智能研究平台，集成了行情监控、风险分析、智能对话等功能。

## 技术栈

### 后端
- **FastAPI** - Web 框架
- **SQLAlchemy** - ORM
- **Qwen / 隔离假模型** - 由后端 `MODEL_PROVIDER` 选择，页面明确显示模式
- **Python 3.11+**

### 前端
- **纯 HTML/CSS/JavaScript** - 无框架依赖
- **黑金配色设计**
- **响应式布局**

## 快速开始

### Windows 一键启动（本项目环境已安装）

双击根目录 **`一键启动.bat`**（或 `start.bat`），自动启动 FastAPI（8888）与 Vite（3000），就绪后打开 `http://localhost:3000`。服务在后台运行，关闭启动窗口不会停止服务。双击 **`停止服务.bat`** 可一起停止前后端。

重复启动会复用本项目的健康进程；其他程序占用端口时会提示，不会强制结束它。首次缺少风险表时，先备份 PostgreSQL 再创建新增表。日志和备份位于 `.local-backups/launcher/`。需要已配置 `.env`、项目虚拟环境、前端依赖和运行中的 PostgreSQL；不会每次启动重复安装依赖或改写 `.env`。

### 1. 后端启动

```powershell
# 进入项目目录
cd C:\Users\LENOVO\Documents\Codex\2026-09-20\n\outputs\a-share-risk-agent

# 安装项目依赖（包含调度器）
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'

# 首次启用账号时，先备份数据库，再显式升级；存在历史分组时需指定已验证所有者
# .\.venv\Scripts\python.exe -m app.schema_upgrade --help

# 本地 HTTP 开发，必须与浏览器访问地址一致
$env:SITE_BASE_URL = 'http://localhost:3000'
$env:AUTH_COOKIE_SECURE = 'false'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8888
```

账号、数据库升级与验收说明见 [本地验收记录](docs/auth-local-acceptance.md)。数据库使用 PostgreSQL；配置字段见 `.env.example`。本地 HTTP 的 Cookie 设置仅用于开发，正式站点使用 HTTPS 和 Secure Cookie。

### 2. 前端访问

另开终端运行 Vite，让页面和 API 使用同一个站点：
```powershell
cd frontend
npm install
npm run dev
```

然后访问 `http://localhost:3000`，点击“进入工作台”登录。不能直接打开 HTML 或用不代理 API 的静态服务器。邮件服务尚未配置时，已有已验证账号可登录，公开注册和找回密码暂不可用。完整前端说明见 [frontend/README.md](frontend/README.md)。

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
   - 行情驾驶舱、分钟分时与独立 K 线详情；公开源失联时保留旧数据并标记

4. **账号与操作边界**
   - 邮箱密码登录、可复用邀请码及邮箱验证流程
   - 用户自选分组隔离、CSRF 防护、调用额度与有限超时
   - AI 建议需用户确认，执行结果与审计由后端记录

### 🚧 待完善

1. **风险监控** - 风险指标计算和预警
2. **模拟交易** - 回测和模拟交易功能
3. **系统设置** - 用户偏好设置
4. **公开注册上线** - 真实邮件送达、服务器及 HTTPS 配置仍待验收

## API 文档

启动后端后访问：
- Swagger UI: http://localhost:8888/docs
- ReDoc: http://localhost:8888/redoc

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
│   └── index.html           # 页面入口；脚本/CSS 由 Vite 打包
├── .env                     # 环境变量（需创建）
└── docs/auth-local-acceptance.md # 本地账号与验收说明
```

## 环境配置

按 `.env.example` 填写 PostgreSQL 和模型配置。实际支持 `MODEL_PROVIDER=fake` 或 `qwen`；Qwen 使用 `DASHSCOPE_API_KEY`。`MODEL_ENABLED=false` 可停止研究调用而保留自选和行情。密钥只保存在本机配置中，不提交 Git。真实邮件与服务器配置留待最后验收。

## 开发建议

### 前端开发
1. 修改 `frontend/index.html`
2. 刷新浏览器查看效果
3. 使用浏览器开发者工具调试

### 后端开发
1. 修改 `app/` 目录下的 Python 文件
2. 开发时可添加 `--reload`，普通启动需重启后应用改动
3. 查看 Swagger 文档测试 API

### 数据库
正式开发数据使用 PostgreSQL，连接配置以 `.env.example` 为准。SQLite 仅用于隔离测试夹具；测试数据库与日常开发数据库分开。升级前备份，历史分组归属由操作者显式指定。

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
