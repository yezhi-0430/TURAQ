# TURAQ API 快速参考

## ⚡ 30 秒快速启动

### Windows
```bash
# 双击运行
quick_start.bat
```

### Linux/Mac
```bash
# 运行启动脚本
bash quick_start.sh

# 或手动启动
source .venv/bin/activate
python -m uvicorn app.main:app --port 9001
```

---

## 📞 核心 API

### 1️⃣ 健康检查
```bash
GET http://127.0.0.1:9001/health

# 响应
{"status": "ok"}
```

### 2️⃣ AI 对话 (最常用)
```bash
POST http://127.0.0.1:9001/api/v1/agent/chat
Content-Type: application/json

{
  "messages": [
    {"role": "user", "content": "从 10 到 11 的变化率是多少？"}
  ],
  "max_rounds": 5
}
```

**响应示例**:
```json
{
  "run_id": "abc123...",
  "status": "completed",
  "answer": "从 10 到 11 的变化率是 10%",
  "rounds": 2,
  "executions": [
    {
      "tool_name": "calculate_change",
      "status": "success",
      "duration_ms": 0.10
    }
  ]
}
```

---

## 🐍 Python 调用示例

### 最简单的方式
```python
import requests

response = requests.post(
    "http://127.0.0.1:9001/api/v1/agent/chat",
    json={
        "messages": [{"role": "user", "content": "从 10 到 11 的变化率是多少？"}],
        "max_rounds": 5
    }
)

data = response.json()
print(f"答案: {data['answer']}")
print(f"用时: {len(data['executions'])} 个工具调用")
```

### 完整的错误处理版本
```python
import requests
import json

def query_agent(question):
    """查询 Agent"""
    url = "http://127.0.0.1:9001/api/v1/agent/chat"
    
    try:
        response = requests.post(
            url,
            json={
                "messages": [{"role": "user", "content": question}],
                "max_rounds": 5
            },
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        
        if data['status'] == 'completed':
            return {
                'success': True,
                'answer': data['answer'],
                'tools_used': len(data['executions'])
            }
        else:
            return {
                'success': False,
                'error': f"未完成。状态: {data['status']}"
            }
            
    except requests.exceptions.Timeout:
        return {'success': False, 'error': '请求超时'}
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': str(e)}

# 使用
result = query_agent("从 10 到 11 的变化率是多少？")
print(result)
```

---

## 🧪 测试命令

### 验证服务是否运行
```bash
# 检查端口
netstat -an | grep 9001

# 或用 curl
curl http://127.0.0.1:9001/health
```

### 运行完整测试
```bash
python test_backend_final.py
```

### 查看 API 文档
```
浏览器访问: http://127.0.0.1:9001/docs
```

---

## 🔧 故障排除

| 问题 | 解决方案 |
|------|--------|
| 端口 9001 被占用 | 使用 `--port 9002` 或杀死占用进程 |
| 找不到 .venv | 检查虚拟环境是否创建 |
| "table does not exist" | 运行 `python -c "from app.database import create_tables; create_tables()"` |
| LLM 错误 | 检查 `.env` 文件中的 API Key |
| 导入错误 | 清除 `__pycache__` 目录，重新启动 |

---

## 📊 响应状态值

| 状态 | 含义 |
|------|------|
| `completed` | ✅ 完成，有最终答案 |
| `max_rounds_exceeded` | ⏱️ 达到最大轮数但未完成 |
| `error` | ❌ 执行出错 |

---

## 🚀 性能参数

```python
# 可调整的参数
{
    "messages": [...],      # 对话消息
    "max_rounds": 5         # 最大循环轮数 (1-10 推荐)
}
```

- `max_rounds` 越小 = 更快但可能不够完整
- `max_rounds` 越大 = 更完整但更慢

---

## 📈 常见对话例子

### 例 1: 计算涨跌幅
```json
{
  "messages": [
    {"role": "user", "content": "从 10 到 11 的变化率是多少？"}
  ]
}
```

### 例 2: 股票查询
```json
{
  "messages": [
    {"role": "user", "content": "查询 000001.SZ (平安银行) 的最近信息"}
  ]
}
```

### 例 3: 多轮对话
```json
{
  "messages": [
    {"role": "user", "content": "平安银行怎么样？"},
    {"role": "assistant", "content": "平安银行是..."},
    {"role": "user", "content": "过去一周的价格变化？"}
  ]
}
```

---

## 📚 完整文档

- [USAGE_GUIDE.md](USAGE_GUIDE.md) - 详细使用指南
- [COMPLETION_REPORT.md](COMPLETION_REPORT.md) - 项目完成报告
- [README.md](README.md) - 项目概述

---

## ✅ 启动检查清单

- [ ] Python 虚拟环境已激活
- [ ] 数据库表已初始化
- [ ] 服务运行在 9001 端口
- [ ] 健康检查返回 200
- [ ] 第一次 Agent 对话成功
- [ ] 工具执行有结果

---

**💡 提示**: 如果第一次使用，建议先看 [USAGE_GUIDE.md](USAGE_GUIDE.md) 了解详细步骤。

**需要帮助?** 查看问题排除部分或检查完整指南。
