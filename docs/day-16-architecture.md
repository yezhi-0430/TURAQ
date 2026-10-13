# Day 16：Nanobot 架构阅读（架构追踪与基础复盘完成）

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

已完成单次 CLI 的正常回答与文件读取总结路径追踪，整理模块图、时序图和阶段状态图，并逐项核对相应源码位置。用户完成了引导式基础复盘，最终能区分 AgentLoop 与 Runner。下文保留各节的课堂进度记录，最终状态以文末复盘为准。

本次完成的是架构阅读、源码验证和引导式基础复盘；用户独立画图、完整路径口述和编写 Agent 的能力尚未验收。Day15 的独立三分钟项目介绍也仍待验证。

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

用户在“连续追问复用同一编号 / 每次换新编号”中选择 A，会话连续性的引导判断正确。

## 第七节：组装模型输入消息

已核对实际消息构造器为 `nanobot/agent/context.py:276` 的 build_transcript。该方法第 286–297 行建立系统消息并追加 transcript.history，第 301–307 行构造本次消息并追加到列表，第 308 行返回 messages。

当前消息构造器 `build_current_message` 从第 310 行开始，默认 current_role 为 user；文字可附加运行上下文或显式技能上下文，所以 API 输入不一定是只有用户原文的字符串。课堂用简化的“系统说明＋可用历史＋当前消息”理解组成，不将示例字典视为真实请求的完整内容。

`nanobot/agent/context.py:231` 的 build_messages 是兼容包装方法，可能合并相邻同角色消息。当前核心路径在 `nanobot/agent/loop.py:1120` 将 build_transcript 包装为 transcript_builder，并在第 1177 行交给 Runner；不应把两种构造接口误写为必然依次调用。

Day15 的 Hello 示例用户文字很短，但真实 usage 报告输入 4753 tokens，说明输入量不能只按用户的 Hello 计算。本节只读源码，不重新生成或请求真实模型消息。

问连续追问需要带什么，用户回答“带上上一轮用户问题”。这是历史的一部分；随后补充还需要相关的上一轮模型回答，用“周五验收”例子说明缺少回答就缺少先前已给出的信息。用户回答“好的”，尚未独立完整说明历史的组成。

## 第八节：Runner 通过 provider 请求模型

目前核对的核心衔接：

| 位置（均在 nanobot 目录内） | 动作 |
|---|---|
| `agent/loop.py:1981` | `_run_turn` 调用 `_run_agent_loop` |
| `agent/loop.py:1170` | 将运行说明 AgentRunSpec 交给 self.runner.run |
| `agent/runner.py:308` | Runner 入口；第 310 行准备初始消息，第 318 行进入 `_run_core` |
| `agent/context_governance.py:147` | 初始消息准备时调用 transcript_builder，实际消息构造回调指向 ContextBuilder.build_transcript |
| `agent/runner.py:435` | 在最大迭代次数内执行循环 |
| `agent/runner.py:448` | 本轮调用 `_request_model` |
| `agent/runner.py:876` | 获取工具定义；第 877 行准备请求上下文，第 884 行生成请求参数 |
| `agent/runner.py:846` | `_build_request_kwargs` 将 messages、tools、model 及生成配置放到字典中 |
| `agent/runner.py:984` | 流式显示分支调用 provider.chat_stream_with_retry；无显示回调分支在第 993 行也使用该接口 |
| `providers/base.py:1443` | 处理流式调用与重试；实际请求继续到适配器 |
| `providers/openai_compat_provider.py:2015` | chat_stream 接口；第 2029 行准备 SDK 客户端 |
| `providers/openai_compat_provider.py:2129` | Chat Completions 分支调用 `client.chat.completions.create(**kwargs)` |

Day15 的 dashscope / qwen-plus 配置对应 OpenAICompatProvider。该类也支持其他供应商的 Responses 分支，不能将其所有模型都描述为固定采用 Chat Completions；选择逻辑在 `providers/openai_compat_provider.py:1106`。本节课堂关注学习配置所用的 Chat Completions 请求位置。

第 2129 行调用后，流式结果还需在后续代码中逐段接收和解析，不能将此处 await 描述为已经得到完整最终文字。Runner 最终还要判断有无工具请求、如何结束，再把结果交给外层保存与显示。

本节只读追踪请求边界，没有再次发送真实模型请求；回复与工具分支的源码尚待展开。

问 `client.chat.completions.create(**kwargs)` 是读取本地历史还是请求模型，用户回答“向模型服务发送请求”，请求边界的引导判断正确。

## 第九节：判断工具请求或正常回答

`nanobot/providers/openai_compat_provider.py:2133` 取得响应流迭代器，第 2134 行开始消费响应流，第 2188 行检查是否收到完成原因；第 2190 行将收集的 chunks 交给解析函数。模型响应整理后交回 Runner。

Runner 在 `nanobot/agent/runner.py:482` 判断：

```python
if response.should_execute_tools:
```

属性定义在 `nanobot/providers/base.py:603`，要求确实存在工具调用，且 finish_reason 是 tool_calls、function_call 或 stop。不能把 refusal、content_filter 或 error 下的工具字段当成可执行授权，也不能只靠“有文字/没有文字”判断是否要工具。

需要工具时，Runner 先将模型的工具请求记录为 assistant 消息（第 497 行），再于第 512 行进入 execute_tool_calls。本轮工具细节仍在继续阅读，课堂先辨认分支。

普通有效文字且无工具请求时，Runner 在后续分支保存最终文字并退出循环；该正常回答分支位于第 756–789 行。错误、空回答、长度恢复和新输入注入等另有处理，不能把 should_execute_tools 为 False 一概描述为成功结束。Day15 的正常 Hello 回复没有工具请求，可作为本节正常结束示例。

问正常问好、没有工具请求时是否还需要调用工具，用户回答“不需要”，普通直接回答分支的引导判断正确。

## 第十节：返回结果、保存会话与显示

普通正常回答分支在 `nanobot/agent/runner.py:785` 设置 final_content，第 789 行 break 退出循环；第 825 行将最终文字、消息、用量和结束原因等包装成 AgentRunResult 返回。第 791 行的 max_iterations 是循环耗尽的另一个分支，不适用于本次正常提前结束。

AgentLoop 在 `nanobot/agent/loop.py:1997` 取得 result.final_content，第 1998 行取得本次消息列表。保存阶段第 2037 行将本轮消息合入会话，第 2054 行调用：

```python
self.sessions.save(session)
```

实际存储入口在 `nanobot/session/manager.py:1786`，由配置的会话存储实现持久化。Day15 学习实例已实际生成 JSONL 会话文件；不能只凭屏幕显示文字就认定会话持久化成功。用户输入在正常用户轮次还有提前保存机制，最终保存不是本轮第一次可能写入用户消息的位置。

显示由 CLI 的 renderer 负责，`nanobot/cli/agent.py:250` 传入 on_stream 回调，`nanobot/cli/stream.py:187` 的 on_delta 可在模型生成时逐段显示内容。若没有流式显示，第 253–263 行才按返回对象的 response.content 打印完整回复。不能把实际流式过程画成严格“保存完成以后才首次显示任何文字”。

正常 Hello 请求的保存/返回/显示路径已完成源码核对；课堂正在讲解持久化与显示的区别，工具回传分支与三种图仍需完成。

问只显示、没有保存到会话文件时，退出程序再启动是否能从文件恢复本轮回答，用户回答“不会”。本轮持久化作用的引导判断正确。

## 第十一节：实际执行 read_file

切换到 Day15 已验证的文件总结案例。Qwen 返回 read_file 工具请求，参数含 path=meeting-notes.txt；这只是请求，文件读取由 Nanobot 工具代码完成。

`nanobot/agent/runner.py:512` 调用工具执行模块；`nanobot/agent/tools/execution.py:142` 通过注册表准备调用和检查参数，第 172 行实际调用已取得的工具对象：

```python
result = await tool.execute(**params)
```

注册表的通用 execute 接口在 `nanobot/agent/tools/registry.py:187`，它也先 prepare_call，再调用工具 execute。当前执行模块能取得准备好的工具对象时直接调用它，第 174 行的注册表 execute 是另一个路径；不能把两次 execute 画成当前成功分支必然连续执行。

read_file 实现在 `nanobot/agent/tools/filesystem.py:270` 的 ReadFileTool。第 281 行给出工具名，第 294 行定义 execute，第 311 行解析受工作目录约束的路径；普通文本分支第 338 行读取字节，后续处理文本与行号。Day15 得到的四行文本是这个工具的实际返回结果，不是模型凭空编写的文件内容。

本节只读源码，没有重新运行文件工具或请求真实 Qwen。模型请求与工具执行的区别仍需用户结合代码判断。

问模型刚返回 read_file 请求、程序还未执行工具时是否已经读取文件，用户回答“没有”，请求与执行的引导区分正确。

## 第十二节：工具结果加入消息并继续循环

`nanobot/agent/runner.py:533` 将工具结果包装为 tool_message，其中第 534 行的 role 为 tool，第 535 行用 tool_call_id 对应模型请求，第 537 行整理工具结果格式；第 544 行追加到 messages：

```python
messages.append(tool_message)
```

模型提出的请求此前已经作为 assistant 消息追加（第 497 行），实际工具结果才是 tool 消息。第 579 行 continue 回到第 435 行的循环，在迭代余量允许时于第 448 行再次请求模型；下一次消息包含刚才的工具结果。Day15 文件示例据此先读取，再由第二次 Qwen 调用总结。

问为什么要把工具结果加入 messages，用户回答“将message一起返回”。能提到与消息一起传递，尚未主动说明接收方和用途；随后补充是把工具结果随消息列表发给 Qwen，让它根据原文总结。课堂开始对照模块图区分 AgentLoop 的整体组织、Runner 的模型/工具循环和 provider 的模型通信职责，尚未进行这三项的独立复述验收。

### 迭代上限与实际请求次数

核对过程中发现必须区分普通迭代次数与模型请求总数：学习配置 maxToolIterations=2 在 `nanobot/agent/loop.py:500` 映射为 max_iterations。普通循环耗尽后，`nanobot/agent/runner.py:791` 标记 max_iterations；第 804–812 行可进入额外的无工具收尾请求，第 1238 行是该收尾请求的 provider 调用。

控制函数在 `nanobot/session/turn_continuation.py:86`，第 98–104 行返回 not(pending_queue_available and goal_continuation_available)。单次 CLI 没有 pending_queue，因此会允许无工具收尾。这意味着 max_iterations 不是所有模型 HTTP 请求的绝对上限；provider 内部重试、摘要等也需要另行计数。Day15 两个成功示例没有触发耗尽，本轮只读核对，没有用真实模型复现耗尽。

## 三种图与技术准备状态

已将普通单次 CLI 路径整理为独立的 [模块图、时序图与阶段状态图](day-16-architecture-diagrams.md)。每个图配有对应源码位置；图中的阶段名称是课堂描述，不声称它们都是源码枚举值。流式显示、循环耗尽收尾和省略的复杂分支均在图旁说明。

主要正常返回与文件工具回传路径、三种图已完成源码核对，并已在对话中逐步展示三种图。已核对 135 处源码引用的文件和行号范围、33 处关键源码语句，检查 Markdown 围栏和三种 Mermaid 图类型；未使用外部 Mermaid 渲染器验证。没有更改参考源码或 A 股业务代码，没有新增真实模型请求。

## 最终基础复盘（2026-10-13）

- 模块图中辨认负责模型与工具循环的组件，用户回答“runner”，正确。
- 文件总结的两次模型请求分别做什么，用户回答“调用工具和生成总结”。随后澄清第一次是模型提出工具调用请求，实际执行由 Nanobot 完成；第二次是根据工具结果生成总结。
- 第一轮已有正常答案、无工具请求，还需要跑满所有配置轮次吗，用户回答“不能”。结合问题语境按“不需要”理解，并明确轮次是上限、正常回答可提前退出；不能据此认为配置轮次一定无法全部使用。对应正常退出代码为 `nanobot/agent/runner.py:789`。
- 完整路径口述时，用户回答“agentloop不知道，runner请求模型、处理工具调用，provider负责传递，工具负责读取，qwen提出工具调用请求和生成总结”。Runner、工具与 Qwen 的职责基本正确，provider 的“传递”仍是通信适配的简化说法；用户当时尚不能说明 AgentLoop。
- 补充 AgentLoop 的接收输入、恢复历史、准备上下文、启动 Runner、保存并返回后，用户回答“AgentLoop管理一轮对话，runner负责管理内部循环”。这是讲解后的正确复述，不视为未经提示的完整源码讲解。

职责总结对应源码：AgentLoop 的阶段组织在 `nanobot/agent/loop.py:1679` 起，Runner 的循环在 `nanobot/agent/runner.py:435`，模型通信请求在 `nanobot/providers/openai_compat_provider.py:2129`，工具执行在 `nanobot/agent/tools/execution.py:172`，会话最终保存调用在 `nanobot/agent/loop.py:2054`。

Day16 计划要求的路径追踪、三种图和源码位置验证已完成，基础引导复盘结束。独立完整口述、独立画图与独立编码仍未验证，不将本次结果描述为已掌握全部源码。下一学习日为 Day17：工具和 Agent Loop；本次尚未开始 Day17。
