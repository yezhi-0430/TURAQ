# 启动后端服务指南

## 前置条件

1. 确保已安装 Python 3.11+
2. 确保虚拟环境已激活
3. 确保已配置环境变量（.env 文件）

## 启动步骤

### 1. 激活虚拟环境

在项目根目录 `C:\Users\LENOVO\Documents\Codex\2026-09-20\n\outputs\a-share-risk-agent` 运行：

```bash
# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

### 2. 检查环境变量

确保 `.env` 文件包含：

```env
ANTHROPIC_API_KEY=your_api_key_here
# 或者
OPENAI_API_KEY=your_api_key_here
```

### 3. 启动服务器

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

或者使用更简单的命令：

```bash
python -m uvicorn app.main:app --reload
```

### 4. 验证服务

打开浏览器访问：
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

## 测试 Agent API

使用 curl 测试：

```bash
curl -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "从 10 到 11 的变化率是多少？"}
    ],
    "max_rounds": 5
  }'
```

## 常见问题

### 问题 1：端口被占用
```bash
# 使用其他端口
uvicorn app.main:app --reload --port 8001
```

### 问题 2：找不到模块
```bash
# 确保在项目根目录
cd C:\Users\LENOVO\Documents\Codex\2026-09-20\n\outputs\a-share-risk-agent

# 重新激活虚拟环境
.venv\Scripts\activate
```

### 问题 3：API Key 未配置
- 检查 `.env` 文件是否存在
- 检查环境变量是否正确设置
- 重启服务器使环境变量生效

## 前端连接

前端会自动连接到 `http://localhost:8000/api/v1/agent/chat`

确保：
1. 后端服务已启动
2. CORS 已配置（已在 main.py 中添加）
3. 前端使用的 API 地址正确
