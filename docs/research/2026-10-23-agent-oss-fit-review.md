# TURAQ 开源项目源码阅读与匹配度评估

阅读日期：2026-10-23（Asia/Shanghai）。

## 结论与边界

本次按用户要求暂停业务实现，阅读 Langfuse、OpenViking、Google DREAM-RSI 与 Harness² 的官方文档、关键源码和相关测试。只下载、静态阅读公开源码，没有安装运行这些项目、执行其脚本、调用付费模型或复现官方成绩。本文新增之外，没有修改 TURAQ 业务代码。下载文件位于系统临时目录。

结论是基于当前 TURAQ 的适配判断，不是开源项目的一般排名，也不是效果实测。没有逐行通读整个仓库；下文列出实际核查的核心链路和证据。

| 项目 | 与 TURAQ 当前目标的匹配度 | 本轮建议 | 暂不承担的职责 |
| --- | --- | --- | --- |
| Langfuse | 高：已有工具审计，但缺跨版本、逐案例的质量对照 | 优先采用评测数据组织方式；按实际部署条件选择最薄、可关闭的追踪接入 | 不代替财报金标准、业务审计、权限和执行期限；不直接启动完整自托管平台 |
| OpenViking | 中：未来跨会话研究档案与资料检索有需求 | 保留为独立对照实验候选，先证明现有方案的不足 | 不替换股票事实库、原始 PDF 与证据版本记录；本轮不迁移全部知识库 |
| Harness² | 机制匹配度中高，整套框架接入匹配度低 | 借鉴证据驱动的候选比较、版本指纹、经验隔离和独立评分 | 不让生产助手自动修改权限、业务规则或发布自己的新配置 |
| DREAM-RSI | 当前低：TURAQ 尚无可回放探索树和稳定数值评价器 | 本轮暂不接入；保留为以后预算分配研究的参考 | 不把普通聊天日志当可评估任意新策略的模拟器 |

AgentFlow 更适合作为后续 Harness² / DREAM-RSI 思路的实验场所，但当前仍应先验证自身执行正确性。这里没有把 TURAQ 优化改成 AgentFlow 的实现任务。

## 版本基线

所有源码结论对应以下快照；main 分支和在线文档可能继续变化。

| 仓库 | 固定提交 | 核验信息 |
| --- | --- | --- |
| langfuse/langfuse | `5005e702a699646dabd7ef832013651fd8b0d4d8` | package.json 标记 4.68.0 |
| langfuse/langfuse-python | `b003b2fcf99180b6c9041c381221c84097849e13` | pyproject.toml 标记 5.0.4；Python >=3.11 |
| volcengine/OpenViking | `2260f6899e882a8d7f693cca4dd8559dfc66b8cf` | 阅读的是 main 快照；未验证 release 安装包 |
| google-research/dream-rsi | `8ec35bd2538220517ce1bfca4282db21b8c518db` | Google 仓库已有实现与复现脚本 |
| google-research/harness2 | `1cfe254e8d25b15f37048c3730134686abe60335` | pyproject.toml 标记 0.1.0；Python >=3.12,<3.14 |

官方字节项目名称是 OpenViking，仓库属于 volcengine；本次未发现官方使用“OpenViking RSI”这一产品名。DREAM-RSI 的作者介绍仓库仍存在“代码准备发布”的旧说明，当前代码可得性应以 Google 实现仓库为准。

## 1. Langfuse：组织观测和实验，不替应用定义正确答案

### 实际读取的主线

- Python SDK `_client/client.py`：observation 父子关系、run_experiment、item / dataset 关联、异常处理。
- Python SDK `experiment.py`：task、evaluator、结果对象、CI RegressionError。
- Python SDK `_client/attributes.py`、`_client/span_exporter.py`：usage / cost 字段、脱敏导出边界。
- Backend `worker/src/services/IngestionService/index.ts` 及成本计算测试：价格匹配、缺失与零成本的区别。
- 官方实验、CI、LLM judge、code evaluator、标注、脱敏与自托管文档。

### 真实机制和接入含义

一次研究可作为根 observation，下面记录每轮模型生成、工具、检索和财报阅读批次。实验可以绑定问题、资料快照、预期证据与评分结果，比较不同提示词、工具描述或分批策略。

SDK 实验任务和 Python evaluator 在调用 SDK 的应用进程中运行，不是把 TURAQ 服务代码交给 Langfuse 后端执行。UI 后端 code evaluator 则是另一条执行路径，有自己的 dispatcher 和部署要求，不能混用两者的能力描述。

当前 SDK 的 `_run_task` 先直接调用同步函数，再判断返回值是否 coroutine；evaluator 类似。虽然 runner 使用 semaphore / gather，仍不能据 `max_concurrency` 推断同步 httpx、SQLAlchemy 的 TURAQ 任务会自动在线程池并发。初期串行评测更容易核对；后续并发需要显式处理会话、上下文传播、额度和期限。

异常案例不会自动成为一个可信的质量总分：task 失败可能从成功结果集合中过滤，evaluator 失败可能产生缺失评分。CI 必须核对预期案例集合、唯一身份、必要评分和数量，再执行明确的失败门槛。报告生成成功不等于所有案例完成且通过。

本地数据集表示数据来源在本地，不代表 tracing / 实验内容不会发往配置的 Langfuse 实例。脱敏应覆盖采集、数据集、评分和附件等通道，不能只依赖某一个 exporter hook。

### TURAQ 的具体缺口

`app/llm_client.py::_request_message` 目前只返回 choices 中的 message，没有保留上游 usage；`ToolReply` 也不携带 usage。现有自定义 httpx 客户端不会因为安装 SDK 就自动变成完整模型用量追踪。

因此，要先保留可获得的原始用量，再区别提供商报告、价格推算、部分已知和未知。没有用量或匹配价格时，不应填 0；超时、断流或重试也可能有无法立即确认的计费。Backend 存在对缺失 cost 保持 undefined 的路径，但部分调用方自报 cost 可能抑制其他项推算，故 total 有值也不自动证明完整。

TURAQ 已有的 audit_writer、权限校验、请求期限与轮数上限仍应保留。本地审计是业务证据，外部追踪不能变成它的唯一持久化依赖；具体导出失败行为需要集成测试。

完整自托管包含 web / worker、Postgres、ClickHouse、Redis 或 Valkey、对象存储。若目的只是先验证评测方法，这个运维规模需要单独衡量，不应默认列为第一批工程。

### 证据入口

- [Python SDK 客户端](https://github.com/langfuse/langfuse-python/blob/b003b2fcf99180b6c9041c381221c84097849e13/langfuse/_client/client.py)
- [实验 task / evaluator 实现](https://github.com/langfuse/langfuse-python/blob/b003b2fcf99180b6c9041c381221c84097849e13/langfuse/experiment.py)
- [成本处理实现](https://github.com/langfuse/langfuse/blob/5005e702a699646dabd7ef832013651fd8b0d4d8/worker/src/services/IngestionService/index.ts)
- [脱敏导出实现](https://github.com/langfuse/langfuse-python/blob/b003b2fcf99180b6c9041c381221c84097849e13/langfuse/_client/span_exporter.py)
- [SDK experiments](https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk)、[CI/CD](https://langfuse.com/docs/evaluation/experiments/experiments-ci-cd)、[Self hosting](https://langfuse.com/self-hosting)

## 2. OpenViking：上下文与记忆候选，不能预设检索改善

### 实际读取的主线

- `retrieve/hierarchical_retriever.py`：查询、向量检索、范围过滤与可选重排。
- `storage/abstract_overview.py`、`core/context.py`：摘要 sidecar、来源和结构字段。
- `session/session.py`、memory context / merge policy：归档、持久队列、摘要、记忆维护和阶段恢复。
- resource-memory references、memory lifecycle：资源链接与活跃程度。
- identity / tenant、`storage/acl.py`：租户、用户、共享空间与 ACL 边界。
- `benchmark/RAG` 的 metrics 和 pipeline、memory organization 文档：已有评测及覆盖范围。

### 当前版本与早期介绍不同

源码虽仍叫 HierarchicalRetriever，当前实现是受目录、类型、level、权限和过滤条件约束的全局向量检索，加可选的一次候选重排。官方当前文档也说明移除了旧的目录递归、父子分数传播与收敛过程。不能根据名称或旧文章把它描述成仍在逐层目录搜索。

L0 / L1 对应目录摘要和概览 sidecar，L2 是原始或解析后的正文。并非每个普通文件都天然有一组 L0 / L1。摘要只能帮助定位，金融数字和引用仍需回到正文与原始文件核对。

sidecar 有限定的 source / generated_by / freshness 结构，不能任意添加证券代码、报告期等字段后就假设它们会完整保留或参与过滤。TURAQ 需要自己管理证券、报告期、披露时间、可见时间、PDF hash、页序、抽取版本及更正关系。

### 会话、长期记忆与权限

`commit_async` 先保存会话归档并提交持久后台任务，之后才做摘要、记忆抽取和维护，最后写完成标记。后台某阶段失败时，已成功阶段可留 checkpoint，未完成标记不能冒充整个抽取已完成。commit 也可能没有新增记忆。

归档与抽取的记忆不是同一份内容。抽取可能合并、拆分、更新或删除，仍依赖模型判断和程序校验；不能宣称无损。删除资源引用也不必然删除由它派生的可见记忆正文，故资料更正和删除后的残留需要专项评测。

项目有真实 account / user 身份和检索过滤，不只靠提示词隔离；但共享资源与用户私有空间不同。当前 account ACL 默认未开启，开启共享根也不自动默认私有；官方文档还说明索引 ACL 更新不是强一致。未来接入时需让 TURAQ 服务端映射已认证身份，并核对私有空间、直接读取、检索、撤权和删除，不能把客户端传来的 URI 当授权。

### 它也有评测，但需要领域适配

`benchmark/RAG` 有 FinanceBench 等 adapter，并实际计算答案 token F1 和 evidence recall，不能说 OpenViking 完全没有评测功能。已查 metrics 使用英文归一化、空格切词、字符串命中及长证据 token 覆盖阈值。它们不能原样代表中文财报的证券、期间、单位和逐页证据正确性。

适配判断：只有当基线表明跨会话资料复用、检索或记忆是主要瓶颈时，再以固定公开语料和独立标注对照。保留现有实现作基线，不先迁移整套业务数据。

### 证据入口

- [当前检索实现](https://github.com/volcengine/OpenViking/blob/2260f6899e882a8d7f693cca4dd8559dfc66b8cf/openviking/retrieve/hierarchical_retriever.py)
- [目录摘要结构](https://github.com/volcengine/OpenViking/blob/2260f6899e882a8d7f693cca4dd8559dfc66b8cf/openviking/storage/abstract_overview.py)
- [会话归档与后台抽取](https://github.com/volcengine/OpenViking/blob/2260f6899e882a8d7f693cca4dd8559dfc66b8cf/openviking/session/session.py)
- [ACL 源码](https://github.com/volcengine/OpenViking/blob/2260f6899e882a8d7f693cca4dd8559dfc66b8cf/openviking/storage/acl.py)、[ACL 文档](https://docs.openviking.ai/en/concepts/15-acl)
- [实际 RAG 指标](https://github.com/volcengine/OpenViking/blob/2260f6899e882a8d7f693cca4dd8559dfc66b8cf/benchmark/RAG/src/core/metrics.py)、[评测 pipeline](https://github.com/volcengine/OpenViking/blob/2260f6899e882a8d7f693cca4dd8559dfc66b8cf/benchmark/RAG/src/pipeline.py)

## 3. Harness²：借鉴可审查的优化过程，暂不接入整个研究运行时

### 实际读取的主线

`core/recursion.py`、`spec.py`、`selection.py`、`library.py`、`context.py`、`tree.py`、`ledger.py`、`judge.py`、`report.py`、`runmark.py`、`schedule.py` 的关键流程；substrate 接口和 Codex / OpenCode 部分适配；setup / experiments 文档和 `tests/test_workflow.py`。

### 方法到底改什么

保持模型权重不变，修改其外围可编辑配置：系统提示、工具说明、记忆、技能、脚本等。Propose 生成通用与领域候选，Probe 在任务上真实执行，Compose 根据执行证据组合候选；并行增加宽度，顺序增加迭代深度。被采用的配置与经验按领域存储，后续任务只读取之前任务的经验。

从源码可以借鉴的具体机制：

- 编辑表面有路径和结构限制，提案非法时反馈一次重试，仍非法则继承已有配置。
- 保存任务、资料、执行轨迹、产物、配置 diff、采用理由；先有证据再总结经验。
- run 完成标记与配置指纹分开，不能仅因目录或产物存在就判为可复用；恢复会检查采用配置和产物。
- 经验库区分运行模式和预算，防止不同对照组读到彼此的新经验。
- 独立 judge 在采用之后评测，改进器的上下文避免携带评分结果；这有助于区分“看起来更好”与“经独立评分更好”。

### 不能误读的几项限制

默认 `selection_pool` 只包含组合后的 k 个结果，不含原始基线。k=1 时唯一有效 final 直接成为结果，不额外调用 selector。因此“新配置被采用”不等于“已证明不劣于原配置”，非法编辑回退也不是质量回退。

`judge.py` / `report.py` 将评分失败留为未评分，并排除在质量均值分母之外。TURAQ 应同时报告请求总数、任务完成率、可评分率及成功评分的质量分；关键案例缺失还应使发布验收失败。

逻辑预算账本是 4k 次任务 rollout 和 3k 个改进阶段。selector / reflection 不在这个阶段账本内，重试也可能增加实际调用；成本对照应算全部模型消耗，不能只报优化后那一次推理。

固定 seed 控制任务流排序，不保证模型采样重现。公开评测答案可能被有网络的执行器取到，仓库明确要求调用方控制网络边界；本地评分文件名和内容检查也不是通用防泄漏证明。

完整框架面向 Linux、Python 3.12/3.13 和 OpenCode / Codex 等执行环境；与 TURAQ 当前同步 FastAPI / 千问工具循环不是直接替换关系。适合借鉴实验规程，不宜在第一批把现有循环整体重写。

### 证据入口

- [递归与错误回退](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/recursion.py)
- [候选池、选择与经验反思](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/selection.py)
- [经验库](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/library.py)、[任务调度与恢复](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/schedule.py)
- [独立评分](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/judge.py)、[报告分母](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/report.py)、[预算账本](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/ledger.py)
- [回归测试阅读入口](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/tests/test_workflow.py)、[实验指南](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/docs/EXPERIMENTS.md)

## 4. DREAM-RSI：已记录探索树上的策略改进，不是任意任务模拟器

### 实际读取的主线

policy API、TraceEnv、online runner、trace pool、heuristic search 的 eval / workflow、orchestrate、共同脚本与 baseline；只读代码，未下载和解读论文作为本次证据。

### 可以回放什么

在线阶段由策略调度编码 Agent 生成候选程序，用固定任务 evaluator 评估并形成探索树。离线阶段修改探索策略，在冻结探索树上试不同的分支次序、并行批次、裁剪和停止方式；底层模型权重及任务评价器保持固定。

`TraceEnv.legal_actions` 只允许已满足父节点可见条件的动作；replay 还要求该节点线上已经 evaluated，未执行 scaffold 被排除。`step` 再次拒绝揭示未评估节点。超出历史支撑的 plan_grid 返回 out_of_support。

所以，重排已有结果可以离线评估；新提示、新检索工具、新代码和未记录分支的结果不能凭旧日志生成。若改变顺序会改变模型所读上下文，未来在线结果也未必等于原已记录节点。

### 分数和“自我改进”的含义

默认评价目标是多种预算偏好下的每条 trace 归一化预算—效果曲线面积，减去并行调度的归一化顺序轮次惩罚。该惩罚并非实际秒数、token 或账单。run_best 非正或可评估节点不足的 trace 会被跳过，不能直接拿负收益、财务风险损失等指标代入。

候选 promotion 要求 replay 和预算偏好测试成功，按 replay reward 排名；已有策略也可胜出。它没有自动证明对独立新任务或下一次在线运行不退化。已读关键路径没有独立 held-out 验收门槛。

策略接口限制可见观察，但 Python 动态加载不等于强沙箱；模板中的不读隐藏分数要求不能被解释为已经强制阻断所有旁路。

公开任务主要是数学优化、Lasso 和 GPU kernel 等编码探索。原实验脚本还有 Bash / POSIX / 可选 GPU 等条件，现有 Windows TURAQ 环境不能默认直接运行完整实验。

### 适配判断

TURAQ 目前缺少此类探索树、可复现环境和独立数值评价器，直接引入会先增加较大的领域建模工作。本轮暂不接入。以后若研究“先读哪份公告、何时停止继续查资料”，也要先冻结资料、定义证据覆盖与错误代价、计入总消耗，并对新分支重新收集在线结果。

### 证据入口

- [Google 实现仓库](https://github.com/google-research/dream-rsi/tree/8ec35bd2538220517ce1bfca4282db21b8c518db)
- [策略 API](https://github.com/google-research/dream-rsi/blob/8ec35bd2538220517ce1bfca4282db21b8c518db/dream_rsi/policy/api.py)、[TraceEnv 的合法动作与执行](https://github.com/google-research/dream-rsi/blob/8ec35bd2538220517ce1bfca4282db21b8c518db/dream_rsi/env/trace_env.py)
- [replay 池](https://github.com/google-research/dream-rsi/blob/8ec35bd2538220517ce1bfca4282db21b8c518db/dream_rsi/learning/trace_pool.py)
- [评价目标与历史支撑](https://github.com/google-research/dream-rsi/blob/8ec35bd2538220517ce1bfca4282db21b8c518db/dream_rsi/learning/heuristic_search/eval.py)、[候选选择](https://github.com/google-research/dream-rsi/blob/8ec35bd2538220517ce1bfca4282db21b8c518db/dream_rsi/learning/heuristic_search/workflow.py)

## 5. 对 TURAQ 下一批优化的约束

这是阅读后提出的实施边界，不表示以下工程已完成。

1. 先定义逐案例评测，再选择记录平台。把程序边界验证、真实模型任务质量和实时来源连通性分开报告；预设模型测试不能冒充真实模型成功率。
2. 冻结资料与版本。保存证券、报告期、可见时间、文档 hash、页序、应用 commit、提示词 / 工具 schema / 评分器版本，使对照有共同输入。金标准不进入生成模型的任务上下文。
3. 建立完整性门槛。预期案例集合、执行错误、缺失评分和未知成本均有明确记录；不能只平均成功案例后声称总体提升。
4. 区分两种失败。任务本身错误影响任务成功率；评分服务错误影响可评分率和验收完整性，不能随意当作答案质量 0 分或静默排除。
5. 真实用量优先，无法确认则保留未知。记录所有重试、候选生成和评分消耗；不能以设置的输出上限代替实际 token。
6. 可选追踪不能接管业务。权限、用户隔离、执行期限、额度、审计与任务快照继续由当前服务端掌握；是否接入云端或自托管另按部署条件决定。
7. 更改先在独立验收集比较。优先比较工具说明、错误反馈、财报批次 / 汇总策略等小范围方案；保持交易和权限规则不可由候选改写。
8. 记忆独立评测。只有确定跨会话复用是瓶颈，才比较 OpenViking；测证券与用户串扰、报告更正、删除残留、异步失败和来源支持，不能只看回答流畅程度。

建议的第一项交付是：本地可重复的带证据案例集、完整性检查和当前基线报告；随后再增加可关闭的 Langfuse 追踪 / 实验记录。Harness² 先借鉴过程，OpenViking 暂作备选，DREAM-RSI 暂不实施。

## 未经验证的事项

- 本次未复现任何官方提升百分比，也没有测出 TURAQ 接入后的质量、延迟、成本或吞吐收益。
- 未运行这些仓库的测试，未证明其在本机 Windows 和当前依赖中的运行兼容性。
- 未部署多租户、导出、身份映射和异步记忆服务，相关说明是源码和文档边界，不是集成验收。
- 未对实际千问账单、模型 judge 一致性或全部财报阅读质量作新的测量。
- 未来实施要锁定选用版本；本文的源码快照结论不能自动推广到其他 tag 或未来 main。
