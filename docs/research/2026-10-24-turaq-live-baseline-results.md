# 公开年报真实模型基线与离线坐标回放

2026-10-23执行真实调用，2026-10-24完成回放与验证。原始qwen-plus回答严格验收通过2/10；对同一批回答仅重定位原引文字符坐标后通过8/10。后者没有新增模型调用，不能作为第二次实跑或泛化能力提升。

## 结果

| 项目 | 原始真实回答 | 同一回答离线回放 |
| --- | ---: | ---: |
| 全部合同条件通过 | 2/10 | 8/10 |
| 有答案案例：证券、期间、数值、单位 | 7/7 | 7/7 |
| 有答案案例：严格引文支持 | 0/7 | 6/7 |
| 无答案案例：选择拒答 | 3/3 | 3/3 |
| 无答案案例：原因码正确 | 2/3 | 2/3 |
| 请求/评分案例 | 10/10 | 10/10 |
| 任务异常/评分异常 | 0/0 | 0/0 |
| 新增提供商请求 | 10 | 0 |

两份报告均acceptance_ok=false，不自动晋级。数值正确并不代表证据链通过。

原始报告：[live-baseline-2026-10-23.json](../../evaluations/turaq/public_reports/results/live-baseline-2026-10-23.json)。SHA-256：`a8e29557e3437ba61bceafa2ee11a69741dffa37ec7df18e1fd294f234feba79`。原文件保持不变。

回放报告：[live-baseline-location-replay-2026-10-23.json](../../evaluations/turaq/public_reports/results/live-baseline-location-replay-2026-10-23.json)。文件名沿用父基线日期，内含父文件与适配器源码hash。

## 调用与实际用量

请求别名qwen-plus，提供商具体模型快照未知。配置上限120秒、12次尝试、每次最多2048输出tokens；实际10次请求，无重试，全部HTTP成功且返回可评分JSON。只发送冻结的公开年报候选页；Langfuse额外导出关闭，独立CLI不导入业务数据库。

提供商返回的usage合计：输入27378、输出1425、总计28803tokens；输入缓存1280tokens已包含在输入量中。实际金额未知，cost=null，不能用预算、token上限或0代替账单。回放不读取密钥、不联网，不增加提供商费用。

## 回放改变了什么

`app/report_quote_replay.py`复用已有生产`locate_fact_citations`。定位器只读取该案例生成时可见的同一批冻结页面，按document_id/page查找原quote，只有唯一精确匹配才更新start/end。它不改数值、单位、证券、期间、状态、拒答原因、引句、文档或页码，也不新增或删减引文。无匹配或多匹配保留原回答。gold只用于回放后的原评分器，未参与定位；测试替换gold数值后，回放答案不变而得分下降。

父报告必须具备匹配的语料与评分器指纹、完整且唯一的10个案例。父报告任务/评分异常保留；无效答案继续计为失败；缺案例不缩小分母。CLI禁止覆盖父报告与冻结语料。

## 两个剩余失败

- `moutai-profit-2024`：数值与单位正确，但模型把跨行表格文字重写为冻结页中不存在的引句。精确定位器拒绝该引句；坐标修正无法修复原文改写。
- `wrong-security`：模型正确选择insufficient，但返回not_yet_public，而规则与可见excluded_sources要求wrong_security。回放保留原因码，仍不通过。

后续行为改动应分别针对“逐字复制引句”和“依据服务端排除原因选择拒答码”验证。现有结果不能证明新的提示或模型已经解决问题；本轮未追加付费实验。

## 复现与验证

原始实跑入口参数如下，需要进程环境中已有DASHSCOPE_API_KEY。不要再次使用已有输出名；本轮实际通过临时子进程载入本地密钥，未将密钥保存到产物。

```powershell
.\.venv\Scripts\python.exe -m app.report_evidence_eval --mode live --allow-paid-model --model qwen-plus --seconds 120 --attempts 12 --output evaluations/turaq/public_reports/results/NEW-live-run.json
```

不调用模型的回放命令：

```powershell
.\.venv\Scripts\python.exe -m app.report_quote_replay --input evaluations/turaq/public_reports/results/live-baseline-2026-10-23.json --output evaluations/turaq/public_reports/results/live-baseline-location-replay-2026-10-23.json
```

返回1是预期的严格验收拒绝，报告仍会保存；8/10不视为成功退出。验证命令与最终结果记录见同目录结果中的`live-baseline-verification-2026-10-24.json`。

本轮12项回放测试、完整隔离unit套件549项通过，3个既有依赖弃用警告。新增模块与测试的Ruff、compileall和tracked diff空白检查通过。新增失败复现覆盖畸形citation元素、超过生产定位器长度限制的混合引文，以及usage缺行/多行/尝试总数不匹配。前两种修复后保留原答案并拒绝修正；用量记录不完整时总量标为未知。未运行真实数据库集成。

独立只读审查重新评分并比对原始响应，确认2/10与8/10、相同上下文、仅6个案例坐标变化、无gold参与定位以及28803tokens。审查发现上述用量缺行问题，修复后再次独立运行12项测试通过，未发现新的重要问题。审查不能独立核实提供商账单。

范围仍为两份2024年报、7个候选页、10个已知案例。语料与gold已曝光，未使用独立留出集，不能外推到全篇投研、风险评级或投资效果。没有生产实跑、部署或自动晋级。
