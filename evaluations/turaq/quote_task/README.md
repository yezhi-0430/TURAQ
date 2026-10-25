# Quote-only任务验证

2026-10-24，任务版本quote-only-server-location-v1。复用原public-report-evidence-v1语料与public-fact-citation-v1严格评分器；原评分器、gold、baseline与坐标回放均不修改。

同日后续已完成一次新提示真实复测：8次模型调用加2例服务端拒答，严格9/10，7/7有答案案例证据通过。原净利润引句和错误证券拒答均通过；剩余不良贷款率value带百分号的格式错误仍按失败保留。实际28176tokens，金额未知。详见[实跑分析](../../../docs/research/2026-10-24-turaq-quote-only-live-results.md)与[原始结果](results/live-quote-only-2026-10-24.json)。

## 已实现的边界

模型输出证券、指标、期间、数值、单位、拒答状态及document_id/page/quote，不输出字符坐标。新提示要求从冻结text逐字复制，保留空白与换行；服务端复用生产定位器，仅为唯一精确匹配生成坐标。缺引文、改写、歧义或任一无效引用导致整条事实citations为空，原proposal仍保留在raw_responses；输出的supported也不会被当作已验证，严格评分器继续拒绝证据失败。

如果没有可见文档且服务端excluded_sources原因一致，则直接返回wrong_security或not_yet_public。混合/未知/无排除原因仅返回sources_unavailable，不猜具体原因。只要仍有可见文档就不走这条捷径。服务器决定和模型proposal在decisions中分别记录。该模块是独立研究入口，尚未接入生产API。

## 离线输入与结果

| 输入 | 结果 | 含义 |
| --- | --- | --- |
| fixture-proposals.json | 10/10 | 已知正确候选的机制自检，非模型质量 |
| injected-rewritten-proposals.json | 9/10，退出1 | 人工改写一条引句后仍被拒绝 |
| cached-baseline-proposals.json | 9/10，退出1 | 旧真实回答套用新服务端规则，非新提示实跑 |

全部离线报告provider_calls=0、real_model_quality=not_run、cost=null，自动晋级关闭。结果保存在results/；inputs-manifest.json记录输入hash与来源。

fixture由原fixture_answers去除坐标；平安营收与不良贷款率两条旧fixture仅含数字，数字在同页重复，因此机制输入改用原坐标所在的完整原表行。此举只构造明确标注的已知正确fixture，不修改语料、gold、原fixture或任何真实回答。

cached输入来自不可变原始baseline，只移除start/end，其它字段不变。服务端对wrong-security重算原因，故离线总得分由此前纯坐标回放8/10变为9/10；这是规则变化，不能归因于模型。moutai-profit-2024原引句仍不精确，新任务拒绝它，不做空白归一化或改写修补。

## 运行

默认不联网，要求新输出路径；存在的输出会被拒绝：

```powershell
.\.venv\Scripts\python.exe -m app.report_fact_eval --answers evaluations/turaq/quote_task/fixture-proposals.json --output evaluations/turaq/quote_task/results/NEW-fixture.json
.\.venv\Scripts\python.exe -m app.report_fact_eval --answers evaluations/turaq/quote_task/cached-baseline-proposals.json --output evaluations/turaq/quote_task/results/NEW-cached.json
```

显式真实调用入口，需要进程环境已设置DASHSCOPE_API_KEY；不会自动加载.env：

```powershell
.\.venv\Scripts\python.exe -m app.report_fact_eval --mode live --allow-paid-model --model qwen-plus --seconds 120 --attempts 10 --output evaluations/turaq/quote_task/results/NEW-live.json
```

原10例中两例服务端拒答，不调用模型，因此理想无重试时仅8次模型请求。所有尝试与重试仍计入配置上限；每次最多2048输出tokens，实际用量保留provider usage，金额未知。案例分母仍为10；预算或任务失败不得缩小分母。此命令可能产生费用，不能把离线结果当成已执行此命令。

最初22项针对性测试通过，包含真实Qwen客户端配Mock HTTP的8次调用；源码独立只读审查未发现需要修改的重要问题。实跑后增加一项原始百分比格式错误的保留测试，23项通过。完整隔离unit、静态检查和实跑审计最终记录见results/verification-2026-10-24.json。当前已知10例、已曝光候选页不是独立留出集，不能外推到完整投研或投资效果。
