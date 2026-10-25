# OpenViking 扩大对照评测 Implementation Plan

用户已确认继续“扩大报告、不同年份/无关资料、更正删除、与现有方案比较准确率/耗时/Token”。本轮依次执行brainstorming、writing-plans、TDD及executing-plans，保留现有未提交工作与所有原始结果，不提交、推送、部署或接入主业务。

## 设计

第一轮仅7个预选页且top3容易饱和。选择三份原始年报（茅台2023/2024、平安银行2024），每份16个物理页，共48页：固定分层抽样并确保被标注证据页存在，清楚标为小型检索集，不能宣称全文或盲测。全PDF冻结留存，原10案例语料与严格评分器均不修改。新增茅台2023来自巨潮官方披露PDF，提取并渲染核对表格后冻结新金标。

比较三种检索：现有Chroma/BGE代码在独立新目录运行；透明词法基线；OpenViking 0.5.2 vectors_only。三者使用相同身份、证券、指定原报告、披露时间和active版本过滤，固定top1/top3并回到原文定位。BGE与OpenViking使用不同embedding模型，结果属于系统级对照，不把差异归因于单一架构。检索质量与端到端事实/引用质量分别记录；模型任务用同一quote-only提示，金标不进入任何生成上下文。

约20个案例：14个可支持事实（原7例+新7例）、缺期间/未披露/错证券/错原报告/错用户/失效版本6个边界。每个模型方案保留全部案例分母，错误和未知费用显式记录；top3之外还测top1以避免饱和。更正与删除使用明确合成测试副本，不伪造公司真实更正公告。

复用现有OpenViking storage/用户及embedding缓存；隔离实验根下新增资源，不读取业务数据库/Chroma库。默认离线，--live才调用现有DashScope。一次有界运行最多200次上游请求、1200000请求字符、每次1024输出tokens、20分钟；含所有初始化、检索、生成和后台维护。达到预算保存incomplete，缓存命中不重复计usage。费用只记录未知，不据输出上限推算账单。实验服务退出时停止。

## 任务

- [x] 资料与冻结集：新增PDF/逐页提取，表格页视觉核对；docs/cases/gold/fixture/manifest独立冻结，48页索引选择、源文件hash和标注局限可复查。
- [x] TDD评测机制：原文引用从检索片段映射到原页；同一过滤策略；无金标进入任务；top1/top3/完整分母；失效版本/错误返回不伪装成功。
- [x] 执行独立Chroma/BGE和词法检索；复用受限运行时导入OpenViking并运行对照；两个主要系统使用同一模型生成并由不变的strict scorer评分。保存检索排名、错误、实际usage、分阶段耗时。
- [x] 更正/删除边界复测；独立只读审查及修复回归，完整unit、ruff/compileall与秘钥扫描；保存中文结论，决定是否已有充分证据进入业务集成。

## 文件与验证

新增app/openviking_benchmark.py负责冻结集加载、过滤、排名/上下文/评分；新增scripts/run_openviking_benchmark.py负责受限运行和结果写入；tests/unit/test_openviking_benchmark.py先失败后实现。复用scripts/run_openviking_pilot.py的运行时启动器，最小扩展callback与预算参数，保持旧默认和旧输出不变。语料与结果放evaluations/turaq/openviking/expanded/。最终独立审查按executing-plans要求委派一名只读agent。

验证命令统一使用 .venv/Scripts/python.exe -m pytest tests/unit --confcutdir=tests/unit -q -o addopts=，禁止根conftest。生产RAG仅在独立目录调用，不打开现有chroma_db或知识库。

## 执行与裁定

- 新增巨潮茅台2023原PDF，SHA256 2125ff97a452ea79b0d784e2432f7d224b6aecc330b644b593477d69e22f4ed1；物理5/6页渲染核对7个新金标。3份PDF共582页，本轮索引48页，20案例/14事实，单人标注且证据页过采样，不能当盲测。
- live-v1至v4保留为incomplete。最初把中断定位在Chroma索引并不准确：原生批量导入任务已经完成，任务result内才有root_uri；递归agent列表使用rel_path而非name。补两个RED→GREEN回归后取完成任务结果、按URI识别文件。首次实际导入16页产生13次embedding/12243 tokens，后续三次相同导入均无新提供商调用。
- Chroma独立索引检查48页完整，后续复用；不把只看到chunk_0当完整，检查全部chunk_index/total_chunks。重试从200次总预算扣除所有旧expanded结果用量，没有扩容。
- 独立review两项P2：失败生成漏计每方案Token、两份catalog撤回状态分裂。分别移到finally计量、同步失效并实际调用两套find，均RED→GREEN。更正/删除后旧resource_id不能进入返回片段；原生删除旧URI读取404。
- live-v5完成全部循环。OpenViking证据@1=3/14、@3=7/14；词法6/14、9/14；现有门槛Chroma0/14、0/14。事实严格通过OpenViking5/14，另1例评分失败、8例任务验证错误；Chroma0/14。六个边界分别OpenViking6/6、Chroma5/6，其中五个属于程序边界拒答，不可算模型能力。
- 事实错误与任务错误完整保留，未改原评分器/旧基线，未修生产RAG混入对照。诊断确认现有collection为l2，当前1-distance门槛拦截候选；smart切句将小数变为点后空格，原样证据定位受损。移除门槛的raw top3证据仍仅1/14，不应只调阈值就声称修好。
- 全部expanded运行76次提供商尝试，已知84177 tokens，另1个后台chat请求结束时usage未知，完整总Token及费用保持null。OpenViking embedding已知37919、回答生成44944、额外后台chat已知1314；BGE本地embedding Token未计量，不能记作免费或0。阶段/每方案口径详见结果报告。
- 35项针对性与625项完整unit通过，3个既有依赖弃用警告；ruff/compileall/diff检查通过。实验服务已停止；没有接入业务、修改现有RAG/交易/权限、提交/推送/部署。结论：暂不推广，先修现有检索基础和引用稳定性，再用同一冻结集复测。
