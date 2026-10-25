# 公开年报事实与证据验收

2026-10-23，本地冻结版 public-report-evidence-v1；评分器public-fact-citation-v1。

后续quote-only任务入口与机制验证见[quote_task说明](../quote_task/README.md)：模型只给逐字引句，服务端定位坐标并对全部被过滤的资料按原因拒答。该任务复用本目录严格评分器与冻结资料，新报告单独保存，不覆盖旧基线。

2026-10-24更新：后续已完成一次qwen-plus真实基线，原始2/10；复用相同回答、仅修正精确引文坐标的离线回放8/10，额外模型调用0。两者都未通过全部验收。实跑10次共28803tokens，金额未知。详见[结果分析](../../../docs/research/2026-10-24-turaq-live-baseline-results.md)、[原始报告](results/live-baseline-2026-10-23.json)、[离线回放](results/live-baseline-location-replay-2026-10-23.json)。下文“未运行”描述的是此前语料建设阶段。

## 实际材料与范围

- 贵州茅台600519.SH，[2024年年度报告原始PDF](https://static.cninfo.com.cn/finalpage/2025-04-03/1222993920.PDF)，143页，披露日期2025-04-03。
- 平安银行000001.SZ，[2024年年度报告原始PDF](https://ebank.pingan.com.cn/ir/file/upload/2025-03-15%20%E5%B9%B3%E5%AE%89%E9%93%B6%E8%A1%8C%E8%82%A1%E4%BB%BD%E6%9C%89%E9%99%90%E5%85%AC%E5%8F%B82024%E5%B9%B4%E5%B9%B4%E5%BA%A6%E6%8A%A5%E5%91%8A.pdf)，296页，披露日期2025-03-15（发行人投关清单及文件名）。

sources/保留两份原始PDF、439页逐页文本；documents.json 保存URL、证券、报告期、披露日期、取得时间、PDF/文本hash及pypdf版本/布局模式/normalizer源码hash；manifest锁定所有资料、案例、gold、fixture及review截图。评测读取冻结文本，不现场重抽、下载或查询数据库。初次抽取方法为pypdf PdfReader逐页extract_text(extraction_mode='layout',layout_mode_space_vertically=False)，再app.document_parser.compact；需要重新抽取时使用记录的版本并另建新版本，不覆盖当前快照。

本批**仅评测给定页的事实提取与引用**，不是全篇研究或检索排名。生成侧每例只获得冻结的7个候选页中的相关证券页面（茅台1/5/6，平安1/16/17/19）及问题；439页全文保留供审计与未来扩展。7个有答案案例分别是茅台2024/2023营业收入、2024归母净利润/经营现金净额，平安2024营业收入/归母净利润/不良贷款率。2023指标来自2024年报比较列，不冒称另行收集了2023年报。3个拒答案例为缺2025期间、披露前截止日、证券不匹配。

只知道披露日期，不知道准确公开时刻，publication_time=null；as_of同日也保守排除。过滤在服务端build_context执行，排除资料只传递规则计算的excluded_sources原因，不传未来/错证券正文。gold不进入生成上下文。标注先由主执行者按PNG表格手工记录，独立reviewer复核原PDF/抽取文本与7处主要定位；review还发现并促成增加3个重复正确位置。新增替代位置由主执行者视觉核对，未做第二次独立复审。不是盲标专家集、未曝光held-out集或独立泛化集；公开资料可能在模型训练集中。

物理页码（1开始）是唯一定位键：平安物理16页印刷15页，物理17页印刷16页，物理19页印刷18页。字符start/end引用冻结text的Python索引，包含start不包含end。原表数值必须保留原单位，金额元/百万元不能混用，百分比保留%。同一事实可以引用已独立标注为有效的不同位置；仅匹配数值字符串、其它列或无关原文不会自动算支持证据。未标注的新等价证据可能仍被拒绝，应独立核对并升版评分资料，不能自动据此认定模型错误。

## 运行

在项目根目录PowerShell：

```powershell
# 默认只核验固定材料；不联网、不调用模型
.\.venv\Scripts\python.exe -m app.report_evidence_eval --output evaluations/turaq/public_reports/results/corpus-validation.json
# 预设输出自检，仅证明机制
.\.venv\Scripts\python.exe -m app.report_evidence_eval --mode fixture --output evaluations/turaq/public_reports/results/fixture-smoke.json
# 评分独立产生的答案（JSON对象，key为稳定case ID，value为FactAnswer）
.\.venv\Scripts\python.exe -m app.report_evidence_eval --mode score --answers path/to/answers.json --output evaluations/turaq/public_reports/results/scored-answers.json
```

FactAnswer的完整示例见fixture_answers.json；字段为status、symbol、metric、period、value（十进制字符串或null）、unit、reason_code、citations（document_id/page/start/end/quote）。严格JSON/Pydantic校验，重复JSON键、缺案例、额外case ID不被静默忽略。每例评分维度identity/value/evidence/abstention全部为布尔值，contract是四项与；缺维度记scoring_error，不当作质量0分，保留请求分母。任务异常与评分异常分开记录；所有预期case保留，拒绝报告退出1。输出不能覆盖冻结语料或输入答案。

## 可选真实Qwen入口——语料建设阶段未运行

只有显式同时提供 --mode live、--allow-paid-model、--model 和进程环境DASHSCOPE_API_KEY才允许真实调用；默认不会从.env载入密钥或DB配置。本次没有执行下列命令：

```powershell
# 此命令会向Qwen发送冻结公开页面并可能产生费用
.\.venv\Scripts\python.exe -m app.report_evidence_eval --mode live --allow-paid-model --model qwen-plus --seconds 120 --attempts 20 --output evaluations/turaq/public_reports/results/live-run.json
```

上限范围1..600秒、1..40次尝试，每次最多2048输出tokens；所有连接重试都计入预算。budget记录的是配置上限，attempt_usage才是提供商实际可得usage或null，成本始终未知，不以0或上限代替账单。model_requested为请求别名，model_resolved未知。JSON解析失败保留已返回的原始回答与上下文指纹；HTTP失败/截断等不保证有完整原始回复，usage仍保留。提示、schema、评分器、语料与应用文件指纹写入本地结果。不启用远程dataset上传；若用户自行启用了现有Langfuse环境配置，仍仅走现有允许的元数据通道。

本地live入口为研究CLI，自己的尝试预算不接入真实用户账户；生产API继续由原Admission执行权限/额度/租约。纯HTTP截止时间函数拆到app/model_http.py，独立评测不再触发app.database或读取业务.env；生产Admission仍委托原期限/取消路径，旧导入及延迟模拟hook保留，已用原有额度/期限回归验证。

## 实跑结果与边界

- corpus-validation.json：2份真实公开PDF、10个case的冻结完整性通过。
- fixture-smoke.json：10/10，仅预设输出机制自检，real_model_quality=not_run。
- injected-bad-unit-answers.json：人工把一项单位改错，非模型运行；rejected-unit-score.json为9/10、验收失败、CLI退出1。
- 23项新增针对性测试通过，包括实际Qwen客户端+Mock HTTP、尝试数/期限、原始无效JSON保留、无DB导入的独立子进程验证。
- 隔离unit 523通过；额度/期限/风险访问29通过；前端70通过。两个后端套件各3个既有依赖弃用警告。Ruff/compileall/diff检查通过。
- 独立review发现的重复正确引用误判与DB配置依赖均以失败复现后修复。没有进行第二轮独立源码复审。

上述语料建设阶段不是实际模型质量基线，未运行真实模型、真实Langfuse服务或PostgreSQL全量集成；后续真实基线见文首更新。各阶段均未证明完整投研、风险评级或投资效果。原合成7-case评测与本语料使用不同评分器，不能直接比较成功率；原research_compare仅支持合成机制报告，不应传入本目录报告。
