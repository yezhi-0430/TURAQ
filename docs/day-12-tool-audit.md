# Day 12：数据库审计

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

第一阶段完成时尚未将保存函数接入 Agent 循环、提供分页查询或完整演示；后续阶段进度见下文。当天未请求真实模型。

## 第一阶段口头复盘

用户能判断提交失败不会正常返回 ID，以及第二条记录失败不会回滚第一条已提交记录。最初认为 run_id 应在 for 循环里面生成，解释后能判断一次三轮运行只需要一个 run_id。尚未验证独立写出相关代码。

## 第二阶段：接入循环

run_agent_loop 在循环前生成 UUID，每个返回结果包含 run_id。新增可选 audit_writer 参数，显式传入第一阶段保存函数即可启用审计：

```python
result = run_agent_loop(client, messages, audit_writer=save_tool_execution)
```

不传 audit_writer 时仍保持原有离线计算能力，生成运行编号本身不访问数据库。run_tool_turn 新增 on_execution 回调，在每个工具形成记录后调用；循环用闭包将本次 run_id 和记录交给 audit_writer。保存函数在工具异常捕获之外运行，因此数据库错误直接抛出，不会伪装成工具业务错误，也不会继续同轮的下一个调用。

成功返回及轮数耗尽都返回运行编号。模型后续超时保留此前已提交记录；异常仍抛出原异常，本阶段没有新增运行状态表或异常运行查询入口。

新增 7 项 PostgreSQL 集成测试，先因缺少 audit_writer 参数和 run_id 字段失败，再通过。覆盖多轮/多工具关联、不同运行不同编号、直接回答零记录、参数拒绝、超时保留、轮数耗尽、首条或第二条保存失败停止后续调用、默认不连接数据库。

2026-10-10 第二阶段全套 307 passed，保留两条既有依赖弃用警告；Ruff、相关文件格式检查通过。独立只读审查未发现可操作问题。

## 第二阶段口头复盘

用户能判断工具 A 执行成功但记录保存失败时，工具 B 不会继续执行。已解释保存失败不撤销工具 A 的执行，不能贸然重试。独立编码能力尚未验收。

## 第三阶段：分页查询与完整演示

list_tool_executions(run_id, after_id=0, limit=20) 按本次运行编号筛选、按数据库主键 ID 升序返回，最多允许 100 条。after_id 表示上页最后一个 ID，下一页只返回比它大的记录。空结果返回空列表。limit 和 after_id 必须为有效整数，拒绝 bool、字符串和浮点数，并在连接数据库前检查。

返回 AuditRecord 快照，包含原调用字段、数据库 id、run_id 和 created_at。快照在数据库会话内生成，关闭会话后仍可读取和序列化。

完整演示命令：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m app.audit_demo
```

演示只使用假模型，固定连接 a_share_risk_agent_test 数据库（主机与凭据沿用本地配置），只创建缺失审计表，不清表。该数据库需已存在并可连接。即使环境配置为 qwen 或其他数据库名称，演示仍固定假模型和测试库。

第一轮预设两次计算：10→9 成功得到 -10.0000；0→9 因参数校验失败拒绝。第二轮根据实际工具结果生成说明。程序将两条记录提交后，使用新数据库会话以每页一条的方式查回。输出 loop 为内存循环结果，stored_records 为数据库查询结果。再次运行使用新 run_id，保留已有记录；后续运行 pytest 会按现有隔离规则清理测试库中的这些演示记录。

新增 14 项测试验证查询隔离、顺序、分页、无结果、快照序列化、参数校验及完整演示。测试初次因缺少模块/函数失败；实现后演示暴露 FakeModelClient 构造缺少 reply 参数，修复后全部通过。禁止 HTTP 请求并设置 qwen 环境的测试验证演示仍使用假模型。独立只读审查未发现可操作问题。

2026-10-10 全套测试 321 passed，保留两条既有依赖弃用警告；Ruff、格式和 diff 检查通过。之后实际执行演示命令一次，run_id 为 563a5eb2-b9fe-432f-ae47-c59618b3cd1e，completed、两轮；查回 id=1 的 success/-10.0000 与 id=2 的 error/invalid_arguments，两条记录共用运行编号。时间戳为带时区值，PostgreSQL 读取时按会话时区显示，本次输出 +08:00，与 UTC 表示的是同一时刻。

Day 12 三个技术阶段已完成；第三阶段口头复盘和独立编码练习尚未验收。
