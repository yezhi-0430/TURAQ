# 👋 欢迎使用 TURAQ

> TURAQ - A 股智能研究平台

---

## 🎯 你在这里做什么？

TURAQ 是一个基于 AI Agent 的 A 股研究平台。现在你已经拥有一个完全功能的**后端 API**，准备好处理：

- ✅ 自然语言问题（中文）
- ✅ 自动工具调用和执行
- ✅ 完整的审计追踪
- ✅ 实时 API 文档

---

## ⚡ 快速开始 (选择一个)

### 🟢 Windows 用户 - 最简单方式
```bash
# 双击运行
quick_start.bat
```

### 🟢 Linux/Mac 用户 - 最简单方式
```bash
bash quick_start.sh
```

### 🟡 手动启动
```bash
# 1. 激活虚拟环境
.venv\Scripts\activate

# 2. 初始化数据库
python << 'EOF'
from app.database import create_tables
create_tables()
