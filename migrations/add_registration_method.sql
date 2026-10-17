-- 为 User 表添加 registration_method 字段
-- 用于标记用户是通过邀请码注册还是直接邮箱注册

ALTER TABLE users
ADD COLUMN IF NOT EXISTS registration_method VARCHAR(12) NOT NULL DEFAULT 'invite';

-- 更新现有用户为 'invite' 方式（已经是默认值，但为了明确）
UPDATE users
SET registration_method = 'invite'
WHERE registration_method IS NULL OR registration_method = '';

COMMENT ON COLUMN users.registration_method IS '注册方式: invite=邀请码注册, email=邮箱注册';
