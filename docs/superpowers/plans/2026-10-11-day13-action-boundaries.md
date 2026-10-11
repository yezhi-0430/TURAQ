# Day 13 建议与执行 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 分离模型建议与显式请求，以后端提交结果决定执行状态。
**Architecture:** agent_actions.py 定义契约、结构化回答解析及显式移除服务；agent_api.py 提供建议返回与独立动作入口，复用现有仓储。仅离线测试，保持三工具白名单。
**Tech Stack:** Python、Pydantic、FastAPI、SQLAlchemy、Pytest。

## Global Constraints

规格 `docs/superpowers/specs/2026-10-11-day13-action-boundaries-design.md`。建议 status 仅 suggested；请求与结果为不同 kind；成功状态无默认值、仅仓储提交后产生。拒绝额外字段、严格 ID 上限 2147483647、完整股票代码格式、建议文本非空最多 4000 字符、最多 5 条建议。普通回答兼容，非法结构化模型建议 502；动作成功 200、缺失 404、失败 500。显式入口不是身份认证。正式数据库与其他前端/行情改动保持原位，本地按路径提交，不上传。

## Task 1: 三类契约和 HTTP/服务边界

**Files:** Create `app/agent_actions.py`; Modify `app/agent_api.py`, `app/agent_policy.py`, `tests/unit/test_agent_safety.py`, `docs/day-13-safety-boundaries.md`。

**Interfaces:** `Suggestion`, `ExecutionRequest`, `ExecutionResult`；`parse_agent_answer(raw: str | None) -> tuple[str | None, list[Suggestion]]`；`execute_watchlist_removal(request: ExecutionRequest, *, session_factory) -> ExecutionResult`；`InvalidSuggestionOutput`；ChatResponse 增加 suggestions，动作 route 在已有 agent router 中。

- [ ] 写真实安全 fixture 测试：合法建议不修改业务表；非法建议 confirmed/success/error/execution_request/多条/无效 ID 502且不打开动作会话；非法动作请求 422且数据库/模型零调用；成功仅移除指定关联；404 与重复请求；before_commit 真提交失败 rollback；Suggestion 不能直接执行；普通文本兼容；执行状态无默认 success。

```python
payload = {'kind': 'suggestion', 'status': 'suggested',
           'operation': 'remove_watchlist_stock', 'watchlist_id': 1,
           'stock_code': '000001.SZ', 'text': '待用户判断'}
response = safety.client.post('/api/v1/agent/chat', json={'messages': [message()]})
assert response.json()['suggestions'] == [payload]
assert snapshot(safety.factory) == before
```

- [ ] 运行 `.venv/Scripts/python.exe -X utf8 -m pytest --confcutdir=tests/unit tests/unit/test_agent_safety.py -q -o addopts=''`，Expected：新增契约/接口用例失败，旧边界用例通过。先仅写测试，不导入不存在的模块到测试顶部，避免 collection error。
- [ ] 实现 strict/extra forbid 的三个契约，text 校验空白和 Unicode；结构化 JSON envelope 的 answer 严格文本及 suggestions 最多 5，明确字段 validation error 转 InvalidSuggestionOutput；普通文本/非建议 JSON 保持原样。
- [ ] 服务只接受 ExecutionRequest，先检查类型，再创建 session；复用 remove_stock_from_watchlist，异常 rollback、明确错误种类、无私有细节；成功必须发生在仓储 commit 返回之后。API 新增 suggestions 和显式入口，以后端 error.kind 映射 404/500；模型格式错误 502，不吞为现有普通 500。
- [ ] 系统说明补充可选 JSON 建议格式、实际 ID 未知时只返回文本、不伪造确认与结果。运行新增测试 Expected：通过；全部隔离 unit 和相关审计/仓储 PostgreSQL 测试 Expected：通过；Ruff/format/diff Expected：通过。
- [ ] 更新笔记概念判断、Literal 引导练习和默认值纠正，明确独立编码未验证、认证/真实模型/前端建议操作仍未建设；按路径本地提交。一次独立只读审查，Important/Critical 用失败回归修复后整套验证。

## Review Focus

确认没有从聊天建议到写入服务的调用路径，kind/status/confirmed 都不能作为模型授权；状态在真实 commit 后生成，失败 rollback；新入口不声称身份认证，错误细节不泄露；结构化输出失败与普通文本兼容；没有破坏三工具、来源和审计，旧手动前端不受影响。

## 执行记录

基线 76b01ea，沿用户已批准范围在当前功能分支执行；Pre-flight：一个任务，无跨任务接口，repo commit 与服务 success 顺序一致。独立动作入口通过已有 router 注册，避免纳入未提交 main.py 改动。

Task 1：实现与回归完成，等待最终审查。新增 29 fail→pass；旧 41 pass；入口 70 pass；全部隔离 unit 349 pass；PostgreSQL schema_upgrade/audit/watchlists 54 pass。两个既有依赖警告保留，Ruff/format 通过。只在隔离测试数据库验证显式移除和事务失败，不执行正式数据操作。
