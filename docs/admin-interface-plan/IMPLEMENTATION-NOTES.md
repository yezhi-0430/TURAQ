# 管理员界面实施补充（2026-10-12）

以用户提供的 README 和 IMPLEMENTATION-PLAN 中方案 A 为实现依据：侧边栏管理员入口，仪表盘、用户管理、邀请码管理。沿用当前实际项目的 FastAPI `app.main:app`、Qwen、同源 API 和深色金色界面。

## 与现有数据契约对齐

- `/auth/session` 已返回可信的 `user.is_admin`，无需改 bootstrap 或新增重复 `/auth/me`。
- User 没有注册时间，Invite 没有创建时间；返回 null、页面显示未记录，不倒推时间，不自动迁移。
- 邀请码只存 digest，新码只在创建响应展示一次；列表显示 ID、使用名额、有效期和状态，不暴露 digest 或伪造原码。新码不存浏览器持久化，离开页面或账号变化清空。
- 工具审计不能代表模型 HTTP 请求、Token 或账单。工具排行、工具成功率、7 日趋势按真实工具尝试统计；近 24 小时研究请求与模型 HTTP 尝试从 ModelBudget 保留的事件统计。7 日模型请求/Token/费用没有可用记录，返回 null 并明确标注未记录。
- 7 日活动仅表示现存 LoginSession 中观察到的 last_seen_at，用户最近活动显示现存会话最大时间；不声明完整历史留存。
- 禁用账号同事务撤销其所有会话，重新启用不会复活旧会话。Web 不修改管理员角色，不禁用管理员账号，避免锁死管理入口。
- 所有管理员接口复用 require_admin 和真实 CSRF，严格拒绝额外/非法写字段；列表分页最多 100。撤销邀请码是更新 revoked 状态，不删除历史。
- 前端只用安全文本节点。请求错误、空状态、分页、确认、迟到响应、重复点击和结果不确定均显式处理；不自动重试写入。

## 实施清单

### 1. 后端 API 与测试

文件：`app/admin/api.py`、`user_service.py`、`invite_service.py`、`stats_service.py`、`app/main.py`、`tests/auth/test_admin_interface.py`。

- [x] 先写真实隔离会话测试：普通用户 403、匿名 401、CSRF/来源拒绝、分页与字段保密、禁用撤销会话、管理员保护、邀请码一次显示/状态、准确统计。
- [x] 用 `python -m pytest --confcutdir=tests/auth tests/auth/test_admin_interface.py` 确认缺少接口的失败。
- [x] 注册 `/api/v1/admin` 路由，提供 users GET/PATCH、invites GET/POST/DELETE、stats/overview GET、stats/llm-usage GET。
- [x] 写入事务提交后响应；数据库错误回滚并统一 503，不回显内部异常。
- [x] 重跑新增与现有账号测试，检查实际状态、会话撤销和数据未泄漏。

### 2. 前端与测试

文件：`frontend/admin.js`、`admin.css`、`index.html`、`vite.config.js`、`tests/frontend/admin.test.mjs`。

- [x] 先写管理员门禁、空/错误状态、安全渲染、取消、重复提交、迟到响应和新码清理的行为测试。
- [x] 添加默认隐藏的 ADMIN 菜单、三个页面、创建表单和操作确认窗口；复用 apiClient。
- [x] 在现有 selectPage 中检查可信会话，退出/换号/403 清除管理数据，切换页面取消旧读取。
- [x] 构建将 admin.js 纳入现有脚本打包，运行 Node 回归与 Vite build。

### 3. 浏览器验收和交付

- [x] 在独立本机服务、内存 SQLite 和合成普通/管理员账号下验证真实登录/CSRF/操作；关闭调度器、模型与外部行情，不修改正式数据。
- [x] 验证普通用户不可见、管理员三页、启用/禁用、生成/撤销、错误状态、手机布局；自动测试补齐空状态；截图不包含真实账号或新邀请码原文。
- [x] 只读审查、修复阻断项、相关回归、文档记录；按路径提交，保留现有其他工作。
