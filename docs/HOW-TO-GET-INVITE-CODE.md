# 如何获取邀请码

邀请码是由管理员生成的，用来控制谁可以注册新账号。

## 🔑 生成邀请码

### 方式 1: 命令行生成

使用管理命令生成邀请码：

```bash
python -m app.auth.admin create-invite --max-uses 50 --days 7
```

**输出示例**:
```
邀请码 ID: 9
eHd_G8xQIs-M3hn1NgIN3eT6lN4mTOdaNZSwk5-ARaI
```

这个邀请码只会显示一次，所以务必记住！

### 参数说明

- `--max-uses` (可选，默认 50): 邀请码最多可以被使用多少次
- `--days` (可选，默认 7): 邀请码有效期（天数）

### 示例

```bash
# 创建一个可被 10 个人使用、有效期 30 天的邀请码
python -m app.auth.admin create-invite --max-uses 10 --days 30

# 创建一个可被 100 个人使用、有效期 1 天的邀请码
python -m app.auth.admin create-invite --max-uses 100 --days 1
```

---

## 📝 使用邀请码注册

### 前端注册流程

1. 打开应用 `http://localhost:3000`
2. 点击"注册"按钮
3. 填写以下信息:
   - **邮箱**: `user@example.com`
   - **密码**: `password123` (6-15 个字符)
   - **邀请码**: 粘贴刚才生成的邀请码

4. 点击"提交注册"

   ![注册流程](注意：这是示意图)

### API 注册

如果你想通过 API 注册:

```bash
curl -X POST http://localhost:3000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <your_csrf_token>" \
  -d '{
    "email": "user@example.com",
    "password": "password123",
    "invite_code": "eHd_G8xQIs-M3hn1NgIN3eT6lN4mTOdaNZSwk5-ARaI"
  }'
```

**响应** (202 Accepted):
```json
{
  "detail": "请求已受理；符合条件时将发送邮件。"
}
```

---

## 📧 邮箱验证

### 收到验证邮件

注册后，用户会收到一封验证邮件，包含验证链接：

```
https://your-domain.com/#verify=token123456
```

### 验证邮箱

1. 点击邮件中的验证链接
2. 或手动进入应用，点击"验证邮箱"
3. 粘贴验证码 (从邮件中获取)
4. **可选**: 如果注册时没填邀请码，这里可以补填

---

## 🔧 邀请码管理命令

### 调整邀请码参数

增加使用次数上限:
```bash
python -m app.auth.admin adjust-invite 9 --max-uses 100
```

延长邀请码有效期:
```bash
python -m app.auth.admin adjust-invite 9 --days 30
```

撤销邀请码（禁用它）:
```bash
python -m app.auth.admin adjust-invite 9 --revoke
```

---

## 💡 常见场景

### 场景 1: 内部测试（一个人注册）

```bash
# 生成一个邀请码，有效期 30 天
python -m app.auth.admin create-invite --max-uses 1 --days 30
```

### 场景 2: 内测邀请（100 个人）

```bash
# 生成一个邀请码，100 个名额，有效期 7 天
python -m app.auth.admin create-invite --max-uses 100 --days 7
```

### 场景 3: 公开内测（无限制）

```bash
# 生成一个邀请码，999 个名额，有效期 30 天
python -m app.auth.admin create-invite --max-uses 999 --days 30
```

---

## ⚠️ 注意事项

### 邀请码只显示一次

邀请码创建后只显示一次，之后无法重新显示。请妥善保管！

如果不小心丢失，需要生成新的邀请码。

### 邀请码和邮箱验证的区别

| 项目 | 邀请码 | 邮箱验证 |
|-----|------|--------|
| 用途 | 控制谁可以注册 | 确认邮箱有效 |
| 必需 | 可选（注册时可补填）| 必需 |
| 有效期 | 默认 7 天 | 30 分钟 |
| 使用次数 | 有限制（默认 50） | 一次 |

### 安全提示

- 不要在公开地方分享邀请码（除非你想让所有人注册）
- 定期检查已使用的邀请码数量
- 如果邀请码被滥用，可以撤销它

---

## 🚀 完整流程示例

### 步骤 1: 生成邀请码

```bash
$ python -m app.auth.admin create-invite --max-uses 50 --days 7

邀请码 ID: 12
aB1cD2eF3gH4iJ5kL6mN7oP8qR9sT0uV
```

记住这个邀请码: `aB1cD2eF3gH4iJ5kL6mN7oP8qR9sT0uV`

### 步骤 2: 用户注册

用户在前端输入:
- 邮箱: `john@example.com`
- 密码: `SecurePass123`
- 邀请码: `aB1cD2eF3gH4iJ5kL6mN7oP8qR9sT0uV`

### 步骤 3: 验证邮件发送

用户收到邮件，链接: `http://localhost:3000/#verify=verification_token_xyz`

### 步骤 4: 验证邮箱

用户点击链接，邮箱被验证，账号激活！

### 步骤 5: 登录

用户使用邮箱和密码登录应用。

---

## 📞 故障排查

### 问题: "邀请码无效或已过期"

**原因**:
- 邀请码已过期（超过 7 天）
- 邀请码已被使用完（50 人）
- 邀请码被撤销了
- 邀请码拼写错误

**解决方案**:
- 生成新的邀请码
- 调整邀请码参数延长有效期

### 问题: "邀请码丢失了"

**解决方案**:
- 生成新邀请码: `python -m app.auth.admin create-invite`
- 邀请码只显示一次，无法恢复

### 问题: 邀请码已用完

**解决方案**:
- 增加使用次数: `python -m app.auth.admin adjust-invite 12 --max-uses 100`

---

## 📚 相关文档

- 📄 [QUICK-REFERENCE.md](QUICK-REFERENCE.md) - 快速参考
- 📄 [code-review-invite-auth-2026-10-12.md](code-review-invite-auth-2026-10-12.md) - 详细设计
- 📄 [FINAL-REVIEW-SUMMARY.md](FINAL-REVIEW-SUMMARY.md) - 审查总结

---

**总结**: 邀请码通过管理命令生成，一次只显示一次，记住它后就可以用来注册新账号了！
