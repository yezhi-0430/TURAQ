# Day 17：工具和 Agent Loop（源码对比与基础复盘完成）

## 学习范围

用户在完成 Day16 基础复盘后请求开始 Day17。依据上级目录的八周学习计划，本日需要阅读工具注册、参数 Schema、调用分发、结果回传和终止逻辑；与第 2 周实现比较至少五个设计差异，并记录适合本项目与暂不需要的设计及理由。

继续使用固定的 HKUDS/nanobot v0.3.5，源码根目录为 `C:\Users\LENOVO\Documents\Codex\2026-09-20\n\outputs\nanobot-0.3.5`。以下 Nanobot 源码路径均相对于该目录。本日从 Day15 的会议记录读取案例入手，本节只读源码，没有新增模型请求或修改业务代码。

## 第一节：工具注册

`nanobot/agent/tools/registry.py:26` 初始化注册表，第 27 行建立名称到 Tool 对象的字典：

```python
self._tools: dict[str, Tool] = {}
```

第 30 行定义 register，第 32 行按工具名称保存对象，第 33 行清除缓存的工具定义：

```python
self._tools[tool.name] = tool
self._cached_definitions = None
```

这里注册的是可供后续查找的工具对象，没有调用 execute。第 40–42 行的 get 用名称查找对象；第 86 行的 get_definitions 在第 94 行对对象调用 to_schema，得到供模型使用的定义。注册、导出定义和执行是不同步骤。

课堂可用“read_file → 读取文件工具对象”的映射理解注册，不将简化字典当成所有内置工具的实际加载代码。具体加载调用位置已找到 `nanobot/agent/tools/loader.py:118`，将在后续核对加载上下文后展开。

本项目的初步比较起点为 `app/tools/registry.py:6` 的 TOOL_ARGUMENT_MODELS：它保存工具名称与 Pydantic 参数模型的映射。执行分发位于其他代码，尚未完成比较，不能据此断言自己的项目缺少工具执行注册或参数检查。

问将工具对象登记进字典是否已经读取会议记录，用户选择 B：“只是登记工具，还没读取”。注册与执行的引导区分正确。

## 第二节：参数 Schema

Schema 描述工具接受哪些参数、参数类型及必填要求。`nanobot/agent/tools/filesystem.py:253` 将 path 定义为 StringSchema，第 267 行声明 required=["path"]；该工具还定义 offset、limit、pages、force 等参数，本节只取 path 讲解。

`nanobot/agent/tools/base.py:306` 的 to_schema 把工具名称、描述和 parameters 放进 function 定义，第 313 行使用 self.parameters。它是工具说明，不是模型某次请求的参数值，也不是执行代码。Day16 已核对 Runner 获取工具定义并通过 provider 请求模型的路径。

课堂将参数说明简化为以下片段，省略其余参数与说明字段：

```json
{
  "type": "object",
  "properties": {
    "path": {"type": "string"}
  },
  "required": ["path"]
}
```

与一次调用的具体参数 `{"path": "meeting-notes.txt"}` 区分：前者规定格式，后者填写本次文件路径。声明必填不等于模型输出必然满足规则；本地参数处理与校验将在后续阅读。

问 required 中的 path 是否必须提供，用户回答“必填”，正确。

## 第三节：本地参数校验

工具说明发给模型后，模型仍可能给出缺少必填字段的参数。`nanobot/agent/tools/registry.py:110` 的 prepare_call 负责准备调用：第 116 行按名称查找工具，第 131 行处理参数格式，第 141 行 cast_params，再于第 142 行 validate_params；第 143–145 行遇到校验错误则返回错误。

`nanobot/agent/tools/base.py:297` 定义 validate_params，第 304 行交给 Schema.validate_json_schema_value 进行 Schema 校验；第 91 行起读取 required 要求。因此应理解为先处理参数再校验，不能断言所有原始类型不同的输入都直接失败。

执行模块在 `nanobot/agent/tools/execution.py:142` 调用 prepare_call，第 147 行起处理准备错误，第 162–163 行提前返回；只有通过该阶段才继续到第 172 行的工具 execute。参数未通过校验时不会在这个调用路径中继续读取文件。

问模型请求 read_file，参数为 `{}`、缺少必填 path 时如何处理，用户选择 B：“返回参数错误，不执行读取”，正确。进一步核对 `nanobot/agent/tools/base.py:92` 的必填字段循环，第 93–94 行对缺少字段添加 missing required 错误。本节为源码推导，没有真实模型调用或工具失败实验。

## 第四节：按名称分发并执行

沿用参数正确的示例：模型请求工具名 read_file，参数为 `{"path": "meeting-notes.txt"}`。注册表在 `nanobot/agent/tools/registry.py:116` 的 self.get(name) 查找对应工具对象；参数处理与校验通过后，执行模块在 `nanobot/agent/tools/execution.py:172` 调用：

```python
result = await tool.execute(**params)
```

`**params` 将字典展开为关键字参数；对于上述仅含 path 的示例，课堂可等价理解为 `await tool.execute(path="meeting-notes.txt")`，不是另一处源码调用。实际函数在 `nanobot/agent/tools/filesystem.py:294`，第 296 行接收 path，第 311 行解析读取路径；普通文件分支第 338 行读取字节。工具名决定选哪个对象，参数决定这次怎样调用该对象。

问上述调用进入 execute 后，path 的具体值是什么，用户回答 `meeting-notes.txt`，具体参数值辨认正确。

### 未注册的工具名称

`nanobot/agent/tools/registry.py:116` 用 self.get(name) 查找工具，第 117 行判断是否未找到，第 120–124 行返回 ToolResult.error，说明该工具不存在并列出可用名称。第 118–119 行可能提供相似名称建议，但要求名称精确匹配，不会替换成建议工具直接执行；第 55 行的注释也明确名称规范化仅用于建议。

课堂假设模型请求 read_notes，而注册表只登记 read_file：参数中的文件路径即使正确，也不能越过工具名称检查。工具未注册与文件不存在是不同错误；后者要到具体文件工具解析路径和读取时才能发现。

问请求未注册的 read_notes 时应如何处理，用户选择 B：“返回工具不存在的错误”，正确。

## 第五节：工具结果回传

工具成功读取文本后，Runner 在 `nanobot/agent/runner.py:533` 构造 tool_message，第 534 行 role 为 tool，第 535 行 tool_call_id 对应模型发起的调用，第 536 行 name 为工具名，第 537 行起将结果整理为消息内容，第 544 行追加到 messages。

课堂使用省略编号、工具名及结果规范化细节的字典说明其角色：`{"role": "tool", "content": "读取到的会议记录……"}`。这不是完整实际消息，也不是 Qwen 已经生成的总结。

第 579 行 continue 回到普通迭代循环，在仍有迭代余量时再次请求模型，让 Qwen 根据工具结果回答。迭代耗尽的无工具收尾机制仍按 Day16 记录处理，不将 continue 描述为保证还有下一次普通迭代。

问文件工具返回的原文消息应使用 user、assistant 还是 tool 角色，用户回答“tool”，正确。模型随后生成的总结属于 assistant 消息。

## 第六节：正常回答时结束循环

会议原文回传后，如果模型给出有效总结且没有新的可执行工具请求，Runner 进入正常最终回答分支。`nanobot/agent/runner.py:785` 设置 final_content，第 789 行 break 提前结束循环。因此配置上限不是必须运行的轮数。

本节只讲普通有效回答分支；错误、空回答与恢复分支仍按 Day16 阅读结果区分。第 791 行的 max_iterations 为普通迭代耗尽路径，第 804–812 行可触发额外无工具收尾请求；不能将它与正常回答提前退出混为一谈，也不能将普通迭代上限当成全部 HTTP 请求次数上限。

问读取后第二次模型请求已经给出有效总结，没有新工具请求时应如何处理，用户选择 B：“结束循环，返回总结”，正确。

## 本项目比较准备

已只读查看 `app/tools/registry.py`、`app/tools/executor.py`、`app/agent_loop.py`、`app/tool_calling.py`、`app/tool_messages.py`、`app/tools/calculations.py` 及 Day11、Day13 学习记录。本项目已有工具名称映射、Pydantic 参数校验、工具执行记录和循环上限，不将这些已有功能误报为缺失。

## 五项设计差异与取舍（源码核对完成，课堂复盘进行中）

下表的 Nanobot 路径相对于参考源码根目录，本项目路径相对于当前工作目录。取舍为当前三个固定查询/计算工具的设计建议，没有实际实施重构。共同具有的未知工具拒绝、参数检查、tool 消息回传及正常答案提前结束不计作差异。

| 比较点 | Nanobot v0.3.5 | 本项目第 2 周实现 | 当前取舍与理由 |
|---|---|---|---|
| 注册与分发 | 注册表保存 Tool 对象，按名称取得对象后调用 execute；`nanobot/agent/tools/registry.py:32`、`nanobot/agent/tools/execution.py:172`。加载器在 `nanobot/agent/tools/loader.py:95` 取得内置与插件来源，第 118 行登记对象。 | 名称映射到参数模型；`app/tools/registry.py:6`。`app/tools/executor.py:45`、第 69 行起按工具名选择业务函数。 | 三个固定工具暂时保留显式分发。工具数量增加、多人扩展时，可以考虑对象式接口，将说明、参数与执行集中在每个工具中；无需为了本次学习立即重写。 |
| Schema 与参数校验实现 | 工具提供 JSON Schema，to_schema 导出；`nanobot/agent/tools/base.py:306`。注册表先 cast_params 再 validate_params；`nanobot/agent/tools/registry.py:141`。 | Pydantic 模型生成 JSON Schema；`app/tools/registry.py:31`。执行器解析 JSON，再 model_validate；`app/tools/executor.py:67`。计算参数还限定正值、精度与额外字段；`app/tools/calculations.py:6`。 | 保留 Pydantic 业务参数模型，复用既有约束。学习“说明给模型、校验由程序执行”的职责分工；无需另写 Nanobot 的 Schema 校验体系。两者都可能存在类型转换，不能简单称本项目全部严格、Nanobot 全部宽松。 |
| 执行接口 | 工具接口是 async execute；`nanobot/agent/tools/base.py:227`，执行模块 await 调用；`nanobot/agent/tools/execution.py:172`。 | execute_tool 是同步函数；`app/tools/executor.py:51`。run_tool_turn 同步请求模型并逐个调用执行器；`app/tool_calling.py:17`、第 25–30 行。 | 当前链路保留现有同步实现。未来需要更多网络工具、流式或并发时再评估异步改造。async 本身不保证文件/数据库操作不阻塞，也不等于多个工具会自动并行。 |
| 整轮对话与内部循环的层次 | AgentLoop 组织恢复、构造、运行、保存、响应；`nanobot/agent/loop.py:1679` 起。Runner 执行模型/工具循环；`nanobot/agent/runner.py:435`。 | run_agent_loop 接收调用方提供的 messages，复制历史并控制循环；`app/agent_loop.py:25`、第 44–63 行。模型与执行步骤又委托给 run_tool_turn。 | 本项目已有模块分工，但这个名为 run_agent_loop 的函数在职责上更接近 Nanobot Runner，不能只按名字对应。今后建设可信会话持久化时，可借鉴在循环外单独组织会话与上下文；本节不声称当前已具备 Nanobot 的完整会话层。 |
| 耗尽上限后的处理 | 普通循环耗尽后，第 804–812 行在允许时追加无工具收尾；`nanobot/agent/runner.py:791` 起，许可细节见 Day16。 | for 循环耗尽直接返回 max_rounds_exceeded、answer=None；`app/agent_loop.py:46`、第 65–70 行。该函数没有额外收尾调用。 | 当前保留明确的未完成状态及循环上限，便于请求预算和前端展示。若未来采用额外总结，需显式计入预算并提示任务未完成，不能把总结当成任务成功。此处比较循环自身调用，不声称限制 provider 重试等全部底层 HTTP 请求。 |

当前适合继续保留的设计：明确工具范围、Pydantic 业务校验、结构化执行记录、工具结果回传和有界循环。可按需求逐步借鉴的设计：统一工具对象接口、将会话组织放在内部循环之外。暂不迁移的设计：自动插件加载、整套异步接口和耗尽后的额外收尾请求，因为当前固定工具范围及既有业务链路尚不需要这些扩展。

课堂从第一项取舍开始：当前只有三个固定查询/计算工具，是否需要立即改成 Nanobot 的完整工具对象与加载器体系？用户回答“不需要”，与当前保留显式分发的取舍一致；这是讲解后的判断，尚未要求独立分析扩展成本。

其余四项按表格概览讲解：保留 Pydantic 参数校验；同步与异步按实际需求选择；分清会话组织与模型/工具循环；本项目耗尽轮数后返回未完成而不额外请求总结。课堂强调不要只根据函数名字对应架构层次。

问本项目 run_agent_loop 主要控制“请求模型、执行工具、回传结果、再请求”的循环，职责更接近 Nanobot AgentLoop 还是 Runner，用户回答“runner”，职责对应正确。

## 最终进度与验收范围

已完成工具注册、参数 Schema、本地参数检查、名称查找与分发、实际执行、tool 结果回传和正常终止的源码阅读；普通迭代耗尽处理已结合 Day16 核对。已按实际源码列出五项设计差异，并说明当前项目的采用、保留与暂缓理由。

用户在引导问答中正确区分注册与执行、必填参数、缺参拒绝、具体路径值、未知工具拒绝、tool 消息角色、正常提前结束，以及本项目循环与 Nanobot Runner 的职责对应。取舍判断为讲解后的确认，不声称用户已能脱离提示独立分析全部设计。

Day17 的源码对比与基础复盘完成。独立完整口述、独立编码尚未验收。本日没有新增真实模型调用、没有执行工具失败实验、没有更改 Nanobot 或本项目业务源码。下一日 Day18 学习会话、记忆和错误恢复；本次未开始 Day18。

## 本日步骤完成情况

1. 阅读模型看到的工具定义和参数 Schema。
2. 沿模型工具请求追踪名称查找、参数处理、实际执行和结果回传。
3. 复查正常结束与迭代耗尽逻辑。
4. 核对本项目第 2 周实现，完成至少五项设计差异与取舍说明。

以上四项已完成源码阅读、文档整理与引导式复盘，独立完整源码讲解和编码能力仍未验收。
