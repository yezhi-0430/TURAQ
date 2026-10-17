# TURAQ 管理员界面实施方案

**版本**: v1.0  
**日期**: 2026-10-12  
**方案**: 方案A - 侧边栏动态显示

---

## 📦 交付物清单

1. **IMPLEMENTATION-PLAN.md** - 完整的技术实施计划
2. **API-SPECIFICATION.md** - 后端 API 接口规范
3. **UI-MOCKUP.md** - 前端界面设计稿
4. **DEPLOYMENT-GUIDE.md** - 部署和测试指南

---

## 🎯 方案概述

### 核心功能
- ✅ 用户管理（查看、启用/禁用）
- ✅ 邀请码管理（生成、撤销、统计）
- ✅ LLM 使用统计（成本监控、用户排行）
- ✅ 管理仪表盘（关键指标概览）

### 技术亮点
- **零侵入式**：基于现有 `is_admin` 字段，无需数据库迁移
- **安全可靠**：前后端双重权限验证 + CSRF 保护
- **开箱即用**：利用现有 `tool_audit_records` 表统计成本

---

## 🚀 快速开始

### 1. 创建管理员账号
```bash
python -m app.auth.admin bootstrap-admin \
    --email admin@turaq.com \
    --verified-email
```

### 2. 启动服务
```bash
uvicorn app.main:application --reload
```

### 3. 登录验证
- 使用管理员账号登录
- 侧边栏应显示 "ADMIN" 区域
- 点击进入管理后台

---

## 📊 效果预览

### 侧边栏菜单
```
WORKSPACE
├─ 行情驾驶舱
├─ 自选管理
├─ AI 研究助手
├─ 风险监控
└─ 模拟交易

ADMIN（仅管理员可见 🔴）
├─ 📊 管理仪表盘
├─ 👥 用户管理
└─ 🎫 邀请码管理
```

### 管理仪表盘
- **总用户数**: 50
- **7日活跃**: 32
- **今日 AI 调用**: 89
- **可用邀请名额**: 127

### 用户管理
| ID | 邮箱 | 状态 | 注册时间 | 操作 |
|----|------|------|----------|------|
| 2 | user@example.com | 正常 | 2026-10-01 | 禁用 |
| 3 | test@example.com | 已禁用 | 2026-10-05 | 启用 |

### 邀请码管理
| 邀请码 | 使用情况 | 有效期 | 状态 | 操作 |
|--------|----------|--------|------|------|
| ABC123 | 23 / 50 | 2026-11-12 | 有效 | 撤销 |
| XYZ789 | 50 / 50 | 2026-10-20 | 已用完 | - |

---

## 🏗️ 实施阶段

### Phase 1: 后端 API（4-6小时）
- 新建 `app/admin/` 模块
- 实现用户、邀请码、统计 API
- 添加 `/auth/me` 端点

### Phase 2: 前端基础（2-3小时）
- 修改 `frontend/index.html` 添加管理员菜单
- 实现权限判断和路由守卫
- 集成到现有页面切换系统

### Phase 3: 前端界面（5-7小时）
- 创建 `frontend/admin.js` 和 `frontend/admin.css`
- 实现仪表盘、用户管理、邀请码管理页面
- 集成 API 调用和错误处理

### Phase 4: 安全加固（1小时）
- 后端权限二次验证
- 前端路由守卫
- CSRF 保护测试

**总工作量**: 12-17 小时

---

## 🔒 安全保障

### 后端保护
```python
@router.get("/api/v1/admin/users")
def list_users(actor: Actor = Depends(require_admin)):
    # 只有 is_admin=True 才能访问
    ...
```

### 前端保护
```javascript
if (page.startsWith('admin-') && !session.user?.is_admin) {
    alert('无权访问管理后台');
    return;
}
```

### CSRF 保护
所有写操作自动携带 `X-CSRF-Token` 头。

---

## 📝 测试验证

### 功能测试
- ✅ 普通用户登录 → 无管理员菜单
- ✅ 管理员登录 → 显示管理员菜单
- ✅ 查看统计数据 → 显示正确数据
- ✅ 禁用/启用用户 → 操作成功
- ✅ 生成邀请码 → 返回新邀请码
- ✅ 撤销邀请码 → 状态更新

### 安全测试
- ✅ 前端绕过权限检查 → 后端 403 拒绝
- ✅ 普通用户直接请求管理员 API → 403 拒绝
- ✅ CSRF 攻击 → Token 验证失败

---

## 📂 文件结构

### 新建文件
```
app/admin/
  ├── api.py              # 管理员路由
  ├── user_service.py     # 用户管理服务
  ├── invite_service.py   # 邀请码管理服务
  └── stats_service.py    # 统计服务

frontend/
  ├── admin.js            # 管理员前端逻辑
  └── admin.css           # 管理员样式
```

### 修改文件
```
app/
  ├── auth/api.py         # 添加 /auth/me
  └── main.py             # 注册管理员路由

frontend/
  ├── index.html          # 添加菜单、页面、权限判断
  └── api.js              # 获取 is_admin 状态
```

---

## 🔮 后续扩展

### 未包含在本计划
- WebSocket 实时通知
- 导出功能（CSV、Excel）
- 批量操作
- 高级统计图表（ECharts）
- 审计日志详情查看
- 用户配额管理

---

## 📞 技术支持

**问题反馈**: 查看 IMPLEMENTATION-PLAN.md 的详细说明  
**API 文档**: 查看 API-SPECIFICATION.md  
**界面设计**: 查看 UI-MOCKUP.md  

---

**制定人**: Claude Opus 5.5  
**审核人**: 待定  
**实施团队**: 待定
