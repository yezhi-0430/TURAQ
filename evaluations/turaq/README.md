# TURAQ 本地研究机制评测

本目录资料为手写合成资料，example.invalid 链接不可作为真实公告引用。没有真实公司数据、用户资料或金标准进入真实模型。7 个稳定案例覆盖工具计算、未知工具恢复、参数修复、轮数限制、期限中止、全文批次与汇总留存、证据证券/期间/来源。两个文档共 4 页，正文通过小预算切成多个批次并强制进入 reduce。

## 运行

在项目根目录 PowerShell：

```powershell
.\.venv\Scripts\python.exe -m app.research_eval --output evaluations/turaq/results/current.json
.\.venv\Scripts\python.exe -m pytest tests/unit --confcutdir=tests/unit -o addopts='' -q
.\.venv\Scripts\python.exe -m pytest tests/auth/test_limits.py tests/auth/test_limits_deadline.py tests/auth/test_risk_access.py --confcutdir=tests/auth -o addopts='' -q
node --test tests/frontend/*.test.mjs
uv run --no-project --with langfuse==5.0.4 python scripts/verify_langfuse_adapter.py
```

评测默认不调用任何模型 API、资料网络或数据库查询；工具案例只执行无数据库的 calculate_change 与校验失败路径。数据库模块仍按现有 Settings 加载，因此需具备项目已有环境或显式的测试数据库配置。单测用 confcutdir 避免根 conftest 的 PostgreSQL 自动清表，认证相关测试使用 SQLite / 本地 mock HTTP。

`cases.json` 是生成侧冻结输入与预设回复；`documents.json` 包含证券、期间、披露/可见时间、页序、抽取版本；`gold.json` 仅由评分侧读取。manifest 锁定三份文件 SHA256；改资料必须显式更新 manifest 和版本。输出保存所有案例的模型请求/工具审计/文档快照、异常类型、评分、预期 ID、应用 commit 和每个 app 源文件 hash、提示、工具 schema、评分器 hash。金标准隔离是接口约束，不是 Python 沙箱：本批没有让不可信真实生成器访问文件系统的安全保证。

`integrity_ok` 要求案例无缺失无重复、无任务/评分异常且有全部布尔 contract 评分；`acceptance_ok` 还要求全部得分通过。失败任务和评分故障均保留在请求总数内。分母不完整时 success_rate=null。任务错误与评分错误分开计数；缺评分不会被当成答案质量 0 分，也不会从分母消失。CLI 验收失败退出 1，冻结输入损坏直接报错。成本保持 null。

## 基线与解释

`results/current.json` 为本批修改后的当前机制基线，7/7 只说明预设模型下的程序契约通过。它不是修改前后的真实模型准确率对照，不是投研质量或费用提升证明。真实模型/公开财报质量实验为 not_run。本批未形成独立 held-out 真实研究集，不能据此进行提示词 promotion。

修改前已运行两个财报留存回归用例，均因 batch_findings 不存在失败（KeyError）；修复后通过。留存缺口是 reduce 替换 findings 导致逐批发现消失，而非原文 evidence 丢失。新增 batch_findings 保存摘要副本、游标、evidence 下标；reduction_history 保存合并输入输出；旧快照不可补回的批次标为 legacy_findings_unavailable。文档 hash 变化重启时清空新旧发现和合并历史。新增来源字段仅转存已有元数据，不推断证券或报告期。

## 可选 Langfuse

2026-10-24更新：已安装固定SDK 5.0.4，并使用用户配置的Cloud项目完成真实认证、生产元数据适配器写入与服务端回查。服务端验证3个observations、合成input=3/output=2/total=5和requested/passed/scored各1；没有模型调用。原始验收记录见[cloud-smoke-2026-10-24.json](langfuse/results/cloud-smoke-2026-10-24.json)。下文“未连接云端”为初期实现阶段的历史状态。

本地一键启动器已加`--env-file`，后端在导入应用前读取项目`.env`；手工启动也需使用`uvicorn app.main:app --env-file .env`。变更配置后须重新启动后端，既有进程不会自动继承新环境。本次没有启动或重启业务服务，没有执行业务数据库操作。

默认关闭且不导入 SDK。选装 `uv pip install --python .venv/Scripts/python.exe '.[observability]'`（SDK 固定 5.0.4），启动服务前显式配置：

```powershell
$env:TURAQ_TRACE_ENABLED = '1'
$env:LANGFUSE_BASE_URL = 'https://your-approved-langfuse-host'
$env:LANGFUSE_PUBLIC_KEY = '<public-key>'
$env:LANGFUSE_SECRET_KEY = '<secret-key>'
```

三个服务配置与开关必须同时存在。配置从进程环境读取；变更后重启进程。关闭时设 TURAQ_TRACE_ENABLED=0 并重启。未部署任何服务，未连接云端。实现使用 [SDK 5.0.4 start_observation](https://github.com/langfuse/langfuse-python/blob/v5.0.4/langfuse/_client/client.py)，本地实验汇总导出为 span/score，不创建远程 dataset，不调用 SDK experiment runner。

有界后台队列最多128条，业务不等待网络；满队列丢弃、导出失败计数，保留本地审计与业务异常。进程退出未发送事件可能丢失。导出器的 dropped / failed 与 queue.unfinished_tasks 可供本地诊断；drain 只用于 CLI/测试，不应放在请求路径。独立评测 CLI 退出时最多等待2秒，worker 对实验事件调用 SDK flush；结果 trace_export 记录 drained / failed / dropped / pending。当前 SDK 自身还有后台缓冲，不保证远程持久化。HTTP 阻塞时最多占用一个导出 worker，业务继续。

只允许随机 trace/event ID、固定状态、整数计数、指纹与提供商 token 数，实验附 requested/passed/scored。禁止提示、回答、工具参数/结果、证券、文档、用户身份、异常文本或自定义模型名传出。由 agent loop 创建随机 trace，循环内所有模型尝试使用同一 trace。独立财报 chat 调用当前只记录模型尝试，尚无跨请求任务关联。

Qwen 每次实际发送（含连接重试、超时、错误 HTTP、截断）记录 usage 或 null，cost 一律 null；未知或部分已知不能解释为免费，也不以 max_tokens 充当实际消耗。原始 usage 在 client.attempt_usage（最近256次）、绑定调用的 admission.model_attempt_usage 与 ToolReply.usage 可读；同一次 admission 下临时财报客户端共享 collector，不同 admission 独立。ToolReply 序列化排除 usage，避免混入模型历史和前端协议。本批不是永久本地计费账本；未启用导出时内存历史随 client 生命周期结束。远程只允许整数顶层 token 项，不发送提供商任意 usage 扩展字段。

真实 SDK 验证脚本在 uv 隔离依赖中运行，HTTP 全部 MockTransport 拦截，以 InMemorySpanExporter 确认两个 span、用量和实验分数；不能声称实际 Langfuse 服务端验收。

## 第一批历史验证记录（2026-10-23，review最终结果见下）

- 后端隔离 unit：488 passed，3 个既有依赖弃用警告。
- 额度、期限与风险访问：29 passed，3 个既有依赖弃用警告。
- 前端：70 passed。
- 本批文件 Ruff 与 compileall 通过；真实 SDK 5.0.4 本地适配验证通过。
- 未运行依赖 PostgreSQL 的全量集成测试，未执行真实账户、交易、模型或披露源操作。

下一步：增加独立标注的公开财报语料与真实模型 opt-in runner，在共同冻结资料上比较候选与原始基线；验证真实服务端 Langfuse 持久化；再决定是否值得投入跨会话检索/记忆。OpenViking、Harness² 执行框架、Dream-RSI 均未接入。

## Review 后的对照验收（contract-v2）

本轮 review 修复空集、错误计算/回答、正文与证据共同篡改、归档摘要/页码/偏移/hash/游标以及错误恢复历史缺失的假阳性。金标准新增独立预期结果和冻结文档hash，评分器升为 contract-v2，manifest版本升为turaq-synthetic-v2。第一批历史报告保存在 results/batch1-contract-v1.json，原始输入逐字节匹配其hash的副本在 archive/contract-v1；旧评分器的7/7不能与新评分器成绩直接比较。current.json已由新评分器重新生成。

```powershell
.\.venv\Scripts\python.exe -m app.research_eval --output evaluations/turaq/results/current.json
.\.venv\Scripts\python.exe -m app.research_compare --baseline evaluations/turaq/results/current.json --candidate evaluations/turaq/results/current.json --output evaluations/turaq/results/self-comparison-v2.json
```

实际候选使用各自运行产生的JSON替换 --candidate。对照器独立重评分，不信任报告自报总分；缺案例/缺评分、错误、版本或输入不一致和任何逐案例退化均拒绝并退出1。源码指纹允许不同，资料、提示、工具schema、评分器保持相同。评分器或冻结资料变化时，必须将原应用与候选都用新版本重新评测；不能直接比较旧分数。只有本地mechanism验收，不自动采用候选。

人工故障注入证据：injected-bad-candidate-v2.json 仅修改计算结果为999并保留自报成功，rejected-comparison-v2.json应为reject。这是门槛测试，不是实际模型实验或候选优化成绩。报告执行真实性未签名，不能凭复制的正确输出证明真实执行。

最终review结论在 docs/implementation/2026-10-23-turaq-review-results.md，实跑验证在 results/review-verification.json。真实模型质量仍为not_run。

Review最终验证：unit 500 passed；额度/期限/风险访问29 passed；前端70 passed；本轮新增针对性19项通过；Ruff、compileall、diff检查和SDK 5.0.4离线验证通过。两个后端套件各有3个既有依赖弃用警告。
