# 逐字引文生成与服务端拒答 Implementation Plan

> 按已获确认的下一步在当前会话内执行；使用brainstorming、writing-plans、TDD与executing-plans。用户已指示继续，不重复申请设计确认，不提交或推送。

**Goal:** 模型不再猜引文字符坐标；明确被过滤的全部资料由服务端按真实排除原因拒答。

**Architecture:** 新建研究任务适配器与CLI，复用现有可见上下文、生产定位器及严格评分器。保留原始proposal、定位诊断、拒答来源；原始baseline、replay、gold和评分器源码不修改。新提示逐字保留空白与换行，缺精确引文则保留未验证状态。

**Tech Stack:** Python、Pydantic、现有Qwen客户端、隔离pytest。

备选方案：仅加强提示改动最小，但仍让模型猜坐标；宽松匹配可能把改写误认原文；选择quote-only输出与唯一精确定位，保留严格拒绝边界。服务端只有在没有任何可见资料且排除原因一致时才返回具体原因；混合/无原因不猜具体原因。

## 约束

- 不新增依赖、不读取业务数据库；研究CLI不自动加载.env。离线阶段不调用提供商，验收与独立审查通过后按用户在完整下一步说明后的“继续”执行一次有界真实复测。
- 原评分器app/report_evidence_eval.py及冻结语料、gold、既有结果不修改。
- 新CLI仅新文件输出，保护既有结果与输入；显式live开关、模型、密钥与预算沿用原研究CLI限制。
- 结果明确区分fixture/离线候选/真实新提示运行；本轮只验证机制与失败边界，不能宣称新模型输出已改善。

## Task 1: 任务输出协议与拒答

Create app/report_fact_task.py、tests/unit/test_report_fact_task.py。

接口：QuoteFactAnswer沿用FactAnswer身份/数值/拒答字段，citations仅document_id/page/quote；resolve_proposal(raw, context)返回(answer, diagnostics)；fact_task(client)返回只消费build_context字典的可调用任务，并记录raw_responses与decisions。

- [x] RED：真实冻结茅台净利润原表引文精确通过，原基线改写引句拒绝，不发明坐标；歧义/混合无效引文失败；数值与单位错误仍由原评分器拒绝。
- [x] RED：wrong-security与before-publication不调用客户端，按一致排除原因返回；混合原因不猜；存在相关可见资料仍调用客户端。
- [x] GREEN：实现quote-only schema、明确复制提示、唯一精确定位、服务端拒答与原始proposal/诊断保留。禁止用gold生成答案或引文。
- [x] 执行`.venv/Scripts/python.exe -m pytest tests/unit/test_report_fact_task.py --confcutdir=tests/unit -q -o addopts=`。

## Task 2: 可复现研究入口

Create app/report_fact_eval.py与tests/unit/test_report_fact_eval.py。

接口：main(argv=None)，--mode score/live；score读取按case ID映射的quote-only proposals，live显式授权参数与原预算；统一使用fact_task，再由未改的evaluate_answers评分。保存任务版本、提示/schema/源码指纹、每例决定与原始回复；offline明确real_model_quality=not_run。

- [x] RED：离线fixture候选通过原严格评分，原始失败引句仍失败；缺/额外case保持错误分母；输出不可覆盖输入、冻结资料或任何既有文件；live缺授权拒绝。
- [x] GREEN：实现CLI与可审计报告，不将fixture结果称为真实质量。
- [x] 用原fixture去除坐标构造明确标注的机制输入，保存新报告；另外保留原改写quote注入的拒绝报告。

## Task 3: 审查、回归与文档

- [x] requesting-code-review独立只读审查新增模块与测试，处理可操作发现。
- [x] 运行完整隔离unit套件、Ruff、compileall、diff检查；核对旧baseline/评分器hash未变。
- [x] 写明新机制结果与真实复测完成后的剩余失败边界，更新README与本清单。

## Task 4: 已获授权的有界真实复测

执行补充记录：最初把本轮限定在离线是执行范围假设；用户是在“离线通过后再做一次有界真实复测”的下一步说明后指示继续。现离线571项unit与独立22项测试审查均通过，继续执行完整已确认步骤。只运行一次qwen-plus新提示，120秒/10次尝试/2048输出tokens上限；不是人民币账单承诺。只传冻结公开页，关闭额外trace导出，密钥仅在子进程临时环境，不输出或写产物。

- [x] 保存results/live-quote-only-2026-10-24.json，禁止覆盖，保留原始proposal与实际usage；只此一次，不循环调提示付费重跑。
- [x] 使用未改评分器独立重评分，逐例核对服务端规则/模型来源、引用与实际用量，报告剩余失败与未知金额；旧基线与gold保持不变。

完成记录：23项针对性测试、572项隔离unit通过（3个既有依赖弃用警告）；Ruff/compileall/diff通过。独立源码审查无重要发现，独立实跑数据审计通过。一次新增真实复测9/10，7/7引用证据通过，8调用共28176tokens，金额未知；NPL value含百分号的格式错误保留，未循环付费重跑或自动晋级。
