# TURAQ 后端 API 使用指南

## 📖 完整使用步骤

### 第一步：环境准备

#### 1.1 进入项目目录
```bash
cd C:\Users\LENOVO\Documents\Codex\2026-09-20\n\outputs\a-share-risk-agent
```

#### 1.2 激活虚拟环境
```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# 或 Windows CMD
.venv\Scripts\activate.bat

# 或 Git Bash
source .venv/Scripts/activate
```

#### 1.3 检查依赖
```bash
pip list | grep -E "fastapi|sqlalchemy|uvicorn|pydantic"
```

---

### 第二步：初始化数据库

#### 2.1 创建数据库表
```bash
python << 'EOF'
from app.database import create_tables

print("初始化数据库表...")
create_tables()
print("✓ 数据库初始化成功！")
EOF
```

#### 2.2 验证初始化
```bash
# 连接数据库检查表
psql -U <user> -d <database> -c "\dt"
# 应该看到 tool_audit_records 表
```

---

### 第三步：启动后端服务

#### 方式 1：简单启动（推荐用于开发）
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 9001
```

**输出示例**：
```
INFO:     Uvicorn running on http://127.0.0.1:9001 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

#### 方式 2：热重载模式（开发时自动重新加载）
```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 9001
```

#### 方式 3：后台运行（Linux/Mac）
```bash
nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 9001 > server.log 2>&1 &
```

#### 方式 4：后台运行（Windows PowerShell）
```powershell
Start-Process -NoNewWindow python -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 9001"
```

---

### 第四步：测试 API

#### 4.1 健康检查
```bash
curl http://127.0.0.1:9001/health
```

**预期响应**：
```json
{"status": "ok"}
```

#### 4.2 测试 Agent 对话

**使用 Python requests**：
```python
import requests
import json

url = "http://127.0.0.1:9001/api/v1/agent/chat"
payload = {
    "messages": [
        {"role": "user", "content": "从 10 到 11 的变化率是多少？"}
    ],
    "max_rounds": 5
}

response = requests.post(url, json=payload)
data = response.json()

print(f"运行 ID: {data['run_id']}")
print(f"状态: {data['status']}")
print(f"答案: {data['answer']}")
print(f"工具执行数: {len(data['executions'])}")
```

**使用 curl**：
```bash
curl -X POST http://127.0.0.1:9001/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "从 10 到 11 的变化率是多少？"}
    ],
    "max_rounds": 5
  }'
```

**预期响应** (200 OK)：
```json
{
  "run_id": "c27876df-cc6a-4b9e-af90-ef832d27fd87",
  "status": "completed",
  "answer": "从 10 到 11 的变化率是 **10.0000%**（即上涨 10%）。",
  "rounds": 2,
  "executions": [
    {
      "tool_name": "calculate_change",
      "arguments": {
        "current_close": 11,
        "previous_close": 10
      },
      "status": "success",
      "result": "{\"change_percent\": \"10.0000\"}",
      "error": null,
      "duration_ms": 0.10
    }
  ]
}
```

---

### 第五步：运行完整测试套件

#### 5.1 使用测试脚本
```bash
python test_backend_final.py
```

#### 5.2 查看测试输出
```
============================================================
TURAQ 后端 API 完整测试
============================================================

=== 测试 1: 健康检查 ===
状态码: 200
[OK] PASSED

=== 测试 2: Agent 对话 ===
状态码: 200
运行 ID: c27876df-cc6a-4b9e-af90-ef832d27fd87
状态: completed
轮次: 2
答案: 从 10 到 11 的变化率是 **10.0000%**...
工具执行数: 1
  工具 1: calculate_change
    状态: success
    Duration: 0.10ms
[OK] PASSED

============================================================
ALL TESTS PASSED - Backend API is working!
============================================================
```

---

### 第六步：使用 API 文档

#### 6.1 访问 Swagger UI
```
http://127.0.0.1:9001/docs
```

#### 6.2 访问 ReDoc
```
http://127.0.0.1:9001/redoc
```

#### 6.3 在 Swagger 中测试
1. 打开 http://127.0.0.1:9001/docs
2. 找到 `POST /api/v1/agent/chat`
3. 点击 "Try it out"
4. 输入示例数据
5. 点击 "Execute"

---

## 🔧 常见操作

### 查询审计记录

```python
from app.audit.repository import list_tool_executions

# 查询特定 run_id 的工具执行记录
run_id = "c27876df-cc6a-4b9e-af90-ef832d27fd87"
records = list_tool_executions(run_id, limit=20)

for record in records:
    print(f"Tool: {record.tool_name}")
    print(f"Status: {record.status}")
    print(f"Duration: {record.duration_ms}ms")
```

### 查看数据库中的记录

```bash
# 连接到 PostgreSQL
psql -U <user> -d <database>

# 查询工具审计记录
SELECT run_id, tool_name, status, duration_ms, created_at 
FROM tool_audit_records 
ORDER BY created_at DESC 
LIMIT 10;
```

### 停止服务器

```bash
# Ctrl+C (在运行的终端中)
# 或者查找进程并杀死
ps aux | grep uvicorn
kill -9 <PID>
```

---

## 🚨 常见问题排除

### 问题 1: 端口被占用
**错误信息**：
```
ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 9001)
```

**解决方案**：
```bash
# 查看占用端口的进程
netstat -ano | grep 9001

# 杀死进程
taskkill /PID <PID> /F

# 使用其他端口
python -m uvicorn app.main:app --port 9002
```

### 问题 2: 数据库表不存在
**错误信息**：
```
psycopg.errors.UndefinedTable: relation "tool_audit_records" does not exist
```

**解决方案**：
```python
from app.database import create_tables
create_tables()  # 初始化所有表
```

### 问题 3: LLM 配置错误
**错误信息**：
```
ModelConfigurationError: 千问模式需要 DASHSCOPE_API_KEY
```

**解决方案**：
检查 `.env` 文件：
```bash
# 查看 .env 文件
cat .env

# 确保设置了 API Key
# DASHSCOPE_API_KEY=your_key_here
# 或
# ANTHROPIC_API_KEY=your_key_here
```

### 问题 4: 导入错误
**错误信息**：
```
ImportError: cannot import name 'X' from 'app.Y'
```

**解决方案**：
```bash
# 清除 Python 缓存
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete

# 重新启动服务器
python -m uvicorn app.main:app --port 9001
```

---

## 📊 API 端点总览

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/v1/agent/chat` | AI 对话 (核心功能) |
| GET | `/api/v1/watchlists` | 获取自选组 |
| POST | `/api/v1/watchlists` | 创建自选组 |
| POST | `/api/v1/watchlists/{id}/stocks` | 添加股票 |
| GET | `/api/v1/stocks` | 搜索股票 |

---

## 💡 最佳实践

### 1. 请求处理
```python
import requests

def chat_with_agent(user_message, max_rounds=5):
    """与 Agent 对话"""
    try:
        response = requests.post(
            "http://127.0.0.1:9001/api/v1/agent/chat",
            json={
                "messages": [{"role": "user", "content": user_message}],
                "max_rounds": max_rounds
            },
            timeout=30  # 设置超时
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        return None
```

### 2. 错误处理
```python
data = chat_with_agent("从 10 到 11 的变化率是多少？")

if data:
    if data['status'] == 'completed':
        print(f"答案: {data['answer']}")
        print(f"工具调用: {len(data['executions'])}")
    else:
        print(f"未完成。状态: {data['status']}, 轮次: {data['rounds']}")
else:
    print("请求失败")
```

### 3. 并发请求
```python
import concurrent.futures

questions = [
    "从 10 到 11 的变化率是多少？",
    "从 100 到 110 的变化率是多少？",
    "从 50 到 100 的变化率是多少？"
]

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(chat_with_agent, q) for q in questions]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]

for result in results:
    print(f"答案: {result['answer']}")
```

---

## 📝 日志查看

### 实时查看日志
```bash
# Linux/Mac
tail -f server.log

# Windows PowerShell
Get-Content server.log -Wait
```

### 启用详细日志
```bash
python -m uvicorn app.main:app --log-level debug --port 9001
```

---

## ✅ 验证清单

启动服务后，逐项检查：

- [ ] 服务器成功启动 (看到 "Application startup complete")
- [ ] 健康检查通过 (`curl http://127.0.0.1:9001/health` 返回 200)
- [ ] 数据库表存在 (运行 `create_tables()`)
- [ ] Agent 对话工作 (收到完整响应)
- [ ] 工具执行成功 (executions 数组有数据)
- [ ] 审计记录保存 (检查数据库)

---

## 🎓 下一步

1. **集成到前端** - 连接前端界面到此 API
2. **添加用户认证** - 实现用户登录和权限
3. **扩展工具** - 添加更多的股票分析工具
4. **性能优化** - 添加缓存和异步处理
5. **部署** - 使用 Docker 容器化部署

---

**注意**：确保所有步骤按顺序完成，特别是第二步（数据库初始化）必须在第三步（启动服务）之前完成。
