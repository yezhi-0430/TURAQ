# Day19 离线课堂示例

这是根据课堂已讲解内容整理的辅助演示。用户已要求停止手写练习，继续看代码和判断结果；本目录不能作为用户独立复现通过的证据。

从主项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 learning/day19-minimal-agent/demo.py
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s learning/day19-minimal-agent -p "test_*.py" -v
```

文件：
- mini_agent.py：名称到函数的字典注册、工具执行、有限循环、执行轨迹、JSON 会话保存/恢复。
- demo.py：离线加法、第二轮使用真实工具输出、会话恢复后追问、轮数耗尽、未知工具。
- test_mini_agent.py：行为测试，含独立子进程重新读取保存文件。

建议先读 execute_tool，再读 run_agent。工具用 success/error；整次运行用 completed/max_rounds_exceeded/model_error/invalid_response。工具 error 会加入消息和轨迹，模型可以在下一轮看到它。模型异常停止本次循环并保留已有轨迹。空回答不会被当作完成。

ScriptedModel 是脚本响应器，支持回调读取传入的消息，便于观察实际数据流。它不具备真实语言理解能力，不发网络请求，也不证明任一真实模型接口兼容。示例采用自定义、可 JSON 序列化的消息结构；工具参数只检查字典形态，关键字绑定错误由 Python 抛出并记录，未实现完整业务参数 Schema。

会话以调用方指定目录及编号定位。保存和恢复是独立步骤；调用方必须把恢复的 messages 交给 run_agent，旧轨迹可通过 prior_executions 传入。缺失会话返回空状态，损坏文件显式报错。文件写入用于单进程课堂，未实现并发锁、历史截断、自动摘要、长期记忆或真实模型重试。

演示和测试都使用自己创建的临时目录，运行结束后清理。测试中的子进程使用同一个 Python 解释器，验证读取来自磁盘而非父进程缓存。没有连接主项目数据库或读取真实模型配置。

