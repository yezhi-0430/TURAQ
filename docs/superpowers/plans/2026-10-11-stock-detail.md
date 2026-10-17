# Stock Detail Implementation Plan

**Goal:** 实现已授权的股票真实行情详情弹窗与分时/日周月K交互。

**Architecture:** 保留行情面板；app/market.py 补全分钟数据，独立 app/market_history.py 验证历史K线；market_api.py 注册K线接口。frontend/market-chart.js 负责SVG与十字线，market-detail.js 负责弹窗与请求生命周期。

**Tech Stack:** FastAPI / httpx / Decimal / 原生dialog与SVG，无新增生产依赖。

## Global Constraints
- 仅真实行情；不复权；报价10秒、图表30秒；隐藏/关闭暂停；失败保留并标记旧数据。
- 保护工作区已有修改，不提交其他变更。

### Task 1: 数据服务
- [x] 写 tests/unit/test_market_detail.py，验证累计手数差分、成交额除以股数、前收、K线OHLC/排序/缺失、缓存与故障、错误周期。
- [x] `.venv/Scripts/python.exe -m pytest tests/unit/test_market_detail.py --confcutdir=tests/unit -q`：先出现缺失功能失败，再实现，最后通过。
- [x] 修改 app/market.py；新增 app/market_history.py；注册 GET /api/v1/market/klines/{symbol}?period=day|week|month。
- [x] 验证现有 market 单测；前端消费者使用 points 的 average_price/volume_lots 和 bars 的 date/open/close/high/low/volume_lots/change_percent。

### Task 2: 详情与图表
- [x] 写 tests/frontend/market-detail.test.mjs，验证点击打开、周期切换、十字线标签、关闭取消轮询及快切不会覆盖新证券。
- [x] `node tests/frontend/market-detail.test.mjs` 先失败；新增 market-chart.js、market-detail.js、market-detail.css，修改 index.html 的加载顺序与 market.js 股票入口，再通过。
- [x] 弹窗报价与图表独立状态，请求修订号/取消信号；绘图保留悬停时间。SVG价格图与成交量共用横轴，价格线/均价线或OHLC蜡烛；无真实记录时显示加载/错误。

### Task 3: 完整验证
- [x] 运行市场后端单测、前端回归、构建。
- [x] 真实股票分时和三个周期接口冒烟，浏览器检查桌面/窄屏、悬停、关闭、切换。
- [x] 自查旧响应、成交量单位、均价、休市提示；更新 frontend/README.md 说明来源与刷新口径。

## Review and adjustments
- 使用独立只读审查代理；已修复指数均价误用、表格重绘后弹窗焦点恢复、自动刷新后图表键盘焦点丢失。三个修复均有失败→通过的回归测试。
- 浏览器验证发现桌面弹窗高度过大：报价并入头部，图表根据容器尺寸绘制，窄屏保留可读标签。
- 构建验证发现经典脚本未进入Vite产物：仅在生产构建的HTML预处理阶段将四个脚本转换为模块，保留源码静态打开行为。产物脚本存在性测试先失败再通过。
- 不提交工作区已有的大量改动；本次修改保留在当前工作区。

## Final evidence
- 251个后端unit测试通过（隔离运行，不使用根目录数据库清理fixture）；修改文件ruff通过。已有Starlette/httpx弃用警告仍存在。
- market、market-detail、watchlist和生产构建脚本存在性四组前端验证通过。明确验证报价10秒更新，分时30秒更新，悬停保留与关闭/隐藏停止。
- Vite生产构建通过；浏览器在8766根目录加载构建产物，真实股票分时及日K可用、无控制台错误。
- 腾讯真实源返回茅台267条分钟记录、320根日K、320根周K、302根月K；非法周期和代码返回422。
- 浏览器验证鼠标十字线显示13:05、价格1272.99、涨跌幅+1.37%、均价1266.71和126手成交量；周/月切换、缩放、Escape关闭和恢复股票按钮焦点通过。
- 桌面与390px窄屏截图保存在docs/visual-qa/stock-detail-{minute,day,mobile}.jpg。
