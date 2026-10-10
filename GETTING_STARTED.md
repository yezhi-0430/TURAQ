# 🚀 TURAQ 快速入门

> 5 分钟内启动并运行 TURAQ 后端 API

---

## 📋 目录

1. [系统要求](#系统要求)
2. [一键启动](#一键启动)
3. [手动启动](#手动启动)
4. [第一个请求](#第一个请求)
5. [常见问题](#常见问题)

---

## 系统要求

### 硬件
- 内存: 最少 2GB
- 磁盘: 最少 1GB 剩余空间

### 软件
- Python 3.11+
- Git
- 数据库: PostgreSQL (或根据 .env 配置)

### 验证环境
```bash
python --version
# 应该输出 Python 3.11 或更新

psql --version
# 应该输出 PostgreSQL 版本
```

---

## 一键启动

### Windows 用户

1. **打开项目文件夹**
   ```
   C:\Users\LENOVO\Documents\Codex\2026-09-20\n\outputs\a-share-risk-agent
   ```

2. **双击运行**
   ```
   quick_start.bat
   ```

3. **等待启动完成**
   ```
   [✓] 服务启动在 http://127.0.0.1:9001
   ```

### Linux/Mac 用户

```bash
cd ~/path/to/a-share-risk-agent
bash quick_start.sh
```

---

## 手动启动

如果一键启动脚本不工作，按以下步骤手动启动：

### 步骤 1: 打开终端
- **Windows**: PowerShell 或 CMD
- **Linux/Mac**: Terminal

### 步骤 2: 进入项目目录
```bash
cd "C:\Users\LENOVO\Documents\Codex\2026-09-20\n\outputs\a-share-risk-agent"
```

### 步骤 3: 激活虚拟环境
```bash
# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

### 步骤 4: 初始化数据库
```bash
python << 'EOF'
from app.database import create_tables
create_tables()
print("数据库初始化成功!")
EOF
```

### 步骤 5: 启动服务
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 9001
```

**预期输出**:
```
INFO:     Uvicorn running on http://127.0.0.1:9001 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

---

## 第一个请求

### 方法 1: 使用浏览器 (最简单)

1. 打开 API 文档页面
   ```
   http://127.0.0.1:9001/docs
   ```

2. 找到 `POST /api/v1/agent/chat`

3. 点击 "Try it out"

4. 输入示例请求:
   ```json
   {
     "messages": [
       {"role": "user", "content": "从 10 到 11 的变化率是多少？"}
     ],
     "max_rounds": 5
   }
   ```

5. 点击 "Execute"

6. 查看响应 ✅

### 方法 2: 使用 Python (推荐)

创建文件 `test_query.py`:
```python
import requests

# 发送请求
response = requests.post(
    "http://127.0.0.1:9001/api/v1/agent/chat",
    json={
        "messages": [
            {"role": "user", "content": "从 10 到 11 的变化率是多少？"}
        ],
        "max_rounds": 5
    }
)

# 显示结果
data = response.json()
print(f"✅ 答案: {data['answer']}")
print(f"⏱️ 轮次: {data['rounds']}")
print(f"🔧 工具调用: {len(data['executions'])}")
```

运行:
```bash
python test_query.py
```

### 方法 3: 使用 curl (命令行)

```bash
curl -X POST "http://127.0.0.1:9001/api/v1/agent/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "从 10 到 11 的变化率是多少？"}
    ],
    "max_rounds": 5
  }'
```

---

## 常见问题

### ❌ 问题: "端口已被占用"

**错误信息**:
```
ERROR: [Errno 10048] error while attempting to bind on address
```

**解决方案**:
使用不同的端口:
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 9002
```

### ❌ 问题: "找不到虚拟环境"

**错误信息**:
```
No module named 'venv'
```

**解决方案**:
创建虚拟环境:
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
```

### ❌ 问题: "数据库表不存在"

**错误信息**:
```
psycopg.errors.UndefinedTable: relation "tool_audit_records" does not exist
```

**解决方案**:
初始化数据库:
```bash
python << 'EOF'
from app.database import create_tables
create_tables()
EOF
```

### ❌ 问题: "无法连接到服务器"

**错误信息**:
```
ConnectionRefusedError: [Errno 111] Connection refused
```

**检查清单**:
- [ ] 终端显示 "Application startup complete"
- [ ] 端口 9001 没有被占用
- [ ] 防火墙允许本地连接
- [ ] 检查错误日志

---

## 📚 后续学习

### 初级
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - 快速参考指南
- 熟悉基本 API 调用

### 中级
- [USAGE_GUIDE.md](USAGE_GUIDE.md) - 详细使用指南
- 学习高级参数和配置
- 探索 API 文档

### 高级
- [COMPLETION_REPORT.md](COMPLETION_REPORT.md) - 项目架构
- 理解内部工作原理
- 自定义和扩展

---

## 🎯 典型工作流

```
启动服务
    ↓
检查健康状态 (GET /health)
    ↓
发送 Agent 查询 (POST /api/v1/agent/chat)
    ↓
查看 AI 答案和工具执行
    ↓
查询审计记录 (可选)
    ↓
停止服务 (Ctrl+C)
```

---

## ✨ 功能演示

### 示例 1: 计算涨跌幅

**请求**:
```
问题: "从 10 到 11 的变化率是多少？"
```

**响应**:
```
答案: 从 10 到 11 的变化率是 10%
执行的工具: calculate_change
状态: 成功 ✓
```

### 示例 2: 多轮对话

**请求**:
```
用户: "平安银行现在的价格？"
```

**AI 处理**:
1. 识别股票: 平安银行 (000001.SZ)
2. 调用工具: get_stock_profile
3. 返回信息

---

## 🆘 获取帮助

1. **查看日志**
   ```bash
   # 查看最后 50 行日志
   tail -50 server.log
   ```

2. **查看详细错误**
   ```bash
   # 启用调试模式
   python -m uvicorn app.main:app --log-level debug --port 9001
   ```

3. **查阅文档**
   - [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
   - [USAGE_GUIDE.md](USAGE_GUIDE.md)
   - API 文档: http://127.0.0.1:9001/docs

---

## ✅ 检查清单

在进行之前，确保已完成:

- [ ] Python 已安装
- [ ] 项目文件已下载
- [ ] 虚拟环境已创建
- [ ] .env 配置已完成
- [ ] 数据库已初始化
- [ ] 服务已启动
- [ ] 健康检查通过

---

## 🎉 成功启动!

如果你看到:
```
INFO:     Uvicorn running on http://127.0.0.1:9001
INFO:     Application startup complete.
```

**恭喜!** 🎊 TURAQ 后端已成功启动！

现在你可以:
1. 访问 API 文档: http://127.0.0.1:9001/docs
2. 进行第一个 API 调用
3. 开始使用 Agent 功能

---

**下一步**: 阅读 [QUICK_REFERENCE.md](QUICK_REFERENCE.md) 了解常见操作

**遇到问题?** 查看 [USAGE_GUIDE.md](USAGE_GUIDE.md) 的故障排除部分
