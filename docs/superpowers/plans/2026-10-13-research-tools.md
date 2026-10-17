# AI 研究助手行情与技术工具

用户已选择“行情与技术分析：搜索股票、报价、K 线、均线、量价统计”。当前三个工具保留，新增五个只读工具，当前工作区直接执行并保留已有修改。

接口：`search_stocks(query, market=null, limit=10)` 返回缓存目录名称与代码；`get_stock_quotes(stock_codes)` 最多十个证券；`get_kline_history(stock_code, period=day, adjustment=none, limit=60)` 最多120根；`calculate_technical_indicators(stock_code, start_date, end_date, ma_periods=[5,10,20,60], rsi_period=14)`；`analyze_price_volume(stock_code, start_date, end_date, volume_window=20)`。计算使用服务端真实日线，不能接受模型编造的价格序列。

架构：`app/tools/research.py` 定义严格参数、目录搜索、程序指标；`app/agent_research.py` 组合现有 `MarketHistoryReader` 并复用行情解析器。统一最多8次实际行情 HTTP 请求/研究，每次最多8秒、1MiB，并遵守当前60秒绝对期限；原日线最多4个不同区间不变。缓存只属于本次研究。假模型不联网，报价/K线返回未启用，日线本地未知复权则指标返回信息不足。模型、权限、审计与超时部分结果展示继续复用。

计算定义：MA 为最近 N 个实际返回日收盘均值；RSI 为 Wilder 平滑、平盘50；MACD 固定 EMA12/26 与 DEA9（首日收盘初始化），柱值为2*(DIF-DEA)，至少35条且注明热启动限制；量价统计包括首末收盘变化、区间高低、收盘最大回撤及最新成交量/前N个返回日平均量。盘中累计量不可解释为完整全天放量，不生成风险分数或自动交易建议。缺少数据、未知复权、零均量各有明确状态。

- [x] 测试先行：注册表八个只读工具、参数拒绝、目录来源、报价部分失败、K线复权/月线核验、指标数值及不足状态、来源与共享请求上限、API工具调用与审计。
- [x] 实现工具与接入，扩展来源状态及指标输入来源；新工具不改变交易/账户数据。
- [x] 更新研究策略、前端可用工具和提问示例；完成前端、后端、构建、桌面/手机验收、只读真实行情验证及最终独立审查。

验证命令：`.venv/Scripts/python.exe -m pytest tests/unit/test_research_tools.py -o addopts='' -q`；全套沿用 `--ignore=tests/test_invite_auth_integration.py`（原工作区旧模型导入问题）；`node --test tests/frontend/*.test.mjs`；`npm run build`；生产浏览器验收使用明确标注的隔离模型。

完成记录：Python621项、前端56项、构建、Ruff与桌面/手机验收通过；真实5工具只读验证成功，3次行情请求。最终独立审查无明确重要问题，运行后端已重启并验证新来源schema。详见`docs/research-tools.md`。
