# A 股自选股风险监控与模拟交易 Agent

面向个人投资者的金融信息研究工作台。系统维护多只自选股，扫描公告、财报和日线指标中的风险线索，生成带来源的研究报告，并在用户确认后执行模拟交易。

## 当前进度

Day 1–7 已完成后端、自选股管理和日线导入查询。Day 8 已加入可切换的假模型与千问客户端，离线测试通过，并已在本地完成一次真实千问调用。第一版界面尚未完成。

Day 9 已加入风险摘要结构校验与接口，20 条模拟输出验收通过，并完成一次真实千问结构化输出验证。格式校验不验证事实真伪。

Day 10 已完成技术验收、基础问答和本轮补充复盘：三个工具、执行前校验、调用日志和模型原生工具选择已连接。已用真实千问选择 `calculate_change`，再由 Python 计算 `10 → 9` 得到 `-10.0000`。工具参数的小数精度问题及整项目审查发现的 7 项问题已修复，最近全套测试 247 passed。列表与字典的区别仍需巩固，尚未验证独立编码能力。修复与数据库升级说明见 [项目审查修复记录](docs/project-review-fixes-2026-10-08.md)。

Day 11 技术验收和本轮基础口头复盘已完成：工具结果回传、自动多轮循环和最大轮数均已实现，得到有效回答时提前结束，达到上限则明确返回未完成。已用真实千问完成两轮“工具选择 → Python 计算 → 结果回传 → 最终回答”，用户也已亲自运行；最近全套 291 passed。基础编码练习仍需提示，继续巩固条件判断、变量名和列表方法。见 [Day 11 学习记录](docs/day-11-agent-loop.md)。

Day 12 第一阶段已实现审计表与独立事务保存函数，成功及失败调用均可持久化；新增 9 项测试，全套 300 passed，Ruff 通过。尚未接入 Agent 循环或提供审计查询入口。见 [Day 12 学习记录](docs/day-12-tool-audit.md)。

## 项目原则

- 一级事实以交易所、巨潮资讯和上市公司正式披露为准。
- 所有重要结论保留来源、发布时间和采集时间。
- 模型负责理解、检索编排和解释；金额与指标由确定性代码计算。
- Agent 不能直接交易，模拟操作必须经过用户确认。
- 项目不构成投资建议，不接入真实券商账户。

## 本地运行

要求 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m app.schema_upgrade
uvicorn app.main:app --reload
```

打开：

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

运行检查：

```powershell
pytest
ruff check .
```

模型客户端的配置、离线测试和手动验证方式见 [Day 8 学习记录](docs/day-08-model-api.md)。
风险摘要的数据结构、接口与验证结果见 [Day 9 学习记录](docs/day-09-structured-output.md)。
工具调用的学习进度与计算工具说明见 [Day 10 学习记录](docs/day-10-function-calling.md)。

已有数据库也需运行一次 `python -m app.schema_upgrade`：该命令保留记录，将股票代码去除两端空白并转为大写，将成交量列升级为 BIGINT；若发现规范化后重复的代码，会回滚并报告冲突。建议在应用停止写入时运行，可重复执行。

日线导入要求四个价格均为有限正数，整数部分最多 14 位、小数部分最多 4 位，并满足 `low <= open/close <= high`。JSON 数字与数字字符串均可使用；返回价格仍为字符串。成交量范围为 `0` 至 `9223372036854775807`。不合法输入返回 422。

`MODEL_PROVIDER=fake` 时，风险摘要接口返回合法的离线占位摘要：评级为 `unknown`，并明确说明尚未分析输入，不生成事实或来源。

运行 Day 10 离线工具演示（Windows 使用 UTF-8 输出）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m app.tools.demo
```

演示计算 `10 → 9` 并拒绝 `0 → 9`；调用记录追加到 `data/private/day10-tool-calls.jsonl`。此演示不请求模型或数据库。

运行包含假模型调用请求的完整离线演示：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m app.tool_calling_demo
```

假模型返回预先配置的两个计算请求；程序经执行器校验后计算或拒绝，并用 `tool_call_id` 关联请求与日志。记录追加到同一私有 JSONL 文件。此演示不请求真实模型或数据库，尚不包含工具结果回传模型的自动循环。

运行真实千问工具选择演示（使用本地 `.env` 中的模型、地址和 API Key）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m app.tool_calling_demo --provider qwen
```

真实模式发送虚构的昨日价格 10、今日价格 9 和三个工具定义，由模型选择工具，再交给 Python 执行。默认不加参数仍使用 fake，即使 `.env` 中的 `MODEL_PROVIDER=qwen` 也保持离线。

运行 Day 11 完整循环演示（默认离线，即使 `.env` 选择了 qwen）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m app.agent_loop_demo
```

显式请求真实千问，使用本地 `.env` 配置：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m app.agent_loop_demo --provider qwen
```

输入为虚构价格 10 和 9，默认最多五轮。输出包含最终状态、回答、实际轮数和工具执行记录；日志追加至 `data/private/day11-tool-calls.jsonl`。离线模式的工具选择与回答逻辑由程序预设，真实模式由千问响应。

## 目录

```text
app/                 应用代码
tests/               自动化测试
docs/                架构和设计记录
data/                 可公开的演示数据
```

详细设计见：

- [产品范围与用户故事](docs/product-scope.md)
- [第一版架构](docs/architecture.md)
