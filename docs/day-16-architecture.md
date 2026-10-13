# Day 16：Nanobot 架构阅读（进行中）

## 范围和起点

2026-10-13，用户请求开始 Day16。依据上级目录 `8-week-agent-learning-roadmap.md`，当天任务是追踪用户请求至模型、工具和结果的路径，绘制模块图、时序图和状态变化图，每项结论均对应实际源码位置。

继续使用 Day15 固定的 HKUDS/nanobot `v0.3.5` 源码包，目录为 `C:\Users\LENOVO\Documents\Codex\2026-09-20\n\outputs\nanobot-0.3.5`。以下源码位置均相对于这个目录。优先追踪 Day15 已运行的单次 CLI Hello 请求，再查看文件读取分支。

Day15 的真实示例和基础复盘已有记录；独立三分钟项目介绍尚未计时验收，不因开始 Day16 自动视为通过。

## 第一节：命令入口和参数

`pyproject.toml:111` 声明：

```toml
nanobot = "nanobot.cli.entry:main"
```

这将安装生成的 nanobot 命令映射到 `nanobot/cli/entry.py:71` 的 `main` 函数。该函数在第 73 行取得命令参数：

```python
raw_args = sys.argv[1:]
```

为说明参数结构，暂时省略 Day15 实际命令中的配置、会话、工作目录和显示参数，简化为 `nanobot agent -m "Hello!"`。这一简化命令不是已经配置默认实例的证明。此时 argv 包含程序路径，取 `[1:]` 后参数可表示为：

```python
["agent", "-m", "Hello!"]
```

`agent` 选择对话子命令，`-m` 是消息选项，`Hello!` 是用户消息。接收这些字符串不等于已经请求模型。

## 已核对的实际路由

| 位置 | 源码事实 |
|---|---|
| `entry.py:23`（目录 `nanobot/cli`） | `_agent_invocation_args` 识别显式 agent 子命令及省略子命令的选项形式 |
| `entry.py:34` | `_native_tui_candidate` 遇到 `-m` 或 `--message` 时返回 False |
| `entry.py:90` | 显式 agent 命令不属于 root agent alias |
| `entry.py:91` | 本轮单次消息因此没有进入 `_run_agent` 快速分支 |
| `entry.py:98` | 导入 `nanobot.cli.commands.app` 并在第 100 行调用该 Typer 应用 |
| `commands.py:56`（目录 `nanobot/cli`） | 导入实际的 agent 函数 |
| `commands.py:472` | 将该函数注册为 agent 子命令 |
| `agent.py:54`（目录 `nanobot/cli`） | 对话函数入口；第 55 行将 `--message` / `-m` 声明为 message 参数 |
| `agent.py:236` | `message is not None` 时采用单次消息分支 |
| `agent.py:246` | 调用 `agent_loop.process_direct(message, session_id, ...)` |
| `agent/loop.py:2318`（目录 `nanobot`） | `process_direct` 接收 content 等参数，构造 InboundMessage，取得会话锁，再调用 `_process_message` |

这里必须区分单次消息、交互终端和聊天平台的路径。单次消息虽然创建 MessageBus 对象，却直接调用 process_direct；不能根据上游通用架构说明把它画成先发布到入站队列的流程。

模型适配初步核对：`nanobot/providers/registry.py:557` 的 dashscope 条目选择 openai_compat 后端；`nanobot/providers/factory.py:224` 导入 OpenAICompatProvider 并在第 226 行创建实例。实际请求方法、响应处理和循环结束分支仍需继续阅读。

## 当前进度与剩余事项

已只读核对入口、单次命令分发、对话参数和 process_direct 的衔接。尚未完成完整 Hello 路径、工具分支或三种图，不声明 Day16 技术验收或用户学习验收通过。

本轮没有请求真实模型、运行额外示例、改动参考源码或连接业务数据库。准备向用户解释第一节的 `sys.argv[1:]`，后续问答按实际回答补录。
