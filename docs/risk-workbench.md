# 自选股风险工作台（2026-10-13）

本次完成文本分析与历史工作台。实际入口是 `frontend/index.html`，新增独立 `risk.js` / `risk.css`，延续原生 JavaScript、Vite、账户栏、导航及黑金配色。React 占位页未改动。已有认证、入场页、部署文件及其他工作区修改保留。

## 功能与统计口径

- 手动提交公告 / 财报（1–20,000 字），可关联当前账号自选股票，附标题、发布日期、HTTP(S) 链接和页码。防止并发提交，通过账号 + request_id 保证重传幂等；不同输入复用编号返回 409。
- 与现有 `POST /api/v1/risk-summary` 使用同一摘要生成函数、模型依赖及 model_admission，原接口响应保持兼容。前端使用带持久化的 `/risk/analyses`，不把客户端结果当可信后端记录重新提交。
- 分析记录保存输入、结构化结果、模型模式、开始/生成时间、生成状态和不可变 version=1。`previous_version_id` 保留后续重新分析版本关联能力；本次没有可修改旧结果的接口。
- 范围为全部自选组、指定分组或单股；股票去重计数。全部范围默认包含未关联资料，可取消；指定组/单股不包含未关联资料。离开自选范围的历史资料仍可通过“分析历史”查看。
- 列表、总数、待关注/高风险/信息不足使用相同类型、股票、等级、处理状态、资料发布日期筛选。待关注 = 未查看 + 持续关注；高风险不因已查看减少。测试模型事件仍可查看，但不进入三项真实风险统计。统计仅反映已保存分析，不表示自动扫描覆盖或风险发生率。
- 默认未查看高风险优先，其后按等级、分析生成时间和 ID 倒序；分页每页 10 条，上限 50。
- 详情区分结论、模型评级依据、资料提取事实、推断、未知项、原始来源、模型来源；查看本身不会自动把事件标记已查看。支持已查看/持续关注和携带股票、资料背景进入研究助手，继续研究不自动提交模型请求。
- 页面适配桌面双栏和手机列表/详情切换；提供加载、空记录、请求失败、限流、模型关闭、超时、资料不足和自选范围部分加载失败提示。

## 身份与证据边界

每个 API 使用 `require_actor`；写操作沿用 Cookie/Origin/CSRF。查询与状态修改均带用户条件，他人 ID 返回 404。前端复用 apiClient 的身份版本和请求取消，组件再检查账号、列表、范围和详情版本；退出清空输入/证据/历史，旧请求不能恢复私有页面。

用户来源是 `kind=user_material, verification=user_provided`，保存原文、日期、标题、URL、页码，`conclusion_refs=[]`。现有摘要接口不能证明原文与每条结论对应，因此页面明确表示“未建立逐条结论对应”；不伪造核验状态。模型 sources 只作未核验字符串展示，不生成证据链接。内容通过 textContent 渲染；来源只启用无凭据、无空白/反斜杠的 HTTP(S)，新窗带 noopener/noreferrer，后端不抓取用户链接。

fake 模式强制清空事实/推断/模型来源、评级 unknown，明确“隔离测试模型，未真实分析”；不能成为真实高风险。程序负责数据库计数，模型负责摘要解释，本次未引入任何模型数值指标。

请求受理后先保存 pending，再调用模型；成功结果与事件在同一个事务中提交，已知模型错误与数据库保存超时记录为 failed。数据库完全不可用时无法确认失败写入，历史 pending 超过全局最大处理时限后展示 unconfirmed（结果待确认），不自动重新分析。不覆盖可能已成功提交的 completed 记录。浏览器连接中断保留 request_id，刷新历史确认失败后才允许新的手动尝试。

## 接口与启用

| 路由 | 用途 |
| --- | --- |
| POST `/api/v1/risk/analyses` | 生成并保存，返回事件及结构化详情 |
| GET `/api/v1/risk/analyses?page=1&page_size=10` | 当前账号全部分析历史及生成状态 |
| GET `/api/v1/risk/events` | 筛选列表、分页、同口径 overview 和扫描能力状态 |
| GET `/api/v1/risk/events/{id}` | 本人事件、结果、输入与证据 |
| PATCH `/api/v1/risk/events/{id}` | `{status: unread/viewed/following}` |

列表参数：group_id、symbol、include_unlinked、risk_type、risk_level、status、date_from/date_to（**资料发布日期**）、page/page_size。关联股票必须在当前用户自选中；客户端不能指定 owner_id、风险结论、生成状态或已核验证据。

已有账号/自选库启用时，按项目习惯先备份数据库，然后运行仅新增两张表的升级命令，再重启 FastAPI：

```powershell
.\.venv\Scripts\python.exe -m app.risk_schema
# 重启原有 FastAPI 启动进程，沿用现有端口与 .env 配置
cd frontend
npm run build
```

`app.risk_schema` 可重复执行，只创建 `risk_analyses` / `risk_events`，不改旧表及旧数据。现有 `app.schema_upgrade` 也会通过 Base.metadata 注册创建新表。后续一键启动器已在本机备份数据库并完成风险表初始化，3000 / 8888 前后端已启动；未提交或发布工作区。双击根目录 `一键启动.bat` 可启动，详见 `docs/windows-launcher.md`。

## 第三阶段接口边界（尚未接通）

当前 scan 返回 `status=not_connected`、`task_status=not_scanned`、last_scanned_at=null、coverage=null，公告、财报、量价适配器均 false。页面没有可点击的“执行扫描”，量价筛选返回真实空状态，没有模拟事件/情绪分数。

接通顺序与数据合同：

1. 动态数据适配器：每份公告/财报返回稳定 source_id、证券代码、标题、发布日期、URL、原文和 collected_at；行情返回 provider、trade_date、quote_time、OHLCV、单位及 freshness。程序校验时间、单位与复权口径，不从模型解释反推数值。
2. 计算器：输入经核验的数据，输出 rule_id、rule_version、数值事实、比较区间、阈值依据与缺失项。公告/财报阈值和量价条件用真实样本验证后上线；模型只能摘要和解释。
3. 扫描任务 API：`POST /risk/scans` 接收 all/group/stock 范围，服务端解析用户所有权并保存证券范围快照；`GET /risk/scans/{id}` 返回 started_at、finished_at、每只股票/每类资料的成功或失败及重试情况。任务状态 queued/running/completed/partial_failed/failed；覆盖状态 not_scanned/current/partial/stale 独立。不存在源数据不能当作扫描成功无事件。
4. 去重：由 owner + symbol + source_id/交易日 + rule_id 生成 dedup_key，已有 owner/dedup_key 唯一约束。重复扫描复用事件、增加新的不可变分析版本，不重置处理状态；与用户 request_id 幂等分别管理。
5. 重试与调度：仅重试明确失败的适配器项，指数退避、次数上限，保存每次错误与最终结果；结果不确定的模型调用不自动重复。复用现有 APScheduler 前须防止多 worker 重复调度，扫描入口待全流程验收后启用。

## RAG / A 股扩展合同

RiskEvent.context 已预留 observations、knowledge_references、historical_cases，risk_type 为可扩展数据库字符串，前端已有未来 sentiment 标签。当前 API 不接受情绪类型，避免尚未验证的手工/模型评分成为正式事件。

静态知识使用独立知识存储与索引，不写进实时行情表。未来知识引用必须包含 reference_id、author、book_title、edition/version、page、applicable_markets、historical_context、excerpt、retrieved_at、verification。动态观测必须包含 source/provider、metric/value/unit、trade_date/observed_at、collected_at、freshness；模型推断仍保存于 inferences。

历史案例关联保存 case_id、参考出处、历史条件、当前条件、相似点、差异及不适用条件。跨市场结论先注明市场机制差异，书籍观点仅为研究材料，不作确定规律。情绪指标、阈值与实时数据接通后验证，不预置分数。检索/用户资料中的指令只能作为材料文本，不能改变 Agent 权限、执行规则或确认流程。

## 验证记录

测试命令：

```powershell
.\.venv\Scripts\python.exe -m pytest --ignore=tests/test_invite_auth_integration.py -o addopts='' -q
node --test tests/frontend/*.test.mjs
cd frontend
npm run build
cd ..
node tests/frontend/risk-browser-qa.mjs
```

已有未提交的 `tests/test_invite_auth_integration.py` 引用了不存在的 InviteCode / VerificationToken，完整默认 pytest 收集被它阻断。该文件按要求保留，通过明确 ignore 单独报告；未改认证实现以迁就过时测试。数据库测试顺序运行，新增风险单元测试使用隔离 SQLite，认证测试验证真实 Cookie/CSRF 与限流。新增升级测试确认重复升级且旧股票记录保留。

桌面 1440×1000、手机 390×844 已在生产构建中用明确 fake 的网络测试夹具检查：登录、空状态、分析、来源文本/链接安全、状态更新、研究跳转、刷新历史、429/503/504、退出清理、无横向溢出和无浏览器异常。截图：`docs/visual-qa/risk-desktop.png`、`risk-mobile.png`；测试夹具不触碰日常数据库和真实模型。

独立审查提出保存 SQL 错误遗漏和状态/分析刷新后旧详情复现两项问题，已分别添加失败回归并修正。审查不涉及工作区原有认证修改。最终结果：580 项 Python 测试通过（上述原有文件单独排除），51 项前端测试通过；Ruff、Vite 构建、桌面及手机浏览器检查通过。Python 测试有 2 项既有依赖弃用警告，无测试失败。
