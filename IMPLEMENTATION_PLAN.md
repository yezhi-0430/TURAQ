# 邮箱验证码登录 + 可选邀请码注册 实现方案

## 概述

当前系统：注册需要邀请码 → 验证邮箱 → 用密码登录

新系统：
- **注册**：邀请码可选（有码用，没码也行）
- **登录**：支持两种方式
  - 密码登录：邮箱 + 密码
  - 验证码登录：邮箱 + 邮件链接中的令牌

---

## 前端改动

### 1. 登录界面改进 (`frontend/auth.js`)
**改前：**
- 登录只有 "邮箱+密码" 方式

**改后：**
- 保留 "邮箱+密码" 登录
- 新增 "邮箱+验证码" 选项

**UI 流程：**
```
登录对话框
├─ 选项1: 密码登录 (email + password)
├─ 选项2: 验证码登录 (email only)
└─ 发送链接 / 请求验证邮件

验证码登录流程：
1. 用户输入邮箱 → 点"发送验证链接"
2. 后端发送邮件（包含验证令牌链接）
3. 用户点击邮件链接 → 自动跳转并登录
```

### 2. 注册界面改进 (`frontend/auth.js`)
**改前：**
- 邀请码为必填

**改后：**
- 邀请码变为可选（placeholder 显示"可选"）

---

## 后端改动

### 1. 数据库 - 用户模型改进 (`app/auth/models.py`)
需要新增字段标记注册方式：
```python
class User(Base):
    __tablename__ = "users"
    # ... 现有字段 ...
    registration_method: Mapped[str] = mapped_column(
        String(12), 
        default="invite"  # "invite" 或 "email"
    )
    # invite 方式：注册时提供邀请码
    # email 方式：注册无邀请码，直接验证邮箱
```

### 2. Schema 改进 (`app/auth/schemas.py`)

**RegisterRequest** - 邀请码变可选：
```python
class RegisterRequest(EmailRequest):
    password: Password
    invite_code: Token | None = None  # 改为可选
```

**新增 MagicLinkRequest** - 验证码登录：
```python
class MagicLinkRequest(EmailRequest):
    """邮箱验证码登录"""
    pass

class MagicLinkVerifyRequest(StrictRequest):
    """用验证码登录"""
    token: Token
```

### 3. 业务逻辑 改进 (`app/auth/service.py`)

**注册函数改进**：
```python
def register(db, email, password, invite_code=None):
    """
    支持两种注册方式：
    1. 有邀请码：传统方式，邀请码占用一个名额
    2. 无邀请码：邮箱方式，无需邀请码
    """
    now = utcnow()
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    
    if user and (user.verified or aware(user.pending_expires_at) > now):
        return None
    
    # 如果提供了邀请码，需要验证
    invitation = None
    if invite_code:
        invitation = db.scalar(
            select(Invite).where(
                Invite.digest == digest(invite_code),
                Invite.revoked.is_(False),
                Invite.expires_at > now,
                Invite.uses < Invite.max_uses,
            )
        )
        if invitation is None:
            return None
    
    if user is None:
        user = User(
            email=email,
            password_hash=password_hash(password),
            pending_expires_at=now + timedelta(hours=24),
            invite_id=invitation.id if invitation else None,
            registration_method="invite" if invite_code else "email"
        )
        db.add(user)
    else:
        user.password_hash = password_hash(password)
        user.invite_id = invitation.id if invitation else None
        user.registration_method = "invite" if invite_code else "email"
        user.pending_expires_at = now + timedelta(hours=24)
    
    db.flush()
    return user
```

**新增登录函数** - 验证码登录：
```python
def login_with_token(db, token_raw: str) -> User | None:
    """
    用验证令牌登录，不需要密码
    """
    now = utcnow()
    
    # 查找有效令牌
    token_record = db.scalar(
        select(EmailToken).where(
            EmailToken.digest == digest(token_raw),
            EmailToken.purpose == "login",
            EmailToken.expires_at > now,
            EmailToken.consumed.is_(False)
        )
    )
    
    if not token_record:
        return None
    
    user = db.get(User, token_record.user_id)
    
    # 检查用户状态
    if not user or not user.verified or user.disabled:
        return None
    
    # 标记令牌已使用
    token_record.consumed = True
    db.commit()
    
    return user
```

### 4. API 改进 (`app/auth/api.py`)

**新增请求验证码登录端点**：
```python
@router.post("/request-login-link", status_code=202)
def request_login_link(
    payload: MagicLinkRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    factory=Depends(get_session_factory),
    mailer=Depends(get_mailer),
):
    """用邮箱请求验证码登录"""
    mail_admission(request, payload, factory, mailer)
    background_tasks.add_task(
        process_mail_request, 
        "login-link", 
        payload, 
        factory, 
        mailer
    )
    return ACCEPTED
```

**修改登录端点** - 支持令牌登录：
```python
@router.post("/login")
def login(
    payload: LoginRequest | MagicLinkVerifyRequest,
    request: Request,
    response: Response,
    factory=Depends(get_session_factory),
    settings=Depends(get_settings),
    mailer=Depends(get_mailer),
):
    ip = request.client.host if request.client else "unknown"
    limit(factory, "login-ip:" + digest(ip), 20, 900)
    
    with factory() as db:
        user = None
        
        # 情况1: 用令牌登录（MagicLinkVerifyRequest）
        if hasattr(payload, 'token') and not hasattr(payload, 'password'):
            user = login_with_token(db, payload.token)
            limit(factory, "login-token:" + digest(payload.token), 5, 900)
        
        # 情况2: 用密码登录（LoginRequest）
        elif hasattr(payload, 'password'):
            user = db.scalar(select(User).where(User.email == payload.email).with_for_update())
            valid = check_password(user.password_hash if user else None, payload.password)
            
            if not valid or not user or not user.verified or user.disabled:
                raise HTTPException(401, "邮箱或密码错误，或账号尚不可用")
            
            limit(factory, "login-email:" + digest(payload.email), 5, 900)
        
        if not user:
            raise HTTPException(401, "验证令牌无效或已过期")
        
        # 释放限流预留
        db.execute(
            update(ThrottleBucket)
            .where(ThrottleBucket.key.in_([...]))
            .values(count=ThrottleBucket.count - 1)
        )
        
        # 生成会话
        previous = load_session(db, request.cookies.get(settings.auth_cookie_name))
        if previous:
            previous.revoked = True
        raw, row = new_session(db, user.id)
        set_cookie(response, raw, settings)
        
        return session_json(db, row, mailer, settings)
```

**修改注册端点** - 邀请码可选：
```python
@router.post("/register", status_code=202)
def signup(
    payload: RegisterRequest,  # invite_code 现在可选
    request: Request,
    background_tasks: BackgroundTasks,
    factory=Depends(get_session_factory),
    mailer=Depends(get_mailer),
):
    mail_admission(request, payload, factory, mailer)
    background_tasks.add_task(process_mail_request, "register", payload, factory, mailer)
    return ACCEPTED
```

### 5. 邮件任务改进 (`app/auth/mail_jobs.py`)

**新增处理 login-link 请求**：
```python
def process_mail_request(action, payload, factory, mailer):
    try:
        with factory() as db:
            if action == "register":
                user = register(db, payload.email, payload.password, payload.invite_code)
                purpose = "verify"
            
            elif action == "login-link":
                # 用户请求登录链接
                user = db.scalar(
                    select(User)
                    .where(User.email == payload.email)
                    .with_for_update()
                )
                # 用户必须已验证、未禁用
                if user and user.verified and not user.disabled:
                    purpose = "login"
                else:
                    return
            
            else:
                # 其他操作（forgot-password, resend-verification）
                user = db.scalar(...)
                purpose = "reset" if action == "forgot-password" else "verify"
            
            if user is None:
                return
            
            token = issue_token(db, user.id, purpose)
        
        mailer.send(payload.email, purpose, token)
    
    except Exception as exc:
        logger.warning("Authentication mail job failed (%s)", type(exc).__name__)
```

### 6. 邮件内容改进 (`app/auth/mail.py`)

```python
def send(self, email: str, purpose: str, token: str) -> None:
    message = EmailMessage()
    message["From"] = self.settings.smtp_from
    message["To"] = email
    
    if purpose == "verify":
        message["Subject"] = "验证邮箱"
    elif purpose == "login":
        message["Subject"] = "登录验证链接"
    else:
        message["Subject"] = "重置密码"
    
    url = f"{self.settings.site_base_url.rstrip('/')}/#{purpose}={token}"
    message.set_content(f"{url}\n链接有效期 30 分钟。")
    
    try:
        with self._connect() as client:
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailUnavailable() from exc
```

---

## 前端改动详细方案

### 登录对话框改进

**改前：** 一个表单（邮箱+密码）

**改后：** 选项卡式界面
```html
<div class="auth-tabs">
  <button class="auth-tab active" data-tab="password">
    密码登录
  </button>
  <button class="auth-tab" data-tab="magic">
    验证码登录
  </button>
</div>

<!-- 密码登录表单 -->
<form id="password-login" class="auth-tab-content">
  <input name="email" type="email" required>
  <input name="password" type="password" required>
  <button type="submit">登录</button>
</form>

<!-- 验证码登录表单 -->
<form id="magic-login" class="auth-tab-content" hidden>
  <input name="email" type="email" required>
  <p class="auth-note">我们将向您的邮箱发送验证链接</p>
  <button type="submit">发送验证链接</button>
</form>
```

**JavaScript 逻辑**：
```javascript
// 切换标签页
document.querySelectorAll('.auth-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const tabName = tab.dataset.tab;
    // 隐藏/显示对应表单
  });
});

// 密码登录提交
$('password-login').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = {
    email: $('email').value,
    password: $('password').value
  };
  await api.authenticate('login', body);
});

// 验证码登录提交
$('magic-login').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = {
    email: $('email').value
  };
  const data = await api.request('/auth/request-login-link', {
    method: 'POST', body
  });
  // 显示"请检查邮箱"提示
});
```

### 注册表单改进

**改前：** 邀请码为必填

**改后：** 邀请码为可选
```html
<form id="register-form">
  <input name="email" type="email" required>
  <input name="password" type="password" required>
  <input 
    name="invite_code" 
    placeholder="可选：输入邀请码以关联名额"
    maxlength="100"
  >
  <button type="submit">注册</button>
</form>
```

**JavaScript 逻辑**：
```javascript
// 邀请码字段从 required 改为可选
$('auth-invite').required = false;

// 注册时邀请码可以为空
const body = {
  email: $('email').value,
  password: $('password').value
};
if ($('invite_code').value.trim()) {
  body.invite_code = $('invite_code').value.trim();
}
await api.request('/auth/register', {method: 'POST', body});
```

---

## 用户体验流程

### 场景1: 用验证码登录（新用户）
```
1. 打开应用 → 点"验证码登录"
2. 输入邮箱 → 点"发送验证链接"
3. 看到提示"请检查邮箱"
4. 打开邮箱 → 点击验证链接
5. 自动登录成功 ✓
```

### 场景2: 用密码登录（新用户注册后）
```
1. 打开应用 → 点"邀请码注册"
2. 输入邮箱、密码、邀请码 → 点"提交注册"
3. 看到提示"请检查邮箱"
4. 打开邮箱 → 点击验证链接
5. 邮箱验证完成
6. 回到登录 → 选"密码登录"
7. 输入邮箱+密码 → 登录成功 ✓
```

### 场景3: 无邀请码注册
```
1. 打开应用 → 点"邀请码注册"
2. 输入邮箱、密码 → 不填邀请码
3. 点"提交注册" → 注册成功
4. 邮箱验证完成
5. 用密码登录 ✓
```

---

## 数据库迁移

需要：
1. 为 `User` 表添加 `registration_method` 列
2. 现有用户默认设置为 `"invite"`

```sql
ALTER TABLE users 
ADD COLUMN registration_method VARCHAR(12) NOT NULL DEFAULT 'invite';
```

---

## 风险与缓解

| 风险 | 缓解方案 |
|------|--------|
| 垃圾邮件地址注册 | 保留邀请码名额限制；邮件发送限流（IP 10/h，邮箱 5/d） |
| 验证码令牌被拦截 | 令牌在 URL Fragment 不发给服务器；30 分钟过期；一次性使用 |
| 用户忘记密码 | 保留"找回密码"功能；可用验证码登录临时进入系统 |

---

## 实现顺序

1. **后端**：模型 + Schema 改动
2. **后端**：业务逻辑函数（注册、登录、验证码登录）
3. **后端**：API 端点（新增 `/request-login-link`，修改 `/login`、`/register`）
4. **后端**：邮件任务处理
5. **数据库**：迁移脚本
6. **前端**：登录界面改进（选项卡）
7. **前端**：注册界面改进（邀请码可选）
8. **测试**：集成测试所有流程

---

## 预期工作量

- 后端：4-6 小时
- 前端：2-3 小时
- 测试：1-2 小时
- **总计**：7-11 小时
