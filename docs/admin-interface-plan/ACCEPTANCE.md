# 管理员界面验收（2026-10-12）

## 使用方式

沿用项目现有启动方式：后端 `app.main:app`，前端 Vite 同源代理。使用已有已验证管理员账号登录，在侧边栏 ADMIN 区域进入管理仪表盘、用户管理、邀请码管理。普通账号不会显示该区域；直接访问管理 API 也会被拒绝。没有创建正式管理员、提升任何正式账号权限或自动修改数据库结构。

管理仪表盘提供总用户数、现存会话记录中观察到的近7日活动用户、可用邀请名额、近24小时研究请求/模型 HTTP 尝试，以及工具排行、工具成功率和上海日期的7日工具趋势。现有数据没有 Token、账单或完整7日模型请求历史，明确显示未记录，不根据工具条数推算金额。

用户列表支持邮箱片段、禁用状态筛选和每页20条分页。管理员账号受保护；禁用普通账号会在同一事务内撤销其会话，启用后需重新登录。注册时间没有原始字段，显示未记录；最近活动以现存会话最大 last_seen_at 为准。

邀请码表单限定名额1–10000、有效天数1–3650，后端严格校验类型与额外字段。创建原码只响应一次，不保存在浏览器持久化存储，离开页面或换号时清空；历史列表仅保留 ID、使用情况、有效期和状态。撤销保留历史，不影响已激活账号。写入断网不自动重试，提示结果待确认；写入已成功但列表刷新失败时保留原码并单独提示刷新失败。

## 后端接口

全部位于 `/api/v1/admin`，复用当前登录会话、require_admin、Origin 与 CSRF 检查；成功响应为 no-store。未新增重复的 `/auth/me`，`/auth/session` 已提供可信 is_admin。

- GET users：limit、offset、q、disabled，limit最多100。
- PATCH users/{id}：严格 `{ "disabled": true/false }`，管理员禁用返回409，不存在返回404。
- GET invites：limit、offset；返回 code=null，永不返回 digest。
- POST invites：max_uses、days，成功201；仅此响应提供原码。
- DELETE invites/{id}：更新 revoked，不删除历史。
- GET stats/overview：已记录指标与未知字段null。
- GET stats/llm-usage：metric=tool_attempts，明确统计工具尝试而非模型调用。

所有列表使用稳定 ID 排序；时间带 UTC 时区，页面转换为 Asia/Shanghai。数据库异常由会话上下文回滚并返回通用503。

## 实际测试

新增15项隔离账号/HTTP测试首先因缺少管理路由失败，然后通过；测试夹具最初使用 `.test` 邮箱被既有邮箱校验拒绝，改为合成 example.com 后才确认接口缺失的失败。覆盖真实登录权限、CSRF、字段保护、分页/搜索、禁用与旧会话撤销、邀请码一次展示/状态及统计口径。时间回归额外先复现 SQLite 无时区返回，再修正为显式 UTC。另有1项 PostgreSQL 专用测试验证上海午夜前后分组；使用独立测试数据库中的唯一临时 schema，测试后清理。

新增前端11项行为测试（10项管理模块、1项工作台重入）：普通账号门禁、安全文本、未知时间、迟到读取、取消、原码清理、403、未知写入、重复创建、跨账号迟到写入、重复确认、成功后刷新失败、写入期间导航与返回首页后重入。换号写入锁与刷新失败提示两条回归分别先复现失败，再修复。

| 检查 | 结果 |
|---|---|
| pytest tests/unit --confcutdir=tests/unit | 349 passed |
| pytest tests/auth --confcutdir=tests/auth（最终，含新增PG测试） | 106 passed |
| pytest tests/auth/test_admin_postgres.py --confcutdir=tests/auth | 1 passed |
| node --test tests/frontend/*.test.mjs（最终） | 50 passed |
| npm run build --prefix frontend | 成功，21模块 |
| Ruff check 本次Python文件及main.py | 通过 |
| Ruff format --check 本次新Python文件 | 通过 |

两个已有 Starlette/httpx/anyio 弃用提示保留。以上不等于所有根目录业务集成测试都重新运行。

## 浏览器验收

使用 `python -m tests.manual.admin_browser_fixture` 启动 `127.0.0.1:8893` 独立服务。真实账号密码校验、Cookie、CSRF、管理员路由、数据库服务和前端；账号与数据为合成样例，数据库为内存 SQLite。关闭调度器与模型、阻止HTTPX出站，不使用正式数据库或邮件。

- 合成管理员登录后显示三项管理菜单，仪表盘准确显示3用户、48可用名额、2工具尝试、50%工具成功率，费用/Token未记录。
- 禁用合成普通账号，确认窗口显示邮箱、ID与会话影响；后端成功后列表为已禁用。重新启用后列表恢复正常，管理员本身显示管理员保护。
- 生成3名额/2天邀请码，原码可见；切到用户页后原码为空。回邀请码页列表只有#3元数据；撤销后状态为已撤销，记录保留。
- 退出管理员并登录普通账号，管理菜单不可见，管理数据容器为空。
- 390×844手机仪表盘，document宽375px、视口390px，无页面横向溢出；恢复默认视口。
- 审查修复后的真实页面，从邀请码页返回首页并重新登录，恢复到同一管理页，刷新和生成按钮正常可用。
- 停止隔离服务后刷新，显示无法连接服务，不宣称刷新成功，也不自动重试写入。

截图均为合成账号，不含邀请码原文：[仪表盘](../visual-qa/admin/dashboard.jpg)、[用户管理](../visual-qa/admin/users.jpg)、[邀请码管理](../visual-qa/admin/invites.jpg)、[手机仪表盘](../visual-qa/admin/mobile-dashboard.jpg)、[普通账号](../visual-qa/admin/ordinary-account.jpg)、[断网提示](../visual-qa/admin/network-error.jpg)。没有用真实管理员执行测试写入。隔离标签与服务已关闭，8893不再监听，内存数据库随进程结束释放。

## 现有方案的修正

原目录仅有 README 和 IMPLEMENTATION-PLAN，所引用的 API-SPECIFICATION、UI-MOCKUP、DEPLOYMENT-GUIDE 未提供。实现以这两份文件和当前真实契约为依据；具体差异见 IMPLEMENTATION-NOTES。原文中的 Claude、app.main:application、完整成本记录、邀请码原码/注册日期可读等假设未沿用。

## 独立审查

只读审查发现两项P2：写入完成时已切换页面会留下禁用的生成按钮；从管理页回首页后重新进入会留下未激活的管理控制器。两项回归先失败，再分别修复为同一操作结束即可恢复控件（继续保留账号/操作编号隔离）、工作台重入恢复对应管理控制器。最终前端50项通过，构建和Ruff通过；未再次派发审查。没有未处理的审查项。

新增夹具显式填写 pending_expires_at，兼容既有非空数据库字段；不依赖工作目录中其他账号字段修改。原有未提交的入场样式、预加载、账号修复等继续保留，不混入本次功能提交。
