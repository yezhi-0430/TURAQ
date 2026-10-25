# TURAQ 第四步：生产财报批次的可定位引用

日期2026-10-23。按用户“下一步”授权，使用既有codex分支，保留所有原有未跟踪资料，不提交、推送、部署或调用付费模型。采用brainstorming/writing-plans设计、系统排错/TDD及独立review。

缺口：document_summary只要求事实字符串中写文件标题/页号；review_step保存source_retrieved与空conclusion_refs，没有逐事实原文定位。来源被取回不代表模型引用的位置真实。

设计：新增app/document_citations.py，批次专用DocumentBatchSummary兼容原RiskSummary字段，并接受fact_citations（fact_index/document_id/page/quote），不让模型自行声明验证状态或字符位置。纯函数只在当前批次excerpts内精确查找，不跨批、不模糊匹配。唯一匹配得到page-relative start/end、content_hash及原证券/报告期；缺失/不存在/重复/非法引用显式失败。多个引用必须全部定位成功才关联事实。服务端生成reading:{batch}:fact:{index}，写入对应evidence.conclusion_refs。

语义边界：quote_located仅表示引文片段可定位，不认证数字、单位、证券期间在事实句中的解释或推断。未定位事实保留但显示[引用未定位]并添加待核实提示；raw_summary与checks/links都存入batch_findings。旧快照和自定义旧summarizer不伪造验证结果，标记legacy_unverified。reduce仍保留原始批次记录，合并结论不自动继承批次定位身份；final_material仅传入总体计数与未验证边界，避免堆入全文引文或误称最终逐条结论已校验。

任务：
- [x] 1. 失败复现默认生产批次的伪页号/伪quote无定位检查；实现严格批次schema和精确定位器及恶意/歧义用例。
- [x] 2. 接入review_step：稳定claim ID、raw_summary、checks、证据索引及conclusion_refs；定位失败的事实明确标记；保持失败不推进游标、成功批次可恢复和资料换版清空。
- [x] 3. 加入有界citation coverage到progress/final_material；保留旧快照与旧summarizer兼容，不把合并输出标为已校验。
- [x] 4. 冻结公开年报+Mock模型验证真实生产路径，独立review，完整隔离unit/期限/访问与前端/静态回归；保存实际结果并刷新可复查快照。

取舍：本批不强制模型精确数Python字符、不引入另一个付费judge，也不修改UI、交易或权限。使用精确原文短引文的服务端定位；歧义时要求更长的上下文而不是挑第一个。失败反馈记录在快照与下游综合材料，不额外自动重试模型。


完成：默认生产批次路径先复现5项缺失检查后修复；最终14项新用例通过。独立review未发现重要问题，提出综合材料仍含完整链接的设计偏差，已按失败测试裁剪，不改变持久化记录。另复现并修复同片段多引用重复登记ID、旧ready快照漏报历史缺失。最终unit537、期限/额度/访问29、前端70通过，Ruff/compileall/diff通过；原7-case机制及新公开语料fixture分别7/7和10/10（均非模型准确率）。实际生产路径的成功/失败快照、源码指纹与验证记录见evaluations/turaq/batch_citations/。没有第二轮独立复审；真实模型新schema遵循率、语义/数值正确性和最终综合逐条引用仍未验证。未调用付费模型、上传资料、提交、推送或部署。
