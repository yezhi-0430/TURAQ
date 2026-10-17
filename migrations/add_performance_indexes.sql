-- 添加数据库索引以提升查询性能
-- 这些索引针对高频查询的外键和过滤条件

-- 1. email_tokens 表索引
-- 用于快速查找用户的验证令牌（登录、重置密码、验证邮箱）
CREATE INDEX IF NOT EXISTS idx_email_tokens_user_id ON email_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_email_tokens_purpose ON email_tokens(purpose);
CREATE INDEX IF NOT EXISTS idx_email_tokens_expires_consumed ON email_tokens(expires_at, consumed);

-- 2. action_audit_records 表索引
-- 用于快速查询用户的操作审计记录
CREATE INDEX IF NOT EXISTS idx_action_audit_records_actor_id ON action_audit_records(actor_id);
CREATE INDEX IF NOT EXISTS idx_action_audit_records_created_at ON action_audit_records(created_at DESC);

-- 3. login_sessions 表索引
-- 用于快速查找用户的活跃会话
CREATE INDEX IF NOT EXISTS idx_login_sessions_user_id ON login_sessions(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_login_sessions_revoked ON login_sessions(revoked) WHERE revoked = false;

-- 4. throttle_buckets 表索引
-- 用于快速查找限流桶（已有 key 作为主键，无需额外索引）

-- 5. invites 表索引
-- 用于快速验证邀请码
CREATE INDEX IF NOT EXISTS idx_invites_revoked_expires ON invites(revoked, expires_at) WHERE revoked = false;

COMMENT ON INDEX idx_email_tokens_user_id IS '加速用户令牌查询';
COMMENT ON INDEX idx_action_audit_records_actor_id IS '加速审计日志查询';
COMMENT ON INDEX idx_login_sessions_user_id IS '加速用户会话查询（仅非空用户）';
