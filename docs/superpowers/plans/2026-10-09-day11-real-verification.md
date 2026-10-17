# Day 11 Real Multi-round Verification Plan

> **For agentic workers:** Use superpowers:executing-plans inline with TDD and verification-before-completion.

**Goal:** 用虚构价格 10 和 9 验证真实千问选择工具、收到 Python 结果、返回最终答案的完整循环。

**Architecture:** 新增独立演示命令 app.agent_loop_demo；默认 fake 不发网络请求，显式 --provider qwen 使用本地 Settings 与现有工厂。所有演示均复用 run_agent_loop、白名单执行器及调用日志，最大轮数沿用默认 5。

**Constraints:** 用户在 Day 11 离线验收完成后要求继续，沿用已批准设计安排真实验证阶段。不显示或修改密钥；输入仅为虚构价格，不新增依赖、不改写数据库。默认运行即使环境设为 qwen 也保持离线。真实验证只运行一次，失败按证据记录，不重复请求以获取理想输出。

## Task 1: 命令与真实验收

Files: 新建 app/agent_loop_demo.py、tests/unit/test_agent_loop_demo.py；更新 README.md 和 docs/day-11-agent-loop.md。

Interface: main(argv: list[str] | None = None) -> None；--provider choices=(fake,qwen)，默认 fake。演示输出 provider 标签和 AgentLoopResult；执行器 JSONL 追加至 data/private/day11-tool-calls.jsonl。

- [x] 测试默认保持离线：环境 MODEL_PROVIDER=qwen，HTTPX MockTransport 拒绝任何请求；断言 completed/rounds=2、计算结果和私有日志。
- [x] 测试显式 qwen：MockTransport 返回第一次工具调用和第二次最终答案；第二次请求断言匹配 call ID 与 Python 的 -10.0000、完整工具定义；验证输入只有虚构价格、最终结果、日志和未泄露测试密钥。
- [x] 测试模型异常时日志 handler、level、propagate 均恢复，避免污染后续调用。
- [x] 运行新测试并观察缺少模块的失败。
- [x] 实现命令：argparse 覆盖 Settings.provider；fake 使用本地顺序响应客户端，首轮请求 calculate_change(10,9)，后续根据实际 tool content 生成离线回答；qwen 经 create_model_client 创建。try/finally 设置并恢复日志 handler，with httpx.Client 调用 run_agent_loop。

```python
args = parser.parse_args(argv)
settings = Settings().model_copy(update={"model_provider": args.provider})
with httpx.Client() as http_client:
    client = OfflineDemoClient() if args.provider == "fake" else create_model_client(settings, http_client)
    result = run_agent_loop(client, messages)
print(label)
print(result.model_dump_json(indent=2))
```

- [x] 运行新增测试、全套 pytest、Ruff 和格式检查，按 requesting-code-review 进行只读审查。
- [x] 先运行离线演示，再运行一次 `.venv/Scripts/python.exe -X utf8 -m app.agent_loop_demo --provider qwen`；核验轮数、调用 ID、实际参数、Python 结果、最终回答与新增日志。
- [x] 如实记录真实验证证据与边界，提交，然后讲解实际结果。

## 执行记录

沿用当前项目目录和 codex/day11-tool-feedback 分支；上一提交 c836ff4，最近代码验证 288 passed。本计划作进度台账。

结果：新增 3 条先失败后通过，全套 291 passed，Ruff/格式检查通过；独立审查无阻断问题。离线运行一次、真实 qwen-plus 运行一次，均 completed/rounds=2。真实调用 calculate_change(10,9)，Python 返回 -10.0000，千问最终回答“涨跌幅为 -10.0000%。”；已核验私有追加日志。
