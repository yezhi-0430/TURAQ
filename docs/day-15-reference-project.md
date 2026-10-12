# Day 15：选择并运行参考项目（进行中）

## 当天目标与学习起点

依据上级目录 `8-week-agent-learning-roadmap.md`，今天选择一个开源 Agent，运行官方最小示例，记录安装与运行问题，了解项目目标、入口和主要模块。验收要求是用户能用自己的话介绍项目约三分钟。

2026-10-12 选择 HKUDS/nanobot，固定官方标签 `v0.3.5`。它是 Python 编写的个人 AI 助手框架，围绕模型、工具和会话组织请求处理。本轮先使用命令行单次消息路径。

用户在热身题中选择 B：模型返回 `read_file` 请求后，真正读取文件的是 Agent 程序里的文件工具。这个回答证明用户能区分工具请求与实际执行，不能据此认定已经掌握参考项目实现。

## 源码与环境

- 官方仓库：https://github.com/HKUDS/nanobot
- 官方源码包：https://codeload.github.com/HKUDS/nanobot/zip/refs/tags/v0.3.5
- 源码包 SHA256：`782D56CE782CBAB8ED4A265947006CD795F41B61FED6B728EFDD83C0C532E93B`
- 源码目录：`C:\Users\LENOVO\Documents\Codex\2026-09-20\n\outputs\nanobot-0.3.5`
- Python：3.13.12；独立环境为该目录中的 `.venv`。
- 安装方式：editable 源码安装。源码包不含 Git 历史，不能视为成功 clone。

实际创建环境命令，在参考源码目录执行：

```powershell
uv venv --python 'C:\Users\LENOVO\Documents\Codex\2026-09-20\n\outputs\a-share-risk-agent\.venv\Scripts\python.exe' .venv
uv pip install --python .venv\Scripts\python.exe --index-url https://pypi.tuna.tsinghua.edu.cn/simple -e .
```

创建环境时指定主项目 Python 仅用于选择解释器；依赖实际安装在参考项目自己的环境里。安装共 92 个包，退出码 0；editable 构建跳过 WebUI 打包，尚未构建或验收 WebUI/TUI。

## 安装问题与处理

1. `git clone --depth 1 --branch v0.3.5` 报 `Recv failure: Connection was reset`，没有获得可用 checkout。检查官方 codeload 地址返回 HTTP 200 后，下载同标签的源码包并解压。
2. 默认 PyPI 安装解析出 92 个依赖后，下载阶段连续重试。停止该次安装；检查清华 PyPI 镜像可访问后，用命令级 `--index-url` 重试，安装成功。没有更改全局包源。默认源下载失败的具体网络原因尚未定位。
3. 安装器报告两个依赖版本说明格式的自动规范化警告；最终依赖兼容性检查通过，没有因此修改上游源码。

## 已验证的入口和模块

下列位置来自本机 `v0.3.5` 源码初步核对，尚未完成 Day16 的完整请求追踪：

| 部分 | 源码位置 | 初步作用 |
|---|---|---|
| 命令注册 | `pyproject.toml:111` | 将 `nanobot` 命令映射至 `nanobot.cli.entry:main` |
| 命令入口 | `nanobot/cli/entry.py:71` | 分发命令，选择 Agent 或其他 CLI 路径 |
| 命令行对话 | `nanobot/cli/agent.py:54` | 接收 message、session、workspace 和 config 等参数 |
| Agent 协调 | `nanobot/agent/loop.py:196` | AgentLoop 类；详细流程待追踪 |
| 模型与工具循环 | `nanobot/agent/runner.py:141` | AgentRunner 类；详细流程待追踪 |
| 工具注册 | `nanobot/agent/tools/registry.py:19` | 按名称注册、查找工具，生成工具定义 |
| 模型接入 | `nanobot/providers/` | 模型供应商与客户端实现 |
| 会话管理 | `nanobot/session/manager.py:1644` | SessionManager 类；持久化细节待后续核对 |
| 配置 | `nanobot/config/schema.py:422` | Config 类型与配置校验 |

## 本轮验证与剩余事项

在参考源码目录执行：

```powershell
.\.venv\Scripts\nanobot.exe --version
.\.venv\Scripts\nanobot.exe agent --help
uv pip check --python .venv\Scripts\python.exe
```

三个命令均退出码 0：版本显示 `nanobot v0.3.5`，帮助列出消息/会话/工作目录/配置参数，依赖检查显示 92 个包兼容。这只证明安装及命令入口可用。

安装阶段尚未创建模型配置或请求真实模型；后续最小对话结果见下文。源码下载与安装没有修改 A 股项目业务代码或数据库。

## 虚拟环境复盘

用户最初将虚拟环境隔离的对象选为数据库股票数据；讲解后，再问只升级 Nanobot 环境中的 Pydantic 是否会影响 A 股项目时，回答“会”。随后解释两个环境各有一份库、只升级其中一份不会升级另一份，用户回答“好”。已完成讲解，尚未独立解释或用操作验证，不能记录为独立掌握。两个环境仍可能通过数据库配置连接到同一数据库，虚拟环境本身不隔离业务数据。

## 配置 Qwen 并运行最小对话

随后沿用主项目现有 Qwen 配置，在独立目录 `C:\Users\LENOVO\Documents\Codex\2026-09-20\n\outputs\nanobot-day15` 创建学习实例：

- `config.json`：配置 `provider=dashscope`、`model=qwen-plus`，API 地址从主项目模型配置读取。
- `workspace/`：参考项目自己的学习工作目录；配置路径也决定该实例的日志与会话目录。
- API Key 字段仅保存 `${DASHSCOPE_API_KEY}` 环境变量引用，实际凭据由启动进程在本机读取并传给子进程，不写入配置、学习记录或 Git。
- 最大输出 256 tokens，工具迭代上限 2，关闭 Dream/heartbeat 及文件、shell、自省工具；开启工作目录限制。没有启用网关、聊天平台或 MCP。

先用上游 `load_config`、`resolve_config_env_vars`、`validate_provider_setup` 核对配置，退出码 0，不请求模型。随后在继承了本机 `DASHSCOPE_API_KEY` 的子进程里执行官方单次消息路径，等价命令为：

```powershell
# 在 nanobot-0.3.5 目录运行；启动进程须先在本机设置 DASHSCOPE_API_KEY。
.\.venv\Scripts\nanobot.exe agent --config ..\nanobot-day15\config.json --workspace ..\nanobot-day15\workspace --session cli:day15-hello --message 'Hello!' --no-markdown
```

2026-10-12 22:32（Asia/Shanghai），保存的 CLI 输出和会话记录都包含正常回复：

```text
Hello! 👋 How can I help you today?
```

会话包含 user 和 assistant 消息，assistant 没有工具调用。上游保存的 `_last_usage` 报告 `request_count=1`、输入 4753 tokens、输出 11 tokens、总计 4764 tokens，来源 `reported`。这证明一次真实 Qwen 最小对话完成；没有重复发出研究问题或用假模型替代。

最小消息很短，但实际输入包含 Nanobot 构造的系统与工具等上下文，输入 token 数并不等于用户消息长度。详细提示构造和工具循环留待 Day16–17 追踪。

### 终端显示问题

子进程输出已经以 UTF-8 保存到 `nanobot-day15/hello-output.txt`，之后外层验证脚本打印输出时默认使用 GBK，猫咪 emoji 导致 `UnicodeEncodeError`，外层脚本退出码为 1。因打印中断，未捕获展示该次子进程的退出码，不能声称整个验证命令退出码为 0。

后续只读取现有输出与 JSONL 会话，先将验证脚本 stdout 设置为 UTF-8；读取核对退出码 0，成功显示原回复和 usage，没有再次请求真实模型。已验证问题发生在外层显示阶段，不能把它记为模型请求失败。

## 当前验收状态

选择项目、独立安装、入口初步核对、官方命令行最小对话和安装/显示问题记录已完成。用户已开始介绍部分职责，完整目标、入口和主要模块尚未独立说明，三分钟学习验收仍待进行；Day15 不标记为全部完成。本轮没有改动参考项目源码或 A 股业务数据库。

## 最小对话后的引导复盘

- 用户回答“nanobot调用工具，qwen负责回答”。随后补充：Nanobot 还组织请求和管理会话，Qwen 也可提出工具调用请求。
- 问入口模块职责时，用户回答“调用工具”。结合刚才 Hello 不需要工具但仍经过入口的实际运行，解释入口接收命令并分发。用户随后在“交给对话模块处理 / 直接读取文件或计算”选项中选择 A。引导选择正确，尚未独立说明具体入口实现。
- 展示入口、Agent Loop / Runner、Providers、Tools 和 Session 的职责表后，用户介绍“nanobot是组织工具，qwen负责生成回复，nanobot显示回复”。能说出部分职责，但尚未明确它是 Agent 程序及其组织整个请求流程的作用。

接下来的口述练习围绕三点：项目帮助用户通过对话使用模型与工具；入口接收并分发命令；Nanobot 协调模型、工具和会话，Qwen 生成回答或工具请求。此处是讲解提纲，不是用户独立回答或三分钟介绍通过的证据。

## 真实读取与总结示例

用户对读取后回传模型的原因回答“这个不知道”。讲解使用虚构会议记录区分工具获取原文和模型按要求总结；用户随后回答“好的”。为使两个环节可观察，同日在已有学习实例中运行一次真实工具示例。

创建 `workspace/meeting-notes.txt`，内容为：

```text
[学习用虚构会议记录]
小王周三完成接口开发。
小李周四进行测试。
周五一起验收。
```

单独复制配置为 `read-demo-config.json`，只将 `tools.file.enable` 改为 true，保留学习目录限制、shell 关闭、2 次工具循环上限等配置。原 Hello 配置保留。文件工具组同时提供上游的读写能力；本轮只观察到 read_file 调用，不能由此宣称整个实例只有读取权限。

运行上游 CLI 的新会话 `cli:day15-read`，要求读取样例后用一句中文总结，不修改文件或做其他操作。CLI 和外层脚本均退出码 0，耗时 7.54 秒，运行前后样例内容一致。输出保存为 `nanobot-day15/read-demo-output.txt`。

核对真实会话 JSONL 的消息顺序：

```text
user → assistant(tool_calls) → tool → assistant(最终回答)
```

第一轮 Qwen 请求 `read_file`，参数为 `{"path":"meeting-notes.txt"}`。工具返回四行原文和行号。第二轮 Qwen 返回：

```text
接下来的安排是：小王周三完成接口开发，小李周四测试，周五双方共同验收。
```

上游 usage 报告 `request_count=2`、输入 13497 tokens、输出 43 tokens、总计 13540 tokens，来源 `reported`。本轮只执行该示例一次，未重复请求；与 Hello 合计两次运行、三次已报告模型请求。完成读取、回传和总结的技术观察，不等于用户已经能独立解释整个过程，学习复盘仍待继续。

## 示例后的复盘

观察真实示例后，用户在“第二次调用 Qwen 是为了读取文件，还是根据原文生成总结”中选择 B，引导判断正确。

随后要求用两三句话介绍项目、职责和结果回传。用户回答：

> Nanobot 是一个 Agent 程序，把模型、工具和会话组织起来，让用户通过对话完成任务。
> qwen负责调用工具，nanobot负责组织
> qwen总结

第一句复述了此前讲解中的项目定位；最后一句表明用户知道模型负责总结。第二句的“调用工具”仍需明确为“提出工具调用请求”，实际执行由 Nanobot 的工具代码完成。再次讲解这一用语区别，不能把该回答视为已独立解释工具请求、执行与回传的完整过程。

截至此次记录，Day15 技术实践已跑通，基础复盘有上述引导证据；独立三分钟介绍、源码逐行解释和独立实现尚未验收。没有开始 Day16，也没有增加真实模型请求。
