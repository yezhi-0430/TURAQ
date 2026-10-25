# 财报分析页与真实评测 Implementation Plan

用户已确认接入真实评测，并追加优化页面与加载过程。使用brainstorming、writing-plans、TDD；API契约先固定，前端与后端可独立实施，最后独立review。

## 设计与边界

保持深色金色产品语言，重做财报页的上传、执行状态和结果信息层级。比较方案：仅改皮肤不能解决评分误导；自动对所有文件打模型分缺金标；选择本地解析+独立可选的已知PDF事实评测。数据缺失不当作安全值，PDF失败报错，不退回模拟数据。演示入口保留但明确标为演示且不可触发模型评测。

使用现有JSON/CSRF/API客户端与模型Admission，不新增绕过权限/额度的入口。PDF JSON base64上传与现有同源JSON协议一致，限20MiB；复用现有受限PDF子进程解析。只对原PDF哈希精确匹配的冻结语料提供金标模型评测，按同文档5个案例评分；资料/gold/原评分器不改。用户点击评测按钮才消耗模型额度；开发验证全部Mock，不追加真实付费调用。

## 固定API契约（前后端并行）

`POST /api/analysis/upload`，JSON `{filename, company_name, content_base64}`；复用apiClient.request的会话、CSRF、取消与超时。成功JSON：

```
{success:true,company_name,source:{sha256,filename,page_count,kind:'uploaded'|'demo'},
 indicators:{revenue,net_profit,total_assets,...},ratios:{...},risks:[{name,level,value,threshold}],
 report:{score:number|null,recommendation,action,rule_checks:[{name,status:'passed'|'triggered'|'not_evaluable'}]},
 quality:{completeness:{found,total,missing:[{key,label}]},
 citations:{state:'located_unverified',located,total,items:[{key,label,page,quote,start,end}]},
 model:{state:'not_run',available:boolean,case_count,scope,reason}}}
```

`GET /api/analysis/test`返回相同结构，但source.kind=demo，明确无真实模型运行且available=false。

`POST /api/analysis/evaluate`，JSON `{source_sha256}`；已登录用户的模型Admission/额度与截止时间保护。返回：

```
{state:'completed'|'incomplete',requested,scored,passed,integrity_ok,acceptance_ok,
 cases:[{id,metric,period,scores:{identity,value,evidence,abstention,contract},task_error,scoring_error,
 output:{status,value,unit,citations:[{document_id,page,quote,start,end}]}}],
 trace_id,trace_enabled,usage:{prompt_tokens,completion_tokens,total_tokens},cost:null,
 scope,model_mode,scorer_version}
```

错误均为安全中文detail；解析失败422，文件过大413，不支持金标404/422，模型限额/期限沿用既有状态码。任何缺案例与异常保留分母，质量评分仅原严格gold scorer，不使用财务规则分代替。Unknown不返回假百分比。

## 任务清单

- [x] 后端TDD：失败PDF不产生模拟指标；缺失指标不打100；原文页码与切片定位；冻结哈希匹配；演示禁评测；金标生成隔离/缺案例不隐藏/未改评分器；复用真实Admission与统一客户端；共同trace仅允许元数据。
- [x] 前端独立实现analysis工作台，移除index.html旧内联处理器，独立analysis-workbench.js/analysis.css；文件校验、清空、重复提交抑制、账号切换清理、耗时/取消/错误重试；使用DOM textContent安全渲染；显示三种分数与逐例结果。
- [x] 前端VM测试交互/状态/异常/取消/旧响应不覆盖；后端隔离测试API与机制；独立review、完整unit/auth相关/frontend/build与视觉核对。
- [x] 启用本地新版本，检查API/页面就绪，记录真实付费评测未自动执行与剩余限制。

## 验收结果（2026-10-24）

完整单元测试590通过；相关权限/限额/期限29通过；前端83通过；Vite生产构建通过。新API、质量服务、评测服务及其测试ruff通过，analysis模块compileall通过，git diff --check通过。测试使用独立confcutdir，没有调用根conftest、清空业务数据库或新增付费模型调用。

独立review发现的评测运行时限额/超时被评分器吞为HTTP200已修复：429/503/504保留完整分母、已完成案例和Retry-After。逐例contract标签修正为“整例通过”，对应完整验收而非仅输出格式。

实际服务 `/health`、`/openapi.json`、前端模块均HTTP200，上传协议确认为JSON。IAB无登录会话，视觉验收使用独立loopback演示夹具，真实组件/CSS与公开财报数据，不绕过业务登录；桌面检查上传、阶段加载、结果，390px手机宽度无横向溢出，控制台无error。截图在忽略目录 `.local-backups/analysis-qa/`，测试服务器验收后停止。

限制：规则提取仍是正则，原文定位不能证明指标语义、单位或期间正确，UI保留核对提示。真实模型金标评测仅支持冻结茅台/平安两份原PDF，每份5例，不能代表全篇投研质量；用户需明确点击评测才调用模型。停止等待不保证服务端取消。20MiB文件上限存在两层校验：模型schema过长base64先422，解码后超限413。实际登录后付费评测本轮未重跑；其调用/严格评分/公共trace/部分结果由mock端到端测试覆盖。

原评分器SHA256保持 `abf2c64e899445cec6be028e6eba270cefb976765ad970a2db0e57797b972caf`；原始实测基线SHA256保持 `a8e29557e3437ba61bceafa2ee11a69741dffa37ec7df18e1fd294f234feba79`。
