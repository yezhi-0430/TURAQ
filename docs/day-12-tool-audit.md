# Day 12：数据库审计（第一阶段）

## 学习范围

今天将每次工具调用尝试保存到数据库，用 run_id 关联同一次 Agent 运行。用户已理解一次运行调用两个工具对应两条记录；最初认为一个失败一个成功只保存一条，经解释后能判断昨日价格为 0 导致拒绝计算也需要保存。尚未验证独立编写审计代码的能力。

## 第一阶段实现

app/database.py 新增 ToolAuditRecord，保存 run_id、tool_call_id、名称、原始参数、状态、结果、错误、耗时和 UTC 保存时间。原始参数使用文本，因此非法 JSON 也可以记录；JSON 结果保留价格和计算结果的字符串表示。数据库限制状态为 success/error、耗时非负。

app/audit/repository.py 的 save_tool_execution 接收现有 ToolExecutionRecord，使用自己的会话和事务保存，提交成功后返回记录 ID。保存失败回滚并抛出原异常，不提交调用者的业务会话。历史已提交记录不受后续失败影响。

```python
with session_factory() as session, session.begin():
    session.add(row)
    session.flush()
    record_id = row.id
return record_id
```

add 将对象加入待保存集合；flush 将 INSERT 发给数据库并获得 ID，但还没有提交；正常退出 session.begin() 才提交。发生异常时回滚，因此不会执行下面的 return。

新表使用现有 create_all/schema_upgrade 机制建立；测试清理已包含新表。当前只升级了隔离测试数据库。实际应用数据库可在后续接入时运行 `.venv/Scripts/python.exe -m app.schema_upgrade`。

## 验证

新增 tests/test_audit_storage.py 的 9 项用例先因缺少 app.audit 模块失败，实现后通过。使用现有 PostgreSQL 隔离测试数据库，覆盖跨会话持久化、成功及拒绝记录、非法 JSON、小数字符串、UTC 时间、重复/空调用 ID、字段约束、业务事务隔离及提交失败回滚。

## 后续阶段

2026-10-10 全套测试 300 passed，保留两条既有依赖弃用警告；全项目 Ruff 通过。

尚未将保存函数接入 Agent 循环，尚未提供按 run_id 分页查询或完整演示。本阶段完成不代表整个 Day 12 完成，也未请求真实模型。
