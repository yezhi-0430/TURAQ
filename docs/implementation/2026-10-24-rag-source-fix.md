# RAG 原文分块与相似度修复 Implementation Plan

用户在“先修现有RAG的小数分块与门槛，再用同一冻结集复测”之后指示继续。使用systematic-debugging、brainstorming、writing-plans、TDD及executing-plans，沿当前工作区保留所有既有工作，不提交、推送或部署。

## 根因和方案

旧smart分块把所有英文句号当断句符，再用空格连接，导致小数被改写；无结尾标点的尾句也会丢失。只排除数字中的句号仍不能保证空白/尾句不变，选择直接记录原文连续切片，优先自然边界并保留有限重叠；长度可容纳的数值token不在中间断开。新增版本与字符位置元数据，三个策略都输出真实切片。参数验证防止overlap>=chunk_size不前进。单个token本身超过块长时只能按长度切分，不宣称此边界下数值完整。

旧collection使用squared L2，1-distance不是余弦相似度。选择查询时请求返回向量，直接计算实际query/document向量余弦值，不假定向量已归一化，不修改旧collection的space。未知/零向量/非有限分数不进入相关上下文；min_similarity仍0.5，语义改为明确余弦值而非放松门槛。研究包装层、enhance-query和旧知识库页面都读取同一score，不再各自换算distance。

不自动迁移或改写现有业务Chroma库。新导入使用source-slices-v2，并记录char_start/char_end；已经改写的旧chunk需要从原文件重新建立，不能猜测修补数字。复测在全新独立Chroma目录执行，原48页/20案例、金标、严格评分器与旧OpenViking结果保持不变。

## 任务

- [x] TDD修复chunker：小数/百分比/负数/多行空白/尾句/重叠/超长无标点/非法参数，原文切片与offset逐字核对；新增元数据版本。
- [x] TDD修复余弦score及三个消费者：以实际向量求cos，不假定归一化，缺失/非有限值fail closed；保留原distance用于诊断。
- [x] 新独立索引离线检索对照，检查同一14事实的top1/top3与原始引用保持；只运行一次有界同提示真实生成复测，20个案例完整保留，错误与用量如实记录。
- [x] 独立只读review与修复回归，完整unit/frontend/build及静态检查；保存中文结果与验证记录，交代旧索引重建要求和是否仍有质量不足。

复测最多24次上游chat请求、220000请求字符、每次1024输出tokens、8分钟，不启动OpenViking或重新跑已冻结的旧方案。复用现有DashScope网关，但只对新的修复候选发生成请求；BGE使用本地缓存离线运行。旧实验记录保持原样。若离线检索暴露新错误，先修回归再进行一次真实复测；评分失败不自动重试刷分。

主要文件：app/rag/chunker.py、app/rag/scoring.py（新）、app/rag/core.py、app/rag/research_integration.py、app/rag/api.py、frontend/rag-manager.js、tests/unit/test_rag_source_fidelity.py（新）、scripts/run_rag_repair_eval.py（新）。最后按executing-plans要求委派一名只读审查agent。

依据：本地Chroma Collection.query源码支持include=embeddings；官方 https://docs.trychroma.com/docs/collections/configure 明确l2为squared L2，而cosine距离为1-cos。

完成记录：33项新增回归，最终658项unit通过；83项frontend通过，build/语法/Ruff/compile/diff通过。独立审查唯一P2负号问题已RED→GREEN修复，未改变冻结集任何分块；15次真实调用只执行一次复测，后续无付费重跑。结果仍不达标（事实2/14，11拒答格式任务错误），详见docs/research/2026-10-24-rag-source-fix-results.md。旧索引、原评分器、金标和旧实验结果保持。
