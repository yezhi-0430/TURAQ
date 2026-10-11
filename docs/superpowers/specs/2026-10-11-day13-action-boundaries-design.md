# Day 13 第三阶段：建议与执行契约

沿用户已批准的三阶段设计，当前会话直接完成建议/执行类型和接口。以已有自选股移除功能为最小实例，不建设模拟账户或交易引擎。

## 数据与入口

- `Suggestion`：kind=suggestion，status 仅 suggested（默认），operation 仅 remove_watchlist_stock，watchlist_id 为严格正整数（最大 2147483647），stock_code 沿用库中完整代码格式，text 为非空严格字符串（最多 4000 字符）。拒绝 confirmed、权限、success/error 等额外状态/字段。
- `ExecutionRequest`：kind=execution_request，operation/目标同上，不接受建议 status/text/confirmed。这是显式客户端请求契约，不是身份认证或真实人类证明。
- `ExecutionResult`：kind=execution_result；status 仅 success/error，必须填写，无成功默认值；error 状态必须有后端错误，success 必须没有错误。只有实际仓储提交成功后构造 success。

`POST /api/v1/agent/chat` 保持 answer 文本、executions 和已有结果格式，并新增 suggestions 列表。普通文本继续兼容。若模型提供 JSON 对象含 suggestions，则完整校验 answer 和最多五条 Suggestion；合法对象解包为 answer/suggestions。非法结构化建议返回 502，错误信息不回显模型原文，不调用动作服务。模型输出的执行请求/确认状态不成为授权。

`POST /api/v1/agent/actions/remove-stock` 接受 ExecutionRequest，显式客户端调用后才调用现有 remove_stock_from_watchlist 仓储。成功 200；目标分组不存在/股票不在组中 404；仓储提交失败 rollback 并返回 500。均给出后端 ExecutionResult。建议对象直接传入服务必须在数据库打开之前拒绝。无需调整旧手动自选管理接口或前端行为。

Agent 的三工具白名单保持不变；不注册写入或确认工具，不把 suggestions 转为 action 请求，不让模型调用该 HTTP 入口。既有未认证手动接口与新显式入口一样，不保证公网多用户访问控制；认证属于独立后续工作。本阶段不声称获得用户身份验证，不以 JSON kind 代替登录权限。

## 验收

离线模型+真实 SQLite：结构化建议与假 success/confirmed/execute JSON 不会改业务表；未知写工具持续拒绝并审计。显式合法请求移除指定关联，保留其他股票/分组；重复请求 404。非法请求在模型与数据库前拒绝；真实 before_commit 失败不删除关联、返回 error 且隐藏私有异常。建议不能直接传进动作服务。旧普通文本和工具来源/审计契约不变。

Pydantic 的 Literal 才在模型验证时约束值；普通 Python 类型注解不会自动拒绝输入。学习记录区分引导练习和独立编码，不将小题正确等同于独立开发。

设计自查：服务提交状态属于后端，客户端显式请求和用户身份验证分别说明；没有账户/交易扩展，无前端未提交代码改动，无模型自动写入。
