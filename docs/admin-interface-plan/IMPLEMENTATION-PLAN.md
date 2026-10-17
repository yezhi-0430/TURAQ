# 管理员界面实施计划 - 方案A

## Context（背景）

TURAQ 是一个 A 股智能研究平台，使用 FastAPI + PostgreSQL + Claude LLM。目前系统已有完整的用户认证体系和管理员权限控制机制，但**缺少 Web 管理界面**。管理员只能通过命令行工具操作，用户无法自助查看统计数据。

**现状**：
- ✅ User 模型有 `is_admin` 字段
- ✅ 邀请码系统已实现（Invites 表 + 命令行工具）
- ✅ LLM 成本记录完整（ToolAuditRecord 表）
- ✅ 权限验证已有 `require_admin` 依赖
- ❌ 无 Web 管理界面
- ❌ 无统计 API

**目标**：
实现基于侧边栏动态显示的管理员 Web 界面（方案A），包含用户管理、邀请码管理、使用统计三大核心功能。

**用户故事**：
作为管理员，我希望登录后能在侧边栏看到"管理后台"入口，点击后查看所有用户、生成邀请码、监控 LLM 使用情况，而不需要登录服务器执行命令行。

---

## 实施计划

### Phase 1: 后端 API（基础设施）

#### 1.1 添加用户信息接口
**文件**: `app/auth/api.py`

添加 `GET /api/v1/auth/me` 端点，返回当前用户信息（包括 `is_admin` 状态）。

**返回结构**:
```json
{
  "id": 1,
  "email": "admin@turaq.com",
  "is_admin": true,
  "verified": true
}
```

**实现**:
```python
@router.get("/me")
def get_current_user(actor: Actor = Depends(require_actor)):
    return {
        "id": actor.id,
        "email": actor.email,
        "is_admin": actor.is_admin,
        "verified": True  # require_actor 已验证
    }
```

---

#### 1.2 创建管理员 API 路由模块
**文件**: `app/admin/api.py` (新建)

创建管理员专属路由，所有端点使用 `require_admin` 依赖保护。

**路由规划**:
- `GET /api/v1/admin/users` - 用户列表（分页）
- `PATCH /api/v1/admin/users/{id}` - 修改用户状态（禁用/启用）
- `GET /api/v1/admin/invites` - 邀请码列表
- `POST /api/v1/admin/invites` - 创建邀请码
- `DELETE /api/v1/admin/invites/{id}` - 撤销邀请码
- `GET /api/v1/admin/stats/overview` - 统计概览
- `GET /api/v1/admin/stats/llm-usage` - LLM 使用明细

**挂载**: 在 `app/main.py` 中注册路由
```python
from app.admin.api import router as admin_router
application.include_router(admin_router)
```

---

#### 1.3 用户管理 API
**文件**: `app/admin/user_service.py` (新建)

**功能**:
- `list_users(session, limit, offset)` - 分页查询用户
- `toggle_user_status(session, user_id, disabled)` - 启用/禁用用户

**返回示例**:
```json
{
  "users": [
    {
      "id": 2,
      "email": "user@example.com",
      "verified": true,
      "disabled": false,
      "is_admin": false,
      "created_at": "2026-10-01T10:00:00Z",
      "invite_code": "ABC123",
      "last_seen": "2026-10-12T08:30:00Z"
    }
  ],
  "total": 50,
  "page": 1,
  "per_page": 20
}
```

---

#### 1.4 邀请码管理 API
**文件**: `app/admin/invite_service.py` (新建)

**功能**:
- `list_invites(session)` - 查询所有邀请码
- `create_invite(session, max_uses, days)` - 生成新邀请码
- `revoke_invite(session, invite_id)` - 撤销邀请码

**复用**: `app/auth/service.py` 中的 `adjust_invite()` 函数

**返回示例**:
```json
{
  "invites": [
    {
      "id": 1,
      "code": "TURAQ2024ABC",
      "max_uses": 50,
      "used_count": 23,
      "expires_at": "2026-11-12T00:00:00Z",
      "revoked": false,
      "created_at": "2026-10-12T10:00:00Z"
    }
  ]
}
```

---

#### 1.5 统计 API
**文件**: `app/admin/stats_service.py` (新建)

**统计概览** (`/stats/overview`):
```json
{
  "total_users": 50,
  "active_users_7d": 32,
  "total_invites": 10,
  "available_slots": 127,
  "llm_calls_today": 89,
  "llm_calls_7d": 543
}
```

**LLM 使用明细** (`/stats/llm-usage`):
```json
{
  "by_user": [
    {"email": "user@example.com", "calls": 45, "success_rate": 0.95},
    {"email": "admin@turaq.com", "calls": 32, "success_rate": 1.0}
  ],
  "by_tool": [
    {"tool_name": "get_stock_profile", "usage": 120},
    {"tool_name": "get_daily_prices", "usage": 85}
  ],
  "daily_trend": [
    {"date": "2026-10-12", "calls": 89},
    {"date": "2026-10-11", "calls": 102}
  ]
}
```

**SQL 查询**: 基于 `tool_audit_records` 表聚合

---

### Phase 2: 前端基础（权限判断 + 路由）

#### 2.1 前端获取用户信息
**文件**: `frontend/api.js`

修改 `bootstrap()` 函数，调用 `/auth/me` 获取完整用户信息。

**现状**:
```javascript
session = {
  user: {id, email},  // 从 /auth/session 获取
  csrf_token: "...",
  mail_configured: true,
  model_mode: "qwen"
}
```

**修改后**:
```javascript
session = {
  user: {id, email, is_admin: true},  // 新增 is_admin
  csrf_token: "...",
  mail_configured: true,
  model_mode: "qwen"
}
```

**实现**: 在 `bootstrap()` 中额外调用 `/auth/me` 或合并到 `/auth/session` 返回。

---

#### 2.2 侧边栏添加管理员菜单
**文件**: `frontend/index.html`

在侧边栏 `<nav>` 中添加管理员菜单（默认隐藏）。

**位置**: 第 91 行后（现有菜单下方）

```html
<!-- 分隔线 -->
<div class="side-label admin-section" id="admin-label" hidden>ADMIN</div>

<!-- 管理员菜单 -->
<button class="nav-button admin-nav" data-page="admin-dashboard" id="admin-dashboard-nav" hidden>
  <svg class="icon"><use href="#i-grid"/></svg>管理仪表盘
</button>
<button class="nav-button admin-nav" data-page="admin-users" id="admin-users-nav" hidden>
  <svg class="icon"><use href="#i-list"/></svg>用户管理
</button>
<button class="nav-button admin-nav" data-page="admin-invites" id="admin-invites-nav" hidden>
  <svg class="icon"><use href="#i-shield"/></svg>邀请码管理
</button>
```

**CSS 样式** (在 `<style>` 中添加):
```css
.admin-section {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid var(--line);
  color: var(--red); /* 红色标识管理区 */
}

.admin-nav {
  border-left: 2px solid transparent;
}

.admin-nav.active {
  border-left-color: var(--red);
}
```

---

#### 2.3 动态显示管理员菜单
**文件**: `frontend/index.html` (JavaScript 部分)

在 `bootstrap()` 成功后，根据 `session.user.is_admin` 显示菜单。

**实现** (约第 216 行后):
```javascript
function updateAdminMenu() {
  const isAdmin = session.user?.is_admin === true;
  const adminElements = [
    $('admin-label'),
    $('admin-dashboard-nav'),
    $('admin-users-nav'),
    $('admin-invites-nav')
  ];
  
  adminElements.forEach(el => {
    if (el) el.hidden = !isAdmin;
  });
}

// 在 bootstrap 成功后调用
window.apiClient.bootstrap().then(() => {
  updateAdminMenu();
  // ... 现有逻辑
});

// 登录/登出后也需更新
window.apiClient.subscribe((newSession) => {
  session = newSession;
  updateAdminMenu();
});
```

---

#### 2.4 添加管理员页面路由
**文件**: `frontend/index.html`

在 `applyPage(page)` 函数中添加管理员页面分支。

**修改** (约第 164 行):
```javascript
function applyPage(page) {
  // 隐藏所有页面
  $('page-dashboard').hidden = true;
  $('page-watchlist').hidden = true;
  $('page-agent').hidden = true;
  $('page-admin').hidden = true;  // 新增

  // 显示目标页面
  if (page === 'dashboard') {
    $('page-dashboard').hidden = false;
    window.marketDashboard?.setVisible(true);
  } else if (page === 'admin-dashboard' || page === 'admin-users' || page === 'admin-invites') {
    $('page-admin').hidden = false;
    window.adminPanel?.setVisible(page);  // 新增模块
  }
  // ... 其他页面
}
```

---

### Phase 3: 前端管理界面

#### 3.1 创建管理员页面容器
**文件**: `frontend/index.html`

在 `<main>` 中添加管理员页面容器。

**位置**: 第 118 行后（其他页面容器旁边）

```html
<section id="page-admin" class="page-container" hidden>
  <div class="admin-header">
    <h1 class="admin-title">管理后台</h1>
    <div class="admin-tabs">
      <button class="admin-tab active" data-tab="dashboard">仪表盘</button>
      <button class="admin-tab" data-tab="users">用户管理</button>
      <button class="admin-tab" data-tab="invites">邀请码</button>
    </div>
  </div>
  
  <div class="admin-content">
    <!-- 动态加载内容 -->
    <div id="admin-tab-dashboard" class="admin-tab-content"></div>
    <div id="admin-tab-users" class="admin-tab-content" hidden></div>
    <div id="admin-tab-invites" class="admin-tab-content" hidden></div>
  </div>
</section>
```

---

#### 3.2 管理员样式
**文件**: `frontend/admin.css` (新建)

```css
.admin-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.admin-title {
  font-size: clamp(1.5rem, 2.5vw, 2rem);
  font-weight: 600;
  color: var(--text);
}

.admin-tabs {
  display: flex;
  gap: 8px;
}

.admin-tab {
  padding: 8px 16px;
  border-radius: 6px;
  background: transparent;
  border: 1px solid var(--line);
  color: var(--muted);
  cursor: pointer;
  transition: all 0.2s;
}

.admin-tab.active {
  background: var(--panel);
  border-color: var(--gold);
  color: var(--gold);
}

.admin-content {
  background: var(--panel);
  border-radius: 12px;
  padding: 24px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
}

.stat-card {
  background: var(--raised);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid var(--line);
}

.stat-label {
  color: var(--muted);
  font-size: 0.875rem;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--gold);
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th {
  text-align: left;
  padding: 12px;
  border-bottom: 1px solid var(--line);
  color: var(--muted);
  font-weight: 500;
}

.data-table td {
  padding: 12px;
  border-bottom: 1px solid var(--line);
}

.badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}

.badge-success { background: #a5c6aa20; color: var(--green); }
.badge-danger { background: #e79a9020; color: var(--red); }
.badge-warning { background: #d2ba8520; color: var(--gold); }
```

**引入**: 在 `frontend/index.html` 的 `<head>` 中添加
```html
<link rel="stylesheet" href="admin.css">
```

---

#### 3.3 管理员 JavaScript 模块
**文件**: `frontend/admin.js` (新建)

```javascript
(function() {
  'use strict';

  const $ = id => document.getElementById(id);
  let currentTab = 'dashboard';

  // 模块接口
  window.adminPanel = {
    async setVisible(page) {
      // 从 page 中提取 tab（admin-users → users）
      const tab = page.replace('admin-', '');
      await switchTab(tab);
    }
  };

  // 切换标签页
  async function switchTab(tab) {
    currentTab = tab;
    
    // 更新标签按钮状态
    document.querySelectorAll('.admin-tab').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    
    // 隐藏所有内容
    document.querySelectorAll('.admin-tab-content').forEach(el => {
      el.hidden = true;
    });
    
    // 显示目标内容
    const content = $(`admin-tab-${tab}`);
    content.hidden = false;
    
    // 加载数据
    if (tab === 'dashboard') await loadDashboard();
    if (tab === 'users') await loadUsers();
    if (tab === 'invites') await loadInvites();
  }

  // 加载仪表盘
  async function loadDashboard() {
    try {
      const stats = await window.apiClient.request('/admin/stats/overview');
      const llm = await window.apiClient.request('/admin/stats/llm-usage');
      
      $('admin-tab-dashboard').innerHTML = `
        <div class="stat-grid">
          <div class="stat-card">
            <div class="stat-label">总用户数</div>
            <div class="stat-value">${stats.total_users}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">7日活跃</div>
            <div class="stat-value">${stats.active_users_7d}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">今日 AI 调用</div>
            <div class="stat-value">${stats.llm_calls_today}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">可用邀请名额</div>
            <div class="stat-value">${stats.available_slots}</div>
          </div>
        </div>
        
        <h3>LLM 使用排行（Top 5）</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>用户</th>
              <th>调用次数</th>
              <th>成功率</th>
            </tr>
          </thead>
          <tbody>
            ${llm.by_user.slice(0, 5).map(u => `
              <tr>
                <td>${u.email}</td>
                <td>${u.calls}</td>
                <td>${(u.success_rate * 100).toFixed(1)}%</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    } catch (error) {
      $('admin-tab-dashboard').innerHTML = '<p class="error">加载失败</p>';
    }
  }

  // 加载用户列表
  async function loadUsers() {
    try {
      const data = await window.apiClient.request('/admin/users?limit=50');
      
      $('admin-tab-users').innerHTML = `
        <table class="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>邮箱</th>
              <th>状态</th>
              <th>管理员</th>
              <th>注册时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            ${data.users.map(u => `
              <tr>
                <td>${u.id}</td>
                <td>${u.email}</td>
                <td>
                  ${u.disabled 
                    ? '<span class="badge badge-danger">已禁用</span>' 
                    : '<span class="badge badge-success">正常</span>'}
                </td>
                <td>${u.is_admin ? '✓' : ''}</td>
                <td>${new Date(u.created_at).toLocaleDateString('zh-CN')}</td>
                <td>
                  <button class="btn-toggle-user" data-id="${u.id}" data-disabled="${u.disabled}">
                    ${u.disabled ? '启用' : '禁用'}
                  </button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
      
      // 绑定禁用/启用按钮事件
      document.querySelectorAll('.btn-toggle-user').forEach(btn => {
        btn.onclick = () => toggleUser(btn.dataset.id, btn.dataset.disabled === 'true');
      });
    } catch (error) {
      $('admin-tab-users').innerHTML = '<p class="error">加载失败</p>';
    }
  }

  // 加载邀请码列表
  async function loadInvites() {
    try {
      const data = await window.apiClient.request('/admin/invites');
      
      $('admin-tab-invites').innerHTML = `
        <div style="margin-bottom: 16px;">
          <button id="btn-create-invite" class="btn-primary">生成新邀请码</button>
        </div>
        
        <table class="data-table">
          <thead>
            <tr>
              <th>邀请码</th>
              <th>使用情况</th>
              <th>有效期</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            ${data.invites.map(inv => `
              <tr>
                <td><code>${inv.code}</code></td>
                <td>${inv.used_count} / ${inv.max_uses}</td>
                <td>${new Date(inv.expires_at).toLocaleDateString('zh-CN')}</td>
                <td>
                  ${inv.revoked 
                    ? '<span class="badge badge-danger">已撤销</span>' 
                    : '<span class="badge badge-success">有效</span>'}
                </td>
                <td>
                  ${!inv.revoked ? `<button class="btn-revoke" data-id="${inv.id}">撤销</button>` : ''}
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
      
      // 绑定创建按钮
      $('btn-create-invite').onclick = createInvite;
      
      // 绑定撤销按钮
      document.querySelectorAll('.btn-revoke').forEach(btn => {
        btn.onclick = () => revokeInvite(btn.dataset.id);
      });
    } catch (error) {
      $('admin-tab-invites').innerHTML = '<p class="error">加载失败</p>';
    }
  }

  // 切换用户状态
  async function toggleUser(userId, currentlyDisabled) {
    const action = currentlyDisabled ? '启用' : '禁用';
    if (!confirm(`确定要${action}此用户吗？`)) return;
    
    try {
      await window.apiClient.request(`/admin/users/${userId}`, {
        method: 'PATCH',
        body: { disabled: !currentlyDisabled }
      });
      await loadUsers(); // 重新加载列表
    } catch (error) {
      alert(`操作失败：${error.message}`);
    }
  }

  // 创建邀请码
  async function createInvite() {
    const maxUses = prompt('邀请名额（例如：50）', '50');
    const days = prompt('有效天数（例如：30）', '30');
    
    if (!maxUses || !days) return;
    
    try {
      const result = await window.apiClient.request('/admin/invites', {
        method: 'POST',
        body: { 
          max_uses: parseInt(maxUses), 
          days: parseInt(days) 
        }
      });
      
      alert(`邀请码已生成：\n${result.code}\n\n请复制给用户使用。`);
      await loadInvites();
    } catch (error) {
      alert(`生成失败：${error.message}`);
    }
  }

  // 撤销邀请码
  async function revokeInvite(inviteId) {
    if (!confirm('确定要撤销此邀请码吗？未使用的名额将失效。')) return;
    
    try {
      await window.apiClient.request(`/admin/invites/${inviteId}`, {
        method: 'DELETE'
      });
      await loadInvites();
    } catch (error) {
      alert(`撤销失败：${error.message}`);
    }
  }

  // 初始化标签切换事件
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.admin-tab').forEach(btn => {
      btn.onclick = () => switchTab(btn.dataset.tab);
    });
  });
})();
```

**引入**: 在 `frontend/index.html` 的 `<body>` 底部添加
```html
<script src="admin.js"></script>
```

---

### Phase 4: 安全加固

#### 4.1 后端权限二次验证
所有管理员 API 都必须使用 `require_admin` 依赖，前端绕过检查也无法访问。

**示例**:
```python
@router.get("/api/v1/admin/users")
def list_users(
    actor: Actor = Depends(require_admin),  # 强制管理员
    session: Session = Depends(get_db)
):
    # 只有 is_admin=True 的用户才能到达这里
    ...
```

#### 4.2 前端路由守卫
在 `selectPage()` 中添加管理员权限检查。

**修改** (frontend/index.html):
```javascript
async function selectPage(page) {
  if (!await window.account.requireLogin()) return;
  
  // 管理员权限检查
  if (page.startsWith('admin-') && !session.user?.is_admin) {
    alert('无权访问管理后台');
    selectPage('dashboard');
    return;
  }
  
  // ... 现有逻辑
}
```

#### 4.3 CSRF 保护
所有写操作（POST/PATCH/DELETE）自动携带 CSRF Token（`api.js` 已实现）。

---

## 关键文件修改清单

### 新建文件
- `app/admin/api.py` - 管理员路由
- `app/admin/user_service.py` - 用户管理服务
- `app/admin/invite_service.py` - 邀请码管理服务
- `app/admin/stats_service.py` - 统计服务
- `frontend/admin.js` - 管理员前端逻辑
- `frontend/admin.css` - 管理员样式

### 修改文件
- `app/auth/api.py` - 添加 `GET /auth/me` 端点
- `app/main.py` - 注册管理员路由
- `frontend/index.html` - 添加侧边栏菜单、页面容器、权限判断
- `frontend/api.js` - 在 `bootstrap()` 中获取 `is_admin` 状态

---

## 验证方案

### 1. 后端 API 测试
```bash
# 创建管理员账号
python -m app.auth.admin bootstrap-admin --email admin@turaq.com --verified-email

# 启动服务
uvicorn app.main:application --reload

# 测试用户信息接口
curl http://localhost:8000/api/v1/auth/me \
  -H "Cookie: session=<token>"

# 测试管理员接口（需登录管理员账号）
curl http://localhost:8000/api/v1/admin/users
curl http://localhost:8000/api/v1/admin/stats/overview
```

### 2. 前端功能测试
1. 使用普通用户登录 → 侧边栏无管理员菜单
2. 使用管理员登录 → 侧边栏显示"ADMIN"区域
3. 点击"管理仪表盘" → 显示统计数据
4. 点击"用户管理" → 显示用户列表，测试禁用/启用功能
5. 点击"邀请码管理" → 生成邀请码，测试撤销功能

### 3. 权限验证测试
1. 前端绕过：修改浏览器 localStorage，手动添加 `is_admin: true` → 后端 403 拒绝
2. 直接访问 API：使用普通用户 Token 请求 `/admin/users` → 403 错误
3. CSRF 攻击：跨域请求管理员接口 → CSRF Token 验证失败

---

## 预估工作量

- **Phase 1 后端 API**: 4-6 小时
  - 用户管理: 1.5 小时
  - 邀请码管理: 1 小时
  - 统计 API: 2 小时
  - 测试: 1 小时

- **Phase 2 前端基础**: 2-3 小时
  - 路由和权限判断: 1 小时
  - 侧边栏菜单: 1 小时
  - 测试: 0.5 小时

- **Phase 3 前端界面**: 5-7 小时
  - 仪表盘: 2 小时
  - 用户管理: 2 小时
  - 邀请码管理: 2 小时
  - 样式优化: 1 小时

- **Phase 4 安全加固**: 1 小时

**总计**: 12-17 小时

---

## 后续扩展（未包含在本计划）

- WebSocket 实时通知（新用户注册、LLM 调用超限）
- 导出功能（用户列表、审计日志 CSV）
- 批量操作（批量禁用用户、批量生成邀请码）
- 高级统计图表（ECharts 趋势图）
- 审计日志详情查看（查看每次 AI 对话的完整内容）
- 用户配额管理（为单个用户设置独立限额）
