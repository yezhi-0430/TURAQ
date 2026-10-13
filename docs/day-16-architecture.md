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

已只读核对入口、单次命令分发、对话参数、配置读取和 process_direct 的衔接。尚未完成完整 Hello 路径、工具分支或三种图，不声明 Day16 技术验收或用户学习验收通过。

本轮没有请求真实模型、运行额外示例、改动参考源码或连接业务数据库。后续问答按实际回答补录。

## 入口与参数的引导问答

- 讲解 `raw_args = sys.argv[1:]` 后，用户选择 B：这一行尚未向 Qwen 发送请求。
- 讲解 Typer 将 `-m` 后的值传给 message 参数后，问命令改为 `nanobot agent -m "你好"` 时 message 的值；用户回答“你好”。

这两项是基于源码片段的引导理解，尚未要求用户独立写参数解析代码或讲解整条请求路径。

## 第二节：读取运行配置

`nanobot/cli/agent.py:82`：

```python
runtime_config = _load_runtime_config(config, workspace)
```

此处 config 是命令行传入的配置文件路径，workspace 是可选的工作目录覆盖值；返回的 runtime_config 是后续运行所用的配置对象。用户消息仍在 message 参数中，读取配置不是模型请求。

`nanobot/cli/runtime_config.py:117` 定义该函数：第 123 行解析显式配置路径，第 124–126 行在文件不存在时退出；第 130 行加载配置并解析环境变量引用；第 131–132 行处理工作目录覆盖，第 133 行返回配置对象。

Day15 学习配置指定模型 qwen-plus、供应商 dashscope、学习工作目录，并通过环境变量引用提供凭据。它们用于配置模型连接和运行环境；“你好”属于本次用户消息。

后续 `nanobot/providers/factory.py:273` 的 make_provider 使用配置解析模型设置，第 285–286 行解析模型预设并创建适配器。实际 CLI 在何处调用工厂、适配器如何发出请求，将在后续小节展开。

用户在“程序从消息还是运行配置知道要使用 qwen-plus”中选择 B，配置与消息的引导区分正确。

## 第三节：创建模型适配器并交给 AgentLoop

`nanobot/cli/agent.py:149`：

```python
provider = make_provider(runtime_config)
```

模型名称等连接设置来自配置，make_provider 据此创建 Nanobot 的模型适配器对象。Day15 使用 dashscope，registry.py:557–560 对应条目选择 openai_compat；factory.py:226–237 将凭据、API 地址和模型等设置传给 OpenAICompatProvider。此处是准备通信对象，不等于已经收到模型回复。该适配器在 `nanobot/providers/openai_compat_provider.py:559` 初始保存 `_client = None`，真正的 SDK 客户端由后续 `_ensure_client` 路径准备。

`nanobot/cli/agent.py:171` 调用 `agent_loop_class.from_config(...)`；第 174 行将 provider 对象传入 AgentLoop，第 178 行传入工具注册表。这是把模型通信与工具能力装配到 Agent 流程中。原文还传入 bus、cron 和 hooks 等依赖，课堂片段只突出 provider，并非完整参数列表。

后续已初步读到 `_run_turn` 调用 `_run_agent_loop`、后者交给 AgentRunner，以及最终保存结果的位置；这些环节的调用路径和用户理解仍待后续逐项核对，不据此更新完整架构验收状态。

用户在“provider 与模型通信 / 读取会议文件”中选择 A，模型适配器职责的引导判断正确。

## 第四节：把用户消息交给 AgentLoop

`nanobot/cli/agent.py:246` 将用户消息、会话编号及显示回调传入 `agent_loop.process_direct(...)`，并将返回对象保存到 response。课堂可省略显示回调，突出：

```python
response = await agent_loop.process_direct(message, session_id)
```

省略回调的片段用于说明对象、方法和消息参数，不是 Day15 原始调用的逐字复制。await 在此等待该异步处理方法返回；原 CLI 同时提供流式显示回调，部分文字可在方法完成前展示。

process_direct 的内部调用已核对至 `nanobot/agent/loop.py:2374`：将构造好的 InboundMessage 交给 `_process_message`。后者在第 1679–1687 行依次处理 restore、compact、command、build、run、save 和 respond；command 若已经处理请求，会提前返回。Hello 属于普通用户消息，后续需要展开正常分支的消息构造与模型请求。

职责区分：provider 处理模型通信，AgentLoop 组织本次请求的处理阶段；本轮工具调用由后续 AgentRunner 和工具代码执行。用户尚未在本节独立讲解这些方法或阶段。

### 流程协调与通信的复盘

问“负责协调消息、模型和工具的是 provider 还是 AgentLoop”，用户选择 A（provider），随后纠正为 AgentLoop。再问安排“执行工具→回传结果→再次请求模型”的顺序属于流程协调还是模型通信，用户选择 B（模型通信），再次讲解什么时候请求与怎样发送的区别，并使用电话比喻。

转为直接读代码，问 `.process_direct` 点号左边的对象名称，用户回答 `agent_loop`。能识别这一处调用对象，不据此认定已经独立区分协调者与模型适配器。后续继续用实际方法内部步骤说明。

## 第五节：包装入站消息

`nanobot/agent/loop.py:2320` 的 process_direct 参数 content 接收调用方传来的 message 字符串。第 2345–2348 行构造消息对象：

```python
msg = InboundMessage(
    channel=channel, sender_id=sender_id, chat_id=chat_id,
    content=content, media=media or [], metadata=metadata,
)
```

用户文字保存到 msg.content，channel、sender_id 和 chat_id 提供消息来路等信息。变量名从调用方的 message 变为本方法的 content，文字值在这一普通无附件示例中保持不变。它是打包用户消息，不是生成模型回复。

第 2350–2352 行取得该会话的锁；第 2374–2377 行把 msg 及处理参数交给 `_process_message`。后续 `_restore_turn` 在第 1766 行读取或创建对应会话，`_build_turn` 在第 1887 行取得历史。这些位置已经只读查看，课堂解释尚未展开到会话历史与请求上下文构造。

问 msg.content 在用户输入“你好”时保存什么，用户回答“字符串”。指出这是数据类型，具体值是“你好”；随后将输入改为“读取会议记录”，用户回答具体值“读取会议记录”。类型与值的迁移判断在引导后正确，尚未独立编写消息对象。

## 第六节：取得会话和历史

`nanobot/agent/loop.py:1766`：

```python
ctx.session = self.sessions.get_or_create(ctx.session_key)
```

这里按会话键查找或创建会话对象。`nanobot/session/manager.py:1740` 的实现先在第 1750 行查缓存，未命中再在第 1754 行读取已保存的会话；没有已有会话时，第 1756 行创建 Session 对象。创建对象不等于立刻把新文件写到磁盘，持久化由后续保存步骤负责。

`nanobot/agent/loop.py:1887` 从该会话取得可用于模型输入的历史：

```python
ctx.history = session.get_history(extend_to_user=is_subagent)
```

`nanobot/session/manager.py:344` 的 get_history 处理可回放消息、摘要检查点和合法的工具消息边界，不应简单描述为不加筛选地回传全部历史。细节在后续会话专题展开，本节先理解旧对话与新消息会一起用于准备本轮请求。

下一步消息准备的对应位置已找到：`nanobot/agent/loop.py:720` 的 `_build_transcript_input` 将 history 与 current_message 等输入分开保存；第 725 行的当前文字来自 ctx.msg.content。请求消息组装的课堂阅读尚未进行。
