# 账号、所有权和操作确认：本地验收

更新：2026-10-12。当前为本地开发分支 `codex/email-invite-auth`；未上线，真实邮件及服务器配置按用户要求留到最后。自动检查及浏览器验收已完成，最终整体代码审查进行中。

## 已实现的边界

- 邮箱密码登录、验证邮箱、注册/重发/找回/重置接口；密码统一为 6–15 个 Unicode 字符，不修剪空格、不截断。
- 可重复使用的邀请码默认允许 50 个激活账号，7 天有效；仅在邮箱验证激活成功时占用名额。操作者可以调整、续期、撤销。
- HttpOnly 会话 Cookie、JSON 写入的 CSRF 与同源检查、共享数据库登录及邮件频率限制。用户身份来自后端会话。
- 私人自选按所有者读取和修改，其他用户分组返回 404；行情驾驶舱只读取当前用户自选。价格导入仅限管理员。
- Agent 只读工具保留原边界。建议显示为待确认；只有用户最终确认才发送执行请求。后端成功移除与动作审计同一事务提交。
- 工具来源区分执行时间、返回数据范围的最新交易日、记录数与未知上游信息。工具审计记录当前账号。
- 研究接口共享用户额度，默认 20 次/滚动 24 小时、2 次/滚动分钟、1 个并发。站点默认每日 200 次实际模型 HTTP 尝试，包含重试和工具轮次；这不是精确金额上限。
- 模型输出、轮数、响应大小、HTTP 和总处理时间有上限，额度或存储故障时拒绝调用。`MODEL_ENABLED=false` 关闭研究调用，保留自选/行情。

## 本地启动

项目根目录中的 PostgreSQL 配置必须先就绪。使用项目虚拟环境避免调用 Conda 中缺少依赖的 Python：

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
$env:SITE_BASE_URL = 'http://localhost:3000'
$env:AUTH_COOKIE_SECURE = 'false'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8888
```

另一个终端：

```powershell
cd frontend
npm install
npm run dev
```

浏览器访问 `http://localhost:3000`，点击“进入工作台”。本地 HTTP 的两个环境变量需要在启动后端的终端中设置；不适用于正式 HTTPS 部署。Vite 将同源 `/api/` 转发至 8888，并保留 Origin；直接打开 HTML 或使用 `python -m http.server` 不支持该登录流程。

看到 `Application startup complete` 表示启动成功。匿名请求私人接口得到 401 是登录保护；正常页面应先展示登录窗口并停止私人刷新。停止后端使用所在终端的 Ctrl+C。

## 本次数据库恢复

原本地数据库缺少账号表与自选所有者列。用户明确要求恢复访问并提供首个账号邮箱后，先用 PostgreSQL 17 `pg_dump` 生成本机备份，再显式运行 schema_upgrade。备份保留在项目 `.local-backups/20261011-230123/before-local-login.dump`，不会提交 Git。

升级前后原数据数量一致：股票 1、日线 0、自选组 0、自选成员 0、工具审计 7；没有旧分组需要认领。首个账号密码由用户在本地命令行交互输入，未经过聊天或测试夹具。本轮不需要重复创建该账号。

其他数据库首次启用必须先备份、显式升级。有历史分组时先创建并核验指定管理员，再使用 `python -m app.schema_upgrade --owner-id <ID>`；不自动将旧数据分配给首个注册者。

操作者命令（按实际需要执行，不是每次启动步骤）：

```powershell
.\.venv\Scripts\python.exe -m app.auth.admin bootstrap-admin --email <自己的邮箱> --verified-email
.\.venv\Scripts\python.exe -m app.auth.admin create-invite --max-uses 50 --days 7
.\.venv\Scripts\python.exe -m app.auth.admin adjust-invite <邀请码ID> --max-uses 100 --days 7
.\.venv\Scripts\python.exe -m app.auth.admin adjust-invite <邀请码ID> --revoke
.\.venv\Scripts\python.exe -m app.auth.admin disable-user <用户ID>
```

邀请码由终端输出，按需交给内测者；真实邮件未配置前不能把它当作可用的公开注册流程。

## 验证记录

在 `f65e100` 修复后由主代理重新执行：

| 检查 | 结果 |
| --- | --- |
| `pytest tests/auth --confcutdir=tests/auth -q -o addopts='' --tb=short` | 85 通过，含 PostgreSQL 邀请/额度竞争、连续 SQL 和实际 HTTP 流取消 |
| `pytest tests/unit --confcutdir=tests/unit -q -o addopts='' --tb=short` | 349 通过 |
| `pytest tests --ignore=tests/unit --ignore=tests/auth --ignore=tests/frontend -q -o addopts='' --tb=short` | 113 通过，专用测试数据库 |
| `node --test tests/frontend/*.test.mjs` | 30 通过 |
| `npm run build --prefix frontend` | 成功，16 模块，所有引用资源存在 |
| `python -m pip check` | 无依赖冲突 |

独立 HTTP 夹具也验证了真实会话/CSRF下的创建、重命名、添加、JSON DELETE、退出、匿名 401、跨账号 404及拒绝其他账号分组的动作，无跨账号修改。Python 测试仅剩已有第三方 Starlette/httpx/anyio 弃用提示。

修复后的实际浏览器（Cua）验收：登录后显示等待提问；日线来源显示返回范围最新日期 2026-10-09 与 2 条合成记录；取消保留股票；最终确认只发送一次成功动作请求，A 分组变为 0；正常退出接口 200，立即可登录 B，B 分组仍有 1 只股票、对话为空；390×844 手机布局可用。停止隔离服务后，退出仍清空本机私有页面，警告服务端结果未确认，关闭窗口不会恢复旧工作台。保留旧 Cookie 的刷新屏蔽另由 Node 回归覆盖，不把服务已停止的浏览器检查当作该情形的证明。

证据见 [执行结果和来源](visual-qa/auth/confirmed-action-source.jpg)、[确认窗口](visual-qa/auth/confirm-before-action.jpg)、[手机隔离页面](visual-qa/auth/mobile-account-isolation.jpg)和[退出失联提示](visual-qa/auth/logout-service-unavailable.jpg)。所有截图均为合成账号/数据。隔离进程已关闭。

测试使用独立 SQLite 夹具或专用 `a_share_risk_agent_test` 数据库。浏览器使用独立后端 8891/前端 3001，合成账号、合成日线和确定性假模型，关闭行情网络与调度器；不调用日常环境的 Qwen、SMTP 或实时行情。浏览器验收图中的 `qa-*` 为测试账号。

初次旧单元夹具没有覆盖新增额度依赖，曾可能尝试日常数据库连接/时钟查询，返回 503 后回滚；随后修正隔离夹具。该次运行不能声称零正式连接尝试；没有成功研究准入或模型调用。

## 尚未验收的上线部分

真实 SMTP 连通及邮箱送达、公开注册端到端、HTTPS 与代理/可信 IP 配置、生产数据库迁移、服务器资源和多进程运行仍需最后验收。发信后台任务是进程内尽力执行，重启可能丢失任务；没有持久邮件队列。

本轮没有调用真实付费模型，不能据此声称供应商服务或账单额度已验收。公开行情源没有 SLA，证券目录仍有覆盖/更新限制，见 [证券目录集成检查](2026-10-11-stock-catalog-integration-review.md)。Day12 对话持久化与刷新恢复、风险监控、模拟交易及系统设置不在本轮完成范围。
