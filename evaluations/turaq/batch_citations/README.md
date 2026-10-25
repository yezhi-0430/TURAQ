# 生产财报批次引文定位

2026-10-23，代码入口app/document_citations.py与app/risk_reading.py。

## 行为

默认document_summary检测本批excerpts时使用DocumentBatchSummary。模型继续返回原RiskSummary字段，另可返回fact_citations：fact_index（0开始）、document_id、PDF实际page、原文quote。模型不得提供offset/hash/state；非法字段或结构被当作格式错误，本批不推进游标或留下部分证据。旧模型未提供引用时仍可返回，但事实明确显示[引用未定位]，并增加待核实提示。

服务端只在本次输入片段中精确查找quote，唯一匹配后保存page-relative start/end、来源content_hash、证券/报告期、来源URL和片段索引。引用不在本批、同文重复导致歧义、来源hash缺失或偏移非法均不关联。单条事实的所有引用必须成功；同一片段多条有效引文不会重复登记claim ID。模型应使用足够长的原文上下文消除歧义；不会模糊匹配、自动挑第一个或额外请求模型重试。

服务端生成reading:{batch}:fact:{index}，仅在当前阅读快照内唯一，不是全局跨用户ID。定位成功的ID写入evidence.conclusion_refs；整个片段的verification仍是source_retrieved。batch_findings保留raw_summary、经检查的summary、引用检查/链接和游标/证据索引，source改版时与原阅读发现一起清空。旧summarizer或旧档案不伪造检查结果；citation_coverage分别列出已定位、未定位、旧记录事实和未归档批次数量。

quote_located **只表示原文短引文可定位**，不是验证该引文支持整句事实，更不是金额/单位/报告期解释、推断或投资评级认证。缺少原文的事实保留但标注，不因引用定位自动调整风险等级。reduce保留全部原批次链接，合并后的新事实标记merged_claims_unverified并提醒待核实；综合输出永远不会自动继承批次定位状态。

progress与final_material提供有界计数和final_claims_verified=false。最终综合材料剥离citation_checks等完整链接载荷，原始数据仍保存在快照。前端没有重做：原有事实/unknowns展示会呈现[引用未定位]及待核实提示，尚无新增的逐引用跳转界面。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_document_citations.py --confcutdir=tests/unit -o addopts='' -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unit --confcutdir=tests/unit -o addopts='' -q --tb=short
```

located.json与unresolved.json来自冻结的茅台2024年报PDF物理第5页，使用真实PDF hash与公开来源URL，经过实际review_step → document_summary → bind_model → FakeModelClient路径。前者保存定位位置和证据关联；后者给出不存在的quote，明确未定位且conclusion_refs为空。Reader只提供该冻结页，是生产批次机制验证，不代表实际下载、全文研究或真实模型质量；两份结果均real_model_quality=not_run、paid_provider_calls=0。

14项新测试覆盖生产schema、唯一/歧义、错误页与文档、跨批、多个引用、hash/偏移、伪验证字段、失败不推进、汇总留存、最终载荷裁剪和旧快照。独立review未发现重要问题，指出final_material仍夹带链接的非阻断设计偏差；已先复现再裁剪验证，未进行第二次独立代码复审。

完整实跑结果见verification.json。本轮未调用付费模型、上传资料或进行真实账户/交易操作，未提交/推送/部署。真实模型遵循新schema的情况和完整研究结论的引用支持质量尚未测量。下一阶段可在用户明确允许模型费用后运行公开语料实验，或继续补充最终综合结论到原文的独立验证；本批仅批次定位。
