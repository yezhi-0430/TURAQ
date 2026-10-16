# 管理员功能探索报告

## 1. 管理员相关数据表结构

### 1.1 Users 表 (app/auth/models.py)
- id: 主键
- email: 邮箱（唯一）
- password_hash: 密码哈希
- verified: 是否已验证
- disabled: 是否禁用
- **is_admin: 管理员标志**
- pending_expires_at: 待验证过期时间
- invite_id: 关联的邀请码ID

### 1.2 Invites 表 (邀请码管理)
- id: 主键
- digest: SHA256 哈希（唯一）
- max_uses: 最大使用次数（默认50）
- uses: 已使用次数
- revoked: 是否撤销
- expires_at: 过期时间

### 1.3 ToolAuditRecord 表 (LLM成本统计核心)
- id: 主键
- **actor_id: 用户ID（外键 users.id）**
- run_id: 运行ID（索引）
- tool_call_id: 工具调用ID
- tool_name: 工具名称
- arguments: 调用参数（JSON）
- status: 成功/失败
- result: 结果（JSON）
- error: 错误信息（JSON）
- source: 来源信息（JSON）
- **duration_ms: 执行时长**
- **created_at: 创建时间**

### 1.4 ModelBudget 表 (模型调用额度)
- key: 主键（如 user:<id>:minute）
- events: 时间戳列表（JSON）
- lease_token: 租约令牌
- lease_expires_at: 租约过期时间

### 1.5 ActionAuditRecord 表 (用户操作审计)
- id: 主键
- actor_id: 用户ID
- operation: 操作类型
- watchlist_id: 自选组ID
- stock_code: 股票代码
- status: 状态
- error_kind: 错误类型
- created_at: 创建时间

---

## 2. 管理员命令行工具

文件路径: app/auth/admin.py

### 可用命令：

#### init-auth-schema
初始化认证数据表
