# 邀请码认证系统 - 快速参考

## 🚀 快速启动

```bash
# 1. 创建数据库表
python -m app.auth.admin init-auth-schema

# 2. 创建管理员账号
python -m app.auth.admin bootstrap-admin --email admin@example.com --verified-email

# 3. 生成邀请码
python -m app.auth.admin create-invite --max-uses 50 --days 7

# 4. 启动后端
uvicorn app.main:app --port 8888

# 5. 启动前端
cd frontend && npm run dev
```

## 📊 数据库模型

```
users (用户表)
├── id (PK)
├── email (唯一)
├── password_hash
├── verified (邮箱验证状态)
├── disabled (禁用状态)
├── is_admin
├── pending_expires_at (待验证过期时间)
└── invite_id (FK → invites)

invites (邀请码表)
├── id (PK)
├── digest (唯一, token 哈希)
├── max_uses (最大使用次数)
├── uses (已使用次数)
├── revoked (撤销标记)
└── expires_at (过期时间)

email_tokens (邮件验证令牌表)
├── digest (PK, token 哈希)
├── user_id (FK → users)
├── purpose (verify/reset)
├── expires_at
└── consumed (使用标记)

login_sessions (登录会话表)
├── digest (PK, session 哈希)
├── user_id (FK → users, 可为空)
├── csrf_token
├── expires_at
├── last_seen_at
└── revoked
```

## 🔐 密码策略

- **长度**: 6-15 个字符（包含边界）
- **算法**: Bcrypt (成本因子 12)
- **内存**: 19456 KiB
- **并行度**: 1
- **前后端**: 规则一致

## 🛑 限流策略

### 邮件请求
```
IP 限流:       10 次 / 小时
邮箱日限:      5 次 / 天
邮箱间隔:      1 次 / 分钟
```

### 登录请求
```
IP 限流:       20 次 / 15 分钟
邮箱限流:      5 次 / 15 分钟
```

### Bootstrap
```
IP 限流:       可配置 / 分钟 (默认 20)
```

## 🎫 邀请码流程

```
1. 管理员生成邀请码
   python -m app.auth.admin create-invite
   输出: 邀请码 ID 和明文码 (只显示一次)

2. 用户使用邀请码注册
   POST /api/v1/auth/register
   {
     "email": "user@example.com",
     "password": "password123",
     "invite_code": "xxxx_xxxx_xxxx"
   }
   响应: 202 (请求已受理)

3. 后台发送验证邮件
   包含: 验证链接 /#verify=token

4. 用户验证邮箱
   POST /api/v1/auth/verify-email
   {
     "token": "token_from_email",
     "invite_code": "xxxx_xxxx_xxxx"  // 可选: 可补填
   }
   响应: 200 (验证成功)

5. 邀请码标记为已使用
   uses 计数 +1
   如果 uses >= max_uses，不再接受新注册
```

## 🔑 会话管理

```
Cookie 设置:
- HttpOnly: true
- Secure: true (生产环境)
- SameSite: Lax
- Path: /
- Max-Age: 7 天

会话状态:
- 过期: 7 天（绝对）
- 空闲撤销: 24 小时
- 登录成功: 自动换发
- 密码重置: 全部撤销
```

## 📧 邮件模板

### 邮箱验证

```
标题: TURAQ 邮箱验证
链接: https://your-domain.com/#verify={token}
```

### 密码重置

```
标题: TURAQ 密码重置
链接: https://your-domain.com/#reset={token}
```

## 🌐 前端整合

```javascript
// 订阅会话变化
api.subscribe(session => {
  if (session.user) {
    // 已登录: 显示工作台
  } else {
    // 未登录: 显示登录对话框
  }
});

// 密码验证规则
window.AuthRules = {
  validPassword: value => 
    typeof value === 'string' && 
    Array.from(value).length >= 6 && 
    Array.from(value).length <= 15
};

// URL token 支持
/#verify=token      // 邮箱验证
/#reset=token       // 密码重置
```

## 🔍 数据隔离检查

### Watchlist 隔离

```python
# ✅ 正确: 过滤 owner_id
watchlists = get_watchlists(db, actor_id=user_id)

# ❌ 错误: 不过滤
watchlists = db.query(Watchlist).all()

# ✅ 正确: 验证所有权
watchlist = db.query(Watchlist).filter(
    Watchlist.id == wl_id,
    Watchlist.owner_id == actor_id
).first()
```

### Agent 审计隔离

```python
# ✅ 正确: 记录 actor_id
save_tool_execution(run_id, record, actor_id=actor.id)

# ✅ 正确: 查询时过滤
audits = db.query(ToolAuditRecord).filter(
    ToolAuditRecord.actor_id == user_id
).all()
```

## ⚙️ 环境变量

```bash
# 数据库
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=a_share_risk_agent
DATABASE_USER=a_share_agent
DATABASE_PASSWORD=password

# 认证
SITE_BASE_URL=https://example.com (生产) / http://localhost:3000 (开发)
AUTH_COOKIE_NAME=session
AUTH_COOKIE_SECURE=true (生产) / false (开发)

# SMTP
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_TLS=starttls
SMTP_USERNAME=account@example.com
SMTP_PASSWORD=password
SMTP_FROM=noreply@example.com

# 限流
BOOTSTRAP_IP_MINUTE_LIMIT=20
MARKET_USER_MINUTE_LIMIT=120
MARKET_IP_MINUTE_LIMIT=240
```

## 🧪 测试用例

### 注册流程
```
1. 有效邀请码 → 注册成功 → 发送验证邮件 ✅
2. 无效邀请码 → 注册失败 ✅
3. 重复邮箱 → 拒绝 ✅
4. 短密码(<6) → 拒绝 ✅
5. 长密码(>15) → 拒绝 ✅
```

### 验证流程
```
1. 有效 token → 验证成功 ✅
2. 过期 token → 拒绝 ✅
3. 已使用 token → 拒绝 ✅
4. 补填邀请码 → 成功 ✅
```

### 数据隔离
```
1. 用户 A 创建 watchlist → 用户 B 看不到 ✅
2. 用户 A 修改 watchlist → 用户 B 无权限 ✅
3. 用户 B 尝试访问 A 的 ID → 404 ✅
```

## 📞 常见问题

**Q: 如何撤销邀请码?**
```bash
python -m app.auth.admin adjust-invite 1 --revoke
```

**Q: 如何增加邀请码名额?**
```bash
python -m app.auth.admin adjust-invite 1 --max-uses 100
```

**Q: 如何续期邀请码?**
```bash
python -m app.auth.admin adjust-invite 1 --days 30
```

**Q: 如何禁用用户?**
```bash
python -m app.auth.admin disable-user 123
```

**Q: 忘记邮箱怎么办?**
- 用户可以通过"找回密码"使用邮箱重置
- 邮箱地址不会在错误提示中泄露

**Q: 邀请码过期了怎么办?**
- 用户可以请求管理员生成新的邀请码
- 或在验证时补填新邀请码

---

**最后更新**: 2026-10-12  
**维护人**: Claude Opus 5.5
