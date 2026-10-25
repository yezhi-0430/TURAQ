# Quote-only新提示与服务端拒答真实复测

2026-10-24已完成一次qwen-plus真实复测，任务quote-only-server-location-v1。严格验收9/10，7个有答案案例的引文全部通过；此前净利润引句改写和错误证券拒答原因两项均在本次通过。剩余一项是百分比数值的输出格式错误，不自动改写或放宽评分。

## 对照结果及归因

| 运行 | 全条件通过 | 有答案案例证据 | 产生新模型回答 |
| --- | ---: | ---: | --- |
| 原始基线 | 2/10 | 0/7 | 是，10次请求 |
| 原回答仅修坐标回放 | 8/10 | 6/7 | 否 |
| 原回答套用新规则，离线 | 9/10 | 6/7 | 否 |
| 新提示与新规则真实复测 | 9/10 | 7/7 | 是，8次请求 |

新旧真实运行同时改变了生成协议、提示和服务端拒答规则，没有做独立消融或多次重复；不能把全部变化归因于提示。新运行的before-publication/wrong-security是服务端决定，不是模型作答得分。7个事实数值/单位合规6/7，1个目标期间缺失的模型拒答通过，2个服务端拒答通过。尽管总分与离线新规则同为9/10，失败案例已经不同，不能只比较总分。

两次均使用相同的已曝光10案例、同一批可见页与同一严格评分器，未使用独立留出集。此结果证明本次有限案例的行为，不能外推到一般研究或投资效果。两份真实报告均未通过全量验收，automatic_promotion=false，不部署。

## 实现

`app/report_fact_task.py`只要求模型输出document_id/page/quote，不输出start/end。新提示要求逐字复制空白与换行、禁止拼接跨行标题；服务端复用生产精确唯一定位器计算坐标。引用失败时保留原proposal，把最终citations留空，原评分器继续拒绝。quote_located仅证明原文位置，不代表数值或语义已验证。

没有可见文档且排除原因一致时，服务端直接产生wrong_security或not_yet_public；混合或未知原因不猜。来源与上下文hash逐例保留。生产API未接入这个新研究入口。

`app/report_fact_eval.py`提供独立score/live入口。原评分器`app/report_evidence_eval.py`、gold、语料、原baseline与坐标回放均未修改；新报告带任务、生成提示、schema、源码及语料指纹。所有已有输出路径拒绝覆盖。

## 剩余失败

`pingan-npl-2024`两个引文均为精确原文，证券/期间和单位正确；原始模型返回value="1.06%"、unit="%"。协议要求value是纯十进制字符串"1.06"，百分号只在unit，因此严格value维度失败。服务器没有擅自删掉百分号，也没有借用gold修正答案。

已增加捕获真实错误的回归测试，确认原值保留、引用通过、数值格式仍被拒绝。下一版本应将纯十进制格式显式写入proposal的schema约束并给出百分比示例；当前版本保持冻结，不在本轮循环调提示或追加付费重跑。

## 真实用量与原始产物

实际8次请求，无重试；全部HTTP成功、返回可评分JSON。另2例服务端拒答不发请求。10例均保留在分母，任务/评分异常各0，integrity_ok=true、acceptance_ok=false，CLI退出1。

提供商usage：输入26794、输出1382、合计28176tokens，输入缓存512tokens已计入输入。实际账单金额未知，各attempt的cost=null；请求别名qwen-plus，具体提供商模型快照未知。

配置上限120秒、10次尝试、每次2048输出tokens。该资源预算不是人民币金额承诺。本轮只执行这一次新增真实调用；关闭额外trace导出，只发送冻结公开页，密钥仅在临时子进程环境，未保存到报告。未访问业务数据库。

- [真实复测原始结果](../../evaluations/turaq/quote_task/results/live-quote-only-2026-10-24.json)
- [旧回答套用新规则的离线结果](../../evaluations/turaq/quote_task/results/cached-baseline-new-rules-2026-10-24.json)
- [离线fixture与拒绝案例说明](../../evaluations/turaq/quote_task/README.md)

可复现命令（要求密钥已在进程环境，输出名必须不存在；重新执行会产生费用）：

```powershell
.\.venv\Scripts\python.exe -m app.report_fact_eval --mode live --allow-paid-model --model qwen-plus --seconds 120 --attempts 10 --output evaluations/turaq/quote_task/results/NEW-live.json
```

源码独立只读审查未发现重要问题，22项针对性测试独立通过；实跑后新增一项错误格式保留测试，本地23项通过。最新完整隔离unit套件572通过、3个既有依赖弃用警告；Ruff/compileall/diff检查通过。最终完整回归、原始文件hash与独立实跑审计记录见[verification-2026-10-24.json](../../evaluations/turaq/quote_task/results/verification-2026-10-24.json)。

独立实跑审计也通过：重评分9/10，7个supported共8条引用均精确且唯一；8份raw到输出只增加坐标，10例上下文hash与冻结上下文一致，两个服务端案例无模型raw且原因正确。NPL原百分号完整保留，实际用量与上述统计相符；此审计不能独立核实提供商账单。
